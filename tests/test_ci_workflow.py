import getpass
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def launcher_source():
    lines = (ROOT / '.github/workflows/deploy.yml').read_text().splitlines()
    start = lines.index("          python3 - <<'PY'") + 1
    end = lines.index('          PY', start)
    return '\n'.join(line[10:] for line in lines[start:end]) + '\n'


class WorkflowGateTests(unittest.TestCase):
    def test_all_deploy_triggers_require_successful_checks_for_the_exact_sha(self):
        text = (ROOT / '.github/workflows/deploy.yml').read_text()
        checks, deploy = text.split('  deploy:\n', 1)
        for trigger in ('schedule:', 'repository_dispatch:', 'workflow_dispatch:', 'push:'):
            self.assertIn(trigger, checks)
        self.assertIn('    needs: checks\n', deploy)
        self.assertIn("needs.checks.result == 'success'", deploy)
        self.assertIn('needs.checks.outputs.source_sha == github.sha', deploy)
        self.assertIn('SOURCE_SHA: ${{ needs.checks.outputs.source_sha }}', deploy)
        self.assertIn('source_sha: ${{ steps.source.outputs.sha }}', checks)
        self.assertIn('git fetch --depth=1 origin "$SOURCE_SHA"', checks)
        self.assertIn('test "$(git rev-parse HEAD)" = "$SOURCE_SHA"', checks)
        self.assertIn('python3 -m unittest discover -s tests -v', checks)
        wrapper = (ROOT / 'ci/run_deploy.sh').read_text()
        self.assertIn('git merge --ff-only "$expected"', wrapper)
        self.assertIn('[[ $(git rev-parse HEAD) == "$expected" ]]', wrapper)


class LauncherRedactionTests(unittest.TestCase):
    def invoke(self, root):
        diagnostics = root / 'private-sentinel-diagnostics'
        diagnostics.mkdir(exist_ok=True)
        env = dict(os.environ, SOURCE_SHA='1'*40, EVENT='workflow_dispatch', REQUESTED_MODE='publish',
                   HERODIAN_DEPLOY_ROOT=str(root), HERODIAN_DEPLOY_USER=getpass.getuser(),
                   RUNNER_TEMP=str(diagnostics))
        ran = subprocess.run([sys.executable, '-'], input=launcher_source(), text=True,
                             env=env, capture_output=True)
        self.assertNotIn('private-sentinel', ran.stdout + ran.stderr)
        self.assertNotIn(str(root), ran.stdout + ran.stderr)
        for log in diagnostics.glob('*.log'):
            self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
        return ran, diagnostics

    def test_missing_private_wrapper_path_is_not_replayed(self):
        with tempfile.TemporaryDirectory(prefix='private-sentinel-') as d:
            root = Path(d)
            ran, diagnostics = self.invoke(root)
            self.assertEqual(ran.returncode, 127)
            self.assertIn('Deployment failed', ran.stdout)
            log = next(diagnostics.glob('*.log')).read_text()
            self.assertIn(str(root / 'ci/run_deploy.sh'), log)

    def test_private_lock_open_error_is_captured_before_it_reaches_ci(self):
        with tempfile.TemporaryDirectory(prefix='private-sentinel-') as d:
            root = Path(d)
            (root / '.git').mkdir()
            (root / 'ci').mkdir()
            (root / 'ci/run_deploy.sh').write_text((ROOT / 'ci/run_deploy.sh').read_text())
            (root / 'logs/pipeline.lock').mkdir(parents=True)  # deterministic open failure
            ran, _ = self.invoke(root)
            self.assertNotEqual(ran.returncode, 0)
            private_log = next((root / 'logs').glob('ci-run.*.log')).read_text()
            self.assertIn('pipeline.lock', private_log)
            self.assertIn(str(root / 'ci/run_deploy.sh'), private_log)

    def test_only_exact_public_attestation_survives_launcher_capture(self):
        with tempfile.TemporaryDirectory(prefix='private-sentinel-') as d:
            root = Path(d)
            (root / 'ci').mkdir()
            (root / 'ci/run_deploy.sh').write_text(
                'echo "$HERODIAN_DEPLOY_ROOT/private-sentinel-detail"\n'
                'printf "Publication verified: source=%s manifest_sha256=%s\\n" "$1" "' + 'c'*64 + '"\n')
            ran, diagnostics = self.invoke(root)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertEqual(ran.stdout.strip(), 'Publication verified: source=' + '1'*40 + ' manifest_sha256=' + 'c'*64)
            self.assertEqual(list(diagnostics.glob('*.log')), [])


if __name__ == '__main__':
    unittest.main()
