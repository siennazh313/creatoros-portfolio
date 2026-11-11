"""Batch entrypoint suitable for Task Scheduler. No background schedule installed."""
import argparse,json,datetime
from core import init,state,ROOT,ingest
from integrations import apify_rows,advise
p=argparse.ArgumentParser();p.add_argument('--collect',action='store_true');p.add_argument('--agent',action='store_true');p.add_argument('--end',default=None);a=p.parse_args()
init()
if a.collect:
 from sync import synchronize
 synchronize()
# Offline replay uses fixed demo date; a scheduled real ingestion uses today's UTC date unless overridden.
end=a.end or state()['end']
s=state(end);s['advice']={}
for c in s['creators']:
 if c['diagnosis']['flags']:
  if a.agent:s['advice'][c['id']]=advise(c['id'],end,.25)
  else:
   from core import rule_advice
   s['advice'][c['id']]=rule_advice(c['id'],c['diagnosis'])
out=ROOT/'evidence'/('daily-report-'+end+'.json');out.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8');print(str(out))
