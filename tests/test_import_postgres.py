"""Opt-in tiny integration tests; refuse production/network databases.

Set PROSODIA_TEST_DSN only to a disposable Unix-socket DB under /tmp named
prosodia_disposable. This suite drops/recreates cathpros_lines in that DB.
"""
import os
import unittest
try:
    import psycopg2
except ImportError:
    psycopg2 = None
from test_handoff import request, result
import cloud_gadgets as gadgets

DSN = os.environ.get('PROSODIA_TEST_DSN')


@unittest.skipUnless(DSN and psycopg2, 'requires isolated disposable PostgreSQL')
class ImportPostgresTests(unittest.TestCase):
    def connect(self):
        conn = psycopg2.connect(DSN, connect_timeout=3)
        if not conn.info.host.startswith('/tmp/prosodia-pg-test-') or conn.info.dbname != 'prosodia_disposable':
            conn.close()
            raise RuntimeError('Refusing non-disposable database')
        return conn

    def setUp(self):
        self.conn = self.connect()
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS cathpros_lines')
                cur.execute('''CREATE TABLE cathpros_lines (
                    id integer PRIMARY KEY, ref text, greek_text text, english_translation text,
                    gadget_html text, gadget_css text, gadget_js text, gadget_model text,
                    gadget_generated_at timestamptz, gadget_error text,
                    gadget_last_attempted_at timestamptz, gadget_attempts integer DEFAULT 0)''')
                for role in ('new', 'past'):
                    row = request()[role]['original']
                    cur.execute('INSERT INTO cathpros_lines ('+', '.join(gadgets.FIELDS)+') VALUES ('+', '.join(['%s']*len(gadgets.FIELDS))+')', tuple(row[k] for k in gadgets.FIELDS))
        self.req = request()
        self.res = result(self.req)

    def tearDown(self):
        self.conn.close()

    def scalar(self, query):
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchone()[0]

    def test_commit_and_marker_recovery_without_second_update(self):
        self.assertEqual(gadgets.apply(self.conn, self.req, self.res), 'imported')
        self.assertEqual(self.scalar('SELECT gadget_attempts FROM cathpros_lines WHERE id=1'), 1)
        self.assertEqual(gadgets.apply(self.conn, self.req, self.res), 'already-imported')
        self.assertEqual(self.scalar('SELECT gadget_attempts FROM cathpros_lines WHERE id=1'), 1)

    def test_second_write_constraint_failure_rolls_back_new_gadget(self):
        self.res['past']['candidate']['css'] = 'body { color: black; }'
        self.res['past']['test_evidence']['candidate_sha256'] = gadgets.digest(self.res['past']['candidate'])
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute('ALTER TABLE cathpros_lines ADD CONSTRAINT reject_past_css CHECK (id<>2 OR gadget_css IS NULL)')
        with self.assertRaises(psycopg2.errors.CheckViolation):
            gadgets.apply(self.conn, self.req, self.res)
        self.assertIsNone(self.scalar('SELECT gadget_html FROM cathpros_lines WHERE id=1'))
        self.assertEqual(self.scalar('SELECT SUM(gadget_attempts) FROM cathpros_lines'), 0)

    def test_stale_past_row_rolls_back_prior_new_write(self):
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE cathpros_lines SET greek_text='edited' WHERE id=2")
        with self.assertRaisesRegex(RuntimeError, 'changed since prepare'):
            gadgets.apply(self.conn, self.req, self.res)
        self.assertIsNone(self.scalar('SELECT gadget_html FROM cathpros_lines WHERE id=1'))
        self.assertEqual(self.scalar('SELECT greek_text FROM cathpros_lines WHERE id=2'), 'edited')

    def test_shared_lock_rejects_concurrent_import_then_allows_retry(self):
        other = self.connect()
        try:
            with other.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(18482, 716)')
            with self.assertRaisesRegex(RuntimeError, 'Another cloud import'):
                gadgets.apply(self.conn, self.req, self.res)
            self.assertIsNone(self.scalar('SELECT gadget_html FROM cathpros_lines WHERE id=1'))
            other.rollback()
            self.assertEqual(gadgets.apply(self.conn, self.req, self.res), 'imported')
        finally:
            other.close()

    def test_legacy_guard_but_cloud_import_does_not_block_next_assignment(self):
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO cathpros_lines(id,gadget_generated_at,gadget_model) VALUES (3, now(), 'legacy-model')")
        with self.assertRaisesRegex(RuntimeError, 'already generated'):
            gadgets.apply(self.conn, self.req, self.res)
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE cathpros_lines SET gadget_model='codex-cloud:other-assignment' WHERE id=3")
        self.assertEqual(gadgets.apply(self.conn, self.req, self.res), 'imported')


if __name__ == '__main__':
    unittest.main()
