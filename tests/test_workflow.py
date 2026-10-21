import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cloud_gadgets


class WorkflowTests(unittest.TestCase):
    def test_evidence_and_stale_bundle(self):
        item = {'candidate': {'html': '<input>', 'css': '', 'js': 'void 0'}, 'test_evidence': {'browser': 'Chromium', 'interaction': 'type alpha', 'expected': 'alpha', 'actual': 'alpha'}}
        bundle = {'day': datetime.now(timezone.utc).date().isoformat(), 'new': item, 'past': None}
        cloud_gadgets.validate_bundle(bundle)
        bad = copy.deepcopy(bundle)
        bad['new']['test_evidence']['actual'] = 'wrong'
        with self.assertRaises(ValueError):
            cloud_gadgets.validate_bundle(bad)
        bundle['day'] = '2000-01-01'
        with self.assertRaises(ValueError):
            cloud_gadgets.validate_bundle(bundle)

    def test_validate_cli_needs_no_db_or_model_configuration(self):
        import json
        bundle = {'day': datetime.now(timezone.utc).date().isoformat(), 'new': {
            'candidate': {'html': '<input>', 'css': '', 'js': 'void 0'},
            'test_evidence': {'browser': 'Chromium', 'interaction': 'type', 'expected': 'ok', 'actual': 'ok'}}, 'past': None}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bundle.json'
            path.write_text(json.dumps(bundle))
            env = {k: v for k, v in os.environ.items() if not k.startswith(('DB_', 'PG', 'OPENAI'))}
            result = subprocess.run([sys.executable, str(ROOT / 'cloud_gadgets.py'), 'validate', str(path)], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b'no DB access', result.stdout)

    def test_offline_validation_rejects_network(self):
        from gadget_validation import _validate_gadget
        for candidate in [dict(html='<script>x</script>', css='', js='x'),
                          dict(html='<input>', css='', js='fetch("/x")'),
                          dict(html='<input>', css='https://example.org', js='x')]:
            with self.assertRaises(ValueError):
                _validate_gadget(**candidate)

    def test_maintenance_preserves_non_gadget_steps_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            script = root / 'run_content_maintenance.sh'
            script.write_text((ROOT / script.name).read_text().replace('export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"', 'export PATH="$TEST_BIN:/usr/bin:/bin"'))
            binary = root / 'bin'
            binary.mkdir()
            uv = binary / 'uv'
            uv.write_text('#!/bin/sh\necho "$*" >> "$TRACE"\necho maintenance-diagnostic\ncase "$*" in *"${FAIL_STEP:-never-match}"*) exit 27;; esac\n')
            uv.chmod(0o755)
            trace = root / 'trace'
            env = dict(os.environ, TEST_BIN=str(binary), TRACE=str(trace))
            ok = subprocess.run(['bash', str(script)], env=env, capture_output=True)
            self.assertEqual((ok.returncode, ok.stdout, ok.stderr), (0, b'', b''))
            steps = trace.read_text().splitlines()
            self.assertEqual(len(steps), 3)
            for step, name in zip(steps, ['translate_lines.py', 'summarize_lines.py', 'compute_overlaps.py']):
                self.assertIn(name, step)
            self.assertNotIn('gadget', trace.read_text())
            trace.unlink()
            failed = subprocess.run(['bash', str(script)], env=dict(env, FAIL_STEP='summarize_lines.py'), capture_output=True)
            self.assertEqual(failed.returncode, 27)
            self.assertIn(b'maintenance-diagnostic', failed.stderr)
            self.assertNotIn('compute_overlaps.py', trace.read_text())

    def test_publish_quiet_success_and_useful_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            script = root / 'run_site_publish.sh'
            script.write_text((ROOT / script.name).read_text().replace('export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"', 'export PATH="$TEST_BIN:/usr/bin:/bin"'))
            binary = root / 'bin'
            binary.mkdir()
            commands = {
                'git': '#!/bin/sh\ncase "$1" in\nstatus) exit 0;;\nremote) echo git@github.com:solresol/prosodia-catholica.git;;\npull) echo pulled;;\nesac\n',
                'uv': '#!/bin/sh\necho build-diagnostic\nexit "${BUILD_STATUS:-0}"\n',
                'python3': '#!/bin/sh\ncase "$2" in\n*DEPLOY_HOST*) echo merah;;\n*) echo /var/www/vhosts/prosodia-catholica.symmachus.org/htdocs;;\nesac\n',
                'rsync': '#!/bin/sh\necho deployed\nexit "${RSYNC_STATUS:-0}"\n',
            }
            for name, body in commands.items():
                p = binary / name
                p.write_text(body)
                p.chmod(0o755)
            (root / 'site').mkdir()
            (root / 'site/index.html').write_text('site')
            env = dict(os.environ, TEST_BIN=str(binary))
            ok = subprocess.run(['bash', str(script)], env=env, capture_output=True)
            self.assertEqual((ok.returncode, ok.stdout, ok.stderr), (0, b'', b''))
            for name, code in [('BUILD_STATUS', '23'), ('RSYNC_STATUS', '24')]:
                failed = subprocess.run(['bash', str(script)], env=dict(env, **{name: code}), capture_output=True)
                self.assertEqual(failed.returncode, int(code))
                self.assertIn(b'build-diagnostic', failed.stderr)
                self.assertIn(b'Site publish failed', failed.stderr)
            self.assertEqual(len(list((root / 'logs').glob('*.log'))), 2)


if __name__ == '__main__':
    unittest.main()
