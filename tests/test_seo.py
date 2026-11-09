import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from goalpilot.core import UserError
from goalpilot.network import fetch
from goalpilot.seo import clean_url, diagnose, inspect, measure_speed, render
from goalpilot.service import Service

BASE = 'https://example.com/'
PROJECT = {'inputs': {'website': BASE, 'audience': 'Readers'}}


def response(url, body='', status=200, **extra):
    return {'url': url, 'text': body, 'status': status, 'content_type': 'text/html', **extra}


def page(title='Example', extra=''):
    return '<title>'+title+'</title><meta name="description" content="A useful page"><h1>Example</h1>'+extra


class FixtureSite:
    def __init__(self, pages=None, robots='User-agent: *\nAllow: /', sitemap=None):
        self.pages = {BASE: response(BASE,page(extra='<link rel="canonical" href="/">')),
                      BASE+'robots.txt':response(BASE+'robots.txt',robots),
                      BASE+'sitemap.xml':response(BASE+'sitemap.xml',sitemap or '<urlset/>')}
        self.pages.update(pages or {}); self.calls=[]

    def __call__(self,url,check,event,allowed=None):
        check()
        if allowed and not allowed(url): raise UserError('Fixture policy excluded URL')
        self.calls.append(url)
        return self.pages.get(url,response(url,'Missing',404))


class SEOTests(unittest.TestCase):
    def audit(self,site,**kwargs):
        limits={'delay':0,**kwargs.pop('limits',{})}
        return diagnose(PROJECT,False,lambda:None,lambda a,s:None,site,limits=limits,**kwargs)

    def test_nested_sitemaps_cycles_and_image_extensions(self):
        index='<sitemapindex><sitemap><loc>'+BASE+'nested.xml</loc></sitemap><sitemap><loc>'+BASE+'sitemap.xml</loc></sitemap></sitemapindex>'
        child='<urlset xmlns:image="urn:image"><url><loc>'+BASE+'guide</loc><image:image><image:loc>'+BASE+'photo.jpg</image:loc></image:image></url></urlset>'
        site=FixtureSite({BASE+'nested.xml':response(BASE+'nested.xml',child),BASE+'guide':response(BASE+'guide',page('Guide'))},sitemap=index)
        report=self.audit(site)
        self.assertEqual(report['sitemap_urls'],[BASE+'guide'])
        self.assertEqual(site.calls.count(BASE+'sitemap.xml'),1)
        self.assertNotIn(BASE+'photo.jpg',site.calls)
        self.assertEqual(report['sitemap_coverage']['inspected'],1)

    def test_robots_sitemap_directive_and_disallow(self):
        site=FixtureSite({BASE+'extra.xml':response(BASE+'extra.xml','<urlset><url><loc>'+BASE+'private</loc></url></urlset>')},robots='User-agent: *\nDisallow: /private\nSitemap: '+BASE+'extra.xml')
        report=self.audit(site)
        self.assertNotIn(BASE+'private',site.calls)
        self.assertTrue(any('robots' in g for g in report['gaps']))

    def test_robot_crawl_delay_is_respected(self):
        site=FixtureSite(robots='User-agent: *\nAllow: /\nCrawl-delay: 2')
        with patch('goalpilot.seo.time.sleep') as wait:
            self.audit(site)
        self.assertAlmostEqual(sum(c.args[0] for c in wait.call_args_list),4,places=6)

    def test_off_host_sitemap_and_action_urls_not_fetched(self):
        site=FixtureSite(sitemap='<urlset><url><loc>https://evil.example/</loc></url><url><loc>'+BASE+'%256cogout</loc></url></urlset>')
        report=self.audit(site)
        self.assertEqual(len(report['pages']),1)
        self.assertTrue(report['gaps'])
        self.assertIsNone(clean_url(BASE,'/logout.php?token=secret'))
        self.assertEqual(clean_url(BASE,'/guide?tracker=secret#part'),BASE+'guide')

    def test_broken_links_have_referrers_and_are_cached(self):
        site=FixtureSite({BASE:response(BASE,page(extra='<link rel="canonical" href="/"><a href="/missing">Missing</a>'))})
        report=self.audit(site)
        broken=next(r for r in report['links'] if r['url'].endswith('missing'))
        self.assertEqual(broken['status'],404); self.assertEqual(broken['referrers'],[BASE])
        self.assertEqual(site.calls.count(BASE+'missing'),1)
        self.assertIn('Broken internal link: HTTP 404',render(report))

    def test_failed_link_is_unverified_not_reported_as_404(self):
        site=FixtureSite({BASE:response(BASE,page(extra='<a href="/network-failure">Link</a>'))})
        def read(url,*args,**kwargs):
            if url.endswith('network-failure'): raise UserError('Network failure')
            return site(url,*args,**kwargs)
        report=self.audit(read)
        self.assertEqual(report['links'][0]['status'],'unverified')
        self.assertNotIn('Broken internal link: HTTP 404',render(report))

    def test_canonical_broken_redirected_and_noindex(self):
        site=FixtureSite({BASE:response(BASE,page(extra='<link rel="canonical" href="/target">')),
                          BASE+'target':response(BASE+'final',page(extra='<meta name="robots" content="noindex">'),redirects=[{'url':BASE+'target','status':301}])})
        report=self.audit(site)
        codes={i['code'] for i in report['pages'][0]['issues']}
        self.assertTrue({'canonical-other','canonical-redirect','canonical-noindex'}<=codes)
        site.pages[BASE+'target']=response(BASE+'target','Missing',404)
        codes={i['code'] for i in self.audit(site)['pages'][0]['issues']}
        self.assertIn('canonical-broken',codes)

    def test_relative_self_canonical_and_header_noindex(self):
        row=inspect(BASE,response(BASE,page(extra='<link rel="canonical" href="/">'),x_robots_tag='noindex'))
        self.assertIn('noindex',{i['code'] for i in row['issues']})
        self.assertNotIn('canonical-count',{i['code'] for i in row['issues']})

    def test_duplicate_metadata_distinct_final_urls_only(self):
        html=page(extra='<a href="/other">Other</a>')
        site=FixtureSite({BASE:response(BASE,html),BASE+'other':response(BASE+'other',html)})
        self.assertIn('duplicate-title',{i['code'] for i in self.audit(site)['pages'][0]['issues']})
        site.pages[BASE+'other']=response(BASE,html,redirects=[{'url':BASE+'other','status':301}])
        self.assertNotIn('duplicate-title',{i['code'] for i in self.audit(site)['pages'][0]['issues']})

    def test_schema_checks_fields_but_does_not_require_optional_faq(self):
        html=page(extra='<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"Item"},{"@type":"FAQPage"},{"@type":"BreadcrumbList"}]}</script>')
        row=inspect(BASE,response(BASE,html)); details=[i['detail'] for i in row['issues']]
        self.assertIn('Product lacks offers (heuristic; review schema intent)',details)
        self.assertTrue(any('FAQPage lacks' in d for d in details))
        self.assertFalse(any('FAQ' in i['detail'] for i in inspect(BASE,response(BASE,page()))['issues']))

    def test_non_html_resources_are_not_flagged_missing_titles(self):
        site=FixtureSite({BASE:response(BASE,page(extra='<a href="/label.pdf">Label</a>')),
                          BASE+'label.pdf':response(BASE+'label.pdf','PDF',content_type='application/pdf')})
        report=self.audit(site)
        self.assertFalse(any(p['url'].endswith('pdf') for p in report['pages']))
        self.assertEqual(report['links'][0]['status'],200)

    def test_limits_return_partial_and_explicit_coverage(self):
        site=FixtureSite({BASE:response(BASE,page(extra='<a href="/one">One</a><a href="/two">Two</a>'))})
        report=self.audit(site,limits={'requests':3})
        self.assertEqual(report['status'],'partial')
        self.assertTrue(any('Request budget' in g for g in report['gaps']))
        with patch('goalpilot.seo.time.monotonic',side_effect=[0,999]):
            report=self.audit(FixtureSite(),limits={'seconds':1})
        self.assertEqual(report['status'],'partial')

    def test_sitemap_and_link_caps_are_explicit(self):
        index='<sitemapindex>'+''.join('<sitemap><loc>'+BASE+str(i)+'.xml</loc></sitemap>' for i in range(9))+'</sitemapindex>'
        report=self.audit(FixtureSite(sitemap=index),limits={'sitemaps':1})
        self.assertTrue(any('Sitemap cap' in g for g in report['gaps']))
        site=FixtureSite({BASE:response(BASE,page(extra='<a href="/one">One</a><a href="/two">Two</a>'))})
        report=self.audit(site,limits={'links':1,'pages':1})
        self.assertEqual(len(report['links']),1)
        self.assertTrue(any('Link-check cap' in g for g in report['gaps']))

    def test_pause_propagates_and_does_not_save_partial_draft(self):
        def check(): raise UserError('PAUSE present')
        with self.assertRaisesRegex(UserError,'PAUSE'):
            diagnose(PROJECT,False,check,lambda a,s:None,FixtureSite())

    def test_demo_has_zero_requests_even_with_speed_key(self):
        with patch.dict(os.environ,{'PAGESPEED_API_KEY':'fake-key'}),patch('urllib.request.build_opener',side_effect=AssertionError('network')):
            report=diagnose({'inputs':{**PROJECT['inputs'],'pagespeed':'yes'}},True,lambda:None,lambda a,s:None,lambda *a,**k:self.fail('network'))
        self.assertEqual(report['requests'],0);self.assertEqual(report['status'],'fixture')

    def test_page_speed_missing_key_requires_no_network(self):
        with patch.dict(os.environ,{},clear=True):
            report=diagnose({'inputs':{**PROJECT['inputs'],'pagespeed':'yes'}},False,lambda:None,lambda a,s:None,FixtureSite())
        self.assertEqual(report['speed']['status'],'not_measured')
        self.assertEqual(report['status'],'partial')

    def test_demo_report_persists_and_old_artifacts_still_read(self):
        with tempfile.TemporaryDirectory() as root:
            service=Service(Path(root)/'db',root)
            p=service.create({'goal':'Audit website SEO','kind':'seo'})
            service.update(p['id'],{'inputs':{'website':BASE,'audience':'Readers','pagespeed':'no'}})
            service.run(p['id'],{'demo':True});service.process_one()
            self.assertEqual(service.view(p['id'])['artifacts'][0]['report']['version'],'1A')
            old=service.store.artifact(p['id'],'Legacy draft')
            self.assertNotIn('report',service.store.get('artifacts',old['id']))
            with self.assertRaises(UserError):service.update(p['id'],{'inputs':{'pagespeed':'yes please'}})


class SpeedTests(unittest.TestCase):
    def opener(self,payload):
        class Stream(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        class Opener:
            def open(self,url,timeout):return Stream(json.dumps(payload).encode())
        return Opener()

    def test_lab_values_and_units(self):
        payload={'lighthouseResult':{'categories':{'performance':{'score':.8}},'fetchTime':'2026-11-09T00:00:00Z',
                'audits':{'largest-contentful-paint':{'numericValue':2400},'cumulative-layout-shift':{'numericValue':.03},'total-blocking-time':{'numericValue':50}}}}
        events=[]
        report=measure_speed(BASE,lambda:None,lambda a,s:events.append((a,s)),'fake-secret',self.opener(payload))
        self.assertEqual(report['status'],'ok');self.assertEqual(len(report['rows']),2)
        self.assertEqual(report['rows'][0]['lab_lcp_ms'],2400)
        self.assertNotIn('fake-secret',str(report)+str(events))
        self.assertNotIn('INP',report['rows'][0])

    def test_api_error_and_null_score_are_unmeasured(self):
        payload={'lighthouseResult':{'categories':{'performance':{'score':None}}}}
        report=measure_speed(BASE,lambda:None,lambda a,s:None,'fake-key',self.opener(payload))
        self.assertEqual(report['status'],'partial')
        self.assertTrue(all(r['status']=='not_measured' for r in report['rows']))


class TransportTests(unittest.TestCase):
    def test_redirect_policy_checked_before_destination_network(self):
        class Resp:
            status=302
            def getheader(self,name,*args):return '/private' if name=='Location' else ''
        class Conn:
            calls=[]
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):self.calls.append(args)
            def getresponse(self):return Resp()
            def close(self):pass
        with patch('goalpilot.network.public_address',return_value='8.8.8.8') as dns,patch('goalpilot.network.PinnedHTTPS',Conn):
            with self.assertRaises(UserError):fetch(BASE,allowed=lambda url:not url.endswith('/private'))
        self.assertEqual(len(Conn.calls),1);self.assertEqual(dns.call_count,1)

    def test_redirect_loop_is_bounded_and_logged(self):
        class Resp:
            status=301
            def getheader(self,name,*args):return '/' if name=='Location' else ''
        class Conn:
            calls=0
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):Conn.calls+=1
            def getresponse(self):return Resp()
            def close(self):pass
        with patch('goalpilot.network.public_address',return_value='8.8.8.8'),patch('goalpilot.network.PinnedHTTPS',Conn):
            with self.assertRaisesRegex(UserError,'Redirect limit'):fetch(BASE)
        self.assertEqual(Conn.calls,4)

    def test_response_headers_and_redirect_evidence(self):
        class Resp:
            def __init__(self,status):self.status=status
            def getheader(self,name,default=''):
                return {'Location':'/final','Content-Type':'text/html','X-Robots-Tag':'noindex'}.get(name,default)
            def read(self,limit):return b'<h1>Final</h1>'
        class Conn:
            count=0
            def __init__(self,*args):Conn.count+=1;self.status=301 if Conn.count==1 else 200
            def request(self,*args,**kwargs):pass
            def getresponse(self):return Resp(self.status)
            def close(self):pass
        with patch('goalpilot.network.public_address',return_value='8.8.8.8'),patch('goalpilot.network.PinnedHTTPS',Conn):
            result=fetch(BASE)
        self.assertEqual(result['url'],BASE+'final');self.assertEqual(result['x_robots_tag'],'noindex')
        self.assertEqual(result['redirects'],[{'url':BASE,'status':301}])

    def test_response_size_limit_and_redacted_network_error(self):
        class Resp:
            status=200
            def getheader(self,*args):return 'text/html'
            def read(self,limit):return b'a'*limit
        class Conn:
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):pass
            def getresponse(self):return Resp()
            def close(self):pass
        with patch('goalpilot.network.public_address',return_value='8.8.8.8'),patch('goalpilot.network.PinnedHTTPS',Conn):
            with self.assertRaisesRegex(UserError,'512 KB'):fetch(BASE)
        with patch('goalpilot.network.public_address',return_value='8.8.8.8'),patch('goalpilot.network.PinnedHTTPS.request',side_effect=OSError('private-detail')):
            with self.assertRaises(UserError) as error:fetch(BASE)
        self.assertNotIn('private-detail',str(error.exception))

if __name__=='__main__':unittest.main()
