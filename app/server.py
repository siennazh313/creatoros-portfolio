import sys,json,datetime,os,csv,io,threading,webbrowser
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pathlib import Path
from core import *
from integrations import advise,apify_rows
import workspace
WEB=ROOT/'web'
class Handler(BaseHTTPRequestHandler):
    def send(self,value,code=200):
        data=json.dumps(value,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        p=urlparse(self.path);q=parse_qs(p.query)
        try:
            params={k:v[0] for k,v in q.items()}
            if p.path=='/api/analysis-dataset':
                with connect() as c:
                    data={name:workspace.rows(c,'SELECT * FROM '+name) for name in ['creators','accounts','metrics','contents','content_snapshots','comments','candidates','campaigns','heating','conversions']}
                data['meta']=workspace.metadata()
                return self.send(data)
            if p.path=='/api/meta':return self.send(workspace.metadata())
            if p.path in ('/api/dashboard','/api/countries','/api/commerce'):return self.send(workspace.dashboard(params))
            if p.path=='/api/contents':return self.send(workspace.content_detail(params))
            if p.path=='/api/discoveries':return self.send(workspace.discoveries(params))
            if p.path=='/api/state':return self.send(state(q.get('end',[None])[0],float(q.get('threshold',[.25])[0])))
            if p.path=='/api/health':return self.send({'ok':True,'llm_configured':bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL')),'apify_configured':bool(os.getenv('APIFY_TOKEN') and os.getenv('APIFY_DATASET_ID'))})
            if p.path=='/api/export':
                data=json.dumps(state(),ensure_ascii=False,indent=2).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Disposition','attachment; filename=creator-report.json');self.end_headers();self.wfile.write(data);return
            file=WEB/('index.html' if p.path=='/' else p.path.lstrip('/'));file=file.resolve()
            if not file.is_relative_to(WEB.resolve()) or not file.is_file():return self.send({'error':'不存在'},404)
            body=file.read_bytes();self.send_response(200);self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}.get(file.suffix[1:],'application/octet-stream'));self.end_headers();self.wfile.write(body)
        except Exception:return self.send({'error':'读取失败，请检查日期和阈值'},400)
    def do_POST(self):
        try:
            # Local-only API: reject cross-origin mutation, including DNS rebinding hosts.
            allowed={'127.0.0.1','localhost'} | {h.strip() for h in os.getenv('PUBLIC_HOSTS','').split(',') if h.strip()}
            if os.getenv('RENDER_EXTERNAL_HOSTNAME'):allowed.add(os.environ['RENDER_EXTERNAL_HOSTNAME'])
            host=self.headers.get('Host','').split(':')[0]
            if host not in allowed:return self.send({'error':'访问域名尚未配置'},403)
            origin=self.headers.get('Origin')
            if origin and origin not in ['http://'+self.headers['Host'],'https://'+self.headers['Host']]:return self.send({'error':'拒绝跨域写入'},403)
            length=int(self.headers.get('Content-Length',0))
            if length>5_000_000:raise ValueError('请求超过5MB')
            b=json.loads(self.rfile.read(length) or b'{}');path=urlparse(self.path).path
            if path=='/api/records/import':return self.send(workspace.import_records(b['kind'],b['records']))
            if path=='/api/candidate-update':return self.send(workspace.update_candidate(b))
            if path=='/api/weights':return self.send(workspace.set_weights(b))
            if path=='/api/sync':
                from sync import synchronize
                return self.send(synchronize())
            if path=='/api/diagnose':
                cid=b['creator_id']
                if cid not in {x['id'] for x in creators()}:raise ValueError('未知创作者')
                out=advise(cid,b.get('end',str(END)),float(b.get('threshold',.25)))
                with connect() as c:c.execute('INSERT INTO diagnoses(creator_id,created,payload) VALUES(?,?,?)',(cid,datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),json.dumps(out,ensure_ascii=False)))
                return self.send(out)
            if path=='/api/creator-update':
                if b.get('status') not in ['签约中','试合作','已终止'] or b.get('tier') not in ['A','B','C']:raise ValueError('无效分层或合作状态')
                owner=str(b.get('owner','')).strip()
                if not owner or len(owner)>60:raise ValueError('负责人不能为空且不超过60字')
                with connect() as c:
                    cur=c.execute('UPDATE creators SET status=?,tier=?,owner=? WHERE id=?',(b['status'],b['tier'],owner,b['creator_id']))
                    if not cur.rowcount:raise ValueError('创作者不存在')
                return self.send({'ok':True})
            if path=='/api/tasks':
                cid=b['creator_id']; title=str(b['title']).strip();owner=str(b.get('owner','Sienna')).strip()
                if cid not in {x['id'] for x in creators()} or not title or len(title)>500:raise ValueError('任务参数不正确')
                with connect() as c:
                    old=c.execute("SELECT id FROM tasks WHERE creator_id=? AND title=? AND status!='已完成'",(cid,title)).fetchone()
                    if old:return self.send({'id':old[0],'duplicate':True})
                    cur=c.execute('INSERT INTO tasks(creator_id,title,owner,created) VALUES(?,?,?,?)',(cid,title,owner,datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()))
                    return self.send({'id':cur.lastrowid})
            if path=='/api/task-update':
                status=b['status'];feedback=str(b.get('feedback',''))[:2000]
                if status not in ['待执行','执行中','已完成','已拒绝']:raise ValueError('无效状态')
                if status in ['已完成','已拒绝'] and not feedback.strip():raise ValueError('请记录执行反馈或拒绝原因')
                with connect() as c:
                    cur=c.execute('UPDATE tasks SET status=?,feedback=? WHERE id=?',(status,feedback,int(b['id'])))
                    if cur.rowcount==0:raise ValueError('任务不存在')
                return self.send({'ok':True})
            if path=='/api/import':return self.send({'rows':ingest(list(csv.DictReader(io.StringIO(b['csv']))))})
            if path=='/api/collect':return self.send({'rows':ingest(apify_rows(),'apify')})
            return self.send({'error':'接口不存在'},404)
        except (KeyError,ValueError,TypeError,sqlite3.IntegrityError) as e:return self.send({'error':str(e)[:200]},400)
        except Exception:return self.send({'error':'上游服务或内部操作失败，请检查环境配置；没有生成成功结果'},502)
    def log_message(self,*args):pass
if __name__=='__main__':
    init();port=int(sys.argv[sys.argv.index('--port')+1]) if '--port' in sys.argv else int(os.getenv('PORT','8787'));url=f'http://127.0.0.1:{port}'
    print('CreatorOS 创作者经营工作台：'+url,flush=True)
    server=ThreadingHTTPServer((os.getenv('HOST','127.0.0.1'),port),Handler)
    if '--no-browser' not in sys.argv:threading.Timer(.8,lambda:webbrowser.open(url)).start()
    server.serve_forever()
