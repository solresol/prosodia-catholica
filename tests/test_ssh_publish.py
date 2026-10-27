import importlib.util
import io
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
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
   with patch.object(p.subprocess,'run',side_effect=run),patch.object(p,'verify_publication') as public_check:
    p.publish(root,'example.invalid','/site',key,known)
   self.assertIn('herodian@example.invalid:/site/',calls[0]);self.assertIn('StrictHostKeyChecking=yes',calls[0][calls[0].index('-e')+1]);self.assertIn('--itemize-changes',calls[1])
   public_check.assert_called_once_with(root,p.manifest(root))
   with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='changed')):
    with self.assertRaises(RuntimeError):p.publish(root,'example.invalid','/site',key,known)
 def test_symlink_is_not_published(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'bad').symlink_to('/etc/passwd')
   with self.assertRaises(ValueError):p.manifest(d)

 @unittest.skipUnless(shutil.which('rsync'),'rsync is required for permission regression')
 def test_restrictive_artifact_and_existing_destination_become_public(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'site';root.mkdir(mode=0o700)
   destination=Path(d)/'destination';destination.mkdir(mode=0o700)
   for relative in ('index.html','passages.json','lines.json','analysis/progress.html','passages/1.1.html'):
    for base in (root,destination):
     target=base/relative;target.parent.mkdir(parents=True,exist_ok=True)
     target.write_text('public '+relative);target.chmod(0o600);target.parent.chmod(0o700)
   key=Path(d)/'key';known=Path(d)/'known';key.touch(mode=0o600);known.touch(mode=0o600)
   real_run=subprocess.run
   def local_rsync(command,**kwargs):
    # Exercise the publisher's real rsync arguments without an SSH server.
    command=list(command);command[-1]=str(destination)+'/'
    return real_run(command,**kwargs)
   with patch.object(p.subprocess,'run',side_effect=local_rsync),patch.object(p,'verify_publication'):
    p.publish(root,'example.invalid','/site',key,known)
   self.assertEqual(stat.S_IMODE(destination.stat().st_mode),0o755)
   for target in destination.rglob('*'):
    self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o755 if target.is_dir() else 0o644)
   self.assertEqual(stat.S_IMODE(root.stat().st_mode),0o700)
   self.assertEqual(stat.S_IMODE((root/'index.html').stat().st_mode),0o600)
   self.assertEqual(stat.S_IMODE(key.stat().st_mode),0o600)
   self.assertEqual(stat.S_IMODE(known.stat().st_mode),0o600)

 def test_public_https_failure_prevents_successful_publication(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'site';root.mkdir()
   for name in ('index.html','passages.json','lines.json'):(root/name).write_text('public')
   key=Path(d)/'key';known=Path(d)/'known';key.touch();known.touch()
   with patch.object(p.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='')),patch.object(p,'verify_publication',side_effect=RuntimeError('Public HTTPS check failed')):
    with self.assertRaisesRegex(RuntimeError,'Public HTTPS check failed'):
     p.publish(root,'example.invalid','/site',key,known)


class PublicResponse(io.BytesIO):
 def __init__(self,body,url,status=200):super().__init__(body);self.url=url;self.status=status
 def geturl(self):return self.url


class PublicHTTPSTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
  self.root=Path(self.directory.name)
  for relative in ('index.html','passages.json','lines.json','analysis/progress.html','passages/1.1.html'):
   target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True)
   target.write_text('ἥρως '+relative,encoding='utf-8')
  self.expected=p.manifest(self.root)

 def test_public_routes_match_the_built_bytes(self):
  checked=[]
  def respond(request,timeout):
   from urllib.parse import urlsplit
   relative=urlsplit(request.full_url).path.lstrip('/') or 'index.html'
   self.assertEqual(timeout,30)
   self.assertEqual(request.get_header('Cache-control'),'no-cache')
   self.assertIn('?publication='+self.expected[relative],request.full_url)
   checked.append(relative)
   return PublicResponse((self.root/relative).read_bytes(),request.full_url)
  with patch.object(p,'urlopen',side_effect=respond):p.verify_publication(self.root,self.expected)
  self.assertEqual(checked,['index.html','analysis/progress.html','passages.json','passages/1.1.html'])

 def test_forbidden_and_timeout_responses_fail(self):
  for error in (HTTPError(p.PUBLIC_SITE_URL,403,'Forbidden',None,None),TimeoutError('timed out')):
   with self.subTest(error=type(error).__name__),patch.object(p,'urlopen',side_effect=error):
    with self.assertRaisesRegex(RuntimeError,'Public HTTPS check failed for index.html'):
     p.verify_publication(self.root,self.expected)

 def test_http_200_with_stale_or_extra_content_fails(self):
  for body in (b'stale page',(self.root/'index.html').read_bytes()+b'extra'):
   with self.subTest(body=body),patch.object(p,'urlopen',side_effect=lambda request,timeout:PublicResponse(body,request.full_url)):
    with self.assertRaisesRegex(RuntimeError,'Public HTTPS content mismatch'):
     p.verify_publication(self.root,self.expected)

 def test_cloudflare_analytics_is_allowed_without_ignoring_other_changes(self):
  beacon=b'<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/version" data-cf-beacon="test"></script>\n'
  def respond(request,timeout):
   from urllib.parse import urlsplit
   relative=urlsplit(request.full_url).path.lstrip('/') or 'index.html'
   body=(self.root/relative).read_bytes()
   if relative.endswith('.html'):body+=beacon
   return PublicResponse(body,request.full_url)
  with patch.object(p,'urlopen',side_effect=respond):p.verify_publication(self.root,self.expected)
  for extra in (b'changed text',b'<script src="https://other.invalid/beacon.min.js/version"></script>'):
   with self.subTest(extra=extra),patch.object(p,'urlopen',side_effect=lambda request,timeout:PublicResponse((self.root/'index.html').read_bytes()+beacon+extra,request.full_url)):
    with self.assertRaisesRegex(RuntimeError,'Public HTTPS content mismatch'):
     p.verify_publication(self.root,self.expected)

 def test_redirect_or_non_200_response_fails(self):
  for url,status in (('http://prosodia-catholica.symmachus.org/',200),(p.PUBLIC_SITE_URL,503)):
   with self.subTest(url=url,status=status),patch.object(p,'urlopen',side_effect=lambda request,timeout:PublicResponse(b'error',url,status)):
    with self.assertRaisesRegex(RuntimeError,'unexpected response'):
     p.verify_publication(self.root,self.expected)

 def test_incomplete_artifact_is_rejected_before_network_access(self):
  expected={name:digest for name,digest in self.expected.items() if not name.startswith('passages/')}
  with patch.object(p,'urlopen') as request:
   with self.assertRaises(ValueError):p.verify_publication(self.root,expected)
  request.assert_not_called()
