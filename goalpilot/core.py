import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]

class UserError(Exception): pass

class Store:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(project_id) WHERE status IN ('queued','running');
            CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, project_id TEXT, at REAL, action TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, enabled INTEGER NOT NULL, next_run REAL NOT NULL, body TEXT NOT NULL);
            ''')
    @contextmanager
    def db(self):
        conn=sqlite3.connect(self.path,timeout=20); conn.row_factory=sqlite3.Row
        try:
            with conn: yield conn
        finally: conn.close()
    def event(self, project_id, action, status):
        with self.db() as db: db.execute('INSERT INTO events(project_id,at,action,status) VALUES(?,?,?,?)',(project_id,time.time(),action,status))
    def put(self, table, body):
        if table not in ('projects','artifacts'): raise ValueError('Invalid table')
        with self.db() as db:
            if table=='projects': db.execute('INSERT OR REPLACE INTO projects VALUES(?,?)',(body['id'],json.dumps(body)))
            else: db.execute('INSERT OR REPLACE INTO artifacts VALUES(?,?,?)',(body['id'],body['project_id'],json.dumps(body)))
    def get(self, table, id):
        if table not in ('projects','artifacts'): raise ValueError('Invalid table')
        with self.db() as db: row=db.execute(f'SELECT body FROM {table} WHERE id=?',(id,)).fetchone()
        if not row: raise UserError('Item not found')
        return json.loads(row['body'])
    def all(self, table, project_id=None):
        if table not in ('projects','artifacts','jobs','schedules'): raise ValueError('Invalid table')
        with self.db() as db:
            if project_id: rows=db.execute(f'SELECT body FROM {table} WHERE project_id=? ORDER BY rowid DESC',(project_id,)).fetchall()
            else: rows=db.execute(f'SELECT body FROM {table} ORDER BY rowid DESC').fetchall()
        return [json.loads(r['body']) for r in rows]
    def events(self, project_id):
        with self.db() as db: return [dict(r) for r in db.execute('SELECT at,action,status FROM events WHERE project_id=? ORDER BY id DESC LIMIT 100',(project_id,))]
    def enqueue(self, project_id, demo=False, allow_model=False):
        project=self.get('projects',project_id)
        if questions(project): raise UserError('Answer the required intake questions first')
        job={'id':uuid.uuid4().hex,'project_id':project_id,'status':'queued','created_at':time.time(),'demo':bool(demo),'allow_model':bool(allow_model),'project_snapshot':project}
        try:
            with self.db() as db: db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(job['id'],project_id,'queued',json.dumps(job)))
        except sqlite3.IntegrityError: raise UserError('This project already has an active run') from None
        self.event(project_id,'run queued','demo' if demo else 'live'); return job
    def claim(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT body FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row: return None
            job=json.loads(row['body']); job['status']='running'
            db.execute('UPDATE jobs SET status=?,body=? WHERE id=?',('running',json.dumps(job),job['id']))
        return job
    def finish(self, job, status, error=None):
        job.update(status=status,finished_at=time.time())
        if error: job['error']=error
        with self.db() as db: db.execute('UPDATE jobs SET status=?,body=? WHERE id=?',(status,json.dumps(job),job['id']))
        self.event(job['project_id'],'run finished',status)
    def recover(self):
        # A paid provider request may have completed before a crash. Never auto-retry.
        for job in self.all('jobs'):
            if job['status']=='running': self.finish(job,'interrupted','Server restarted; review before retrying')
    def artifact(self, project_id, text, demo=False):
        item={'id':uuid.uuid4().hex,'project_id':project_id,'text':text,'sha256':digest(text),'created_at':time.time(),'demo':demo,'approval':None}
        self.put('artifacts',item); self.event(project_id,'draft created','fixture' if demo else 'review required'); return item
    def approve(self, id, expected_hash):
        item=self.get('artifacts',id)
        if item['sha256']!=expected_hash or digest(item['text'])!=expected_hash: raise UserError('Draft changed; review the current version')
        if item['demo']: raise UserError('Demo artifacts cannot be approved as real deliverables')
        item['approval']={'APPROVED':True,'sha256':expected_hash,'at':time.time(),'scope':'reviewed draft only; no external publication','approver':'local owner'}
        self.put('artifacts',item); self.event(item['project_id'],'draft reviewed','approved for export only'); return item


def digest(text): return hashlib.sha256(text.encode()).hexdigest()

def classify(goal):
    words=goal.lower()
    if any(w in words for w in ('youtube','video','reel','shorts','channel','script')): return 'video'
    if any(w in words for w in ('seo','rank','website','organic','search traffic')): return 'seo'
    return 'custom'


def create_project(data):
    goal=str(data.get('goal','')).strip()
    if not 8<=len(goal)<=4000: raise UserError('Describe your goal in 8–4000 characters')
    kind=data.get('kind','auto')
    if kind=='auto': kind=classify(goal)
    if kind not in ('seo','video','custom'): raise UserError('Unknown workflow')
    return {'id':uuid.uuid4().hex,'goal':goal,'kind':kind,'title':goal[:70], 'created_at':time.time(),
            'inputs':{},'plan':default_plan(kind)}


def default_plan(kind):
    if kind=='seo': return ['Inspect permitted public pages, robots.txt and sitemap','Identify technical issues with dated URL evidence','Record missing analytics and business facts','Prepare a prioritised audit for review']
    if kind=='video': return ['Clarify audience, topic and supported facts','Review supplied reference transcript or shot notes','Create an original script, shot list and handoff prompt','Review claims, assets and publication requirements']
    return ['Clarify the desired outcome and constraints','Choose a supported workflow or write a manual brief','Review required integrations before execution']


def questions(project):
    required={'seo':{'website':'Which public website should I audit?','audience':'Who is the target audience and market?'},
              'video':{'topic':'What topic or niche should the video cover?','audience':'Who should watch it?','facts':'Which facts or source notes may the script use?'},
              'custom':{'outcome':'What concrete deliverable do you want?'}}
    return [{'key':k,'question':v} for k,v in required[project['kind']].items() if not str(project['inputs'].get(k,'')).strip()]


def integrations(project):
    if project['kind']=='custom': return [{'name':'Manual brief','status':'available','purpose':'Organise a custom goal without external requests','required_now':True,'setup':'No general-purpose executor is implemented in v0.1.'}]
    if project['kind']=='seo': return [
        {'name':'Public site crawler','status':'available','purpose':'Read-only HTML, robots and sitemap checks','required_now':True},
        {'name':'Search Console + GA4','status':'planned','purpose':'Search and sales measurement; reporting-only OAuth scopes','required_now':False,'setup':'Analytics adapters are not implemented in v0.1; never treat missing metrics as zero'},
        {'name':'Repository access','status':'planned','purpose':'Prepare website changes as reviewable PRs','required_now':False}]
    return [{'name':'OpenAI-compatible model','status':'configured' if model_ready() else 'needs_configuration','purpose':'Generate an original video script from supplied notes','required_now':True,
             'setup':'Set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in the server environment. Review the destination and provider costs. A run also requires explicit model-call consent.'},
            {'name':'Search / transcript / video analysis','status':'planned','purpose':'Independent research and audiovisual inspection','required_now':False,'setup':'v0.1 uses supplied notes/transcripts; it does not watch videos or scrape YouTube'},
            {'name':'YouTube / Instagram publishing','status':'planned','purpose':'Upload approved rendered assets','required_now':False,'setup':'No publishing adapter exists in v0.1; do not supply social credentials yet'}]


def model_ready(): return all(os.environ.get(k) for k in ('LLM_BASE_URL','LLM_MODEL','LLM_API_KEY'))
