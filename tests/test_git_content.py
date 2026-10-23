import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from content_store import load, encode, transaction
from git_content_workflow import apply
from test_handoff import request,result

class GitContentTests(unittest.TestCase):
 def document(self,req):
  rows=[]
  for role in ('new','past'):
   if req[role]: rows.append(dict(req[role]['original'],ref_major=1,ref_minor=len(rows),summary='summary',translated_at=None))
  return dict(schema=1,provenance=load()["provenance"],receipts={},passages=rows)
 def test_snapshot_is_allowlisted_and_deterministic(self):
  d=load(); self.assertEqual(len(d['passages']),544)
  self.assertEqual(json.loads(encode(d)),d)
  self.assertFalse(any(r['ref']=='E' for r in d['passages']))
  self.assertIsInstance(d['receipts'],dict)
 def test_apply_retry_stale_edit_and_rehearsal(self):
  req=request(); res=result(req); rec=dict(mode='production',request=req,result=res,ack=None)
  doc=self.document(req)
  self.assertEqual(apply(doc,rec),'imported')
  self.assertEqual(apply(doc,rec),'already-imported')
  self.assertEqual(len(doc['receipts']),1)
  changed=copy.deepcopy(doc);changed['passages'][0]['greek_text']='changed'
  with self.assertRaises(RuntimeError): apply(changed,rec)
  stale=self.document(req);stale['passages'][0]['summary']='safe unrelated summary'
  self.assertEqual(apply(stale,rec),'imported')
  rec['mode']='rehearsal'
  with self.assertRaises(RuntimeError): apply(self.document(req),rec)
 def test_transaction_rollback_and_uncooperative_writer(self):
  doc=self.document(request())
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'passages.json';path.write_text(encode(doc));original=path.read_bytes()
   with self.assertRaises(ValueError):
    with transaction(path) as changed:
     changed['passages'][0]['summary']='lost';raise ValueError('failure')
   self.assertEqual(path.read_bytes(),original)
   with self.assertRaises(RuntimeError):
    with transaction(path): path.write_text('other writer')
   self.assertEqual(path.read_text(),'other writer')
 def test_identity_and_receipt_collision(self):
  req=request();res=result(req);rec=dict(mode='production',request=req,result=res,ack=None)
  doc=self.document(req);res['day']='2020-01-01'
  with self.assertRaises(ValueError): apply(doc,rec)
  self.assertEqual(doc['receipts'],{})

if __name__=='__main__':unittest.main()

class GitSafetyTests(unittest.TestCase):
 def test_duplicate_refs_and_metadata_are_rejected(self):
  from content_store import validate
  d=load();d['passages'][1]['ref']=d['passages'][0]['ref']
  with self.assertRaises(ValueError):validate(d)
  d=load();d['provenance']['private_error']='no'
  with self.assertRaises(ValueError):validate(d)
 def test_commit_retry_scopes_and_whitespace(self):
  from unittest.mock import patch
  import git_content_workflow as w
  path=w.DEFAULT.resolve();root=path.parents[1]
  calls=[]
  def fakegit(*args):
   if args[:2]==('rev-parse','--show-toplevel'):return str(root)
   if args[:2]==('remote','get-url'):return 'git@github.com:solresol/prosodia-catholica.git'
   if args[0]=='branch':return 'main'
   if args[0]=='rev-list':return ''
   if args[0]=='ls-remote':return 'abc refs/heads/main'
   if args[0]=='rev-parse':return 'abc'
   raise AssertionError(args)
  with patch.object(w,'git',side_effect=fakegit),patch.object(w.subprocess,'check_output',return_value=' M content/passages.json\n'),patch.object(w.subprocess,'run',side_effect=lambda args,**kw:calls.append(args)):
   w.publish_content(path)
  self.assertTrue(any(c[1]=='commit' for c in calls))
  def ahead(*args):
   if args[0]=='rev-list':return 'unrelated'
   if args[0]=='show':return 'README.md'
   return fakegit(*args)
  with patch.object(w,'git',side_effect=ahead),patch.object(w.subprocess,'run') as run:
   with self.assertRaises(RuntimeError):w.publish_content(path)
   self.assertFalse(any(c.args[0][1]=='push' for c in run.call_args_list))
 def test_workflow_lock_serializes_processes(self):
  import subprocess,os
  from content_store import workflow_lock
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'passages.json';marker=Path(d)/'entered'
   code='from content_store import workflow_lock; from pathlib import Path; import sys\nwith workflow_lock(Path(sys.argv[1])): Path(sys.argv[2]).write_text("entered")'
   with workflow_lock(path):
    child=subprocess.Popen([sys.executable,'-c',code,str(path),str(marker)],cwd=Path(__file__).resolve().parents[1])
    import time;time.sleep(.1)
    self.assertFalse(marker.exists())
   self.assertEqual(child.wait(timeout=5),0)
   self.assertTrue(marker.exists())

class GenerationTests(unittest.TestCase):
 def test_partial_failure_retains_success_and_default_model(self):
  from unittest.mock import patch
  import types,contextlib
  import generate_content
  from content_store import load
  doc=copy.deepcopy(load());doc['passages']=doc['passages'][:2]
  for r in doc['passages']:r['summary']=None
  @contextlib.contextmanager
  def transaction():yield doc
  @contextlib.contextmanager
  def lock():yield
  module=types.SimpleNamespace(summarize_one=__import__('unittest.mock').mock.Mock(side_effect=[('new summary',2),ValueError('private error')]),_load_model=lambda default:default)
  modules={'openai':types.SimpleNamespace(OpenAI=lambda **kw:object()),'openai_utils':types.SimpleNamespace(load_openai_api_key=lambda:'not-a-real-key'),'summarize_lines':module}
  with patch.object(generate_content,'transaction',transaction),patch.object(generate_content,'workflow_lock',lock),patch.dict(sys.modules,modules),patch.object(sys,'argv',['generate_content.py','summary','--delay','0']):
   with self.assertRaises(RuntimeError):generate_content.main()
  self.assertEqual(doc['passages'][0]['summary'],'new summary')
  self.assertIsNone(doc['passages'][1]['summary'])
  self.assertEqual(module.summarize_one.call_args_list[0].kwargs['model'],'gpt-5.6-luna')
