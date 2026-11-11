"""Controlled synthetic rule benchmark. Not a real-user or model benchmark."""
import sys,json,csv,random,time,datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import diagnose,END,ROOT
(ROOT/'evidence').mkdir(exist_ok=True)
rng=random.Random(42);cases=[];started=time.perf_counter()
for typ in ['normal','reach_drop','cadence_drop','engagement_drop','data_gap','low_sample']:
    for i in range(12):
        rows=[]
        for d in range(14):
            p=2;v=round(20000*rng.uniform(.92,1.08));e=round(v*.04)
            if typ=='low_sample':p=0;v=0;e=0
            if d>=7:
                if typ=='reach_drop':v=round(v*.4);e=round(v*.04)
                if typ=='cadence_drop':p=1;v=round(v*.5);e=round(v*.04)
                if typ=='engagement_drop':e=round(e*.35)
                if typ=='data_gap' and d==12:continue
            rows.append(dict(date=str(END-datetime.timedelta(days=13-d)),posts=p,views=v,engagements=e))
        predicted=diagnose(rows,END)['flags'];expected=[] if typ=='normal' else [typ]
        cases.append(dict(case_id=f'{typ}-{i:02}',expected=expected,predicted=predicted,passed=predicted==expected))
metrics=dict(total=len(cases),passed=sum(x['passed'] for x in cases),exact_match=sum(x['passed'] for x in cases)/len(cases),elapsed_ms=round((time.perf_counter()-started)*1000,3),scope='受控合成规则回归，非真实业务准确率；未评测真实LLM')
(ROOT/'evidence/rule_evaluation.json').write_text(json.dumps(dict(metrics=metrics,cases=cases),ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(metrics,ensure_ascii=False))
