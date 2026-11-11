import unittest,tempfile,sys,os,datetime,json,random,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from fixture import TestDirectory
import core,integrations
from unittest.mock import patch
class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TestDirectory();self.old=core.DB;core.DB=Path(self.tmp.name)/self.tmp.filename;core.init()
    def tearDown(self):core.DB=self.old;self.tmp.cleanup()
    def test_seed_reproducible_and_flags(self):
        s=core.state();self.assertEqual(len(s['creators']),30)
        actual={x['id']:x['diagnosis']['flags'] for x in s['creators']}
        for cid,flag in [('C001','reach_drop'),('C002','cadence_drop'),('C003','engagement_drop'),('C004','data_gap')]:self.assertIn(flag,actual[cid])
        self.assertEqual(sum(bool(x) for x in actual.values()),8)
    def test_atomic_validation(self):
        good={'creator_id':'C001','date':'2026-11-10','posts':1,'views':100,'engagements':5};bad={**good,'creator_id':'UNKNOWN'}
        with self.assertRaises(ValueError):core.ingest([good,bad])
        self.assertFalse(any(x['date']=='2026-11-10' for x in core.history('C001')))
    def test_idempotent_upsert(self):
        row={'creator_id':'C001','date':'2026-11-09','posts':1,'views':100,'engagements':5};n=len(core.history('C001'));core.ingest([row]);core.ingest([row]);self.assertEqual(n,len(core.history('C001')))
    def test_duplicate_batch_rejected(self):
        r={'creator_id':'C001','date':'2026-11-10','posts':1,'views':100,'engagements':5}
        with self.assertRaises(ValueError):core.ingest([r,r])
    def test_bad_numbers(self):
        for value in [-1,'nan','inf',1.2]:
            with self.subTest(value=value),self.assertRaises(ValueError):core.ingest([dict(creator_id='C001',date='2026-11-10',posts=1,views=value,engagements=0)])
    def test_missing_intercepts_business_flags(self):
        d=core.diagnose(core.history('C004'),core.END);self.assertEqual(d['flags'],['data_gap'])
    def test_rule_fallback_truthful(self):
        with patch.dict(os.environ,{'LLM_API_KEY':'','LLM_MODEL':''}):out=integrations.advise('C001',str(core.END),.25)
        self.assertEqual(out['mode'],'规则建议');self.assertTrue(out['actions'])
    def test_agent_tool_loop_mock(self):
        calls=[{'id':'1','type':'function','function':{'name':'get_creator_metrics','arguments':'{}'}},{'id':'2','type':'function','function':{'name':'get_anomaly_evidence','arguments':'{}'}}]
        responses=[{'choices':[{'message':{'role':'assistant','content':None,'tool_calls':calls}}]},{'choices':[{'message':{'role':'assistant','content':json.dumps({'summary':'触达下降','actions':[{'title':'抽查选题','priority':'P1','evidence':'reach_drop'}],'caveat':'待验证假设'})}}]}]
        with patch.dict(os.environ,{'LLM_API_KEY':'mock-key','LLM_MODEL':'mock-model'}),patch.object(integrations,'request_json',side_effect=responses):out=integrations.advise('C001',str(core.END),.25)
        self.assertEqual(out['mode'],'LLM Agent');self.assertEqual(len(out['trace']),2)
    def test_agent_rejects_invented_evidence(self):
        calls=[{'id':str(i),'type':'function','function':{'name':name,'arguments':'{}'}} for i,name in enumerate(['get_creator_metrics','get_anomaly_evidence'])]
        responses=[{'choices':[{'message':{'role':'assistant','tool_calls':calls}}]},{'choices':[{'message':{'role':'assistant','content':json.dumps({'summary':'test','actions':[{'title':'foo','priority':'P1','evidence':'sales_drop'}],'caveat':'test'})}}]}]
        with patch.dict(os.environ,{'LLM_API_KEY':'mock','LLM_MODEL':'mock'}),patch.object(integrations,'request_json',side_effect=responses),self.assertRaises(ValueError):integrations.advise('C001',str(core.END),.25)
    def test_apify_mapping_mock(self):
        with patch.dict(os.environ,{'APIFY_TOKEN':'mock','APIFY_DATASET_ID':'test','APIFY_FIELD_MAP':'{"views":"playCount"}'}),patch.object(integrations,'request_json',return_value=[dict(creator_id='C001',date='2026-11-10',posts=1,playCount=100,engagements=5)]):
            self.assertEqual(integrations.apify_rows()[0]['views'],100)
    def test_weighted_rate(self):
        self.assertAlmostEqual(core.summarize([dict(posts=1,views=100,engagements=20),dict(posts=1,views=900,engagements=0)])['er'],.02)
if __name__=='__main__':unittest.main()
