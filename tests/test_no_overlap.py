import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class NoOverlapTests(unittest.TestCase):
    def test_full_static_build_uses_only_core_db_and_preserves_content_urls(self):
        row = dict(id=241, ref='1.244', ref_major=1, ref_minor=244,
                   greek_text='ἥρως <καί>', english_translation='Hero & accent', summary='Example',
                   gadget_html='<input id="word">', gadget_css='', gadget_js='void 0', translated_at=None)
        queries = []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, query, params=None):
                queries.append(query)
                for forbidden in ('stephanos','overlap','assembled_lemmas','lemma_source_text_versions'):
                    if forbidden in query.lower(): raise AssertionError(query)
            def fetchall(self): return [row]
            def fetchone(self):
                if len(queries)==2: return dict(total=1, translated=1, summarized=1)
                return dict(total_all=1,total_non_e=1,total_translatable=1,translated_done=1,summarized_done=1,gadget_done=1)
        class Connection:
            closed = False
            def cursor(self): return Cursor()
            def close(self): self.closed=True
        conn = Connection()
        spec = importlib.util.spec_from_file_location('core_site_only', ROOT/'generate_site.py')
        site = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'db':types.SimpleNamespace(get_connection=lambda **kwargs:conn),
                                     'stephanos_db':None, 'config':types.ModuleType('config')}):
            spec.loader.exec_module(site)
            with tempfile.TemporaryDirectory() as d:
                out=Path(d)
                analysis=out/'analysis';analysis.mkdir()
                retired=('index.html','coverage.html','reuse_predictors_words.html','reuse_predictors_ngrams_2_3.html')
                for name in retired: (analysis/name).write_text('old overlap output')
                (analysis/'unrelated.txt').write_text('preserve')
                with patch.object(sys,'argv',['generate_site.py','--database','--out',str(out)]), contextlib.redirect_stdout(io.StringIO()):
                    site.main()
                self.assertEqual(len(queries),3)
                self.assertTrue(conn.closed)
                self.assertEqual(json.loads((out/'passages.json').read_text()),[row])
                index=(out/'index.html').read_text()
                self.assertIn('passages/1.244.html',index)
                self.assertIn('analysis/progress.html',index)
                self.assertNotIn('Top overlap',index)
                self.assertNotIn('coverage.html',index)
                page=(out/'passages/1.244.html').read_text()
                self.assertIn('ἥρως &lt;καί&gt;',page)
                self.assertIn('Hero &amp; accent',page)
                self.assertIn('sandbox="allow-scripts allow-forms"',page)
                self.assertIn('Content-Security-Policy',page)
                self.assertNotIn('Overlaps',page)
                self.assertTrue((out/'about/lentz.html').exists())
                progress=(analysis/'progress.html').read_text()
                self.assertIn('translate_lines.py',progress)
                self.assertIn('summarize_lines.py',progress)
                self.assertNotIn('compute_overlaps.py',progress)
                for name in retired: self.assertFalse((analysis/name).exists())
                self.assertEqual((analysis/'unrelated.txt').read_text(),'preserve')

    def test_retired_job_and_access_helpers_are_absent_without_dropping_history(self):
        pipeline=(ROOT/'run_daily_pipeline.sh').read_text()
        self.assertNotIn('compute_overlaps.py',pipeline)
        self.assertNotIn('--overlap-metric-version',pipeline)
        self.assertFalse((ROOT/'stephanos_db.py').exists())
        self.assertFalse((ROOT/'compute_overlaps.py').exists())
        schema=(ROOT/'init_db.py').read_text()
        self.assertNotIn('DROP TABLE',schema)
        self.assertNotIn('DELETE FROM',schema)
        self.assertNotIn('CREATE TABLE IF NOT EXISTS stephanos_overlap',schema)
        self.assertIn('CREATE TABLE IF NOT EXISTS cathpros_lines',schema)


if __name__=='__main__': unittest.main()
