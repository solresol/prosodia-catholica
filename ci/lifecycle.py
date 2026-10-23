"""Hosted lifecycle. No credentials/configuration are installed by this program."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ci.ssh_publish import publish,verified_gate


def command(*args,env=None):
    return subprocess.check_output(list(args),cwd=ROOT,env=env,text=True,stderr=subprocess.STDOUT).strip()


class Operations:
    def __init__(self,args):self.args=args
    def sha(self):return command('git','rev-parse','HEAD')
    def current(self):return command('git','ls-remote','origin','refs/heads/main').split()[0]
    def guard(self):
        if command('git','branch','--show-current')!='main' or command('git','status','--porcelain','--untracked-files=no') or self.sha()!=self.current():
            raise RuntimeError('Clean exact current main required')
    def reconcile(self):command(sys.executable,'git_content_workflow.py','import-ready')
    def checks(self,sha):
        command(sys.executable,'-m','unittest','discover','-s','tests','-v')
        env=dict(os.environ,SOURCE_DATE_EPOCH=command('git','show','-s','--format=%ct',sha))
        command(sys.executable,'tests/offline_build.py','--out',str(self.args.site),env=env)
    def publication(self,sha):
        verified_gate(sha,sha,self.current(),'success')
        return publish(self.args.site,self.args.host,self.args.path,self.args.key,self.args.known_hosts)
    def receipt(self,record):
        self.args.receipt.parent.mkdir(parents=True,exist_ok=True)
        self.args.receipt.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
    def enqueue(self,sha):
        if sha!=self.current():raise RuntimeError('Main advanced after publication; enqueue deferred')
        command(sys.executable,'git_content_workflow.py','enqueue','--published-file',str(self.args.site/'passages.json'))


def cycle(ops,now):
    """No publication cache: late results and failed publications cannot be skipped."""
    ops.guard()
    ops.reconcile()  # Includes content commit/push before handoff acknowledgement.
    ops.guard()
    sha=ops.sha()
    ops.checks(sha)  # Tests and artifact are bound to resulting SHA, not triggering SHA.
    if ops.sha()!=sha:raise RuntimeError('Source changed during checks')
    files=ops.publication(sha)
    ops.receipt({'sha':sha,'day':now.date().isoformat(),'files':files,'published':True})
    ops.enqueue(sha)
    return sha


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('host','path','key','known-hosts'):p.add_argument('--'+name,required=True)
    p.add_argument('--site',type=Path,default=ROOT/'site')
    p.add_argument('--receipt',type=Path,default=ROOT/'publication.json')
    a=p.parse_args()
    try:print('Published checked source '+cycle(Operations(a),datetime.now(ZoneInfo('Australia/Sydney'))))
    except Exception:
        # Captured subprocess/API details can include credentials or host-local context.
        print('Herodian hosted lifecycle failed; no later stage was claimed successful.',file=sys.stderr)
        raise SystemExit(1)

if __name__=='__main__':main()
