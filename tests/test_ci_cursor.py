"""Exercise the real CI wrapper against deterministic local command doubles."""
import getpass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicationCursorTests(unittest.TestCase):
    def test_result_arriving_during_publication_is_consumed_on_next_poll(self):
        source = '1' * 40
        before = 'a' * 40
        consumed_at_import = 'b' * 40
        arriving = 'c' * 40
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            binary = root / 'bin'
            binary.mkdir()
            (root / '.git').mkdir()
            state = root / 'remote-state'
            state.write_text(before)
            (root / 'config.py').write_text("GADGET_WORKFLOW='cloud'\nDEPLOY_HOST='test-target'\nDEPLOY_PATH='/public-output'\n")

            def program(path, body):
                path.write_text('#!' + sys.executable + '\n' + body)
                path.chmod(0o755)

            program(binary / 'git', '''import os, sys
from pathlib import Path
args = sys.argv[1:]
if args[:2] == ['remote', 'get-url']:
    print('git@github.com:solresol/prosodia-catholica.git')
elif args[:2] == ['branch', '--show-current']:
    print('main')
elif args[:2] == ['rev-parse', 'HEAD']:
    print(os.environ['TEST_SOURCE'])
elif args[:1] == ['ls-remote']:
    print(Path(os.environ['TEST_STATE']).read_text().strip() + '\\trefs/heads/gadget-handoff')
elif args[:1] not in (['status'], ['fetch'], ['merge-base'], ['merge']):
    raise AssertionError(args)
''')
            program(binary / 'date', "print('20261023')\n")
            program(binary / 'ssh', '''import hashlib
from pathlib import Path
print(hashlib.sha256(Path('site/ci-deployment.json').read_bytes()).hexdigest())
''')
            program(root / 'run_daily_pipeline.sh', '''import json, os
from pathlib import Path
state = Path(os.environ['TEST_STATE'])
# Another update can become visible after preflight but before actual import.
if not Path('import-started').exists():
    state.write_text(os.environ['TEST_AT_IMPORT'])
    Path('import-started').touch()
# Import consumes this snapshot. Arrival is strictly after this point but
# strictly before the wrapper verifies/records the publication: no sleeps.
consumed = state.read_text().strip()
Path(os.environ['HERODIAN_IMPORT_OBSERVATION']).write_text(json.dumps({'observed_ref':consumed,'outcome':'pending'}))
with Path('consumed-snapshots').open('a') as trace:
    trace.write(consumed + '\\n')
Path('site').mkdir(exist_ok=True)
Path('site/ci-deployment.json').write_text(json.dumps({'source_commit':os.environ['HERODIAN_EXPECTED_SHA']}))
if not Path('result-arrived').exists():
    state.write_text(os.environ['TEST_ARRIVING'])
    Path('result-arrived').touch()
''')
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                       HERODIAN_DEPLOY_ROOT=str(root), HERODIAN_DEPLOY_USER=getpass.getuser(),
                       TEST_SOURCE=source, TEST_STATE=str(state), TEST_AT_IMPORT=consumed_at_import, TEST_ARRIVING=arriving)

            def poll():
                ran = subprocess.run(['bash', str(ROOT / 'ci/run_deploy.sh'), source, 'publish'],
                                     env=env, capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
                return ran.stdout

            self.assertIn('Publication verified', poll())
            self.assertEqual((root / 'logs/ci-published').read_text().strip(),
                             f'{source} 20261023 {consumed_at_import}')
            self.assertEqual(state.read_text(), arriving)
            self.assertIn('Publication verified', poll())
            self.assertEqual((root / 'consumed-snapshots').read_text().splitlines(), [consumed_at_import, arriving])
            self.assertEqual((root / 'logs/ci-published').read_text().strip(),
                             f'{source} 20261023 {arriving}')
            self.assertIn('No changes since verified publication', poll())
            self.assertEqual((root / 'consumed-snapshots').read_text().splitlines(), [consumed_at_import, arriving])

    def test_failed_daily_publication_retries_without_repeating_source_work(self):
        source = '1' * 40
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            binary = root / 'bin'
            binary.mkdir()
            (root / '.git').mkdir()
            (root / 'config.py').write_text("GADGET_WORKFLOW='cloud'\nDEPLOY_HOST='test-target'\nDEPLOY_PATH='/public-output'\n")
            pipeline = (ROOT / 'run_daily_pipeline.sh').read_text().replace(
                'export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"',
                'export PATH="$TEST_BIN:/usr/bin:/bin"')
            (root / 'run_daily_pipeline.sh').write_text(pipeline)
            (root / 'run_daily_pipeline.sh').chmod(0o755)

            def program(path, body):
                path.write_text('#!' + sys.executable + '\n' + body)
                path.chmod(0o755)

            program(binary / 'git', """import os, sys
args = sys.argv[1:]
if args[:2] == ['remote', 'get-url']:
    print('git@github.com:solresol/prosodia-catholica.git')
elif args[:2] == ['branch', '--show-current']:
    print('main')
elif args[:2] == ['rev-parse', 'HEAD']:
    print(os.environ['TEST_SOURCE'])
elif args[:1] == ['ls-remote']:
    print('a'*40 + '\\trefs/heads/gadget-handoff')
elif args[:1] not in (['status'], ['fetch'], ['merge-base'], ['merge']):
    raise AssertionError(args)
""")
            program(binary / 'date', "print('20261023')\n")
            program(binary / 'uv', """import json, os, sys
from pathlib import Path
args = sys.argv[1:]
name = next(a for a in args if a.endswith('.py'))
with Path('steps').open('a') as f:
    f.write(name + '\\n')
if name == 'git_gadget_handoff.py' and 'import-ready' in args:
    Path(os.environ['HERODIAN_IMPORT_OBSERVATION']).write_text(json.dumps({'observed_ref':'a'*40,'outcome':'pending'}))
if name == 'translate_lines.py':
    state = Path('data-version')
    state.write_text(str(int(state.read_text() if state.exists() else '0') + 1))
if name == 'generate_site.py':
    if Path('fail-next-build').exists():
        Path('fail-next-build').unlink()
        sys.exit(33)
    Path('site').mkdir(exist_ok=True)
    Path('site/index.html').write_text(Path('data-version').read_text() if Path('data-version').exists() else '0')
    Path('site/passages.json').write_text('[]')
""")
            program(binary / 'rsync', """from pathlib import Path
import shutil
Path('live').mkdir(exist_ok=True)
for name in ('index.html', 'ci-deployment.json'):
    shutil.copyfile(Path('site') / name, Path('live') / name)
count = Path('publication-count')
count.write_text(str(int(count.read_text() if count.exists() else '0') + 1))
""")
            program(binary / 'ssh', """import hashlib
from pathlib import Path
print(hashlib.sha256(Path('live/ci-deployment.json').read_bytes()).hexdigest())
""")
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
                       TEST_BIN=str(binary), TEST_SOURCE=source,
                       HERODIAN_DEPLOY_ROOT=str(root), HERODIAN_DEPLOY_USER=getpass.getuser())

            def poll(mode):
                return subprocess.run(['bash', str(ROOT / 'ci/run_deploy.sh'), source, mode],
                                      env=env, capture_output=True, text=True)

            early = poll('publish')
            self.assertEqual(early.returncode, 0, early.stdout + early.stderr)
            self.assertEqual((root / 'live/index.html').read_text(), '0')
            self.assertTrue((root / 'logs/ci-published').exists())
            (root / 'fail-next-build').touch()
            failed = poll('daily')
            self.assertEqual(failed.returncode, 33, failed.stdout + failed.stderr)
            self.assertEqual((root / 'data-version').read_text(), '1')
            self.assertTrue((root / 'logs/daily-20261023.done').exists())
            self.assertFalse((root / 'logs/ci-published').exists())
            self.assertEqual((root / 'live/index.html').read_text(), '0')
            retry = poll('daily')
            self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)
            self.assertIn('Publication verified', retry.stdout)
            self.assertEqual((root / 'live/index.html').read_text(), '1')
            self.assertEqual((root / 'publication-count').read_text(), '2')
            steps = (root / 'steps').read_text().splitlines()
            for name in ('init_db.py', 'translate_lines.py', 'summarize_lines.py', 'compute_overlaps.py'):
                self.assertEqual(steps.count(name), 1, steps)
            self.assertEqual(steps.count('generate_site.py'), 3)
            self.assertIn('No changes since verified publication', poll('daily').stdout)
            self.assertEqual((root / 'steps').read_text().splitlines(), steps)


if __name__ == '__main__':
    unittest.main()
