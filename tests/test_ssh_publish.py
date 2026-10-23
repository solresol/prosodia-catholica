import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('publisher',Path(__file__).resolve().parents[1]/'ci/ssh_publish.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class PublicationTests(unittest.TestCase):
 def test_exact_sha_gate(self):
  sha='a'*40;p.verified_gate(sha,sha,sha,'success')
  for args in ((sha,'b'*40,sha,'success'),(sha,sha,'b'*40,'success'),(sha,sha,sha,'failure')):
   with self.assertRaises(RuntimeError):p.verified_gate(*args)
 def test_fixed_account_strict_host_keys_and_checksum_failure(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'site';root.mkdir()
   for name in ('index.html','passages.json','lines.json'):(root/name).write_text('public')
   key=Path(d)/'key';known=Path(d)/'known';key.touch();known.touch()
   calls=[]
   def run(cmd,**kw):calls.append(cmd);return subprocess.CompletedProcess(cmd,0,stdout='')
   with patch.object(p.subprocess,'run',side_effect=run):p.publish(root,'example.invalid','/site',key,known)
   self.assertIn('herodian@example.invalid:/site/',calls[0]);self.assertIn('StrictHostKeyChecking=yes',calls[0][4]);self.assertIn('--itemize-changes',calls[1])
   with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='changed')):
    with self.assertRaises(RuntimeError):p.publish(root,'example.invalid','/site',key,known)
 def test_symlink_is_not_published(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'bad').symlink_to('/etc/passwd')
   with self.assertRaises(ValueError):p.manifest(d)
