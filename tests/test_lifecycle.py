from contextlib import redirect_stderr
from datetime import datetime
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ci import lifecycle, ssh_publish
from ci.lifecycle import cycle

class Ops:
 def __init__(self):
  self.source='a'*40;self.remote=self.source;self.events=[];self.pending=False;self.imports=0;self.acks=0;self.fail=None;self.receipts=[];self.late=False
 def guard(self):
  self.events.append('guard')
  if self.source!=self.remote:raise RuntimeError('advanced')
 def sha(self):return self.source
 def reconcile(self):
  self.events.append('reconcile')
  if self.pending:
   self.source='b'*40;self.remote=self.source;self.pending=False;self.imports+=1;self.acks+=1
 def checks(self,sha):
  self.events.append(('checks',sha))
  if self.fail=='checks':raise RuntimeError('checks failed')
  if self.fail=='advance':self.remote='c'*40
 def publication(self,sha):
  self.events.append(('publication',sha))
  if self.fail=='publication' or sha!=self.remote:raise RuntimeError('publication failed')
  if self.late:self.pending=True;self.late=False
  return {'index.html':'d'*64}
 def receipt(self,value):self.events.append('receipt');self.receipts.append(value)
 def enqueue(self,sha):
  self.events.append('enqueue')
  if self.fail=='enqueue':raise RuntimeError('enqueue failed')

class LifecycleTests(unittest.TestCase):
 def test_resulting_sha_and_publication_order(self):
  o=Ops();o.pending=True
  self.assertEqual(cycle(o,datetime(2026,10,23,1,17)),'b'*40)
  self.assertEqual(o.imports,1);self.assertEqual(o.acks,1)
  self.assertLess(o.events.index(('checks','b'*40)),o.events.index(('publication','b'*40)))
  self.assertLess(o.events.index('receipt'),o.events.index('enqueue'))
 def test_publication_failure_then_retry_does_not_reimport(self):
  o=Ops();o.pending=True;o.fail='publication'
  with self.assertRaises(RuntimeError):cycle(o,datetime(2026,10,23,1,17))
  self.assertNotIn('enqueue',o.events);self.assertFalse(o.receipts)
  o.fail=None;cycle(o,datetime(2026,10,23,2,17))
  self.assertEqual((o.imports,o.acks),(1,1));self.assertEqual(o.receipts[0]['sha'],'b'*40)
 def test_late_result_arriving_during_publication_is_not_consumed(self):
  o=Ops();o.late=True
  cycle(o,datetime(2026,10,23,0,17))
  self.assertTrue(o.pending);self.assertEqual(o.receipts[-1]['sha'],'a'*40)
  cycle(o,datetime(2026,10,23,1,17))
  self.assertEqual(o.imports,1);self.assertEqual(o.receipts[-1]['sha'],'b'*40)
 def test_failed_checks_or_advanced_main_never_publish(self):
  for failure in ('checks','advance'):
   o=Ops();o.fail=failure
   with self.assertRaises(RuntimeError):cycle(o,datetime(2026,10,23,1,17))
   self.assertFalse(o.receipts);self.assertNotIn('enqueue',o.events)
 def test_enqueue_failure_retains_publication_receipt_and_retries(self):
  o=Ops();o.fail='enqueue'
  with self.assertRaises(RuntimeError):cycle(o,datetime(2026,10,23,1,17))
  self.assertTrue(o.receipts)
  o.fail=None;cycle(o,datetime(2026,10,23,2,17));self.assertEqual(o.imports,0)
 def test_no_model_stage_is_present(self):
  source=(Path(__file__).resolve().parents[1]/'ci/lifecycle.py').read_text()
  self.assertNotIn('OPENAI',source);self.assertNotIn('generate_content',source);self.assertFalse(hasattr(Ops,'maintenance'))
  fallback=(Path(__file__).resolve().parents[1]/'run_git_pipeline.sh').read_text()
  self.assertNotIn('generate_content.py',fallback)
  self.assertNotIn('gadgetize_lines.py',fallback)

class AuthenticationLogTests(unittest.TestCase):
 def test_git_config_failure_does_not_log_encoded_token(self):
  import base64,os,subprocess,tempfile
  from unittest.mock import patch
  workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/lifecycle.yml').read_text()
  start=workflow.index('          import base64,os,subprocess')
  end=workflow.index('\n          PY',start)
  code='\n'.join(line[10:] for line in workflow[start:end].splitlines())
  token='a-test-token-that-must-not-leak'
  with patch.dict(os.environ,GH_TOKEN=token),patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],1)),self.assertRaises(SystemExit) as failed:
   exec(code,{})
  self.assertEqual(str(failed.exception),'Temporary Git authentication setup failed')
  self.assertNotIn(token,str(failed.exception));self.assertNotIn(base64.b64encode(('x-access-token:'+token).encode()).decode(),str(failed.exception))


class PublicationLogTests(unittest.TestCase):
    def test_failure_stages_report_safe_diagnostics_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / 'site'
            for name in ('index.html', 'passages.json', 'lines.json',
                         'analysis/progress.html', 'passages/1.1.html'):
                file = site / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('public test content')
            key, known = root / 'private-key', root / 'known-hosts'
            key.touch()
            known.touch()
            argv = ['lifecycle.py', '--site', str(site), '--host', 'private.invalid',
                    '--path', '/private/deploy', '--key', str(key), '--known-hosts', str(known)]
            self.check_failure_cases(argv)

    def check_failure_cases(self, argv):
        sha = 'a' * 40
        unsafe = 'https://deploy:secret-token@private.invalid/::error::'
        success = subprocess.CompletedProcess([], 0, stdout='')
        changes = subprocess.CompletedProcess([], 0, stdout=f'>fcs {unsafe}\n')
        auth = subprocess.CalledProcessError(
            255, ['rsync', unsafe], output=f'{unsafe}\x1b\r\n',
            stderr=f'deploy@private.invalid: Permission denied (publickey).\n::error::{unsafe}'
        )
        dns = subprocess.CalledProcessError(
            128, ['git', unsafe], stderr=f"fatal: unable to access '{unsafe}': Could not resolve host: private.invalid"
        )
        denied = HTTPError(unsafe, 403, '\n::error::secret-token\x1b', None, None)
        cases = (
            ('exact-main verification', 'Deployment requires successful checks for exact current main SHA',
             'b' * 40, [], 0),
            ('exact-main verification', 'exit code 128: DNS lookup failed', dns, [], 0),
            ('SSH/rsync publish', 'exit code 255: authentication failed', sha, [auth], 0),
            ('rsync dry-run checksum', 'exit code 255: authentication failed', sha, [success, auth], 0),
            ('rsync dry-run checksum', 'Published artifact checksum mismatch (rsync reported changes)',
             sha, [success, changes], 0),
            ('public HTTPS verification', 'Public HTTPS check failed for index.html: HTTP 403',
             sha, [success, success], 1),
        )
        for stage, detail, current, results, http_calls in cases:
            with self.subTest(stage=stage, detail=detail):
                log = io.StringIO()
                current_values = [current]
                with (
                    patch.object(sys, 'argv', argv),
                    patch.object(lifecycle.Operations, 'guard'),
                    patch.object(lifecycle.Operations, 'reconcile'),
                    patch.object(lifecycle.Operations, 'checks'),
                    patch.object(lifecycle.Operations, 'sha', return_value=sha),
                    patch.object(lifecycle.Operations, 'current', side_effect=current_values),
                    patch.object(lifecycle.Operations, 'receipt') as receipt,
                    patch.object(lifecycle.Operations, 'enqueue') as enqueue,
                    patch.object(ssh_publish.subprocess, 'run', side_effect=results) as rsync,
                    patch.object(ssh_publish, 'urlopen', side_effect=denied) as request,
                    redirect_stderr(log),
                    self.assertRaises(SystemExit) as failed,
                ):
                    lifecycle.main()
                self.assertEqual(failed.exception.code, 1)
                self.assertEqual(
                    log.getvalue(),
                    f'Herodian hosted lifecycle failed at {stage} ({detail}); later stages not claimed successful.\n',
                )
                self.assertEqual(rsync.call_count, len(results))
                self.assertEqual(request.call_count, http_calls)
                receipt.assert_not_called()
                enqueue.assert_not_called()
