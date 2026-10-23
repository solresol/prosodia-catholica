"""Git-authoritative gadget reconciliation; cloud claim/submit protocol stays unchanged."""
import argparse
import copy
import json
from pathlib import Path
import secrets
import subprocess
from content_store import DEFAULT, load, transaction, workflow_lock
from cloud_gadgets import FIELDS, PARTS, check_bundle, digest, logical_day, validate_result
from git_gadget_handoff import GitQueue, enqueue, remote_identity


def prepare(document, published):
    public={r['id']:{k:r[k] for k in FIELDS} for r in published}
    rows=[{k:r[k] for k in FIELDS} for r in document['passages'] if r['english_translation'] is not None and r['greek_text'] is not None and r['ref_major']!=0]
    rows=[r for r in rows if public.get(r['id'])==r]
    rows.sort(key=lambda r:r['id'])
    def wrap(row):
        return None if row is None else {'original':row,'candidate':{k:row['gadget_'+k] or '' for k in PARTS}}
    new=next((r for r in rows if r['gadget_html'] is None),None)
    past=[r for r in rows if r['gadget_html'] is not None]
    result={'day':logical_day(),'new':wrap(new),'past':wrap(secrets.choice(past)) if past else None}
    check_bundle(result,current=True)
    return result


def apply(document, record):
    if record['mode']!='production':
        raise RuntimeError('Rehearsal cannot enter authoritative content')
    request,result=record['request'],record['result']
    validate_result(request,result)
    key=digest(request); result_hash=digest(result)
    rows={r['id']:r for r in document['passages']}
    items=[result[r] for r in ('new','past') if result[r]]
    receipt=document['receipts'].get(key)
    if receipt is not None:
        if receipt != {'day':request['day'],'result_sha256':result_hash}:
            raise RuntimeError('Conflicting result receipt')
        for item in items:
            row=rows[item['original']['id']]
            if any(row[k]!=item['original'][k] for k in ('id','ref','greek_text','english_translation')) or any((row['gadget_'+k] or '')!=item['candidate'][k] for k in PARTS):
                raise RuntimeError('Imported passage subsequently edited')
        return 'already-imported'
    if record['ack'] is not None:
        raise RuntimeError('Previously acknowledged DB result missing Git receipt; reconcile explicitly')
    for item in items:
        row=rows.get(item['original']['id'])
        if row is None or {k:row[k] for k in FIELDS}!=item['original']:
            raise RuntimeError('Passage changed since assignment; refusing overwrite')
    for item in items:
        row=rows[item['original']['id']]
        for k in PARTS: row['gadget_'+k]=item['candidate'][k]
    document['receipts'][key]={'day':request['day'],'result_sha256':result_hash}
    return 'imported'


def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()


def publish_content(path):
    """Push only the allowlisted content file, then caller may ack. No deployment claim."""
    path=path.resolve(); root=Path(git('rev-parse','--show-toplevel')).resolve()
    if path!=root/'content/passages.json': raise RuntimeError('Unexpected content path')
    remote_identity(git('remote','get-url','origin'))
    if git('branch','--show-current')!='main': raise RuntimeError('Reconciliation requires checked-out main')
    subprocess.run(['git','fetch','origin','main'],check=True)
    subprocess.run(['git','merge-base','--is-ancestor','origin/main','HEAD'],check=True)
    ahead=git('rev-list','origin/main..HEAD').splitlines()
    if len(ahead)>1 or any(git('show','--format=','--name-only',commit)!='content/passages.json' or git('show','-s','--format=%s',commit)!='Reconcile independently tested cloud gadget result' for commit in ahead):
        raise RuntimeError('Unrelated unpushed commits; refusing publication')
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],text=True).splitlines()
    if any(line[3:]!='content/passages.json' for line in dirty):
        raise RuntimeError('Unrelated tracked changes; refusing commit')
    if dirty:
        subprocess.run(['git','add','--','content/passages.json'],check=True)
        subprocess.run(['git','commit','-m','Reconcile independently tested cloud gadget result','--','content/passages.json'],check=True)
    subprocess.run(['git','push','origin','HEAD:refs/heads/main'],check=True)
    if git('ls-remote','origin','refs/heads/main').split()[0]!=git('rev-parse','HEAD'):
        raise RuntimeError('Main advanced; confirm reconciliation before acknowledging')


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('action',choices=['import-ready','enqueue','recover-content'])
    p.add_argument('--content',type=Path,default=DEFAULT)
    p.add_argument('--published-file',type=Path)
    p.add_argument('--day')
    args=p.parse_args()
    if args.action=='recover-content':
        with workflow_lock(args.content):
            load(args.content)
            publish_content(args.content)
        print('Content recovered to Git; no handoff acknowledgement or deployment performed')
        return
    queue=GitQueue(day=args.day,pending=not args.day)
    def update(record):
        if args.action=='enqueue':
            if record is not None: return record,'already-enqueued'
            if not args.published_file: raise RuntimeError('Published snapshot required')
            request=prepare(load(args.content),json.loads(args.published_file.read_text()))
            return enqueue(record,request)
        if record is None or record['result'] is None or record['mode']=='rehearsal': return record,'pending'
        with transaction(args.content) as document:
            outcome=apply(document,record)
        # A crash before/after push is recovered by the receipt and candidate comparison.
        publish_content(args.content)
        record=copy.deepcopy(record)
        record['ack']=digest(record['result'])
        return record,outcome
    with workflow_lock(args.content):
        print(queue.transact(update))


if __name__=='__main__': main()
