"""Actual local-bare Git commits/pushes, including lost acknowledgement recovery."""
import copy
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import git_content_workflow as content
import git_gadget_handoff as handoff
from content_store import load,encode,workflow_lock
from cloud_gadgets import digest
from test_handoff import request,result

class GitImportRoundtrip(unittest.TestCase):
 def test_push_before_ack_and_failed_ack_retry(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);bare=root/'remote.git';work=root/'work'
   env=dict(os.environ,GIT_AUTHOR_NAME='Test',GIT_AUTHOR_EMAIL='test@example.invalid',GIT_COMMITTER_NAME='Test',GIT_COMMITTER_EMAIL='test@example.invalid')
   def git(*args,cwd=None):return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
   with patch.dict(os.environ,env):
    git('init','-q','--bare','--initial-branch=main',str(bare));git('clone','-q',str(bare),str(work))
    path=work/'content/passages.json';path.parent.mkdir()
    req=request();res=result(req);doc=dict(schema=1,provenance=load()['provenance'],receipts={},passages=[])
    for item in (req['new'],req['past']):doc['passages'].append(dict(item['original'],ref_major=1,ref_minor=item['original']['id'],summary='accepted',translated_at=None))
    path.write_text(encode(doc));git('add','content/passages.json',cwd=work);git('commit','-qm','baseline',cwd=work);git('push','-qu','origin','main',cwd=work)
    queue=handoff.GitQueue(str(bare));queue.transact(lambda r:handoff.enqueue(r,req));queue.transact(lambda r:handoff.claim(r,'worker'));queue.transact(lambda r:handoff.submit(r,'worker',res))
    before=git('rev-parse','HEAD',cwd=work);original_run=handoff.run
    def fail_ack(*args,**kwargs):
     if args[:3]==('git','push','origin'):raise RuntimeError('Simulated lost acknowledgement push')
     return original_run(*args,**kwargs)
    old=Path.cwd()
    try:
     os.chdir(work)
     with workflow_lock(path),patch.object(content,'remote_identity'),patch.object(handoff,'run',side_effect=fail_ack):
      with self.assertRaises(RuntimeError):queue.transact(lambda r:content.reconcile_content(r,path))
     imported=git('rev-parse','HEAD');self.assertNotEqual(before,imported)
     self.assertEqual(git('--git-dir',str(bare),'rev-parse','main'),imported)
     self.assertIsNone(queue.transact(lambda r:(r,r))['ack'])
     with workflow_lock(path),patch.object(content,'remote_identity'):
      self.assertEqual(queue.transact(lambda r:content.reconcile_content(r,path)),'already-imported')
     self.assertEqual(git('rev-parse','HEAD'),imported)
     self.assertEqual(queue.transact(lambda r:(r,r))['ack'],digest(res))
    finally:os.chdir(old)
