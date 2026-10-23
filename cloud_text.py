"""Bounded Codex-only missing-text maintenance. No model client or API key.

Prepare before writing prose; apply only independently reviewed results. Stable IDs,
exact snapshots, one Sydney-day receipt, existing prompts and limits are preserved.
"""
import argparse
import copy
import json
from pathlib import Path
from cloud_gadgets import digest,logical_day,day_bounds
from content_store import DEFAULT,load,transaction,workflow_lock,validate
from git_content_workflow import publish_content
ORIGINAL=('id','ref','greek_text','english_translation','summary')


def prepare(document):
    day=logical_day()
    if day in document.get('text_receipts',{}):return None
    rows=sorted(document['passages'],key=lambda r:(r['ref_major'] is None,r['ref_major'] or 0,r['ref_minor'] is None,r['ref_minor'] or 0,r['ref']))
    limits={'english_translation':5,'summary':25};items=[]
    for row in rows:
        if row['greek_text'] is None:continue
        fields=[f for f in limits if limits[f] and row[f] is None and (f=='summary' or row['ref_major']!=0)]
        if fields:
            items.append({'original':{k:row[k] for k in ORIGINAL},'fields':fields})
            for field in fields:limits[field]-=1
    return {'day':day,'items':items} if items else None


def apply(document,result):
    if set(result)!={'request','candidates','review'}:raise ValueError('Invalid text result')
    req=result['request'];review=result['review']
    if set(req)!={'day','items'} or not req['items'] or len(req['items'])>30:raise ValueError('Invalid text request')
    day_bounds(req['day'])
    if req['day']>logical_day():raise ValueError('Future text day')
    if set(review)!={'reviewer','notes'} or any(not isinstance(v,str) or not v.strip() or len(v)>2000 for v in review.values()):raise ValueError('Independent text review required')
    counts={'english_translation':0,'summary':0};seen=set();candidates=result['candidates']
    if len(candidates)!=len(req['items']):raise ValueError('Candidate count changed')
    rows={r['id']:r for r in document['passages']}
    for item,candidate in zip(req['items'],candidates):
        if set(item)!={'original','fields'} or set(item['original'])!=set(ORIGINAL):raise ValueError('Unexpected text snapshot')
        original=item['original'];fields=item['fields']
        if original['id'] in seen or not fields or len(set(fields))!=len(fields):raise ValueError('Duplicate text assignment')
        seen.add(original['id'])
        if set(candidate)!={'id',*fields} or candidate['id']!=original['id']:raise ValueError('Text identity changed')
        row=rows.get(original['id'])
        if row is None:raise ValueError('Missing text passage')
        for f in fields:
            if f not in counts or original[f] is not None or (f=='english_translation' and row['ref_major']==0):raise ValueError('Only missing eligible text may be filled')
            counts[f]+=1
            if not isinstance(candidate[f],str) or not candidate[f].strip() or len(candidate[f])>64000:raise ValueError('Invalid text candidate')
    if counts['english_translation']>5 or counts['summary']>25:raise ValueError('Daily text limits exceeded')
    receipt={'request_sha256':digest(req),'result_sha256':digest(result),'review':review}
    prior=document.get('text_receipts',{}).get(req['day'])
    if prior is not None:
        if prior!=receipt:raise RuntimeError('Different text work already accepted for this Sydney day')
        for item,c in zip(req['items'],candidates):
            row=rows[c['id']]
            expected={k:(c[k] if k in item['fields'] else item['original'][k]) for k in ORIGINAL}
            if any(row[k]!=v for k,v in expected.items()):raise RuntimeError('Accepted text subsequently edited')
        return 'already-imported'
    for item in req['items']:
        if {k:rows[item['original']['id']][k] for k in ORIGINAL}!=item['original']:raise RuntimeError('Text changed since assignment')
    for item,c in zip(req['items'],candidates):
        for f in item['fields']:rows[c['id']][f]=c[f]
        if 'english_translation' in item['fields']:
            from datetime import datetime,timezone
            rows[c['id']]['translated_at']=datetime.now(timezone.utc).isoformat()
    document.setdefault('text_receipts',{})[req['day']]=receipt
    validate(document)
    return 'imported'


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('action',choices=['prepare','apply']);p.add_argument('--bundle',type=Path,required=True)
    a=p.parse_args()
    with workflow_lock():
        if a.action=='prepare':
            req=prepare(load())
            if req is None:print('No missing translation/summary work');return
            if a.bundle.exists():raise RuntimeError('Preserve existing bundle; refusing overwrite')
            a.bundle.write_text(json.dumps({'request':req,'candidates':[],'review':{}},ensure_ascii=False,indent=2)+'\n')
        else:
            with transaction() as doc:outcome=apply(doc,json.loads(a.bundle.read_text()))
            publish_content(DEFAULT)
            print(outcome+' text in Git; publication pending')

if __name__=='__main__':main()
