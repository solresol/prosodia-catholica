"""Export a small daily work bundle; atomically publish tested Codex edits.

No model API calls, schema changes, or deployment. JSON bundles stay in exports/.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets

FIELDS = ('id', 'ref', 'greek_text', 'english_translation', 'gadget_html', 'gadget_css', 'gadget_js')


def validate_bundle(bundle):
    if bundle['day'] != datetime.now(timezone.utc).date().isoformat():
        raise ValueError('Bundle is not from today (UTC); prepare again')
    for role in ('new', 'past'):
        item = bundle.get(role)
        if item is None:
            if role == 'new':
                raise ValueError('No new candidate')
            continue
        evidence = item.get('test_evidence', {})
        if not all(evidence.get(k) for k in ('browser', 'interaction', 'expected', 'actual')):
            raise ValueError(f'{role}: browser and behavioral evidence required')
        if evidence['expected'] != evidence['actual']:
            raise ValueError(f'{role}: expected/actual mismatch')
        candidate = item['candidate']
        if not candidate['html'].strip() or not candidate['js'].strip():
            raise ValueError('Empty gadget')
        # Shared validation has no DB or model dependencies.
        from gadget_validation import _validate_gadget
        _validate_gadget(**candidate)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('action', choices=['prepare', 'validate', 'apply'])
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    if args.action == 'validate':
        validate_bundle(json.loads(args.bundle.read_text()))
        print('validate: complete (no DB access)')
        return
    from db import get_connection
    from psycopg2.extras import RealDictCursor
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '10s'")
                cur.execute("SET LOCAL lock_timeout = '2s'")
                # Same lock across cloud workers; transaction contains no model/browser waits.
                cur.execute('SELECT pg_try_advisory_xact_lock(18482, 716) AS locked')
                if not cur.fetchone()['locked']:
                    raise RuntimeError('Another cloud publish is running')
                cur.execute("SELECT 1 FROM cathpros_lines WHERE gadget_generated_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' LIMIT 1")
                if cur.fetchone():
                    raise RuntimeError('A gadget was already generated today; do not duplicate')
                if args.action == 'prepare':
                    if args.bundle.exists():
                        raise RuntimeError('Refusing to overwrite existing work bundle')
                    columns = ', '.join(FIELDS)
                    cur.execute(f"SELECT {columns} FROM cathpros_lines WHERE gadget_html IS NULL AND english_translation IS NOT NULL AND greek_text IS NOT NULL AND ref <> 'E' AND COALESCE(ref_major,1) <> 0 ORDER BY gadget_attempts, id LIMIT 1")
                    new = cur.fetchone()
                    # Small corpus (~544 rows); avoid ORDER BY random().
                    cur.execute('SELECT id FROM cathpros_lines WHERE gadget_html IS NOT NULL ORDER BY id')
                    ids = [r['id'] for r in cur.fetchall()]
                    past = None
                    if ids:
                        cur.execute(f'SELECT {columns} FROM cathpros_lines WHERE id = %s', (secrets.choice(ids),))
                        past = cur.fetchone()
                    def wrap(row):
                        return None if row is None else {'original': dict(row), 'candidate': dict(zip(('html','css','js'), (row[k] or '' for k in ('gadget_html','gadget_css','gadget_js'))))}
                    bundle = {'day': datetime.now(timezone.utc).date().isoformat(), 'new': wrap(new), 'past': wrap(past)}
                    args.bundle.parent.mkdir(parents=True, exist_ok=True)
                    with args.bundle.open('x') as f:
                        json.dump(bundle, f, ensure_ascii=False, indent=2)
                else:
                    bundle = json.loads(args.bundle.read_text())
                    validate_bundle(bundle)
                    for role in ('new', 'past'):
                        item = bundle.get(role)
                        if item is None:
                            continue
                        original = item['original']
                        cur.execute('SELECT ' + ', '.join(FIELDS) + ' FROM cathpros_lines WHERE id = %s FOR UPDATE', (original['id'],))
                        if dict(cur.fetchone() or {}) != original:
                            raise RuntimeError('Passage changed since prepare; refusing overwrite')
                        c = item['candidate']
                        if role == 'new' or any(c[k] != (original['gadget_'+k] or '') for k in ('html','css','js')):
                            cur.execute("UPDATE cathpros_lines SET gadget_html=%s, gadget_css=%s, gadget_js=%s, gadget_generated_at=now(), gadget_model='codex-cloud', gadget_error=NULL, gadget_last_attempted_at=now(), gadget_attempts=gadget_attempts+1 WHERE id=%s", (c['html'], c['css'], c['js'], original['id']))
        print(f'{args.action}: complete')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
