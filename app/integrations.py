"""Explicit network adapters; no calls without user configuration."""
import os,json,urllib.request,urllib.parse,time
from core import history,diagnose,rule_advice

def request_json(url,token,body=None,timeout=45):
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    for i in range(3):
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or i==2:raise RuntimeError(f'上游 HTTP {e.code}，请检查配置；未返回凭据') from None
            time.sleep(2**i)

def apify_rows():
    token=os.environ.get('APIFY_TOKEN');dataset=os.environ.get('APIFY_DATASET_ID')
    if not token or not dataset:raise ValueError('先配置 APIFY_TOKEN 与 APIFY_DATASET_ID')
    mapping=json.loads(os.getenv('APIFY_FIELD_MAP','{}'));out=[];offset=0
    while True:
        rows=request_json('https://api.apify.com/v2/datasets/'+urllib.parse.quote(dataset,safe='')+'/items?clean=true&format=json&limit=1000&offset='+str(offset),token)
        for r in rows:out.append({k:r[mapping.get(k,k)] for k in ['creator_id','date','posts','views','engagements']})
        if len(rows)<1000:break
        offset+=len(rows)
        if offset>=100000:raise ValueError('数据超出单次导入上限')
    return out

def advise(cid,end,threshold):
    d=diagnose(history(cid),end,threshold)
    key=os.getenv('LLM_API_KEY');base=os.getenv('LLM_BASE_URL','https://api.openai.com/v1').rstrip('/');model=os.getenv('LLM_MODEL')
    if not key or not model:return rule_advice(cid,d)
    if not base.startswith('https://'):raise ValueError('模型地址必须使用 HTTPS')
    tools=[{'type':'function','function':{'name':n,'description':desc,'parameters':{'type':'object','properties':{},'additionalProperties':False}}} for n,desc in [('get_creator_metrics','读取当前创作者的两周汇总数据'),('get_anomaly_evidence','读取规则证据和异常类型')]]
    messages=[{'role':'system','content':'你是创作者运营分析助手。必须先调用两个数据工具。只依据工具证据，不能声称因果关系。最终仅输出JSON对象，包含summary字符串、actions数组（每项title字符串、evidence为规则flag、priority为P0或P1）、caveat字符串。无异常时actions为空。数据缺口时只能建议补数。最多3条建议。禁止编造订单或销售转化。'}, {'role':'user','content':'分析当前创作者 '+cid+'，截止 '+end}];trace=[];called=set()
    for step in range(4):
        response=request_json(base+'/chat/completions',key,{'model':model,'messages':messages,'tools':tools,'tool_choice':'required' if not {'get_creator_metrics','get_anomaly_evidence'}<=called else 'auto','temperature':.2})
        msg=response['choices'][0]['message'];messages.append(msg)
        if msg.get('tool_calls'):
            for call in msg['tool_calls']:
                name=call['function']['name']
                if name not in ['get_creator_metrics','get_anomaly_evidence']:raise ValueError('模型请求未授权工具')
                result={k:d[k] for k in ['current','baseline','delta']} if name=='get_creator_metrics' else {k:d[k] for k in ['flags','window_end','threshold']}
                messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)});trace.append({'tool':name,'result':result});called.add(name)
        else:
            if not {'get_creator_metrics','get_anomaly_evidence'}<=called:raise ValueError('模型未完成证据读取')
            out=json.loads(msg['content'])
            if not isinstance(out.get('summary'),str) or not isinstance(out.get('caveat'),str) or not isinstance(out.get('actions'),list):raise ValueError('模型输出格式不合格')
            if len(out['actions'])>3:raise ValueError('模型输出建议过多')
            for a in out['actions']:
                if not isinstance(a.get('title'),str) or not a['title'].strip() or len(a['title'])>500 or a.get('evidence') not in d['flags'] or a.get('priority') not in ['P0','P1']:raise ValueError('模型建议缺少有效证据')
            out.update(mode='LLM Agent',trace=trace);return out
    raise ValueError('Agent 超出4轮调用限制，请重试；未生成任务')
