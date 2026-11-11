import sqlite3, json, random, math, datetime, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Local configuration is shared by interactive startup and scheduled sync.
config=ROOT/'.env'
if config.is_file():
    for line in config.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line:continue
        key,value=line.split('=',1);key=key.strip()
        if key.startswith(('APIFY_','TIKTOK_','THREADS_','INSTAGRAM_','LLM_','CREATOR_')) or key=='PORT':os.environ.setdefault(key,value.strip().strip("\"'"))
DB=Path(os.getenv('CREATOR_DB',str(ROOT/'data/platform.db')))
END=datetime.date(2026,11,9)
class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()

def connect():
    c=sqlite3.connect(DB,factory=ClosingConnection); c.row_factory=sqlite3.Row; return c

def init():
    DB.parent.mkdir(parents=True,exist_ok=True)
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS creators(id TEXT PRIMARY KEY,name TEXT,platform TEXT,country TEXT,tier TEXT,status TEXT,owner TEXT,topic TEXT);
        CREATE TABLE IF NOT EXISTS metrics(creator_id TEXT,date TEXT,posts INTEGER,views INTEGER,engagements INTEGER,source TEXT,PRIMARY KEY(creator_id,date));
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,creator_id TEXT,title TEXT,owner TEXT,status TEXT DEFAULT '待执行',feedback TEXT DEFAULT '',created TEXT);
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,created TEXT,kind TEXT,detail TEXT);
        CREATE TABLE IF NOT EXISTS diagnoses(id INTEGER PRIMARY KEY,creator_id TEXT,created TEXT,payload TEXT);''')
        if c.execute('SELECT COUNT(*) FROM creators').fetchone()[0]:
            from workspace import migrate
            migrate(c)
            return
        rng=random.Random(20261110)
        names=['Mila Studio','Noah Finds','Luna Travels','Arlo Kitchen','Ivy Design','Theo Fit','Nova Daily','Leo Lens','Ella Garden','Finn Style','Maya Crafts','Hugo Tech','Zoe Books','Kai Living','Ada Beauty','Owen Runs','Nina Art','Ezra Eats','Ruby Home','Luca Sound','Isla Play','Eli Green','Ava Motion','Jude Notes']
        for i,name in enumerate(names):
            cid=f'C{i+1:03d}';base=8000+i*1600
            c.execute('INSERT INTO creators VALUES(?,?,?,?,?,?,?,?)',(cid,name,['TikTok','Threads'][i%2],['US','UK','ID','TH'][i%4],['A','B','C'][i%3],'签约中' if i%6 else '试合作',['Sienna','Alex','Morgan'][i%3],['生活方式','美食','旅行','科技'][i%4]))
            for d in range(42):
                day=END-datetime.timedelta(days=41-d); posts=2;vpp=base*rng.uniform(.88,1.12);rate=.045*rng.uniform(.93,1.07)
                if d>=35:
                    if i in [0,8]:vpp*=.43
                    if i in [1,9]:posts=0 if d%2 else 1
                    if i in [2,10]:rate*=.40
                    if i in [3,11]:continue
                views=round(vpp*posts);eng=round(views*rate)
                c.execute('INSERT INTO metrics VALUES(?,?,?,?,?,?)',(cid,str(day),posts,views,eng,'synthetic-v1'))
        c.execute('INSERT INTO runs(created,kind,detail) VALUES(?,?,?)',(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'seed','固定随机种子；24个虚构账号；42日；8个注入异常'))

        from workspace import migrate
        migrate(c)

def creators():
    with connect() as c:return [dict(x) for x in c.execute('SELECT * FROM creators ORDER BY id')]

def history(cid):
    with connect() as c:return [dict(x) for x in c.execute('SELECT * FROM metrics WHERE creator_id=? ORDER BY date',(cid,))]

def summarize(rows):
    p=sum(x['posts'] for x in rows);v=sum(x['views'] for x in rows);e=sum(x['engagements'] for x in rows)
    return dict(days=len(rows),posts=p,views=v,engagements=e,vpp=v/p if p else None,er=e/v if v else None)

def change(a,b):return a/b-1 if b and a is not None else None

def diagnose(rows,end,threshold=.25):
    if not math.isfinite(threshold) or not 0 < threshold < 1:raise ValueError('异常阈值须在0与1之间')
    end=datetime.date.fromisoformat(str(end)); current=[x for x in rows if end-datetime.timedelta(days=6)<=datetime.date.fromisoformat(x['date'])<=end];before=[x for x in rows if end-datetime.timedelta(days=13)<=datetime.date.fromisoformat(x['date'])<=end-datetime.timedelta(days=7)]
    a,b=summarize(current),summarize(before); delta={k:change(a[k],b[k]) for k in ['posts','views','vpp','er']}
    flags=[]
    if a['days']<7 or b['days']<7:flags=['data_gap']
    elif b['posts']<3 or b['views']<1000:flags=['low_sample']
    else:
        if delta['posts'] is not None and delta['posts'] < -threshold:flags.append('cadence_drop')
        if delta['vpp'] is not None and delta['vpp'] < -threshold:flags.append('reach_drop')
        if delta['er'] is not None and delta['er'] < -threshold:flags.append('engagement_drop')
    return dict(current=a,baseline=b,delta=delta,flags=flags,window_end=str(end),threshold=threshold)

LABEL={'data_gap':'采集缺口','low_sample':'样本不足','cadence_drop':'发布节奏下降','reach_drop':'单帖触达下降','engagement_drop':'互动率下降'}
ACTIONS={'data_gap':'核对采集任务日志并补齐缺失日期；补齐前暂停经营归因','low_sample':'延长观察窗口，避免小样本误判','cadence_drop':'与创作者核对本周排期，确认缺发原因并补充下周内容计划','reach_drop':'对比最近两周选题与发布时间，抽查低触达内容；先做小规模内容测试','engagement_drop':'复查互动统计口径，并抽样检查评论主题与内容匹配度'}

def rule_advice(cid,d):
    flags=d['flags']; return dict(mode='规则建议',summary='；'.join(LABEL[f] for f in flags) if flags else '本期未触发异常阈值',actions=[dict(title=ACTIONS[f],evidence=f,priority='P0' if f=='data_gap' else 'P1') for f in flags],caveat='这些是相关性诊断与待验证假设，不能证明平台限流或内容变化的因果关系。',trace=[{'tool':'get_creator_metrics','creator_id':cid},{'tool':'get_anomaly_evidence','flags':flags}])

def state(end=None,threshold=.25):
    with connect() as c:
        latest=c.execute('SELECT MAX(date) FROM metrics').fetchone()[0]
    end=end or latest or str(END); cs=creators();allrows=[]
    for x in cs:
        rows=history(x['id']); allrows+=rows;x['diagnosis']=diagnose(rows,end,threshold)
    with connect() as c:
        tasks=[dict(x) for x in c.execute('SELECT * FROM tasks ORDER BY id DESC')];runs=[dict(x) for x in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 10')]
    return dict(creators=cs,tasks=tasks,runs=runs,history=allrows,end=end,synthetic=True)

def ingest(rows,source='csv'):
    clean=[]; keys=set(); known={x['id'] for x in creators()}
    for r in rows:
        cid=str(r['creator_id']);day=str(r['date']);datetime.date.fromisoformat(day)
        if cid not in known:raise ValueError('未知 creator_id: '+cid)
        nums=[]
        for k in ['posts','views','engagements']:
            n=float(r[k])
            if not math.isfinite(n) or n<0 or n!=int(n):raise ValueError('指标必须为非负整数: '+k)
            nums.append(int(n))
        key=(cid,day)
        if key in keys:raise ValueError('本批次存在重复日期，请先去重')
        keys.add(key);clean.append((cid,day,*nums,source))
    if not clean:raise ValueError('没有可导入的数据')
    with connect() as c:
        c.executemany('INSERT INTO metrics VALUES(?,?,?,?,?,?) ON CONFLICT(creator_id,date) DO UPDATE SET posts=excluded.posts,views=excluded.views,engagements=excluded.engagements,source=excluded.source',clean)
        c.execute('INSERT INTO runs(created,kind,detail) VALUES(?,?,?)',(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),source,f'成功写入 {len(clean)} 行'))
    return len(clean)
