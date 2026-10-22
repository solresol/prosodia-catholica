"""Git-only queue transport; DB credentials remain on Raksasa.

Dedicated branch gadget-handoff contains only handoff/YYYY-MM-DD.json records.
Claims never expire automatically. Push rejection causes reload/revalidation.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import urlopen
from urllib.parse import urlsplit
from cloud_gadgets import apply, check_bundle, digest, logical_day, prepare, validate_result

REPOSITORY = 'solresol/prosodia-catholica'
BRANCH = 'gadget-handoff'


def run(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


def remote_identity(remote):
    """Accept only equivalent existing GitHub origins, preserving transport."""
    if remote.startswith('git@github.com:'):
        path = remote[len('git@github.com:'):]
        transport = 'ssh'
    else:
        url = urlsplit(remote)
        if url.hostname != 'github.com' or url.query or url.fragment or url.port is not None or url.password is not None:
            raise ValueError('Unexpected Git remote')
        if url.scheme == 'https' and url.username is None:
            transport = 'https'
        elif url.scheme == 'ssh' and url.username == 'git':
            transport = 'ssh'
        else:
            raise ValueError('Unsupported Git transport/identity')
        path = url.path.removeprefix('/')
    path = path.removesuffix('/')
    path = path.removesuffix('.git')
    if path != REPOSITORY:
        raise ValueError('Unexpected repository identity')
    return REPOSITORY, transport


def resolve_remote(cwd=None):
    # get-url expands configured insteadOf/pushInsteadOf; reject multiple origins
    # or a surprising push transport instead of silently switching protocols.
    fetch = run('git', 'remote', 'get-url', '--all', 'origin', cwd=cwd).stdout.splitlines()
    push = run('git', 'remote', 'get-url', '--push', '--all', 'origin', cwd=cwd).stdout.splitlines()
    if len(fetch) != 1 or len(push) != 1 or remote_identity(fetch[0]) != remote_identity(push[0]):
        raise ValueError('Origin fetch/push identity or transport differs')
    return push[0]


def check_record(record):
    if set(record) != {'mode', 'request', 'claim', 'result', 'ack'}:
        raise ValueError('Unexpected queue fields')
    if record['mode'] not in ('production', 'rehearsal'):
        raise ValueError('Invalid queue mode')
    check_bundle(record['request'], current=False)
    claim = record['claim']
    if claim is not None and (not isinstance(claim, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', claim)):
        raise ValueError('Invalid worker identifier')
    if record['result'] is not None:
        if claim is None:
            raise ValueError('Unclaimed result')
        validate_result(record['request'], record['result'], current=False)
    if record['ack'] is not None:
        if record['result'] is None or record['ack'] != digest(record['result']):
            raise ValueError('Invalid import acknowledgement')


class GitQueue:
    def __init__(self, remote=None, day=None, pending=False):
        self.remote = remote if remote is not None else resolve_remote(Path(__file__).resolve().parent)
        self.day = day or logical_day()
        self.pending = pending
        self.observed_ref = None
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', self.day):
            raise ValueError('Invalid day')

    def transact(self, update):
        # A separate temporary checkout never touches the source/production tree.
        for attempt in range(3):
            with tempfile.TemporaryDirectory(prefix='gadget-git-') as tmp:
                root = Path(tmp)
                run('git', 'init', '-q', cwd=root)
                run('git', 'remote', 'add', 'origin', self.remote, cwd=root)
                refs = run('git', 'ls-remote', '--exit-code', 'origin', 'refs/heads/'+BRANCH, cwd=root, check=False)
                if refs.returncode == 0:
                    run('git', 'fetch', '-q', 'origin', 'refs/heads/'+BRANCH, cwd=root)
                    run('git', 'checkout', '-q', '-b', BRANCH, 'FETCH_HEAD', cwd=root)
                    self.observed_ref = run('git', 'rev-parse', 'HEAD', cwd=root).stdout.strip()
                elif refs.returncode == 2:
                    self.observed_ref = None
                    run('git', 'checkout', '-q', '--orphan', BRANCH, cwd=root)
                else:
                    raise RuntimeError(refs.stderr)
                records = {}
                for name in run('git', 'ls-files', cwd=root).stdout.splitlines():
                    if not re.fullmatch(r'handoff/\d{4}-\d{2}-\d{2}\.json', name):
                        raise RuntimeError('Unexpected files on data branch; stop')
                    file = root / name
                    if file.is_symlink() or file.stat().st_size > 1500000:
                        raise ValueError('Invalid queue file')
                    record = json.loads(file.read_text())
                    check_record(record)
                    day = file.stem
                    if record['request']['day'] != day:
                        raise ValueError('Queue day/path mismatch')
                    records[day] = record
                day = self.day
                if self.pending:
                    outstanding = sorted(d for d, r in records.items() if r['mode'] == 'production' and r['ack'] is None)
                    if outstanding:
                        day = outstanding[0]
                path = root / 'handoff' / (day+'.json')
                record = records.get(day)
                before = copy.deepcopy(record)
                record, output = update(record)
                if record == before:
                    return output
                check_record(record)
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
                run('git', 'add', '--', str(path.relative_to(root)), cwd=root)
                run('git', 'commit', '-q', '-m', 'Gadget handoff '+day, cwd=root)
                pushed = run('git', 'push', 'origin', 'HEAD:refs/heads/'+BRANCH, cwd=root, check=False)
                if pushed.returncode == 0:
                    return output
                # No force push/rebase. Reload on rejected races; other failures stop.
                if '[rejected]' not in pushed.stderr:
                    raise RuntimeError(pushed.stderr)
        raise RuntimeError('Concurrent updates did not settle; retry after inspection')


def enqueue(record, request, *, rehearsal=False):
    if record is not None:
        return record, record['request']
    check_bundle(request, current=True)
    return {'mode': 'rehearsal' if rehearsal else 'production', 'request': request, 'claim': None, 'result': None, 'ack': None}, request


def claim(record, worker):
    if record is None:
        raise RuntimeError('No daily queue bundle')
    check_bundle(record['request'])
    if record['ack'] is not None:
        raise RuntimeError('Day already imported')
    if record['claim'] not in (None, worker):
        raise RuntimeError('Day claimed by another worker; no automatic takeover')
    record['claim'] = worker
    return record, record['result'] or record['request']


def submit(record, worker, result):
    if record is None or record['claim'] != worker:
        raise RuntimeError('Worker does not own daily claim')
    if record['result'] is not None:
        if record['result'] != result:
            raise RuntimeError('Result is immutable once submitted')
        return record, digest(result)
    validate_result(record['request'], result)
    for role in ('new', 'past'):
        if result[role] and result[role]['test_evidence']['review']['reviewer'] == worker:
            raise ValueError('Author cannot act as independent reviewer')
    record['result'] = result
    return record, digest(result)


def import_result(record, connection_factory, *, if_ready=False):
    if if_ready and (record is None or record['result'] is None or record['mode'] == 'rehearsal'):
        return record, 'pending'
    if record is None or record['result'] is None:
        raise RuntimeError('No tested result to import')
    if record['mode'] != 'production':
        raise RuntimeError('Rehearsal result cannot be imported; no DB access')
    if record['ack'] is not None:
        return record, 'already-acknowledged'
    conn = connection_factory()
    try:
        outcome = apply(conn, record['request'], record['result'])
    finally:
        conn.close()
    # apply has committed before acknowledgement is pushed. A crash is recovered
    # by the DB marker and full candidate comparison on the next import attempt.
    record['ack'] = digest(record['result'])
    return record, outcome


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('action', choices=['enqueue', 'claim', 'submit', 'import', 'import-ready', 'status'])
    parser.add_argument('--published-file', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--worker')
    parser.add_argument('--observation-file', type=Path, help='local import-read snapshot receipt')
    parser.add_argument('--rehearsal', action='store_true', help='enqueue only; result can never be imported')
    parser.add_argument('--day', help='Explicit Sydney request day; otherwise resume oldest pending production work')
    args = parser.parse_args()
    if args.observation_file and args.action not in ('import', 'import-ready'):
        parser.error('--observation-file is only for local import')
    # Verify the existing destination before any data-branch read/write.
    with urlopen('https://api.github.com/repos/solresol/prosodia-catholica', timeout=15) as response:
        info = json.load(response)
    if info.get('full_name') != 'solresol/prosodia-catholica' or info.get('private') is not False:
        raise RuntimeError('Unexpected remote identity or visibility')
    if args.day and args.action == 'enqueue':
        parser.error('enqueue assigns today or resumes pending work')
    if args.rehearsal and args.action != 'enqueue':
        parser.error('--rehearsal is only for enqueue')
    if args.action == 'submit' and args.bundle:
        submitted_day = json.loads(args.bundle.read_text())['day']
        if args.day and args.day != submitted_day:
            parser.error('--day disagrees with result bundle')
        args.day = submitted_day
    queue = GitQueue(day=args.day, pending=not args.day and not args.rehearsal)
    if args.action == 'enqueue':
        if not args.published_file:
            parser.error('--published-file must be the last successfully published passages.json')
        def update(record):
            if record is not None:
                return record, {'state': 'already-enqueued', 'day': record['request']['day'], 'mode': record['mode']}
            from db import get_connection
            conn = get_connection()
            try:
                request = prepare(conn, json.loads(args.published_file.read_text()), rehearsal=args.rehearsal)
            finally:
                conn.close()
            record, _ = enqueue(record, request, rehearsal=args.rehearsal)
            return record, {'state': 'enqueued', 'day': record['request']['day'], 'mode': record['mode'], 'request_sha256': digest(request)}
        output = queue.transact(update)
    elif args.action == 'claim':
        if not args.worker or not args.bundle:
            parser.error('claim requires stable --worker and ignored --bundle path')
        output = queue.transact(lambda r: claim(r, args.worker))
        args.bundle.parent.mkdir(parents=True, exist_ok=True)
        if args.bundle.exists() and json.loads(args.bundle.read_text()) != output:
            raise RuntimeError('Local bundle differs; preserve edits and inspect before retry')
        args.bundle.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')
        output = 'claimed bundle: '+str(args.bundle)
    elif args.action == 'submit':
        if not args.worker or not args.bundle:
            parser.error('submit requires --worker and --bundle')
        result = json.loads(args.bundle.read_text())
        output = queue.transact(lambda r: submit(r, args.worker, result))
    elif args.action in ('import', 'import-ready'):
        from db import get_connection
        output = queue.transact(lambda r: import_result(r, get_connection, if_ready=args.action == 'import-ready'))
        if args.observation_file:
            args.observation_file.write_text(json.dumps({'observed_ref': queue.observed_ref, 'outcome': output})+'\n')
    else:
        def status(record):
            if record is None:
                raise RuntimeError('No daily queue bundle')
            return record, {'day': record['request']['day'], 'mode': record['mode'], 'claimed': record['claim'], 'result': record['result'] is not None, 'ack': record['ack']}
        output = queue.transact(status)
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
