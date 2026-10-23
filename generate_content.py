"""Maintain public translations/summaries in the authoritative Git snapshot.

No API client/key is loaded if there is no pending work. Errors are reported locally,
never persisted into public content. Caller must commit/push before publication.
"""
import argparse
from datetime import datetime, timezone
import time
from content_store import transaction, workflow_lock


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('kind',choices=['translation','summary'])
    p.add_argument('--limit',type=int,default=5)
    p.add_argument('--delay',type=float,default=1)
    args=p.parse_args()
    field='english_translation' if args.kind=='translation' else 'summary'
    failed=False
    with workflow_lock(), transaction() as doc:
        rows=[r for r in doc['passages'] if r[field] is None and r['greek_text'] is not None and (args.kind=='summary' or r['ref_major']!=0)]
        rows.sort(key=lambda r:(r['ref_major'] is None,r['ref_major'] or 0,r['ref_minor'] is None,r['ref_minor'] or 0,r['ref']))
        rows=rows[:max(0,args.limit)]
        if not rows:
            print('No pending '+args.kind); return
        from openai import OpenAI
        from openai_utils import load_openai_api_key
        if args.kind=='translation':
            from translate_lines import translate_one as generate, _load_model
        else:
            from summarize_lines import summarize_one as generate, _load_model
        client=OpenAI(api_key=load_openai_api_key()); model=_load_model("gpt-6-sol" if args.kind=="translation" else "gpt-5.6-luna")
        for row in rows:
            try:
                text,_=generate(client,model=model,greek_text=row['greek_text'])
                row[field]=text
                if args.kind=='translation': row['translated_at']=datetime.now(timezone.utc).isoformat()
            except Exception:
                failed=True
                print('Generation failed for passage',row['id'])
            if args.delay>0: time.sleep(args.delay)
    if failed: raise RuntimeError('Some generation failed; successful content retained, inspect local diagnostics')



if __name__=='__main__': main()
