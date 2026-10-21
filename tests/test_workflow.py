import copy
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cloud_gadgets


class WorkflowTests(unittest.TestCase):
    def test_evidence_and_stale_bundle(self):
        item = {'candidate': {'html': '<input>', 'css': '', 'js': 'void 0'}, 'test_evidence': {'browser': 'Chromium', 'interaction': 'type alpha', 'expected': 'alpha', 'actual': 'alpha'}}
        bundle = {'day': datetime.now(timezone.utc).date().isoformat(), 'new': item, 'past': None}
        with patch.dict(sys.modules, {'gadgetize_lines': types.SimpleNamespace(_validate_gadget=lambda **kw: None)}):
            cloud_gadgets.validate_bundle(bundle)
            bad = copy.deepcopy(bundle)
            bad['new']['test_evidence']['actual'] = 'wrong'
            with self.assertRaises(ValueError):
                cloud_gadgets.validate_bundle(bad)
            bundle['day'] = '2000-01-01'
            with self.assertRaises(ValueError):
                cloud_gadgets.validate_bundle(bundle)

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
