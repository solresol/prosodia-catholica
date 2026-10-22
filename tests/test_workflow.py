import ast
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cloud_gadgets
from test_handoff import request, result


class WorkflowTests(unittest.TestCase):
    def test_validate_cli_needs_no_db_or_model_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bundle.json'
            path.write_text(json.dumps(result(request())))
            env = {k:v for k,v in os.environ.items() if not k.startswith(('DB_', 'PG', 'OPENAI'))}
            done = subprocess.run([sys.executable, str(ROOT/'cloud_gadgets.py'), 'validate', str(path)], env=env, capture_output=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn(b'no DB access', done.stdout)

    def test_public_deployment_files_exclude_host_specific_settings(self):
        for name in ('ci/run_deploy.sh','.github/workflows/deploy.yml','docs/ci-deployment.md'):
            text=(ROOT/name).read_text()
            for private in ('/home/', '/var/www/', 'sudo -', 'localhost:5432'):
                self.assertNotIn(private,text,name)

    def test_network_navigation_checks_and_runtime_csp(self):
        from gadget_validation import _validate_gadget
        cases = [dict(html='<input>', css='', js=s) for s in ('fetch("/x")', 'navigator.sendBeacon("/x")', 'window.location="/x"', 'window.open("/x")')]
        cases += [dict(html=s, css='', js='void 0') for s in ('<img src="//evil/x">', '<a href="/x">go</a>', '<meta http-equiv="refresh" content="0;url=/x">')]
        cases += [dict(html='<input>', css='background:url(//evil/x)', js='void 0')]
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError): _validate_gadget(**candidate)
        # Inspect the actual production renderer without importing DB helpers.
        tree = ast.parse((ROOT/'generate_site.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='gadget_srcdoc')
        scope = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<production-renderer>', 'exec'), scope)
        doc = scope['gadget_srcdoc'](html='<input>', css='', js='void 0')
        for policy in ('Content-Security-Policy', "default-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'"):
            self.assertIn(policy, doc)
        self.assertLess(doc.index('Content-Security-Policy'), doc.index('<style>'))

    def test_ci_wrapper_refuses_invalid_commit_before_host_access(self):
        ran=subprocess.run(['bash',str(ROOT/'ci/run_deploy.sh'),'not-a-commit','publish'],capture_output=True)
        self.assertEqual(ran.returncode,2)
        env=dict(os.environ,HERODIAN_DEPLOY_ROOT='/nonpublic-test-marker',HERODIAN_DEPLOY_USER='nonpublic-test-user')
        ran=subprocess.run(['bash',str(ROOT/'ci/run_deploy.sh'),'0'*40,'publish'],env=env,capture_output=True)
        self.assertEqual(ran.returncode,77)
        self.assertNotIn(b'nonpublic-test',ran.stdout+ran.stderr)

    def test_single_pipeline_preserves_steps_quiet_success_and_failures(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); binary=root/'bin'; binary.mkdir()
            script=root/'run_daily_pipeline.sh'
            script.write_text((ROOT/script.name).read_text().replace('export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"', 'export PATH="$TEST_BIN:/usr/bin:/bin"'))
            commands={
                'git':'#!/bin/sh\necho "git $*" >> "$TRACE"\nexit 0\n',
                'uv':'#!/bin/sh\necho "uv $*" >> "$TRACE"\necho step-diagnostic\ncase "$*" in *"${FAIL_STEP:-never-match}"*) exit "${FAIL_CODE:-23}";; esac\n',
                'rsync':'#!/bin/sh\necho "rsync $*" >> "$TRACE"\necho deployed\n',
                'python3':'#!/bin/sh\ncase "$2" in *GADGET_WORKFLOW*) echo legacy;; *DEPLOY_HOST*) echo merah;; *) echo /var/www/vhosts/prosodia-catholica.symmachus.org/htdocs;; esac\n',
            }
            for name, body in commands.items():
                p=binary/name; p.write_text(body); p.chmod(0o755)
            trace=root/'trace'
            # A concurrent cron or CI process holds the same host lock.
            import fcntl
            (root/'logs').mkdir()
            with (root/'logs/pipeline.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                blocked=subprocess.run(['bash',str(script)],env=dict(os.environ,TEST_BIN=str(binary),TRACE=str(trace)),capture_output=True)
                self.assertEqual(blocked.returncode,75)
                self.assertIn(b'already running',blocked.stderr)
                self.assertFalse(trace.exists())
            env=dict(os.environ, TEST_BIN=str(binary), TRACE=str(trace))
            def execute(**changes):
                trace.unlink(missing_ok=True)
                for receipt in (root/'logs').glob('daily-*'):
                    receipt.unlink()
                ran=subprocess.run(['bash',str(script)], env=dict(env,**changes), capture_output=True)
                return ran, trace.read_text()
            legacy, steps=execute()
            self.assertEqual((legacy.returncode,legacy.stdout,legacy.stderr),(0,b'',b''))
            self.assertIn('git pull', steps)
            for name in ('init_db.py','translate_lines.py','summarize_lines.py','gadgetize_lines.py','compute_overlaps.py','generate_site.py','rsync'):
                self.assertIn(name,steps)
            self.assertNotIn('git_gadget_handoff.py',steps)
            cloud, steps=execute(GADGET_WORKFLOW='cloud')
            self.assertEqual((cloud.returncode,cloud.stdout,cloud.stderr),(0,b'',b''))
            self.assertNotIn('gadgetize_lines.py',steps)
            names=['init_db.py','translate_lines.py','summarize_lines.py','import-ready','compute_overlaps.py','generate_site.py','rsync','enqueue']
            self.assertEqual([steps.index(n) for n in names],sorted(steps.index(n) for n in names))
            trace.unlink()
            repeat=subprocess.run(['bash',str(script)],env=dict(env,GADGET_WORKFLOW='cloud'),capture_output=True)
            self.assertEqual(repeat.returncode,0,repeat.stderr)
            repeated=trace.read_text()
            self.assertNotIn('translate_lines.py',repeated)
            self.assertNotIn('compute_overlaps.py',repeated)
            self.assertIn('import-ready',repeated)
            self.assertIn('rsync',repeated)
            trace.unlink()
            publish=subprocess.run(['bash',str(script),'publish'],env=dict(env,GADGET_WORKFLOW='cloud'),capture_output=True)
            self.assertEqual(publish.returncode,0,publish.stderr)
            self.assertNotIn('init_db.py',trace.read_text())
            failed,steps=execute(GADGET_WORKFLOW='cloud',FAIL_STEP='import-ready',FAIL_CODE='25')
            self.assertEqual(failed.returncode,25)
            self.assertIn(b'step-diagnostic',failed.stderr)
            self.assertIn('rsync',steps)
            failed,steps=execute(FAIL_STEP='generate_site.py',FAIL_CODE='23')
            self.assertEqual(failed.returncode,23,failed.stderr.decode())
            self.assertNotIn('rsync',steps)
            self.assertIn(b'Herodian pipeline failed',failed.stderr)
            failed,steps=execute(GADGET_WORKFLOW='cloud',FAIL_STEP='translate_lines.py',FAIL_CODE='24')
            self.assertEqual(failed.returncode,24)
            trace.unlink()
            ambiguous=subprocess.run(['bash',str(script)],env=dict(env,GADGET_WORKFLOW='cloud'),capture_output=True)
            self.assertEqual(ambiguous.returncode,75)
            self.assertFalse(trace.exists())
            inherited=subprocess.run(['bash','-c','exec 9>"$LOCK"; flock 9; HERODIAN_LOCK_INHERITED=1 bash "$SCRIPT" publish'],env=dict(env,GADGET_WORKFLOW='cloud',LOCK=str(root/'logs/pipeline.lock'),SCRIPT=str(script)),capture_output=True)
            self.assertEqual(inherited.returncode,0,inherited.stderr)
            failed,steps=execute(GADGET_WORKFLOW='cloud',FAIL_STEP='enqueue',FAIL_CODE='26')
            self.assertEqual(failed.returncode,26)
            self.assertIn('rsync',steps)


if __name__ == '__main__': unittest.main()
