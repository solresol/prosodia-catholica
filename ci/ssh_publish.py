"""Publish a checked static artifact with an explicitly provisioned Herodian key.

No credential discovery, host-key acceptance or persistence is performed here.
Caller supplies temporary identity/known-host files and a verified exact-SHA gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PUBLIC_SITE_URL = 'https://prosodia-catholica.symmachus.org'
PUBLIC_MODES = '--chmod=D755,F644'
EXACT_MAIN = 'exact-main verification'
SSH_PUBLISH = 'SSH/rsync publish'
DRY_RUN = 'rsync dry-run checksum'
PUBLIC_HTTPS = 'public HTTPS verification'
CLOUDFLARE_BEACON = re.compile(
    rb'<script\b[^>]*\bsrc="https://static\.cloudflareinsights\.com/beacon\.min\.js/[^"\s]+"[^>]*></script>\n?'
)
STDERR_DIAGNOSTICS = tuple((re.compile(pattern, re.IGNORECASE), detail) for pattern, detail in (
    (r'ssh: could not resolve hostname |fatal: unable to access .+: could not resolve (?:host|proxy):',
     'DNS lookup failed'),
    (r'ssh: connect to host .+ port \d+: (?:connection |operation )?timed out'
     r'|connection (?:timed out during banner exchange|to .+ port \d+ timed out)'
     r'|rsync error: timeout (?:in data send/receive|waiting for daemon connection)'
     r'|fatal: unable to access .+: (?:failed to connect .+timed out|operation timed out)',
     'connection or transfer timed out'),
    (r'host key verification failed\.?$|warning: remote host identification has changed!$'
     r'|no \S+ host key is known for .+ strict checking',
     'SSH host-key verification failed'),
    (r'(?:\S+@\S+: )?permission denied \((?:publickey|password|keyboard-interactive)(?:,|\))'
     r'|received disconnect from .+: too many authentication failures'
     r'|fatal: (?:authentication failed for |could not read username for )',
     'authentication failed'),
    (r'load key ".+": (?:error in libcrypto|invalid format|permission denied)'
     r'|.+unprotected private key file!',
     'SSH identity could not be loaded'),
    (r'rsync: (?:\[(?:receiver|generator)\] |recv_generator: ).+(?:permission denied|operation not permitted)',
     'remote destination permission denied'),
    (r'rsync: .+(?:permission denied|operation not permitted)',
     'rsync filesystem permission denied'),
    (r'(?:rsync: |warning: |error: ).+ failed verification -- update discarded',
     'rsync file verification failed'),
    (r'ssh: connect to host .+ port \d+: connection refused',
     'SSH connection refused'),
))


class PublicationError(RuntimeError):
    """A stage and diagnostic assembled only from fixed text and numeric metadata."""

    def __init__(self, stage, detail):
        self.stage = stage
        super().__init__(detail)


def subprocess_diagnostic(error):
    """Classify a bounded stderr sample without copying any subprocess text."""
    sample = (error.stderr or '')[:8192]
    if isinstance(sample, bytes):
        sample = sample.decode('ascii', errors='replace')
    for line in sample.split('\n'):
        if line.isascii() and line.isprintable():
            for pattern, detail in STDERR_DIAGNOSTICS:
                if pattern.match(line):
                    return f'exit code {error.returncode}: {detail}'
    return f'exit code {error.returncode}: no recognized stderr diagnostic'


def _run_rsync(args, stage):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, errors='replace')
    except subprocess.CalledProcessError as error:
        raise PublicationError(stage, subprocess_diagnostic(error)) from None
    except OSError:
        raise PublicationError(stage, 'rsync could not start') from None


def manifest(root):
    root=Path(root)
    files={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise ValueError('Artifact symlink refused')
        if p.is_file():
            relative=p.relative_to(root).as_posix()
            if not re.fullmatch(r'[A-Za-z0-9_./-]+',relative):raise ValueError('Unsafe artifact path')
            files[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
    if not {'index.html','passages.json','lines.json'}<=files.keys():raise ValueError('Incomplete site')
    return files


def verified_gate(sha,checked_sha,current_sha,conclusion):
    if not re.fullmatch(r'[0-9a-f]{40}',sha) or sha!=checked_sha or sha!=current_sha or conclusion!='success':
        raise PublicationError(EXACT_MAIN, 'Deployment requires successful checks for exact current main SHA')


def _http_status(code):
    return f'HTTP {code}' if type(code) is int and 100 <= code <= 599 else 'invalid HTTP status'


def _https_diagnostic(error):
    if isinstance(error, HTTPError):
        return _http_status(error.code)
    reason = error.reason if isinstance(error, URLError) else error
    for error_type, detail in (
        (socket.gaierror, 'DNS lookup failed'),
        (TimeoutError, 'request timed out'),
        (ssl.SSLCertVerificationError, 'TLS certificate verification failed'),
        (ssl.SSLError, 'TLS negotiation failed'),
        (ConnectionRefusedError, 'connection refused'),
    ):
        if isinstance(reason, error_type):
            return detail
    return 'request failed'


def verify_publication(root, expected):
    """Check representative public routes against this exact built artifact."""
    passages = sorted(name for name in expected if name.startswith('passages/') and name.endswith('.html'))
    routes = ['index.html', 'analysis/progress.html', 'passages.json']
    if not passages or not set(routes) <= expected.keys():
        raise ValueError('Public HTTPS check requires index, progress, data and passage pages')
    routes.append(passages[0])
    for relative in routes:
        label = relative if relative in ('index.html', 'analysis/progress.html', 'passages.json') else 'passage page'
        route = '' if relative == 'index.html' else relative
        url = f'{PUBLIC_SITE_URL}/{route}?publication={expected[relative]}'
        request = Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'Prosodia-Catholica-deployment-check'})
        try:
            with urlopen(request, timeout=30) as response:
                if response.status != 200:
                    detail = _http_status(response.status)
                    raise PublicationError(PUBLIC_HTTPS, f'Public HTTPS check failed for {label}: unexpected response ({detail})')
                if response.geturl() != url:
                    raise PublicationError(PUBLIC_HTTPS, f'Public HTTPS check failed for {label}: unexpected response (redirect)')
                # Allow bounded CDN instrumentation, while detecting extra content.
                body = response.read((Path(root) / relative).stat().st_size + 4097)
        except (URLError, TimeoutError) as error:
            raise PublicationError(PUBLIC_HTTPS, f'Public HTTPS check failed for {label}: {_https_diagnostic(error)}') from None
        if relative.endswith('.html'):
            body = CLOUDFLARE_BEACON.sub(b'', body)
        if hashlib.sha256(body).hexdigest() != expected[relative]:
            raise PublicationError(PUBLIC_HTTPS, f'Public HTTPS content mismatch for {label}')


def publish(root,host,path,key,known_hosts):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]+',host):raise ValueError('Invalid host')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+',path) or '..' in Path(path).parts:raise ValueError('Invalid destination')
    for file in (key,known_hosts):
        if not Path(file).is_file():raise ValueError('Explicit identity and trusted host keys required')
    expected=manifest(root)
    # Key/known-host paths are temporary runner paths generated by trusted workflow.
    if any(not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(p)) for p in (key,known_hosts)):
        raise ValueError('Unsafe temporary SSH path')
    transport=f'ssh -i {key} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile={known_hosts}'
    destination=f'herodian@{host}:{path.rstrip("/")}/'
    _run_rsync(['rsync','-az','--delete',PUBLIC_MODES,'-e',transport,str(Path(root))+'/',destination], SSH_PUBLISH)
    checked = _run_rsync(['rsync','-aznc','--delete',PUBLIC_MODES,'--itemize-changes','-e',transport,str(Path(root))+'/',destination], DRY_RUN)
    if checked.stdout.strip():
        raise PublicationError(DRY_RUN, 'Published artifact checksum mismatch (rsync reported changes)')
    try:
        verify_publication(root, expected)
    except PublicationError:
        raise
    except Exception:
        raise PublicationError(PUBLIC_HTTPS, 'Public HTTPS check failed without a recognized diagnostic') from None
    return expected


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('sha','checked-sha','current-sha','conclusion','site','host','path','key','known-hosts','receipt'):p.add_argument('--'+name,required=True)
    a=p.parse_args()
    try:
        verified_gate(a.sha,a.checked_sha,a.current_sha,a.conclusion)
        files=publish(a.site,a.host,a.path,a.key,a.known_hosts)
    except PublicationError as error:
        raise SystemExit(f'{error.stage}: {error}') from None
    Path(a.receipt).write_text(json.dumps({'sha':a.sha,'files':files},sort_keys=True,indent=2)+'\n')

if __name__=='__main__':main()
