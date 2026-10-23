import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud_text import prepare,apply
from content_store import load
class CloudTextTests(unittest.TestCase):
 def document(self):
  d=copy.deepcopy(load());d['passages']=d['passages'][:35]
  for row in d['passages']:row['english_translation']=None;row['summary']=None
  return d
 def result(self,doc):
  req=prepare(doc)
  return {'request':req,'candidates':[dict(id=i['original']['id'],**{f:'Reviewed text' for f in i['fields']}) for i in req['items']],'review':{'reviewer':'independent reviewer','notes':'Checked against Greek and existing prompts'}}
 def test_no_work_for_complete_snapshot(self):self.assertIsNone(prepare(load()))
 def test_daily_caps_and_idempotency(self):
  d=self.document();r=self.result(d)
  self.assertEqual(sum('english_translation' in i['fields'] for i in r['request']['items']),5)
  self.assertEqual(sum('summary' in i['fields'] for i in r['request']['items']),25)
  self.assertEqual(apply(d,r),'imported');self.assertEqual(apply(d,r),'already-imported');self.assertIsNone(prepare(d))
  other=copy.deepcopy(r);other['candidates'][0]['summary']='Other'
  with self.assertRaises(RuntimeError):apply(d,other)
 def test_stale_snapshot_existing_text_and_review_checks(self):
  d=self.document();r=self.result(d);d['passages'][0]['greek_text']='edited'
  with self.assertRaises(RuntimeError):apply(d,r)
  d=self.document();r=self.result(d);r['review']={}
  with self.assertRaises(ValueError):apply(d,r)
  d=self.document();r=self.result(d);r['request']['items'][0]['original']['summary']='accepted'
  with self.assertRaises(ValueError):apply(d,r)
