from datetime import datetime
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
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
