import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from goalpilot.core import UserError,create_project,questions,classify,digest
from goalpilot.network import validate_url,public_address,fetch
from goalpilot.service import Service
from goalpilot.workflows import video,seo,SEOPage
from goalpilot.__main__ import handler

class GoalPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.app=Service(self.root/'app.sqlite3',self.root)
    def tearDown(self):self.temp.cleanup()
    def project(self,kind='video'):
        p=self.app.create({'goal':'Make a video script for a channel' if kind=='video' else 'Audit my website SEO','kind':kind})
        inputs={'topic':'Desk organisation','audience':'Students','facts':'Use a notebook to list three tasks.'} if kind=='video' else {'website':'https://example.com/','audience':'Students'}
        return self.app.update(p['id'],{'inputs':inputs})
    def test_intent_classification_and_unknown_goal(self):
        self.assertEqual(classify('Grow my YouTube channel'),'video');self.assertEqual(classify('Improve website SEO'),'seo');self.assertEqual(classify('Build a garden'),'custom')
    def test_required_intake_blocks_run(self):
        p=self.app.create({'goal':'Make a video script','kind':'video'})
        self.assertEqual(len(p['questions']),3)
        with self.assertRaises(UserError):self.app.run(p['id'],{'demo':True})
    def test_validation_prevents_secret_input_fields(self):
        p=self.project()
        with self.assertRaises(UserError):self.app.update(p['id'],{'inputs':{'api_key':'not-an-actual-key'}})
    def test_editable_plan_validated(self):
        p=self.project();updated=self.app.update(p['id'],{'plan':['Review sources','Draft original script']});self.assertEqual(updated['plan'][0],'Review sources')
        with self.assertRaises(UserError):self.app.update(p['id'],{'plan':['x']*13})
    def test_only_one_active_job_per_project(self):
        p=self.project();self.app.run(p['id'],{'demo':True})
        with self.assertRaises(UserError):self.app.run(p['id'],{'demo':True})
    def test_demo_has_no_network_and_persists(self):
        p=self.project()
        with patch('urllib.request.build_opener',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')):
            self.app.run(p['id'],{'demo':True});self.assertTrue(self.app.process_one())
        result=self.app.view(p['id']);self.assertEqual(result['jobs'][0]['status'],'done');self.assertIn('DEMO',result['artifacts'][0]['text'])
        again=Service(self.root/'app.sqlite3',self.root);self.assertEqual(len(again.view(p['id'])['artifacts']),1)
    def test_queued_snapshot_not_changed_by_later_edits(self):
        p=self.project();self.app.run(p['id'],{'demo':True});self.app.update(p['id'],{'inputs':{'facts':'A different approved fact'}});self.app.process_one()
        self.assertIn('notebook',self.app.view(p['id'])['artifacts'][0]['text'])
        self.assertNotIn('different approved fact',self.app.view(p['id'])['artifacts'][0]['text'])
    def test_demo_artifacts_cannot_be_approved_as_real(self):
        p=self.project();a=self.app.store.artifact(p['id'],'# DEMO',True)
        with self.assertRaises(UserError):self.app.approve(a['id'],{'sha256':a['sha256']})
    def test_review_is_hash_bound_and_export_only(self):
        p=self.project();a=self.app.store.artifact(p['id'],'Original draft')
        with self.assertRaises(UserError):self.app.approve(a['id'],{'sha256':'stale'})
        approved=self.app.approve(a['id'],{'sha256':a['sha256']});self.assertTrue(approved['approval']['APPROVED']);self.assertIn('no external publication',approved['approval']['scope'])
    def test_pause_blocks_actions_but_schedule_can_be_disabled(self):
        p=self.project('seo');s=self.app.schedule(p['id'],{'APPROVED':True,'demo':True})
        (self.root/'PAUSE').touch()
        for fn in [lambda:self.app.run(p['id'],{'demo':True}),self.app.tick,self.app.process_one,lambda:self.app.create({'goal':'Another goal'})]:
            with self.assertRaises(UserError):fn()
        self.assertFalse(self.app.disable_schedule(s['id'])['enabled'])
    def test_schedule_requires_boolean_approval_and_rejects_paid_video(self):
        p=self.project()
        with self.assertRaises(UserError):self.app.schedule(p['id'],{'APPROVED':'true','demo':True})
        with self.assertRaises(UserError):self.app.schedule(p['id'],{'APPROVED':True,'demo':False})
    def make_due(self,s,**updates):
        s.update(updates);s['next_run']=time.time()-1
        with self.app.store.db() as db:db.execute('UPDATE schedules SET next_run=?,body=? WHERE id=?',(s['next_run'],json.dumps(s),s['id']))
    def test_schedule_enqueues_once_and_honors_cap(self):
        p=self.project('seo');s=self.app.schedule(p['id'],{'APPROVED':True,'demo':True,'interval_hours':1});self.make_due(s,runs=6)
        self.app.tick();self.app.tick();view=self.app.view(p['id']);self.assertEqual(len(view['jobs']),1);self.assertFalse(view['schedules'][0]['enabled']);self.assertEqual(view['schedules'][0]['runs'],7)
    def test_schedule_invalidates_when_inputs_change(self):
        p=self.project('seo');s=self.app.schedule(p['id'],{'APPROVED':True,'demo':True});self.app.update(p['id'],{'inputs':{'audience':'A new audience'}});self.make_due(s);self.app.tick()
        self.assertFalse(self.app.view(p['id'])['schedules'][0]['enabled']);self.assertFalse(self.app.view(p['id'])['jobs'])
    def test_new_schedule_disables_previous_body_and_column(self):
        p=self.project('seo');self.app.schedule(p['id'],{'APPROVED':True,'demo':True});self.app.schedule(p['id'],{'APPROVED':True,'demo':True});self.assertEqual(sum(s['enabled'] for s in self.app.view(p['id'])['schedules']),1)
    def test_interrupted_paid_outcome_not_retried(self):
        p=self.project();self.app.run(p['id'],{'demo':True});self.app.store.claim();Service(self.root/'app.sqlite3',self.root)
        self.assertEqual(self.app.view(p['id'])['jobs'][0]['status'],'interrupted')
    def test_seo_demo_never_uses_fetch(self):
        p=self.project('seo')
        with patch('goalpilot.workflows.fetch',side_effect=AssertionError('network')):self.assertIn('DEMO',seo(p,True,lambda:None,lambda a,s:None))
    def test_model_needs_configuration_and_consent(self):
        p=self.project()
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(UserError):video(p,False,True,lambda:None,lambda a,s:None)
        with patch.dict(os.environ,{'LLM_BASE_URL':'https://api.example.com/v1','LLM_MODEL':'test','LLM_API_KEY':'fake-test-key'},clear=True),patch('urllib.request.build_opener',side_effect=AssertionError('network')):
            with self.assertRaises(UserError):video(p,False,False,lambda:None,lambda a,s:None)
    def test_live_model_contract_without_real_paid_request(self):
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        class Opener:
            def open(self,req,timeout):
                data=json.loads(req.data);self.body=data
                assert data['max_completion_tokens']==1600
                return Response(json.dumps({'choices':[{'message':{'content':'# Original test draft'}}]}).encode())
        opener=Opener();events=[]
        with patch.dict(os.environ,{'LLM_BASE_URL':'https://api.example.com/v1','LLM_MODEL':'test','LLM_API_KEY':'fake-test-key'},clear=True),patch('urllib.request.build_opener',return_value=opener):
            text=video(self.project(),False,True,lambda:None,lambda a,s:events.append((a,s)))
        self.assertIn('Original test draft',text);self.assertNotIn('fake-test-key',text+str(events))
    def test_url_and_dns_guards(self):
        for url in ['http://example.com','https://user:pass@example.com','https://example.com:8443','file:///etc/passwd']:
            with self.assertRaises(UserError):validate_url(url)
        for address in ('127.0.0.1','10.0.0.1','169.254.169.254','::1'):
            with patch('socket.getaddrinfo',return_value=[(None,None,None,None,(address,443))]):
                with self.assertRaises(UserError):public_address('example.com')
    def test_mixed_dns_is_blocked(self):
        with patch('socket.getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',443)),(None,None,None,None,('127.0.0.1',443))]):
            with self.assertRaises(UserError):public_address('example.com')
    def test_schema_parser_reads_graph(self):
        p=SEOPage();p.feed('<title>One &amp; two</title><h1>Hello</h1><script type="application/ld+json">{"@graph":[{"@type":"Product"}]}</script>')
        self.assertEqual(p.title,'One & two');self.assertIn('Product',p.types)
    def test_safe_errors_do_not_echo_provider_secrets(self):
        with patch.dict(os.environ,{'LLM_BASE_URL':'https://api.example.com/v1','LLM_MODEL':'test','LLM_API_KEY':'fake-test-key'},clear=True),patch('urllib.request.build_opener',side_effect=Exception('fake-test-key')):
            with self.assertRaises(UserError) as error:video(self.project(),False,True,lambda:None,lambda a,s:None)
            self.assertNotIn('fake-test-key',str(error.exception))

    def test_live_seo_inspection_with_offline_http_fixtures(self):
        project=self.project('seo');pages={
            'https://example.com/robots.txt':{'status':200,'text':'User-agent: *\nAllow: /','content_type':'text/plain'},
            'https://example.com/sitemap.xml':{'status':200,'text':'<urlset><url><loc>https://example.com/page</loc></url><url><loc>https://evil.example/</loc></url><url><loc>https://example.com/logout</loc></url></urlset>','content_type':'application/xml'},
            'https://example.com/':{'status':200,'text':'<title>Home</title><h1>Home</h1><a href="/page">Page</a>','content_type':'text/html'},
            'https://example.com/page':{'status':200,'text':'<title>Page</title><h1>Page</h1>','content_type':'text/html'}}
        fetched=[]
        def fixture(url,*args):
            fetched.append(url);return {**pages[url],'url':url}
        with patch('goalpilot.workflows.fetch',side_effect=fixture),patch('goalpilot.workflows.time.sleep'):
            text=seo(project,False,lambda:None,lambda a,s:None)
        self.assertIn('Missing description',text);self.assertIn('https://example.com/page',text)
        self.assertFalse(any('evil' in url or 'logout' in url for url in fetched))

    def test_live_seo_stops_on_unreadable_robots(self):
        with patch('goalpilot.workflows.fetch',return_value={'status':403}) as mocked:
            with self.assertRaises(UserError):seo(self.project('seo'),False,lambda:None,lambda a,s:None)
        self.assertEqual(mocked.call_count,1)

    def test_seo_ten_page_cap_is_explicit(self):
        urls=['https://example.com/page'+str(i) for i in range(15)]
        def fixture(url,*args):
            if url.endswith('robots.txt'):text='User-agent: *\nAllow: /';kind='text/plain'
            elif url.endswith('sitemap.xml'):text='<urlset>'+''.join('<url><loc>'+u+'</loc></url>' for u in urls)+'</urlset>';kind='application/xml'
            else:text='<title>Example</title><h1>Example</h1>';kind='text/html'
            return {'url':url,'status':200,'text':text,'content_type':kind}
        with patch('goalpilot.workflows.fetch',side_effect=fixture),patch('goalpilot.workflows.time.sleep'):
            text=seo(self.project('seo'),False,lambda:None,lambda a,s:None)
        self.assertIn('Ten-page cap reached',text);self.assertEqual(text.count('### https://'),10)

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Service(Path(self.tmp.name)/'db',self.tmp.name)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app,'test-local-token'))
        threading.Thread(target=self.server.serve_forever,daemon=True).start();self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def request(self,path,body=None,origin=None,token='test-local-token'):
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req) as response:return response.status,json.loads(response.read())
    def test_end_to_end_demo(self):
        _,p=self.request('/api/projects',{'goal':'Audit my website SEO','kind':'seo'})
        req=urllib.request.Request(self.base+'/api/projects/'+p['id'],method='PATCH',data=json.dumps({'inputs':{'website':'https://example.com','audience':'Readers'}}).encode(),headers={'Authorization':'Bearer test-local-token'})
        urllib.request.urlopen(req).close()
        status,_=self.request('/api/projects/'+p['id']+'/runs',{'demo':True});self.assertEqual(status,202)
        self.app.process_one();_,project=self.request('/api/projects/'+p['id']);self.assertEqual(project['jobs'][0]['status'],'done')
    def test_token_and_cross_origin_guards(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/status',token='wrong')
        self.assertEqual(error.exception.code,401)
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/projects',{'goal':'Some website goal'},origin='https://evil.example')
        self.assertEqual(error.exception.code,403)
    def test_no_publication_endpoint_and_no_secret_status(self):
        _,data=self.request('/api/status');self.assertFalse(data['publication_enabled']);self.assertNotIn('api_key',json.dumps(data))
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/publish',{})
        self.assertEqual(error.exception.code,404)
    def test_static_workspace_loads(self):
        with urllib.request.urlopen(self.base+'/') as response:
            self.assertIn(b'goalpilot',response.read());self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])

    def test_static_workflow_options_are_valid_opening_tags(self):
        from html.parser import HTMLParser
        from goalpilot.core import ROOT
        class Options(HTMLParser):
            def __init__(self): super().__init__(); self.values=[]
            def handle_starttag(self,tag,attrs):
                if tag=='option':self.values.append(dict(attrs).get('value'))
        parser=Options();parser.feed((ROOT/'goalpilot/static/index.html').read_text())
        self.assertEqual(parser.values,['auto','seo','video','custom'])

if __name__=='__main__':unittest.main()
