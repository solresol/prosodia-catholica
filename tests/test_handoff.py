import copy
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cloud_gadgets as gadgets
import git_gadget_handoff as handoff


def request():
    def item(n, past=False):
        return {'original': dict(id=n, ref=str(n), greek_text='α', english_translation='alpha', gadget_html='<input>' if past else None, gadget_css=None, gadget_js='void 0' if past else None), 'candidate': dict(html='<input>' if past else '', css='', js='void 0' if past else '')}
    return {'day': gadgets.logical_day(), 'new': item(1), 'past': item(2, True)}


def result(req):
    res = copy.deepcopy(req)
    for role in ('new', 'past'):
        res[role]['candidate'] = dict(html='<input>', css='', js='void 0')
        res[role]['test_evidence'] = dict(candidate_sha256=gadgets.digest(res[role]['candidate']), browser='Chromium', interaction='Greek input and empty/reset', expected='α', actual='α', assertions=[dict(case=c, expected='α', actual='α', passed=True) for c in ('Greek input', 'second input', 'reset')], harness='await page.locator("input").fill("α");', review=dict(reviewer='independent-test-reviewer', notes='Reviewed harness and assertions'))
    return res


class FakeCursor:
    def __init__(self, request, *, marker=None, changed=False, duplicate=False):
        self.rows = {i['original']['id']: dict(i['original'], gadget_model=None, gadget_generated_at=None) for i in (request['new'], request['past'])}
        if changed:
            self.rows[1]['greek_text'] = 'edited'
        if marker:
            self.rows[1].update(gadget_html='<input>', gadget_css='', gadget_js='void 0', gadget_model=marker)
        self.duplicate = duplicate
        self.updates = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params=None):
        self.query = query
        self.params = params
        if query.startswith('UPDATE'):
            self.updates.append(params)
    def fetchone(self):
        if 'pg_try_advisory' in self.query: return (True,)
        if 'FOR UPDATE' in self.query:
            r = self.rows[self.params[0]]
            return tuple(r[k] for k in (*gadgets.FIELDS, 'gadget_model', 'gadget_generated_at'))
        if self.query.startswith('SELECT 1'): return (1,) if self.duplicate else None
        raise AssertionError(self.query)


class FakeConnection:
    def __init__(self, cursor): self.c = cursor; self.committed = False
    def __enter__(self): return self
    def __exit__(self, typ, *args): self.committed = typ is None
    def cursor(self): return self.c
    def close(self): pass


class HandoffTests(unittest.TestCase):
    def test_verified_remote_normalization_preserves_https(self):
        from types import SimpleNamespace
        for remote in ('https://github.com/solresol/prosodia-catholica.git', 'https://github.com/solresol/prosodia-catholica', 'https://github.com/solresol/prosodia-catholica.git/'):
            self.assertEqual(handoff.remote_identity(remote), ('solresol/prosodia-catholica', 'https'))
            with patch.object(handoff, 'run', return_value=SimpleNamespace(stdout=remote+'\n')):
                self.assertEqual(handoff.resolve_remote(), remote)
        for remote in ('git@github.com:solresol/prosodia-catholica.git', 'ssh://git@github.com/solresol/prosodia-catholica.git'):
            self.assertEqual(handoff.remote_identity(remote)[1], 'ssh')
        for remote in ('https://github.com/other/prosodia-catholica', 'https://github.com.evil/solresol/prosodia-catholica', 'https://token@github.com/solresol/prosodia-catholica', 'http://github.com/solresol/prosodia-catholica', 'https://github.com/solresol/prosodia-catholica?x=1', 'ssh://git@github.com:22/solresol/prosodia-catholica'):
            with self.assertRaises(ValueError): handoff.remote_identity(remote)
        with patch.object(handoff, 'run', side_effect=[SimpleNamespace(stdout='https://github.com/solresol/prosodia-catholica.git\n'), SimpleNamespace(stdout='git@github.com:solresol/prosodia-catholica.git\n')]):
            with self.assertRaises(ValueError): handoff.resolve_remote()

    def test_result_day_binding_evidence_and_midnight_retry(self):
        req = request(); res = result(req)
        wrong = copy.deepcopy(res); wrong['day'] = '2000-01-01'
        with self.assertRaises(ValueError): gadgets.validate_result(req, wrong, current=False)
        wrong = copy.deepcopy(res); del wrong['new']['test_evidence']['assertions']
        with self.assertRaises(ValueError): gadgets.validate_result(req, wrong)
        record, _ = handoff.enqueue(None, req)
        record, _ = handoff.claim(record, 'worker')
        bad = copy.deepcopy(res); bad['new']['test_evidence']['candidate_sha256'] = '0'*64
        with self.assertRaises(ValueError): handoff.submit(record, 'worker', bad)
        bad = copy.deepcopy(res); bad['new']['test_evidence']['review']['reviewer'] = 'worker'
        with self.assertRaises(ValueError): handoff.submit(record, 'worker', bad)
        record, _ = handoff.submit(record, 'worker', res)
        with patch.object(gadgets, 'logical_day', return_value='2099-01-01'):
            _, returned = handoff.submit(record, 'worker', res)
            self.assertEqual(returned, gadgets.digest(res))

    def test_import_observation_is_the_read_snapshot_not_its_ack_commit(self):
        import contextlib
        import io
        import types
        with tempfile.TemporaryDirectory() as d:
            bare = Path(d) / 'remote.git'
            subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True)
            env = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid')
            with patch.dict(os.environ, env):
                req = request()
                queue = handoff.GitQueue(str(bare))
                queue.transact(lambda r: handoff.enqueue(r, req))
                queue.transact(lambda r: handoff.claim(r, 'worker'))
                queue.transact(lambda r: handoff.submit(r, 'worker', result(req)))
                before = subprocess.check_output(['git', '--git-dir', str(bare), 'rev-parse', handoff.BRANCH], text=True).strip()
                receipt = Path(d) / 'observation.json'
                cls = handoff.GitQueue
                def local_queue(**kwargs):
                    return cls(remote=str(bare), **kwargs)
                public_info = io.StringIO(json.dumps({'full_name':'solresol/prosodia-catholica','private':False}))
                with patch.object(handoff, 'GitQueue', side_effect=local_queue), patch.object(handoff, 'urlopen', return_value=public_info), patch.dict(sys.modules, {'db':types.SimpleNamespace(get_connection=lambda:FakeConnection(FakeCursor(req)))}), patch.object(sys, 'argv', ['git_gadget_handoff.py','import-ready','--observation-file',str(receipt)]), contextlib.redirect_stdout(io.StringIO()):
                    handoff.main()
                observed = json.loads(receipt.read_text())
                after = subprocess.check_output(['git', '--git-dir', str(bare), 'rev-parse', handoff.BRANCH], text=True).strip()
                self.assertEqual(observed, {'observed_ref':before,'outcome':'imported'})
                self.assertNotEqual(before, after)  # ack push is not a consumed input

    def test_sydney_dst_and_logical_midnight(self):
        start, end = gadgets.day_bounds('2026-10-04')
        self.assertEqual(end.timestamp() - start.timestamp(), 23*3600)
        start, end = gadgets.day_bounds('2026-04-05')
        self.assertEqual(end.timestamp() - start.timestamp(), 25*3600)
        with patch.object(gadgets, 'datetime') as dt:
            dt.now.return_value = datetime(2026, 10, 23, 0, 15, tzinfo=gadgets.SYDNEY)
            self.assertEqual(gadgets.logical_day(), '2026-10-23')
            dt.now.assert_called_once_with(gadgets.SYDNEY)

    def test_claim_immutable_result_and_fields(self):
        req = request()
        record, _ = handoff.enqueue(None, req)
        record, _ = handoff.claim(record, 'opaque-worker')
        with self.assertRaises(RuntimeError): handoff.claim(record, 'another-worker')
        res = result(req)
        record, _ = handoff.submit(record, 'opaque-worker', res)
        handoff.submit(record, 'opaque-worker', res)
        altered = copy.deepcopy(res)
        altered['new']['candidate']['css'] = 'body{}'
        with self.assertRaises(RuntimeError): handoff.submit(record, 'opaque-worker', altered)
        altered = copy.deepcopy(res)
        altered['new']['original']['greek_text'] = 'changed'
        with self.assertRaises(ValueError): gadgets.validate_result(req, altered)
        altered = copy.deepcopy(req)
        altered['secret'] = 'do not transmit'
        with self.assertRaises(ValueError): gadgets.check_bundle(altered)

    def test_apply_atomic_checks_and_commit_ack_recovery(self):
        req = request(); res = result(req)
        cursor = FakeCursor(req); conn = FakeConnection(cursor)
        self.assertEqual(gadgets.apply(conn, req, res), 'imported')
        self.assertTrue(conn.committed)
        self.assertEqual(len(cursor.updates), 1)  # unchanged past gadget preserved
        for flags in ({'changed': True}, {'duplicate': True}):
            cursor = FakeCursor(req, **flags); conn = FakeConnection(cursor)
            with self.assertRaises(RuntimeError): gadgets.apply(conn, req, res)
            self.assertFalse(conn.committed)
            self.assertFalse(cursor.updates)
        cursor = FakeCursor(req, marker='codex-cloud:'+gadgets.digest(req))
        conn = FakeConnection(cursor)
        self.assertEqual(gadgets.apply(conn, req, res), 'already-imported')
        self.assertFalse(cursor.updates)
        record, _ = handoff.enqueue(None, req)
        record, _ = handoff.claim(record, 'worker')
        record, _ = handoff.submit(record, 'worker', res)
        record, outcome = handoff.import_result(record, lambda: conn)
        self.assertEqual(record['ack'], gadgets.digest(res))
        self.assertEqual(outcome, 'already-imported')
        _, outcome = handoff.import_result(record, lambda: self.fail('acknowledged import must not access DB'))
        self.assertEqual(outcome, 'already-acknowledged')

    def test_public_snapshot_gate_and_post_midnight_ack(self):
        req = request()
        class Cursor(FakeCursor):
            def fetchall(self):
                return [tuple(self.rows[n][k] for k in gadgets.FIELDS) for n in (1, 2)]
        c = Cursor(req)
        published = [req[r]['original'] for r in ('new', 'past')]
        bundle = gadgets.prepare(FakeConnection(c), published)
        self.assertEqual(bundle['new']['original'], published[0])
        changed_public = copy.deepcopy(published)
        changed_public[0]['english_translation'] = 'not the DB text'
        with self.assertRaises(ValueError): gadgets.prepare(FakeConnection(c), changed_public)
        res = result(req)
        with patch.object(gadgets, 'logical_day', return_value='2099-01-01'):
            c = FakeCursor(req, marker='codex-cloud:'+gadgets.digest(req))
            self.assertEqual(gadgets.apply(FakeConnection(c), req, res), 'already-imported')
            c = FakeCursor(req)
            self.assertEqual(gadgets.apply(FakeConnection(c), req, res), 'imported')
            self.assertEqual(len(c.updates), 1)

    def test_delayed_pending_work_is_resumed_instead_of_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            bare = Path(d) / 'remote.git'
            subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True)
            env = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid')
            req = request()
            with patch.dict(os.environ, env):
                handoff.GitQueue(str(bare)).transact(lambda r: handoff.enqueue(r, req))
                with patch.object(gadgets, 'logical_day', return_value='2099-01-01'), patch.object(handoff, 'logical_day', return_value='2099-01-01'):
                    queue = handoff.GitQueue(str(bare), pending=True)
                    # Next day's enqueue receives the old record and must not query DB.
                    old = queue.transact(lambda r: (r, r))
                    self.assertEqual(old['request'], req)
                    queue.transact(lambda r: handoff.claim(r, 'late-worker'))
                    queue.transact(lambda r: handoff.submit(r, 'late-worker', result(req)))
                    outcome = queue.transact(lambda r: handoff.import_result(r, lambda: FakeConnection(FakeCursor(req))))
                    self.assertEqual(outcome, 'imported')
                    state = handoff.GitQueue(str(bare), day=req['day']).transact(lambda r: (r, r))
                    self.assertIsNotNone(state['ack'])
                    names = subprocess.check_output(['git', '--git-dir', str(bare), 'ls-tree', '-r', '--name-only', handoff.BRANCH], text=True).splitlines()
                    self.assertEqual(names, ['handoff/'+req['day']+'.json'])

    def test_import_ready_does_not_open_db_without_a_production_result(self):
        fail = lambda: self.fail('Pending/rehearsal must not access DB')
        self.assertEqual(handoff.import_result(None, fail, if_ready=True), (None, 'pending'))
        record, _ = handoff.enqueue(None, request())
        _, status = handoff.import_result(record, fail, if_ready=True)
        self.assertEqual(status, 'pending')
        record, _ = handoff.enqueue(None, request(), rehearsal=True)
        record, _ = handoff.claim(record, 'worker')
        record, _ = handoff.submit(record, 'worker', result(record['request']))
        _, status = handoff.import_result(record, fail, if_ready=True)
        self.assertEqual(status, 'pending')

    def test_rehearsal_never_accesses_import_db(self):
        req = request()
        record, _ = handoff.enqueue(None, req, rehearsal=True)
        record, _ = handoff.claim(record, 'worker')
        record, _ = handoff.submit(record, 'worker', result(req))
        with self.assertRaises(RuntimeError):
            handoff.import_result(record, lambda: self.fail('Rehearsal must not access DB'))
        self.assertIsNone(record['ack'])

    def test_git_roundtrip_and_racing_claim(self):
        with tempfile.TemporaryDirectory() as d:
            bare = Path(d) / 'remote.git'
            subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True)
            env = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.invalid')
            with patch.dict(os.environ, env):
                queue = handoff.GitQueue(str(bare))
                req = request()
                queue.transact(lambda r: handoff.enqueue(r, req))
                # Second worker wins between first worker's read and push.
                raced = False
                def race(record):
                    nonlocal raced
                    if not raced:
                        raced = True
                        handoff.GitQueue(str(bare)).transact(lambda r: handoff.claim(r, 'winner'))
                    return handoff.claim(record, 'loser')
                with self.assertRaises(RuntimeError): queue.transact(race)
                claimed = queue.transact(lambda r: handoff.claim(r, 'winner'))
                self.assertEqual(claimed, req)
                res = result(req)
                queue.transact(lambda r: handoff.submit(r, 'winner', res))
                queue.transact(lambda r: handoff.import_result(r, lambda: FakeConnection(FakeCursor(req))))
                state = queue.transact(lambda r: (r, r))
                self.assertEqual(state['ack'], gadgets.digest(res))
                # Re-enqueue preserves exactly the original randomly assigned work.
                other = request(); other['new']['original']['id'] = 99
                self.assertEqual(queue.transact(lambda r: handoff.enqueue(r, other)), req)
                names = subprocess.check_output(['git', '--git-dir', str(bare), 'ls-tree', '-r', '--name-only', handoff.BRANCH], text=True).splitlines()
                self.assertEqual(names, ['handoff/'+gadgets.logical_day()+'.json'])


if __name__ == '__main__':
    unittest.main()
