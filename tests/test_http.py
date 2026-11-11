import unittest,sys,tempfile,threading,json,urllib.request,urllib.error,io,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from fixture import TestDirectory
import core,server
class HttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TestDirectory();self.old=core.DB;core.DB=Path(self.tmp.name)/self.tmp.filename;core.init();self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=self.http.serve_forever,daemon=True).start();self.base='http://127.0.0.1:'+str(self.http.server_port)
 def tearDown(self):self.http.shutdown();self.http.server_close();core.DB=self.old;self.tmp.cleanup()
 def request(self,path,body=None,headers=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**(headers or {})})
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def test_full_feedback_loop(self):
  status,d=self.request('/api/diagnose',{'creator_id':'C001'});self.assertEqual(status,200)
  task={'creator_id':'C001','title':d['actions'][0]['title'],'owner':'Sienna'}
  _,t=self.request('/api/tasks',task);_,again=self.request('/api/tasks',task);self.assertEqual(t['id'],again['id']);self.assertTrue(again['duplicate'])
  status,_=self.request('/api/task-update',{'id':t['id'],'status':'已完成','feedback':''});self.assertEqual(status,400)
  status,_=self.request('/api/task-update',{'id':t['id'],'status':'已完成','feedback':'模拟执行，结果待观察'});self.assertEqual(status,200)
  _,s=self.request('/api/state');self.assertEqual(s['tasks'][0]['status'],'已完成')
 def test_creator_edit(self):
  status,_=self.request('/api/creator-update',dict(creator_id='C001',status='已终止',tier='C',owner='Demo Owner'));self.assertEqual(status,200)
  _,s=self.request('/api/state');self.assertEqual(s['creators'][0]['owner'],'Demo Owner')
 def test_csv_ingestion_and_replay(self):
  text='creator_id,date,posts,views,engagements\nC001,2026-11-10,2,1500,60'
  for i in range(2):
   status,r=self.request('/api/import',{'csv':text});self.assertEqual(status,200);self.assertEqual(r['rows'],1)
  _,s=self.request('/api/state?end=2026-11-10');self.assertEqual(len([x for x in s['history'] if x['creator_id']=='C001' and x['date']=='2026-11-10']),1)
 def test_csrf_rejected(self):
  status,_=self.request('/api/tasks',{}, {'Origin':'https://example.org'});self.assertEqual(status,403)
 def test_invalid_threshold(self):
  for t in ['nan','2','-1']:
   status,_=self.request('/api/state?threshold='+t);self.assertEqual(status,400)
 def test_missing_config_is_error(self):
  from unittest.mock import patch
  with patch.dict('os.environ',{'APIFY_TOKEN':'','APIFY_DATASET_ID':''}):status,_=self.request('/api/collect',{})
  self.assertEqual(status,400)
 def test_workspace_endpoints(self):
  for path,key in [('/api/meta','contracts'),('/api/dashboard?platform=Instagram','current'),('/api/countries?country=US','countries'),('/api/commerce','commerce'),('/api/contents?creator_id=C001','contents'),('/api/discoveries','candidates')]:
   status,r=self.request(path);self.assertEqual(status,200,path);self.assertIn(key,r)
  status,r=self.request('/api/records/import',{'kind':'comments','records':[{'id':'bad','content_id':'UNKNOWN','date':'2026-11-09','text':'x'}]});self.assertEqual(status,400)
  with __import__('unittest.mock',fromlist=['patch']).patch.dict('os.environ',{'APIFY_TOKEN':''}):
   status,r=self.request('/api/sync',{});self.assertEqual(status,400)
if __name__=='__main__':unittest.main()
