"""Pull explicitly configured, existing datasets. Never starts paid actors."""
import os,json,urllib.parse,threading
import core,workspace
from integrations import request_json
LOCK=threading.Lock()

def dataset_rows(platform):
    token=os.getenv('APIFY_TOKEN');dataset=os.getenv(platform.upper()+'_DATASET_ID')
    if not token or not dataset:return None
    mapping=json.loads(os.getenv(platform.upper()+'_FIELD_MAP','{}'));out=[];offset=0
    while True:
        url='https://api.apify.com/v2/datasets/'+urllib.parse.quote(dataset,safe='')+'/items?clean=true&format=json&limit=1000&offset='+str(offset)
        batch=request_json(url,token)
        if not isinstance(batch,list):raise ValueError('数据源须返回记录数组')
        for raw in batch:
            record={mapping.get(k,k):v for k,v in raw.items()};record['platform']=platform;out.append(record)
        if len(batch)<1000:break
        offset+=len(batch)
        if offset>=50000:raise ValueError('单平台超过50000条，请按日期分批同步')
    return out

def synchronize():
    if not LOCK.acquire(blocking=False):raise ValueError('已有同步正在执行')
    try:
        configured=[p for p in workspace.PLATFORMS if os.getenv(p.upper()+'_DATASET_ID') and os.getenv('APIFY_TOKEN')]
        if not configured:raise ValueError('尚未配置平台数据源，请先配置平台 Dataset 与访问令牌')
        completed=[]
        for platform in configured:
            data=dataset_rows(platform);groups={}
            for record in data:
                kind=record.pop('record_type','candidates');groups.setdefault(kind,[]).append(record)
            # Import dependencies before their referencing records. Each group is atomic.
            for kind in ('profiles','accounts','candidates','contents','campaigns','snapshots','comments','heating','conversions','metrics'):
                if kind in groups:
                    result={'rows':core.ingest(groups[kind],platform)} if kind=='metrics' else workspace.import_records(kind,groups[kind],platform)
                    completed.append({'platform':platform,'kind':kind,**result});groups.pop(kind)
            if groups:raise ValueError('未知record_type：'+','.join(groups))
        with core.connect() as c:c.execute('INSERT INTO runs(created,kind,detail) VALUES(?,?,?)',(workspace.now(),'sync-success',json.dumps(completed,ensure_ascii=False)))
        return {'ok':True,'completed':completed,'synced_at':workspace.now()}
    except Exception as error:
        with core.connect() as c:c.execute('INSERT INTO runs(created,kind,detail) VALUES(?,?,?)',(workspace.now(),'sync-failed',type(error).__name__+'；请核对数据源与字段，已完成批次可安全重试'))
        raise
    finally:LOCK.release()

if __name__=='__main__':
    core.init()
    try:print(json.dumps(synchronize(),ensure_ascii=False))
    except Exception as error:print(str(error));raise SystemExit(1)
