import datetime as dt
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import core,workspace,sync
from fixture import TestDirectory

class WorkspaceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.fixture=TestDirectory();cls.original=core.DB;core.DB=Path(cls.fixture.name)/cls.fixture.filename;core.init();cls.seed=core.DB.read_bytes()
 @classmethod
 def tearDownClass(cls):core.DB=cls.original;cls.fixture.cleanup()
 def setUp(self):core.DB.write_bytes(self.seed)
 def event(self,**kw):return dict(id='test-event',date='2026-11-09',kind='order',order_id='test-order',user_id='test-user',creator_id='C001',amount=100,refund=10,currency='USD',**kw)
 def test_country_contribution_and_weighting(self):
  d=workspace.dashboard({});self.assertEqual(sum(r['contribution'] for r in d['countries']),d['current']['views']-d['baseline']['views']);self.assertAlmostEqual(d['current']['er'],d['current']['engagements']/d['current']['views']);self.assertIn('数据完整',d['conclusion'])
 def test_filters_and_natural_periods(self):
  d=workspace.dashboard(dict(platform='Instagram',country='JP',start='2026-10-01',end='2026-11-09',grain='month'));self.assertTrue(all(c['platform']=='Instagram' and c['country']=='JP' for c in d['creators']));self.assertEqual([r['date'] for r in d['trend']],['2026-10-01','2026-11-01']);self.assertFalse(d['trend'][0]['partial']);self.assertTrue(d['trend'][1]['partial'])
  self.assertEqual(workspace.bucket('2026-11-01','week'),dt.date(2026,10,26))
 def test_ninety_days_and_idempotent_migration(self):
  for cr in core.creators():self.assertGreaterEqual(len(core.history(cr['id'])),83)
  with core.connect() as c:
   n=c.execute('SELECT COUNT(*) FROM contents').fetchone()[0];c.execute("UPDATE creators SET owner='Keep' WHERE id='C001'");c.execute("INSERT INTO tasks(creator_id,title,owner,created) VALUES('C001','Keep task','Keep','2026-11-09')")
  core.init()
  with core.connect() as c:
   self.assertEqual(n,c.execute('SELECT COUNT(*) FROM contents').fetchone()[0]);self.assertEqual('Keep',c.execute("SELECT owner FROM creators WHERE id='C001'").fetchone()[0]);self.assertEqual('Keep task',c.execute('SELECT title FROM tasks').fetchone()[0])
 def test_migration_from_legacy_preserves_feedback(self):
  with core.connect() as c:
   for table in ('schema_versions','accounts','contents','content_snapshots','comments','candidates','candidate_history','campaigns','heating','conversions','settings'):c.execute('DROP TABLE '+table)
   c.execute("INSERT INTO tasks(creator_id,title,owner,status,feedback,created) VALUES('C001','legacy','Sienna','已完成','keep feedback','2026-11-09')")
  core.init()
  with core.connect() as c:self.assertEqual(c.execute("SELECT feedback FROM tasks WHERE title='legacy'").fetchone()[0],'keep feedback')
 def test_snapshot_difference_and_missing_metrics(self):
  items=workspace.content_detail(dict(creator_id='C002'))['contents'];item=items[0]
  self.assertEqual(item['platform'],'Threads');self.assertIsNone(item['values']['saves'])
  r=workspace.content_detail(dict(creator_id='C001'))['contents'][5];data=workspace.content_detail(dict(content_id=r['id']))['contents'][0];self.assertTrue(data['words']);self.assertTrue(data['comment_samples'])
  self.assertAlmostEqual(sum(t['share'] for t in data['topics']),1)
 def test_atomic_import_and_cumulative_validation(self):
  record=dict(id='new-content',creator_id='C001',published_at='2026-11-09',kind='视频',title='New')
  with self.assertRaises(ValueError):workspace.import_records('contents',[record,{**record,'id':'bad','creator_id':'UNKNOWN'}])
  with core.connect() as c:self.assertIsNone(c.execute("SELECT id FROM contents WHERE id='new-content'").fetchone())
  workspace.import_records('contents',[record]);workspace.import_records('snapshots',[dict(content_id='new-content',date='2026-11-08',views=100),dict(content_id='new-content',date='2026-11-09',views=200)])
  with self.assertRaises(ValueError):workspace.import_records('snapshots',[dict(content_id='new-content',date='2026-11-10',views=50)])
  d=workspace.content_detail(dict(content_id='new-content',start='2026-11-09',end='2026-11-09'))['contents'][0];self.assertEqual(d['values']['views'],100);self.assertIsNone(d['values']['likes'])
 def test_orders_dedup_refunds_conflicts_and_currency(self):
  e=self.event();workspace.import_records('conversions',[e]);workspace.import_records('conversions',[{**e,'id':'another-id'}])
  with core.connect() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM conversions WHERE order_id='test-order'").fetchone()[0],1)
  workspace.import_records('conversions',[{**e,'id':'conflict','order_id':'conflict-order','campaign_id':'CP-C002'},{**e,'id':'unattributed','order_id':'unknown-order','creator_id':None,'currency':'EUR'}])
  with core.connect() as c:
   r=c.execute("SELECT * FROM conversions WHERE id='conflict'").fetchone();self.assertIsNone(r['creator_id']);self.assertEqual(r['attribution'],'conflict')
   cm=workspace.commerce(c,dt.date(2026,11,9),dt.date(2026,11,9));self.assertEqual(len(cm['currencies']),2);self.assertEqual(cm['unattributed'],2)
   for ccy in cm['currencies']:self.assertAlmostEqual(ccy['net_gmv'],ccy['gmv']-ccy['refund'])
  with self.assertRaises(ValueError):workspace.import_records('conversions',[{**e,'refund':101}])
 def test_new_users_dedup_and_invitation_match(self):
  e=dict(id='N1',date='2026-11-09',kind='new_user',user_id='test-new',currency='USD',invite_code='JOINC001');workspace.import_records('conversions',[e]);workspace.import_records('conversions',[{**e,'id':'N2'}])
  with core.connect() as c:
   a=workspace.rows(c,"SELECT * FROM conversions WHERE user_id='test-new'");self.assertEqual(len(a),1);self.assertEqual(a[0]['creator_id'],'C001')
 def test_discovery_dedup_unknown_and_promotion(self):
  ds=workspace.discoveries({});self.assertTrue(ds['candidates'][0]['uncovered']);self.assertTrue(any(d['country']=='UNKNOWN' for d in ds['candidates']));candidate=ds['candidates'][0]
  workspace.update_candidate(dict(id=candidate['id'],favorite=True,owner='Sienna',status='已联系'));workspace.update_candidate(dict(id=candidate['id'],owner='Sienna',promote=True));workspace.update_candidate(dict(id=candidate['id'],owner='Sienna',promote=True))
  self.assertNotIn(candidate['id'],[d['id'] for d in workspace.discoveries({})['candidates']])
  with core.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM accounts WHERE platform=? AND handle=?',(candidate['platform'],candidate['handle'])).fetchone()[0],1)
 def test_pending_recommendation_and_weights(self):
  candidate=dict(id='test-c',name='New',platform='Instagram',handle='NEW_USER',discovered_at='2026-11-09')
  workspace.import_records('candidates',[candidate]);workspace.import_records('candidates',[{**candidate,'id':'changed-id','handle':'new_user'}]);d=next(r for r in workspace.discoveries({})['candidates'] if r['handle']=='new_user');self.assertEqual(d['recommendation'],'待评估')
  with self.assertRaises(ValueError):workspace.set_weights({'weights':{k:0 for k in workspace.DEFAULT_WEIGHTS}})
 def test_unconfigured_sync_logs_failure(self):
  with patch.dict('os.environ',{'APIFY_TOKEN':''}),self.assertRaises(ValueError):sync.synchronize()
  with core.connect() as c:self.assertEqual(c.execute('SELECT kind FROM runs ORDER BY id DESC LIMIT 1').fetchone()[0],'sync-failed')
 def test_sync_repeat_does_not_duplicate(self):
  e=self.event();e['record_type']='conversions'
  with patch.dict('os.environ',{'APIFY_TOKEN':'test','TIKTOK_DATASET_ID':'test','THREADS_DATASET_ID':'','INSTAGRAM_DATASET_ID':''}),patch.object(sync,'dataset_rows',side_effect=lambda p:[dict(e)]):
   sync.synchronize();sync.synchronize()
  with core.connect() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM conversions WHERE order_id='test-order'").fetchone()[0],1)
 def test_tracking_url_match_and_conflict(self):
  e=self.event();e.pop('creator_id');e['tracking_url']='https://example.com/?tracking_code=track-C001'
  workspace.import_records('conversions',[e])
  with core.connect() as c:self.assertEqual(c.execute("SELECT creator_id FROM conversions WHERE order_id='test-order'").fetchone()[0],'C001')
  workspace.import_records('conversions',[{**e,'campaign_id':'CP-C002'}])
  with core.connect() as c:self.assertEqual(c.execute("SELECT attribution FROM conversions WHERE order_id='test-order'").fetchone()[0],'conflict')
 def test_profiles_accounts_and_missing_new_history(self):
  p=dict(id='P100',name='New Person',platform='Instagram',country='NZ',tier='B',status='试合作',owner='Sienna',topic='生活方式')
  workspace.import_records('profiles',[p]);workspace.import_records('accounts',[dict(creator_id='P100',platform='Instagram',handle='@NewPerson')]);core.init()
  self.assertEqual(core.history('P100'),[]);self.assertEqual(workspace.metadata()['countries']['NZ'],'NZ')
  with core.connect() as c:self.assertEqual(c.execute("SELECT handle FROM accounts WHERE creator_id='P100'").fetchone()[0],'newperson')
 def test_zero_denominator_and_empty_comment(self):
  with core.connect() as c:cm=workspace.commerce(c,dt.date(2030,1,1),dt.date(2030,1,2));self.assertEqual(cm['currencies'],[])
  self.assertIsNone(workspace.ratio(1,0));self.assertRaises(ValueError,workspace.period,dict(start='2026-11-10',end='2026-11-09'))
if __name__=='__main__':unittest.main()
