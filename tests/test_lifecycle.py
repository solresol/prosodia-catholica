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
