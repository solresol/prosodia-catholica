"""Bounded public gadget bundles. Database operations run only on Raksasa."""
from __future__ import annotations
import argparse
from datetime import datetime, time, timedelta
import hashlib
import json
from pathlib import Path
import secrets
from zoneinfo import ZoneInfo
from gadget_validation import _validate_gadget

SYDNEY = ZoneInfo('Australia/Sydney')
FIELDS = ('id', 'ref', 'greek_text', 'english_translation', 'gadget_html', 'gadget_css', 'gadget_js')
PARTS = ('html', 'css', 'js')


def logical_day():
    return datetime.now(SYDNEY).date().isoformat()


def day_bounds(day):
    start = datetime.combine(datetime.fromisoformat(day).date(), time(), SYDNEY)
    return start, start + timedelta(days=1)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_bundle(bundle, *, tested=False, current=False):
    if set(bundle) != {'day', 'new', 'past'} or (current and bundle['day'] != logical_day()):
        raise ValueError('Invalid bundle fields or requested current Sydney day')
    day_bounds(bundle['day'])
    if bundle['day'] > logical_day():
        raise ValueError('Future Sydney day')
    if bundle['new'] is None:
        raise ValueError('No new candidate')
    for role in ('new', 'past'):
        item = bundle[role]
        if item is None:
            continue
        if set(item) != ({'original', 'candidate', 'test_evidence'} if tested else {'original', 'candidate'}):
            raise ValueError('Unexpected bundle fields')
        row = item['original']
        if set(row) != set(FIELDS) or type(row['id']) is not int:
            raise ValueError('Unexpected passage fields')
        for key in FIELDS[1:]:
            if row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > 64000):
                raise ValueError('Passage field too large or not text')
        c = item['candidate']
        if set(c) != set(PARTS) or any(not isinstance(c[k], str) or len(c[k]) > 64000 for k in PARTS):
            raise ValueError('Unexpected candidate fields or size')
        if tested:
            evidence = item['test_evidence']
            if set(evidence) != {'browser', 'interaction', 'expected', 'actual'} or any(not isinstance(v, str) or not v.strip() or len(v) > 2000 for v in evidence.values()):
                raise ValueError('Bounded browser and behavioral evidence required')
            if evidence['expected'] != evidence['actual']:
                raise ValueError('Expected/actual mismatch')
            if not c['html'].strip() or not c['js'].strip():
                raise ValueError('Empty gadget')
            _validate_gadget(**c)
    if bundle['past'] and bundle['past']['original']['id'] == bundle['new']['original']['id']:
        raise ValueError('New and past must differ')
    if bundle['new']['original']['gadget_html'] is not None:
        raise ValueError('New passage already has a gadget')
    if bundle['past'] and bundle['past']['original']['gadget_html'] is None:
        raise ValueError('Past passage has no gadget')
    if len(json.dumps(bundle).encode()) > 512000:
        raise ValueError('Bundle exceeds 512KB')


def validate_bundle(bundle):
    check_bundle(bundle, tested=True)


def validate_result(request, result, *, current=False):
    check_bundle(request, current=current)
    check_bundle(result, tested=True, current=current)
    for role in ('new', 'past'):
        if (request[role] is None) != (result[role] is None):
            raise ValueError('Result changed assigned passages')
        if request[role] and request[role]['original'] != result[role]['original']:
            raise ValueError('Result changed original snapshot')


def prepare(conn, published, *, rehearsal=False):
    # Only queue snapshots already present in the existing site publication.
    public = {r['id']: {k: r[k] for k in FIELDS} for r in published}
    with conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '10s'")
            cur.execute('SELECT 1 FROM cathpros_lines WHERE gadget_generated_at >= %s AND gadget_generated_at < %s LIMIT 1', day_bounds(logical_day()))
            if cur.fetchone() and not rehearsal:
                raise RuntimeError('A gadget already generated this Sydney day; no duplicate queue')
            cur.execute('SELECT ' + ', '.join(FIELDS) + " FROM cathpros_lines WHERE english_translation IS NOT NULL AND greek_text IS NOT NULL AND ref <> 'E' AND COALESCE(ref_major,1) <> 0 ORDER BY gadget_attempts, id")
            rows = [dict(zip(FIELDS, row)) for row in cur.fetchall()]
    eligible = [r for r in rows if public.get(r['id']) == r]
    new = next((r for r in eligible if r['gadget_html'] is None), None)
    past = [r for r in eligible if r['gadget_html'] is not None]
    def wrap(row):
        return None if row is None else {'original': row, 'candidate': {k: row['gadget_'+k] or '' for k in PARTS}}
    bundle = {'day': logical_day(), 'new': wrap(new), 'past': wrap(secrets.choice(past)) if past else None}
    check_bundle(bundle, current=True)
    return bundle


def apply(conn, request, result):
    validate_result(request, result, current=False)
    marker = 'codex-cloud:' + digest(request)
    start, end = day_bounds(logical_day())
    with conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '10s'")
            cur.execute("SET LOCAL lock_timeout = '2s'")
            cur.execute('SELECT pg_try_advisory_xact_lock(18482, 716)')
            if not cur.fetchone()[0]:
                raise RuntimeError('Another cloud import is running')
            # Lock in ID order; inspect the marker to recover a commit-before-ack crash.
            current = {}
            items = [result[r] for r in ('new', 'past') if result[r]]
            for item in sorted(items, key=lambda i: i['original']['id']):
                cur.execute('SELECT ' + ', '.join(FIELDS) + ', gadget_model, gadget_generated_at FROM cathpros_lines WHERE id=%s FOR UPDATE', (item['original']['id'],))
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError('Passage disappeared')
                current[item['original']['id']] = dict(zip((*FIELDS, 'gadget_model', 'gadget_generated_at'), row))
            def matches(item):
                r = current[item['original']['id']]
                return all(r[k] == item['original'][k] for k in ('id', 'ref', 'greek_text', 'english_translation')) and all((r['gadget_'+k] or '') == item['candidate'][k] for k in PARTS)
            new = result['new']
            nr = current[new['original']['id']]
            if nr['gadget_model'] == marker:
                if not all(matches(i) for i in items):
                    raise RuntimeError('Previously imported data was subsequently edited; inspect manually')
                return 'already-imported'
            cur.execute('SELECT 1 FROM cathpros_lines WHERE gadget_generated_at >= %s AND gadget_generated_at < %s LIMIT 1', (start, end))
            if cur.fetchone():
                raise RuntimeError('A gadget already generated this Sydney day; inspect legacy/cloud overlap')
            for item in items:
                row = current[item['original']['id']]
                if {k: row[k] for k in FIELDS} != item['original']:
                    raise RuntimeError('Passage changed since prepare; refusing overwrite')
                c = item['candidate']
                if item is new or any(c[k] != (row['gadget_'+k] or '') for k in PARTS):
                    cur.execute('UPDATE cathpros_lines SET gadget_html=%s, gadget_css=%s, gadget_js=%s, gadget_generated_at=now(), gadget_model=%s, gadget_error=NULL, gadget_last_attempted_at=now(), gadget_attempts=gadget_attempts+1 WHERE id=%s', (c['html'], c['css'], c['js'], marker, row['id']))
    return 'imported'


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('action', choices=['validate'])
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    validate_bundle(json.loads(args.bundle.read_text()))
    print('validate: complete (no DB access)')


if __name__ == '__main__':
    main()
