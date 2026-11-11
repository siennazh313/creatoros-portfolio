"""Workspace v2: incremental schema, source-preserving fixtures and analytics.
Fixtures are deterministic portfolio data, never a substitute for an online collector.
"""
import collections
import datetime as dt
import json
import math
import random
import re
import urllib.parse
import core

ZONE = dt.timezone(dt.timedelta(hours=8))
COUNTRIES = {'US':'美国','UK':'英国','ID':'印度尼西亚','TH':'泰国','JP':'日本','DE':'德国','BR':'巴西','MX':'墨西哥','FR':'法国','KR':'韩国','AU':'澳大利亚','PH':'菲律宾','UNKNOWN':'未知国家'}
PLATFORMS = ('TikTok','Threads','Instagram')
DEFAULT_WEIGHTS = {'growth':25,'engagement':25,'stability':20,'fit':15,'coverage':15}

def now(): return dt.datetime.now(ZONE).isoformat(timespec='seconds')
def rows(c, sql, args=()): return [dict(r) for r in c.execute(sql,args)]
def ratio(a,b): return a/b if b else None

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY, applied TEXT);
    CREATE TABLE IF NOT EXISTS accounts(creator_id TEXT PRIMARY KEY,platform TEXT NOT NULL,handle TEXT NOT NULL,url TEXT,UNIQUE(platform,handle));
    CREATE TABLE IF NOT EXISTS contents(id TEXT PRIMARY KEY,creator_id TEXT NOT NULL,published_at TEXT NOT NULL,kind TEXT,title TEXT,url TEXT,source TEXT);
    CREATE INDEX IF NOT EXISTS content_creator_date ON contents(creator_id,published_at);
    CREATE TABLE IF NOT EXISTS content_snapshots(content_id TEXT,date TEXT,views INTEGER,likes INTEGER,comments INTEGER,shares INTEGER,saves INTEGER,organic_views INTEGER,paid_views INTEGER,source TEXT,PRIMARY KEY(content_id,date));
    CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY,content_id TEXT,date TEXT,text TEXT,topic TEXT,source TEXT);
    CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,platform TEXT,handle TEXT,country TEXT,topic TEXT,name TEXT,followers INTEGER,posts INTEGER,growth REAL,er REAL,stability REAL,fit REAL,url TEXT,discovered_at TEXT,favorite INTEGER DEFAULT 0,owner TEXT DEFAULT '',status TEXT DEFAULT '待评估',source TEXT,UNIQUE(platform,handle));
    CREATE TABLE IF NOT EXISTS candidate_history(id INTEGER PRIMARY KEY,candidate_id TEXT,created TEXT,detail TEXT);
    CREATE TABLE IF NOT EXISTS campaigns(id TEXT PRIMARY KEY,creator_id TEXT,content_id TEXT,platform TEXT,country TEXT,tracking_code TEXT UNIQUE,invite_code TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS heating(id TEXT PRIMARY KEY,date TEXT,creator_id TEXT,content_id TEXT,campaign_id TEXT,currency TEXT,spend REAL,impressions INTEGER,paid_views INTEGER,clicks INTEGER,visits INTEGER,registrations INTEGER,source TEXT);
    CREATE TABLE IF NOT EXISTS conversions(id TEXT PRIMARY KEY,date TEXT,creator_id TEXT,campaign_id TEXT,tracking_code TEXT,invite_code TEXT,user_id TEXT,order_id TEXT,kind TEXT,amount REAL,refund REAL,currency TEXT,status TEXT,attribution TEXT,source TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS unique_order ON conversions(order_id) WHERE kind='order' AND order_id IS NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS unique_new_user ON conversions(user_id) WHERE kind='new_user';
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
    ''')
    if 'tracking_url' not in {r[1] for r in c.execute('PRAGMA table_info(conversions)')}:c.execute('ALTER TABLE conversions ADD COLUMN tracking_url TEXT')
    if c.execute('SELECT 1 FROM schema_versions WHERE version=2').fetchone(): return
    rng=random.Random(20261111)
    # Preserve all old profiles and their operational edits. New accounts are additive.
    for i,name in enumerate(['Sofia Moreau','Hana Mori','Clara Weiss','Rafael Costa','Amelia Park','Lucas Rivera'],25):
        c.execute('INSERT OR IGNORE INTO creators VALUES(?,?,?,?,?,?,?,?)',(f'C{i:03}',name,'Instagram',['FR','JP','DE','BR','US','MX'][(i-25)%6],'B','试合作','Sienna',['生活方式','美食','旅行'][i%3]))
    creators=rows(c,'SELECT * FROM creators ORDER BY id')
    end=core.END
    for idx,cr in enumerate(creators):
        cid=cr['id']; handle=re.sub(r'[^a-z0-9]','',cr['name'].lower())
        host={'TikTok':'https://www.tiktok.com/@','Threads':'https://www.threads.net/@','Instagram':'https://www.instagram.com/'}[cr['platform']]
        c.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?,?)',(cid,cr['platform'],handle,host+handle))
        # Only backfill the fixture cohort; never synthesize dates for imported accounts.
        if not c.execute("SELECT 1 FROM metrics WHERE creator_id=? AND source='synthetic-v1'",(cid,)).fetchone() and idx<24: continue
        for d in range(90):
            day=str(end-dt.timedelta(days=89-d)); posts=2; base=8000+idx*1600
            views=round(base*posts*rng.uniform(.88,1.12)); eng=round(views*.045)
            if idx>=24 and d>=83: views=round(views*1.22);eng=round(views*.052)
            # Preserve the existing, deliberately missing latest observations.
            if idx<24 and day>=str(end-dt.timedelta(days=41)): continue
            c.execute('INSERT OR IGNORE INTO metrics VALUES(?,?,?,?,?,?)',(cid,day,posts,views,eng,'portfolio-v2'))
        daily=rows(c,'SELECT * FROM metrics WHERE creator_id=? ORDER BY date',(cid,))
        previous=[]; totals={}
        for m in daily:
            ids=[]
            for n in range(m['posts']):
                ident=f"{cid}-{m['date']}-{n}";ids.append(ident)
                title=['A slower morning','Small things, well made','A weekend worth keeping','From my kitchen','Places close to home','The everyday edit'][(idx+n)%6]
                kind='文字' if cr['platform']=='Threads' else ('图文' if cr['platform']=='Instagram' and n else '视频')
                c.execute('INSERT OR IGNORE INTO contents VALUES(?,?,?,?,?,?,?)',(ident,cid,m['date']+'T09:00:00+08:00',kind,title,None,'portfolio-v2'))
            targets=ids+previous
            if targets:
                remaining=m['views']
                for k,ident in enumerate(targets):
                    v=remaining if k==len(targets)-1 else m['views']//len(targets);remaining-=v
                    values=[v,round(v*.032),round(v*.004),round(v*.003),None if cr['platform']=='Threads' else round(v*.002),round(v*.82),v-round(v*.82)]
                    old=totals.get(ident,[0,0,0,0,None if cr['platform']=='Threads' else 0,0,0])
                    total=[None if a is None else a+(b or 0) for a,b in zip(values,old)];totals[ident]=total
                    c.execute('INSERT OR IGNORE INTO content_snapshots VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,m['date'],*total,'portfolio-v2'))
            previous=ids
        recent=rows(c,'SELECT id,published_at FROM contents WHERE creator_id=? ORDER BY published_at DESC LIMIT 12',(cid,))
        for item in recent:
            for n,(text,topic) in enumerate([('Love the quiet details, so inspiring','内容共鸣'),('Where can I find this?','购买意向'),('Please share the location','信息咨询'),('The colors are beautiful','视觉反馈'),('Would love a full tutorial','内容需求'),('This feels like my kind of weekend','内容共鸣')]):
                c.execute('INSERT OR IGNORE INTO comments VALUES(?,?,?,?,?,?)',(item['id']+f'-R{n}',item['id'],item['published_at'][:10],text,topic,'portfolio-v2'))
        content=recent[0]['id'] if recent else None
        c.execute('INSERT OR IGNORE INTO campaigns VALUES(?,?,?,?,?,?,?)',('CP-'+cid,cid,content,cr['platform'],cr['country'],'track-'+cid,'JOIN'+cid))
        for d in range(35):
            day=str(end-dt.timedelta(days=34-d));spend=round(18+idx*1.2+rng.random()*12,2);visits=100+idx*8+int(rng.random()*80)
            c.execute('INSERT OR IGNORE INTO heating VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(cid+'-'+day,day,cid,content,'CP-'+cid,'USD',spend,visits*38,visits*22,visits*2,visits,visits//3,'portfolio-v2'))
            for n in range(3):
                uid=f'U-{cid}-{day}-{n}'
                c.execute('INSERT OR IGNORE INTO conversions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('NU-'+uid,day,cid,'CP-'+cid,None,None,uid,None,'new_user',0,0,'USD','registered','matched','portfolio-v2',None))
                if n<2:
                    amount=round(20+idx+rng.random()*35,2)
                    c.execute('INSERT OR IGNORE INTO conversions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('O-'+uid,day,cid,'CP-'+cid,None,None,uid,'ORD-'+uid,'order',amount,5 if n==0 and d%11==0 else 0,'USD','paid','matched','portfolio-v2',None))
    for i in range(18):
        platform=PLATFORMS[i%3];name=['Yuki Tanaka','Léa Bernard','Min Seo','Olivia Brooks','Mateo Silva','Ari Santos'][i%6]+(' '+str(i//6+1) if i>=6 else '')
        handle=''.join(ch for ch in name.lower() if ch.isascii() and ch.isalnum())
        c.execute('INSERT OR IGNORE INTO candidates(id,platform,handle,country,topic,name,followers,posts,growth,er,stability,fit,url,discovered_at,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f'D{i+1:03}',platform,handle,['KR','AU','PH','JP','DE','UNKNOWN'][i%6],['生活方式','旅行','美食'][i%3],name,12000+i*4300,8+i%9,.08+i*.014,.025+i*.002,.6+(i%4)*.1,.8,None,str(end),'portfolio-v2'))
    c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('weights',json.dumps(DEFAULT_WEIGHTS)))
    c.execute('INSERT INTO schema_versions VALUES(2,?)',(now(),))

def latest_date(c):
    return c.execute("SELECT MAX(day) FROM (SELECT MAX(date) day FROM metrics UNION ALL SELECT MAX(date) FROM content_snapshots UNION ALL SELECT MAX(date) FROM heating UNION ALL SELECT MAX(date) FROM conversions)").fetchone()[0] or str(core.END)

def period(q):
    with core.connect() as c: latest=latest_date(c)
    end=dt.date.fromisoformat(q.get('end') or latest or str(core.END))
    start=dt.date.fromisoformat(q['start']) if q.get('start') else end-dt.timedelta(days=int(q.get('days',30))-1)
    if start>end or (end-start).days>730: raise ValueError('日期范围须为1至731天')
    grain=q.get('grain','day')
    if grain not in ('day','week','month'): raise ValueError('无效时间粒度')
    return start,end,grain

def bucket(day,grain):
    d=dt.date.fromisoformat(day)
    if grain=='week': d-=dt.timedelta(days=d.weekday())
    if grain=='month': d=d.replace(day=1)
    return d

def trend(metrics,start,end,grain):
    groups={};d=start
    while d<=end:
        b=bucket(str(d),grain);groups.setdefault(str(b),{'date':str(b),'views':0,'posts':0,'observed':set()});d+=dt.timedelta(days=1)
    for m in metrics:
        b=str(bucket(m['date'],grain));g=groups[b];g['views']+=m['views'];g['posts']+=m['posts'];g['observed'].add(m['date'])
    for b,g in groups.items():
        bd=dt.date.fromisoformat(b)
        stop=bd if grain=='day' else bd+dt.timedelta(days=6) if grain=='week' else (bd.replace(day=28)+dt.timedelta(days=4)).replace(day=1)-dt.timedelta(days=1)
        g['partial']=bd<start or stop>end;g['observed_days']=len(g.pop('observed'));g['missing']=g['observed_days']==0
    return list(groups.values())

def aggregate(ms):
    out=core.summarize(ms);out['active']=len({m['creator_id'] for m in ms if m['posts']>0});return out

def commerce(c,start,end,ids=None,detail=True,cache=None):
    heats=cache['heats'] if cache else rows(c,'SELECT * FROM heating WHERE date BETWEEN ? AND ?',(str(start),str(end)))
    events=cache['events'] if cache else rows(c,'SELECT * FROM conversions WHERE date BETWEEN ? AND ?',(str(start),str(end)))
    if ids is not None:
        heats=[r for r in heats if r['creator_id'] in ids];events=[r for r in events if r['creator_id'] in ids]
    currencies=sorted({r['currency'] for r in heats+events});summaries=[]
    first_dates=cache['first_dates'] if cache else {r['user_id']:r['first_date'] for r in rows(c,"SELECT user_id,MIN(date) AS first_date FROM conversions WHERE kind='order' AND status='paid' GROUP BY user_id")}
    for currency in currencies:
        h=[r for r in heats if r['currency']==currency];e=[r for r in events if r['currency']==currency];o=[r for r in e if r['kind']=='order' and r['status']=='paid']
        total={k:sum(r[k] or 0 for r in h) for k in ('spend','impressions','paid_views','clicks','visits','registrations')}
        # User counts are currency-local; the global user count below is distinct across currencies.
        users={r['user_id'] for r in e if r['kind']=='new_user'};buyers={r['user_id'] for r in o if r['user_id']}
        first_buyers={r['user_id'] for r in o if r['user_id'] and first_dates.get(r['user_id'], '')>=str(start)}
        total.update(currency=currency,gmv=sum(r['amount'] for r in o),refund=sum(r['refund'] for r in o),orders=len(o),new_users=len(users),buyers=len(buyers),first_buyers=len(first_buyers))
        total['net_gmv']=total['gmv']-total['refund'];total.update(ctr=ratio(total['clicks'],total['impressions']),registration_rate=ratio(total['registrations'],total['visits']),purchase_rate=ratio(len(buyers),total['visits']),cac=ratio(total['spend'],len(users)),roas=ratio(total['net_gmv'],total['spend']))
        summaries.append(total)
    return {'currencies':summaries,'heating':heats if detail else [],'events':events if detail else [],'new_users':len({r['user_id'] for r in events if r['kind']=='new_user'}),'unattributed':sum(r['attribution']!='matched' for r in events)}

def dashboard(q):
    start,end,grain=period(q);length=(end-start).days+1;bs=start-dt.timedelta(days=length);be=start-dt.timedelta(days=1)
    with core.connect() as c:
        cs=rows(c,'SELECT c.*,a.handle,a.url FROM creators c LEFT JOIN accounts a ON a.creator_id=c.id ORDER BY c.id')
        cs=[r for r in cs if (not q.get('platform') or r['platform']==q['platform']) and (not q.get('country') or r['country']==q['country']) and (not q.get('creator_id') or r['id']==q['creator_id'])]
        ids={r['id'] for r in cs};allms=rows(c,'SELECT * FROM metrics WHERE date BETWEEN ? AND ?',(str(bs),str(end)));allms=[r for r in allms if r['creator_id'] in ids]
        current=[m for m in allms if m['date']>=str(start)];before=[m for m in allms if m['date']<str(start)]
        cache={'heats':rows(c,'SELECT * FROM heating WHERE date BETWEEN ? AND ?',(str(start),str(end))),'events':rows(c,'SELECT * FROM conversions WHERE date BETWEEN ? AND ?',(str(start),str(end))),'first_dates':{r['user_id']:r['first_date'] for r in rows(c,"SELECT user_id,MIN(date) AS first_date FROM conversions WHERE kind='order' AND status='paid' GROUP BY user_id")}}
        countries=[]
        for country in sorted({r['country'] for r in cs}):
            subset={r['id'] for r in cs if r['country']==country};a=aggregate([r for r in current if r['creator_id'] in subset]);b=aggregate([r for r in before if r['creator_id'] in subset])
            countries.append({'country':country,'name':COUNTRIES.get(country,country),'current':a,'baseline':b,'contribution':a['views']-b['views'],'change':core.change(a['views'],b['views']),'complete':a['days']==len(subset)*length and b['days']==len(subset)*length,'commerce':commerce(c,start,end,subset,False,cache)})
        for cr in cs:
            ms=[m for m in current if m['creator_id']==cr['id']];pr=[m for m in before if m['creator_id']==cr['id']]
            paid_recent=c.execute('SELECT SUM(paid_views) FROM heating WHERE creator_id=? AND date BETWEEN ? AND ?',(cr['id'],str(end-dt.timedelta(days=6)),str(end))).fetchone()[0]
            paid_before=c.execute('SELECT SUM(paid_views) FROM heating WHERE creator_id=? AND date BETWEEN ? AND ?',(cr['id'],str(end-dt.timedelta(days=13)),str(end-dt.timedelta(days=7)))).fetchone()[0]
            cr.update(paid_change=core.change(paid_recent,paid_before),current=aggregate(ms),baseline=aggregate(pr),diagnosis=core.diagnose(core.history(cr['id']),str(end)),commerce=commerce(c,start,end,{cr['id']},False,cache),trend=trend(ms,start,end,grain))
        if cr['diagnosis']['flags'] not in (['data_gap'],['low_sample']) and cr['paid_change'] is not None and abs(cr['paid_change'])>.25:cr['diagnosis']['flags'].append('paid_change')
        totals=aggregate(current);base=aggregate(before)
        coverage=len(current);expected=len(cs)*length;baseline_complete=len(before)==expected;complete=coverage==expected
        ranked=sorted(countries,key=lambda x:x['contribution']);delta=totals['views']-base['views']
        if not cs: conclusion='当前筛选范围内暂无创作者。'
        elif not complete or not baseline_complete:
            valid=[cr for cr in cs if cr['current']['days']==length and cr['baseline']['days']==length]
            if valid:
                leader=max(valid,key=lambda cr:abs(cr['current']['views']-cr['baseline']['views']))
                vd=sum(cr['current']['views']-cr['baseline']['views'] for cr in valid)
                conclusion=f"数据完整的{len(valid)}位创作者，播放／浏览合计变化 {vd:+,}；其中 {leader['name']}（{COUNTRIES.get(leader['country'],leader['country'])}）变化 {leader['current']['views']-leader['baseline']['views']:+,}。另有{len(cs)-len(valid)}位存在数据缺口，待补齐后判断全盘。"
            else:conclusion='数据缺口或基期不足；请先补齐观测数据，再判断经营变化。'
        elif delta==0: conclusion='本期播放／浏览与前期持平。'
        else:
            lead=ranked[0] if delta<0 else ranked[-1];contributors=sorted([cr for cr in cs if cr['country']==lead['country']],key=lambda cr:cr['current']['views']-cr['baseline']['views'],reverse=delta>0)[:2]
            conclusion=f"本期播放／浏览{'下降' if delta<0 else '增长'} {abs(delta):,}，{'拖累' if delta<0 else '增长贡献'}最大的是{lead['name']}（{lead['contribution']:+,}），重点查看 {'、'.join(cr['name'] for cr in contributors)}。"
        last=c.execute("SELECT created FROM runs WHERE kind NOT IN ('seed','sync-failed') ORDER BY id DESC LIMIT 1").fetchone()
        return dict(start=str(start),end=str(end),grain=grain,baseline_start=str(bs),baseline_end=str(be),current=totals,baseline=base,complete=complete,baseline_complete=baseline_complete,conclusion=conclusion,countries=countries,creators=cs,trend=trend(current,start,end,grain),commerce=commerce(c,start,end,ids if q.get('platform') or q.get('country') or q.get('creator_id') else None,True,cache),last_sync=last[0] if last else None,country_names=COUNTRIES)

def content_detail(q):
    start,end,grain=period(q);cid=q.get('creator_id');content_id=q.get('content_id')
    with core.connect() as c:
        items=rows(c,'SELECT x.*,c.name,c.platform,c.country FROM contents x JOIN creators c ON c.id=x.creator_id WHERE substr(published_at,1,10)<=?',(str(end),))
        items=[r for r in items if (not cid or r['creator_id']==cid) and (not content_id or r['id']==content_id) and (not q.get('platform') or r['platform']==q['platform']) and (not q.get('country') or r['country']==q['country'])]
        out=[]
        for item in items:
            snaps=rows(c,'SELECT * FROM content_snapshots WHERE content_id=? AND date<=? ORDER BY date',(item['id'],str(end)))
            prior=next((r for r in reversed(snaps) if r['date']<str(start)),None);last=snaps[-1] if snaps else None
            if not content_id and item['published_at'][:10]<str(start) and not any(r['date']>=str(start) for r in snaps):continue
            values={}
            for key in ('views','likes','comments','shares','saves','organic_views','paid_views'):
                values[key]=max(0,last[key]-((prior[key] or 0) if prior else 0)) if last and last[key] is not None and (prior is not None or item['published_at'][:10]>=str(start)) and (not prior or prior[key] is not None) else None
            item.update(values=values,lifetime={k:last[k] for k in values} if last else {},snapshot_date=last['date'] if last else None)
            if content_id:
                daily=[];prev=None
                for s in snaps:
                    if s['date']>=str(start) and s['views'] is not None and (prev is not None or item['published_at'][:10]>=str(start)): daily.append({'creator_id':item['creator_id'],'date':s['date'],'posts':0,'views':max(0,s['views']-((prev['views'] or 0) if prev else 0)) if s['views'] is not None else 0})
                    prev=s
                comments=rows(c,'SELECT * FROM comments WHERE content_id=? AND date BETWEEN ? AND ?',(item['id'],str(start),str(end)))
                topics=collections.Counter(r['topic'] or '其他' for r in comments);words=collections.Counter()
                stop={'the','this','and','for','are','can','from','with','that','like','please','would','where','share','love','my','so','it','is','a','i','to','of','in'}
                for r in comments:
                    for word in re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{2,}',r['text'].lower()):
                        if word not in stop:words[word]+=1
                item.update(trend=trend(daily,start,end,grain),comment_samples=comments,topics=[{'name':k,'count':v,'share':v/len(comments)} for k,v in topics.most_common()],words=[{'text':k,'count':v} for k,v in words.most_common(28)])
            out.append(item)
        return {'contents':sorted(out,key=lambda x:x['published_at'],reverse=True),'start':str(start),'end':str(end)}

def discoveries(q):
    start,end,_=period(q)
    with core.connect() as c:
        covered={r[0] for r in c.execute("SELECT DISTINCT country FROM creators WHERE status IN ('签约中','试合作')")}
        known={(r[0],r[1].lower()) for r in c.execute('SELECT platform,handle FROM accounts')}
        weights=json.loads(c.execute("SELECT value FROM settings WHERE key='weights'").fetchone()[0]);items=rows(c,'SELECT * FROM candidates')
        for r in items:
            r['uncovered']=r['country'] not in covered and r['country']!='UNKNOWN';r['pending']=any(r[k] is None for k in ('growth','er','stability','fit','posts','followers'))
            scores={'growth':min(1,(r['growth'] or 0)/.3),'engagement':min(1,(r['er'] or 0)/.08),'stability':r['stability'] or 0,'fit':r['fit'] or 0,'coverage':int(r['uncovered'])}
            r['score']=None if r['pending'] else round(sum(scores[k]*weights[k] for k in weights)/sum(weights.values())*100,1)
            r['recommendation']='待评估' if r['pending'] else '优先联系' if r['score']>=65 else '持续观察' if r['score']>=45 else '暂缓'
            r['evidence']=[f"近期增长 {(r['growth'] or 0)*100:.1f}% · 互动率 {(r['er'] or 0)*100:.1f}%",'可补充未覆盖国家' if r['uncovered'] else '现有国家可补充内容供给']
            r['next_action']='补齐缺失指标' if r['pending'] else '联系并确认合作意向' if r['recommendation']=='优先联系' else '观察下一周发布与增长' if r['recommendation']=='持续观察' else '保留档案，暂缓联系'
            r['history']=rows(c,'SELECT created,detail FROM candidate_history WHERE candidate_id=? ORDER BY id DESC LIMIT 8',(r['id'],))
        items=[r for r in items if (r['platform'],r['handle'].lower()) not in known and r['discovered_at'][:10]<=str(end) and (not q.get('platform') or r['platform']==q['platform']) and (not q.get('country') or r['country']==q['country'])]
        return {'candidates':sorted(items,key=lambda r:(not r['uncovered'],-(r['score'] or -1))), 'weights':weights,'covered':sorted(covered)}

def update_candidate(b):
    with core.connect() as c:
        r=c.execute('SELECT * FROM candidates WHERE id=?',(b['id'],)).fetchone()
        if not r:raise ValueError('达人不存在')
        favorite=int(bool(b.get('favorite',r['favorite'])));owner=str(b.get('owner',r['owner'])).strip()[:60];status=b.get('status',r['status'])
        if status not in ('待评估','待联系','已联系','洽谈中','暂缓','已转入'):raise ValueError('无效联系状态')
        c.execute('UPDATE candidates SET favorite=?,owner=?,status=? WHERE id=?',(favorite,owner,status,r['id']))
        if b.get('promote'):
            if not owner:raise ValueError('转入试合作前请填写负责人')
            existing=c.execute('SELECT creator_id FROM accounts WHERE platform=? AND lower(handle)=?',(r['platform'],r['handle'].lower())).fetchone()
            cid=existing[0] if existing else 'EXT-'+r['id']
            if not existing:
                c.execute('INSERT INTO creators VALUES(?,?,?,?,?,?,?,?)',(cid,r['name'],r['platform'],r['country'],'C','试合作',owner,r['topic']))
                c.execute('INSERT INTO accounts VALUES(?,?,?,?)',(cid,r['platform'],r['handle'].lower(),r['url']))
            c.execute("UPDATE candidates SET status='已转入' WHERE id=?",(r['id'],));status='已转入'
        c.execute('INSERT INTO candidate_history(candidate_id,created,detail) VALUES(?,?,?)',(r['id'],now(),f'状态：{status}；负责人：{owner or "未分配"}；收藏：{favorite}'))
    return {'ok':True}

# Import contracts intentionally use explicit allowlists. All rows validate inside one transaction.
CONTRACTS={
 'profiles':('creators',['id','name','platform','country','tier','status','owner','topic'],['id','name','platform','country','tier','status','owner','topic']),
 'accounts':('accounts',['creator_id','platform','handle','url'],['creator_id','platform','handle']),
 'contents':('contents',['id','creator_id','published_at','kind','title','url','source'],['id','creator_id','published_at']),
 'snapshots':('content_snapshots',['content_id','date','views','likes','comments','shares','saves','organic_views','paid_views','source'],['content_id','date']),
 'comments':('comments',['id','content_id','date','text','topic','source'],['id','content_id','date','text']),
 'candidates':('candidates',['id','platform','handle','country','topic','name','followers','posts','growth','er','stability','fit','url','discovered_at','source'],['id','platform','handle','name','discovered_at']),
 'campaigns':('campaigns',['id','creator_id','content_id','platform','country','tracking_code','invite_code'],['id','creator_id']),
 'heating':('heating',['id','date','creator_id','content_id','campaign_id','currency','spend','impressions','paid_views','clicks','visits','registrations','source'],['id','date','currency']),
 'conversions':('conversions',['id','date','creator_id','campaign_id','tracking_code','invite_code','user_id','order_id','kind','amount','refund','currency','status','attribution','source','tracking_url'],['id','date','kind','currency'])}
NUMBERS={'views','likes','comments','shares','saves','organic_views','paid_views','followers','posts','spend','impressions','clicks','visits','registrations','growth','er','stability','fit','amount','refund'}
DECIMALS={'spend','growth','er','stability','fit','amount','refund'}

def resolve(c,r):
    choices=set();invalid=False
    if r.get('tracking_url'):
        parsed=urllib.parse.urlparse(str(r['tracking_url']))
        if parsed.scheme not in ('https','http'):raise ValueError('追踪链接须使用HTTP或HTTPS')
        parameters=urllib.parse.parse_qs(parsed.query)
        for key in ('creator_id','campaign_id','tracking_code','invite_code'):
            for value in parameters.get(key,[]):
                mapped,reason=resolve(c,{key:value})
                if reason!='matched':invalid=True
                elif mapped:choices.add(mapped)
    if r.get('creator_id'):
        if c.execute('SELECT 1 FROM creators WHERE id=?',(r['creator_id'],)).fetchone(): choices.add(r['creator_id'])
        else: invalid=True
    for field,column in [('campaign_id','id'),('tracking_code','tracking_code'),('invite_code','invite_code')]:
        if r.get(field):
            found=c.execute(f'SELECT creator_id FROM campaigns WHERE {column}=?',(r[field],)).fetchone()
            if found: choices.add(found[0])
            else: invalid=True
    return (next(iter(choices)),'matched') if len(choices)==1 and not invalid else (None,'conflict' if len(choices)>1 or invalid else 'unattributed')

def import_records(kind,records,source='import'):
    if kind not in CONTRACTS:raise ValueError('不支持的数据类型')
    if not isinstance(records,list) or not records or len(records)>50000:raise ValueError('请提供1至50000条记录')
    table,columns,required=CONTRACTS[kind];seen=set();count=0
    with core.connect() as c:
        for raw in records:
            if not isinstance(raw,dict):raise ValueError('记录须为对象')
            r={k:(None if raw.get(k) in ('',None) else raw[k]) for k in columns};r['source']=source if 'source' in columns else None
            for key in required:
                if r.get(key) is None:raise ValueError('缺少字段：'+key)
            for key in ('date','discovered_at','published_at'):
                if r.get(key):dt.date.fromisoformat(str(r[key])[:10])
            for key in NUMBERS & set(columns):
                if r.get(key) is None:continue
                value=float(r[key])
                if not math.isfinite(value) or (value<0 and key!='growth') or (key not in DECIMALS and value!=int(value)):raise ValueError('无效数值：'+key)
                if key in ('er','stability','fit') and value>1:raise ValueError(key+'须在0与1之间')
                r[key]=value if key in DECIMALS else int(value)
            if r.get('currency') and not re.fullmatch('[A-Z]{3}',str(r['currency'])):raise ValueError('币种须为三位大写代码')
            if kind in ('profiles','accounts','candidates'):
                if r['platform'] not in PLATFORMS:raise ValueError('无效平台')
            if kind=='profiles':
                if r['tier'] not in ('A','B','C') or r['status'] not in ('签约中','试合作','已终止'):raise ValueError('无效合作状态或分层')
            if kind=='accounts':
                cr=c.execute('SELECT platform FROM creators WHERE id=?',(r['creator_id'],)).fetchone()
                if not cr or cr[0]!=r['platform']:raise ValueError('账号平台须与创作者档案一致')
                r['handle']=str(r['handle']).lstrip('@').lower()
            if kind=='candidates':
                if r['platform'] not in PLATFORMS:raise ValueError('无效平台')
                r['handle']=str(r['handle']).lstrip('@').lower();r['country']=r['country'] or 'UNKNOWN'
                existing=c.execute('SELECT id FROM candidates WHERE platform=? AND lower(handle)=?',(r['platform'],r['handle'])).fetchone()
                if existing:r['id']=existing[0]
            if kind in ('contents','campaigns') and not c.execute('SELECT 1 FROM creators WHERE id=?',(r['creator_id'],)).fetchone():raise ValueError('未知创作者')
            if kind in ('snapshots','comments') and not c.execute('SELECT 1 FROM contents WHERE id=?',(r['content_id'],)).fetchone():raise ValueError('未知内容')
            if r.get('url') and not str(r['url']).startswith(('https://','http://')):raise ValueError('内容链接须使用HTTP或HTTPS')
            if kind=='contents' and r['kind'] not in ('视频','图文','文字'):raise ValueError('内容类型须为视频、图文或文字')
            if kind=='snapshots':
                # Cumulative counters must be monotonic relative to both neighbors.
                for key in NUMBERS & set(columns):
                    if r.get(key) is None:continue
                    older=c.execute(f'SELECT {key} FROM content_snapshots WHERE content_id=? AND date<? AND {key} IS NOT NULL ORDER BY date DESC LIMIT 1',(r['content_id'],r['date'])).fetchone()
                    newer=c.execute(f'SELECT {key} FROM content_snapshots WHERE content_id=? AND date>? AND {key} IS NOT NULL ORDER BY date LIMIT 1',(r['content_id'],r['date'])).fetchone()
                    if older and r[key]<older[0] or newer and r[key]>newer[0]:raise ValueError('累计快照回退或超过后续快照：'+key)
                if all(r.get(k) is not None for k in ('organic_views','paid_views','views')) and r['organic_views']+r['paid_views']!=r['views']:raise ValueError('自然与付费播放之和须等于总播放')
            if kind=='heating':
                r['creator_id'],attrib=resolve(c,r)
                if attrib=='conflict':raise ValueError('加热记录的创作者与活动标识冲突')
                for key in ('spend','impressions','paid_views','clicks','visits','registrations'):r[key]=r[key] or 0
                if r.get('content_id'):
                    found=c.execute('SELECT creator_id FROM contents WHERE id=?',(r['content_id'],)).fetchone()
                    if not found or found[0]!=r['creator_id']:raise ValueError('加热内容与创作者不匹配')
            if kind=='conversions':
                r['creator_id'],r['attribution']=resolve(c,r)
                if r['kind'] not in ('new_user','order'):raise ValueError('转化类型须为new_user或order')
                r['amount']=r['amount'] or 0;r['refund']=r['refund'] or 0;r['status']=r['status'] or ('paid' if r['kind']=='order' else 'registered')
                if r['status'] not in ('paid','pending','cancelled','registered'):raise ValueError('无效支付状态')
                if r['refund']>r['amount']:raise ValueError('退款不能超过支付金额')
                ident='order_id' if r['kind']=='order' else 'user_id'
                if not r.get(ident):raise ValueError('缺少去重标识：'+ident)
                old=c.execute(f'SELECT id FROM conversions WHERE kind=? AND {ident}=?',(r['kind'],r[ident])).fetchone()
                if old:r['id']=old[0]
            if kind=='campaigns' and r.get('content_id'):
                item=c.execute('SELECT creator_id FROM contents WHERE id=?',(r['content_id'],)).fetchone()
                if not item or item[0]!=r['creator_id']:raise ValueError('活动内容与创作者不匹配')
            pk=('content_id','date') if kind=='snapshots' else ('creator_id',) if kind=='accounts' else ('id',)
            signature=tuple(r[k] for k in pk)
            if signature in seen:raise ValueError('批次内存在重复主键')
            seen.add(signature)
            updates=','.join(f'{col}=excluded.{col}' for col in columns if col not in pk)
            c.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) ON CONFLICT({','.join(pk)}) DO UPDATE SET {updates}",[r.get(col) for col in columns]);count+=1
            if kind=='candidates':c.execute('INSERT INTO candidate_history(candidate_id,created,detail) VALUES(?,?,?)',(r['id'],now(),'同步公开账号指标'))
        c.execute('INSERT INTO runs(created,kind,detail) VALUES(?,?,?)',(now(),source,f'{kind}：写入 {count} 条记录'))
    return {'rows':count}

def set_weights(b):
    values=b.get('weights',{})
    if set(values)!=set(DEFAULT_WEIGHTS):raise ValueError('权重字段须为growth/engagement/stability/fit/coverage')
    values={k:float(v) for k,v in values.items()}
    if any(not math.isfinite(v) or v<0 for v in values.values()) or sum(values.values())<=0:raise ValueError('权重须为非负且总和大于0')
    with core.connect() as c:c.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(values),'weights'))
    return {'ok':True}

def metadata():
    with core.connect() as c:
        names=dict(COUNTRIES)
        for cr in c.execute('SELECT DISTINCT country FROM creators UNION SELECT DISTINCT country FROM candidates'):
            if cr[0]:names.setdefault(cr[0],cr[0])
        return {'latest':latest_date(c), 'countries':names,'platforms':PLATFORMS,'runs':rows(c,'SELECT * FROM runs ORDER BY id DESC LIMIT 20'),'contracts':{k:{'columns':v[1],'required':v[2]} for k,v in CONTRACTS.items()},'configured':{p:bool(__import__('os').getenv(p.upper()+'_DATASET_ID') and __import__('os').getenv('APIFY_TOKEN')) for p in PLATFORMS}}
