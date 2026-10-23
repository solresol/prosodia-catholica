"""Allowlisted public content. Atomic replacement under a local lock; Git is the history.

A writer must commit and push with ordinary fast-forward semantics before acknowledging
external work. Rejected pushes require reconciliation, never force push.
"""
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
import re
from pathlib import Path
import tempfile

DEFAULT = Path(__file__).parent / 'content/passages.json'
FIELDS = {'id','ref','ref_major','ref_minor','greek_text','english_translation','summary','gadget_html','gadget_css','gadget_js','translated_at'}


def validate(document):
    if set(document) not in ({'schema','provenance','receipts','passages'}, {'schema','provenance','receipts','passages','text_receipts'}) or document['schema'] != 1:
        raise ValueError('Unsupported content schema')
    if set(document["provenance"]) != {"edition","publication","scope"} or any(not isinstance(v,str) or len(v)>1000 for v in document["provenance"].values()):
        raise ValueError("Invalid safe provenance")
    seen=set(); refs=set()
    for row in document['passages']:
        if set(row) != FIELDS or type(row['id']) is not int or row['id'] in seen or row['ref']=='E':
            raise ValueError('Unexpected, duplicate or excluded passage')
        seen.add(row['id'])
        if not isinstance(row["ref"],str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",row["ref"]) or row["ref"] in refs:
            raise ValueError("Duplicate or unsafe canonical reference")
        refs.add(row["ref"])
        if any(row[k] is not None and type(row[k]) is not int for k in ("ref_major","ref_minor")):
            raise ValueError("Invalid numeric reference")
        for key in FIELDS-{'id','ref_major','ref_minor'}:
            if row[key] is not None and not isinstance(row[key],str):
                raise ValueError('Non-text content')
        if row['translated_at'] is not None:
            datetime.fromisoformat(row['translated_at'])
    if not isinstance(document['receipts'],dict):
        raise ValueError('Invalid reconciliation receipts')
    for key,receipt in document["receipts"].items():
        if not re.fullmatch(r"[0-9a-f]{64}",key) or set(receipt)!={"day","result_sha256"} or not re.fullmatch(r"[0-9a-f]{64}",receipt["result_sha256"]):
            raise ValueError("Invalid receipt")
        if datetime.fromisoformat(receipt["day"]).date().isoformat()!=receipt["day"]:
            raise ValueError("Invalid receipt day")
    texts=document.get('text_receipts',{})
    if not isinstance(texts,dict):raise ValueError('Invalid text receipts')
    for day,receipt in texts.items():
        if datetime.fromisoformat(day).date().isoformat()!=day or set(receipt)!={'request_sha256','result_sha256','review'}:
            raise ValueError('Invalid text receipt identity')
        if any(not re.fullmatch(r'[0-9a-f]{64}',receipt[k]) for k in ('request_sha256','result_sha256')):
            raise ValueError('Invalid text receipt digest')
        review=receipt['review']
        if set(review)!={'reviewer','notes'} or any(not isinstance(v,str) or not v.strip() or len(v)>2000 for v in review.values()):
            raise ValueError('Bounded independent text review required')
    return document


def load(path=DEFAULT):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


def encode(document):
    validate(document)
    return json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+'\n'


@contextmanager
def transaction(path=DEFAULT):
    path=Path(path)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        original=path.read_bytes()
        document=validate(json.loads(original))
        yield document
        # Catch edits by processes that do not cooperate with this lock too.
        if path.read_bytes()!=original:
            raise RuntimeError('Content changed concurrently; refusing overwrite')
        payload=encode(document).encode()
        if payload == original:
            return
        fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.content-')
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.replace(tmp,path)
            dfd=os.open(path.parent,os.O_DIRECTORY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)


def rendering_inputs(document):
    rows=[dict(row) for row in document['passages']]
    rows.sort(key=lambda r:(r['ref_major'] is None,r['ref_major'] or 0,r['ref_minor'] is None,r['ref_minor'] or 0,r['ref']))
    for r in rows:
        if r['translated_at']: r['translated_at']=datetime.fromisoformat(r['translated_at'])
    eligible=[r for r in rows if r['ref_major']!=0]
    stats={'total':len(rows),'translated':sum(r['english_translation'] is not None for r in eligible),'summarized':sum(r['summary'] is not None for r in rows)}
    progress={'total_all':len(rows),'total_non_e':len(rows),'total_translatable':len(eligible),'translated_done':stats['translated'],'summarized_done':stats['summarized'],'gadget_done':sum(r['gadget_html'] is not None for r in eligible),'gadget_ready_pending':sum(r['english_translation'] is not None and r['gadget_html'] is None for r in eligible),'gadget_blocked_translation':sum(r['english_translation'] is None for r in eligible),'latest_translated_at':max((r['translated_at'] for r in rows if r['translated_at']),default=None)}
    return rows,stats,progress


@contextmanager
def workflow_lock(path=DEFAULT):
    """Cooperating writers serialize generation, commit, push and acknowledgement."""
    with Path(path).with_name('workflow.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield
