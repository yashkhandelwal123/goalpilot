import json
import threading
import time
import uuid
from pathlib import Path
from .core import ROOT,Store,UserError,create_project,questions,integrations,digest
from .workflows import seo,video

class Service:
    def __init__(self,path=None,root=ROOT):
        self.root=Path(root);self.store=Store(path or self.root/'runtime/goalpilot.sqlite3');self.stop=threading.Event()
        self.store.recover()
    def check(self):
        if (self.root/'PAUSE').exists():raise UserError('PAUSE is present; runs, edits and scheduling are stopped')
    def list_projects(self):return [self.view(p['id']) for p in self.store.all('projects')]
    def view(self,id):
        p=self.store.get('projects',id)
        return {**p,'questions':questions(p),'integrations':integrations(p),'artifacts':self.store.all('artifacts',id),
                'jobs':self.store.all('jobs',id),'schedules':self.store.all('schedules',id),'events':self.store.events(id)}
    def create(self,data):
        self.check();p=create_project(data);self.store.put('projects',p);self.store.event(p['id'],'project created',p['kind']);return self.view(p['id'])
    def update(self,id,data):
        self.check();p=self.store.get('projects',id)
        inputs=data.get('inputs',{})
        if not isinstance(inputs,dict):raise UserError('Inputs must be an object')
        allowed={'website','audience','topic','facts','reference','language','outcome'}
        for k,v in inputs.items():
            if k not in allowed or not isinstance(v,str) or len(v)>12000:raise UserError('Invalid input field or input too long')
        p['inputs'].update(inputs)
        if 'plan' in data:
            if not isinstance(data['plan'],list) or not 1<=len(data['plan'])<=12 or any(not isinstance(v,str) or not v.strip() or len(v)>300 for v in data['plan']):raise UserError('Plan needs 1–12 short task descriptions')
            p['plan']=data['plan']
        self.store.put('projects',p);self.store.event(id,'intake and plan saved','existing drafts remain immutable; new input applies to future runs');return self.view(id)
    def run(self,id,data):
        self.check()
        if type(data.get('demo',False)) is not bool or type(data.get('allow_model',False)) is not bool:raise UserError('Consent fields must be boolean')
        return self.store.enqueue(id,data.get('demo',False),data.get('allow_model',False))
    def approve(self,id,data):
        self.check();return self.store.approve(id,data.get('sha256'))
    def schedule(self,id,data):
        self.check();p=self.store.get('projects',id)
        if questions(p):raise UserError('Complete intake before scheduling')
        if p['kind']=='custom':raise UserError('Custom workflow is manual-only in v0.1')
        if data.get('APPROVED') is not True:raise UserError('Explicit approval is required to schedule draft generation')
        if not isinstance(data.get('demo',False),bool) or data.get('demo',False) is not True:
            if p['kind']=='video':raise UserError('Paid model schedules are disabled in v0.1; run live video drafts manually')
        interval=data.get('interval_hours',24)
        if type(interval) is not int or not 1<=interval<=168:raise UserError('Choose an interval from 1 to 168 hours')
        s={'id':uuid.uuid4().hex,'project_id':id,'enabled':True,'next_run':time.time()+interval*3600,'interval_hours':interval,
           'runs':0,'max_runs':7,'expires_at':time.time()+7*86400,'demo':bool(data.get('demo',False)),
           'approved_input_sha256':digest(json.dumps(p,sort_keys=True)), 'scope':'Generate drafts only; no publication','APPROVED':True}
        with self.store.db() as db:
            previous=db.execute('SELECT body FROM schedules WHERE project_id=? AND enabled=1',(id,)).fetchall()
            for row in previous:
                old=json.loads(row['body']);old['enabled']=False
                db.execute('UPDATE schedules SET enabled=0,body=? WHERE id=?',(json.dumps(old),old['id']))
            db.execute('INSERT INTO schedules VALUES(?,?,?,?,?)',(s['id'],id,1,s['next_run'],json.dumps(s)))
        self.store.event(id,'schedule approved','draft-only; max 7 runs; expires in 7 days');return s
    def disable_schedule(self,id):
        # Disabling is always allowed, including while PAUSE is present.
        with self.store.db() as db:
            row=db.execute('SELECT body FROM schedules WHERE id=?',(id,)).fetchone()
            if not row:raise UserError('Schedule not found')
            s=json.loads(row['body']);s['enabled']=False
            db.execute('UPDATE schedules SET enabled=0,body=? WHERE id=?',(json.dumps(s),id))
        self.store.event(s['project_id'],'schedule disabled','owner request');return s
    def tick(self):
        self.check()
        # Acquire schedule row and enqueue under one transaction; restart-safe and no overlapping claims.
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT * FROM schedules WHERE enabled=1 AND next_run<=?',(time.time(),)).fetchall()
            for row in rows:
                s=json.loads(row['body']);p=self.store.get('projects',s['project_id'])
                valid=s['APPROVED'] is True and s['expires_at']>time.time() and s['runs']<s['max_runs'] and digest(json.dumps(p,sort_keys=True))==s['approved_input_sha256']
                if not valid:s['enabled']=False
                else:
                    active=db.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('queued','running')",(p['id'],)).fetchone()
                    if not active:
                        j={'id':uuid.uuid4().hex,'project_id':p['id'],'status':'queued','created_at':time.time(),'demo':s['demo'],'allow_model':False,'project_snapshot':p}
                        db.execute('INSERT INTO jobs VALUES(?,?,?,?)',(j['id'],p['id'],'queued',json.dumps(j)));s['runs']+=1
                        db.execute('INSERT INTO events(project_id,at,action,status) VALUES(?,?,?,?)',(p['id'],time.time(),'schedule queued a run','draft-only'))
                    s['next_run']=time.time()+s['interval_hours']*3600
                    if s['runs']>=s['max_runs']:s['enabled']=False
                db.execute('UPDATE schedules SET enabled=?,next_run=?,body=? WHERE id=?',(int(s['enabled']),s['next_run'],json.dumps(s),s['id']))
    def process_one(self):
        self.check();job=self.store.claim()
        if not job:return False
        try:
            self.check();p=job['project_snapshot']
            event=lambda action,status:self.store.event(p['id'],action,status)
            if p['kind']=='seo':text=seo(p,job['demo'],self.check,event)
            elif p['kind']=='video':text=video(p,job['demo'],job['allow_model'],self.check,event)
            else:text='# Manual project brief\n\n'+json.dumps({'goal':p['goal'],'inputs':p['inputs'],'plan':p['plan']},indent=2)+'\n\nNo general-purpose tool executor is implemented in v0.1.'
            self.check();self.store.artifact(p['id'],text,job['demo']);self.store.finish(job,'done')
        except UserError as e:self.store.finish(job,'blocked',str(e))
        except Exception:self.store.finish(job,'failed','Run failed; details redacted. Check permissions, network and configuration.')
        return True
    def loop(self):
        while not self.stop.is_set():
            try:self.tick();self.process_one()
            except UserError:pass
            self.stop.wait(2)
