"""Phase 1A: evidence-first diagnosis, bounded crawl and structural schema checks."""
import json
import os
import time
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urlencode, urljoin, urlsplit, urlunsplit
from .core import UserError
from .network import validate_url

USER_AGENT = 'GoalPilotAudit'
DEFAULT_LIMITS = {'pages': 10, 'sitemaps': 6, 'links': 40, 'requests': 80, 'seconds': 120, 'delay': 0.25}
ACTION_SEGMENTS = {'api','admin','auth','login','logout','signout','checkout','cart','delete','remove','unsubscribe','subscribe','account'}


class AuditLimit(UserError): pass


def clean_url(base, href):
    try:
        p = validate_url(urljoin(base, href))
        if p.hostname != urlsplit(base).hostname:
            return None
        # Never send tracker, token, cart-action or variant query strings to audited sites.
        path = p.path or '/'
        decoded = unquote(unquote(path)).lower()
        segments = {part.split('.')[0] for part in decoded.replace('\\', '/').split('/')}
        if segments & ACTION_SEGMENTS:
            return None
        return urlunsplit(('https', p.netloc.lower(), path, '', ''))
    except (UserError, ValueError, TypeError):
        return None


def schema_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from schema_nodes(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from schema_nodes(item)


class SEOPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ''; self.title_count = 0; self.description = ''; self.descriptions = 0
        self.h1s = 0; self.canonical = []; self.robots = ''; self.links = []
        self.types = []; self.nodes = []; self.json_errors = 0
        self._title = False; self._json = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title': self._title = True; self.title_count += 1
        if tag == 'h1': self.h1s += 1
        if tag == 'meta' and a.get('name', '').lower() == 'description':
            self.description = a.get('content', ''); self.descriptions += 1
        if tag == 'meta' and a.get('name', '').lower() in ('robots', 'googlebot'):
            self.robots += ' ' + a.get('content', '')
        if tag == 'link' and 'canonical' in a.get('rel', '').lower().split():
            self.canonical.append(a.get('href', ''))
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
        if tag == 'script' and a.get('type', '').lower() == 'application/ld+json': self._json = ''

    def handle_data(self, data):
        if self._title: self.title += data
        if self._json is not None: self._json += data

    def handle_endtag(self, tag):
        if tag == 'title': self._title = False
        if tag == 'script' and self._json is not None:
            try: self.collect(json.loads(self._json))
            except ValueError: self.json_errors += 1
            self._json = None

    def collect(self, data):
        for node in schema_nodes(data):
            self.nodes.append(node)
            kind = node.get('@type', [])
            if isinstance(kind, str): self.types.append(kind)
            elif isinstance(kind, list): self.types.extend(x for x in kind if isinstance(x, str))


def inspect(url, response):
    page = SEOPage(); page.feed(response['text'])
    issues = []
    def add(priority, code, detail): issues.append({'priority': priority, 'code': code, 'detail': detail})
    if response['status'] >= 400: add('P1','http-error','HTTP ' + str(response['status']))
    if not page.title.strip(): add('P1','missing-title','Missing title')
    elif page.title_count != 1: add('P2','title-count','Multiple title tags')
    elif len(page.title.strip()) > 65: add('P3','long-title','Title may truncate; assess actual search intent and pixel width')
    if not page.description.strip(): add('P2','missing-description','Missing description')
    elif page.descriptions != 1: add('P2','description-count','Multiple description tags')
    if page.h1s != 1: add('P2','h1-count','Initial HTML H1 count ' + str(page.h1s))
    if len(page.canonical) != 1: add('P1','canonical-count','Canonical count ' + str(len(page.canonical)))
    elif not page.canonical[0].strip(): add('P1','empty-canonical','Canonical URL is empty')
    if 'noindex' in (page.robots + ' ' + response.get('x_robots_tag','')).lower():
        add('P1','noindex','Noindex in HTML or response header; verify intent')
    if page.json_errors: add('P1','invalid-jsonld','Invalid JSON-LD')
    if not page.links: add('P2','no-internal-anchors','No crawlable anchors in initial HTML')
    for node in page.nodes:
        kinds = node.get('@type', [])
        if isinstance(kinds, str): kinds = [kinds]
        if not isinstance(kinds, list): continue
        for kind, fields in [('Product', ('name','image','offers')), ('ProductGroup',('name','productGroupID','hasVariant')),
                             ('Offer',('price','priceCurrency','url')), ('FAQPage',('mainEntity',)), ('BreadcrumbList',('itemListElement',))]:
            if kind in kinds:
                for field in fields:
                    if field not in node or node[field] in (None, '', []):
                        add('P2','schema-field',kind + ' lacks ' + field + ' (heuristic; review schema intent)')
    return {'url': response['url'], 'requested_url': url, 'status': response['status'], 'title': page.title.strip(),
            'description': page.description, 'h1_count': page.h1s, 'canonicals': page.canonical,
            'schema_types': sorted(set(page.types)), 'issues': issues, 'links': page.links,
            'redirects': response.get('redirects',[])}


def measure_speed(url, check, event, key, opener=None):
    """Two explicit, one-shot official PSI requests; no field-INP claims."""
    if not key: return {'status':'not_measured','reason':'PAGESPEED_API_KEY is not configured','rows':[]}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    opener = opener or urllib.request.build_opener(NoRedirect())
    rows = []
    for strategy in ('mobile','desktop'):
        check(); event('PageSpeed ' + strategy,'request to Google; key and URL omitted from logs')
        request_url = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed?' + urlencode({'url':url,'strategy':strategy,'category':'performance','key':key})
        try:
            with opener.open(request_url,timeout=45) as response:
                raw = response.read(5_000_001)
                if len(raw)>5_000_000: raise ValueError('response limit')
                data = json.loads(raw)
            check(); lh = data['lighthouseResult']
            score = lh['categories']['performance']['score']
            if lh.get('runtimeError') or not isinstance(score,(int,float)) or isinstance(score,bool) or not 0<=score<=1:
                raise ValueError('measurement unavailable')
            audits = lh.get('audits',{})
            rows.append({'strategy':strategy,'status':'ok','performance_score':score,
                         'lab_lcp_ms':audits.get('largest-contentful-paint',{}).get('numericValue'),
                         'lab_cls':audits.get('cumulative-layout-shift',{}).get('numericValue'),
                         'lab_tbt_ms':audits.get('total-blocking-time',{}).get('numericValue'),
                         'measured_at':lh.get('fetchTime'),'warnings':lh.get('runWarnings',[])})
            event('PageSpeed ' + strategy,'measurement received')
        except UserError: raise
        except Exception:
            check(); event('PageSpeed ' + strategy,'not measured; provider details redacted')
            rows.append({'strategy':strategy,'status':'not_measured','reason':'API/network/quota error; details redacted'})
    return {'status':'ok' if all(r['status']=='ok' for r in rows) else 'partial','rows':rows}


def diagnose(project, demo, check, event, fetcher, limits=None):
    settings = {**DEFAULT_LIMITS, **(limits or {})}
    base = clean_url(project['inputs']['website'].strip(),project['inputs']['website'].strip())
    if not base: raise UserError('Supply a public HTTPS content URL; action routes are excluded')
    check()
    report = {'version':'1A','demo':demo,'generated_at':datetime.now(timezone.utc).isoformat(),'site':base,
              'limits':settings,'pages':[],'sitemaps':[],'links':[],'gaps':[], 'requests':0,
              'robots':{},'speed':{'status':'not_measured','reason':'PageSpeed not requested','rows':[]}}
    if demo:
        event('fixture audit','no network')
        report['pages'] = [inspect('https://example.com/',{'url':'https://example.com/','status':200,'text':'<title>Fixture page</title><h1>Example</h1><a href="/guide">Guide</a>'})]
        report['gaps'] = ['Synthetic fixture only. No website, rankings, analytics or speed measured.']
        report['status'] = 'fixture'; return report
    started = time.monotonic(); cache = {}; root = urljoin(base,'/'); policy = urllib.robotparser.RobotFileParser()
    def guard():
        check()
        if time.monotonic()-started > settings['seconds']: raise AuditLimit('Run time budget reached; coverage is partial')
    def permitted(url):
        return clean_url(base,url)==url and policy.can_fetch(USER_AGENT,url)
    def read(url, robots=False):
        guard()
        if url in cache: return cache[url]
        if report['requests'] >= settings['requests']: raise AuditLimit('Request budget reached; coverage is partial')
        if not robots and not permitted(url): raise UserError('URL excluded by robots or content-route policy')
        delay = settings['delay']
        if not robots:
            crawl_delay = policy.crawl_delay(USER_AGENT)
            rate = policy.request_rate(USER_AGENT)
            delay = max(delay, crawl_delay or 0, rate.seconds/rate.requests if rate and rate.requests else 0)
        while delay > 0:
            guard(); step = min(delay, 0.1); time.sleep(step); delay -= step
        guard()
        report['requests'] += 1
        allowed = (lambda dest: clean_url(base,dest)==dest) if robots else permitted
        response = fetcher(url,guard,event,allowed=allowed)
        # Also validate the returned final URL for provider/test adapters that do not enforce redirects themselves.
        if not allowed(response.get('url',url)): raise UserError('Final URL excluded by crawl policy')
        cache[url] = response
        return response
    try:
        robots = read(urljoin(root,'robots.txt'),True)
        if robots['status'] != 200:
            raise UserError('robots.txt could not be read; stopped rather than assuming crawl permission')
        policy.parse(robots['text'].splitlines()); report['robots']={'status':200,'sitemap_directives':policy.site_maps() or []}
        queue = deque([urljoin(root,'sitemap.xml'),*(policy.site_maps() or [])]); seen_maps=set(); sitemap_pages=set()
        while queue and len(seen_maps)<settings['sitemaps']:
            guard(); raw = queue.popleft(); url = clean_url(base,raw)
            if not url or url in seen_maps: continue
            seen_maps.add(url)
            try:
                response = read(url)
                if response['status']!=200: raise UserError('Sitemap HTTP ' + str(response['status']))
                xml = ET.fromstring(response['text']); kind=xml.tag.rsplit('}',1)[-1]
                # Direct children only: image/video extension locs must not become page URLs.
                values = [loc.text.strip() for child in xml for loc in child if loc.tag.rsplit('}',1)[-1]=='loc' and loc.text]
                if kind not in ('urlset','sitemapindex'): raise UserError('Unsupported sitemap XML root')
                report['sitemaps'].append({'url':url,'kind':kind,'locations':len(values),'status':'ok'})
                if kind=='sitemapindex': queue.extend(values)
                else:
                    for value in values:
                        clean = clean_url(base,value)
                        if clean: sitemap_pages.add(clean)
                        else: report['gaps'].append('Sitemap URL excluded by same-host/content policy')
            except AuditLimit: raise
            except (UserError,ET.ParseError):
                check(); report['sitemaps'].append({'url':url,'status':'unavailable'})
                report['gaps'].append('Sitemap could not be fetched or parsed: ' + url)
        if any(clean_url(base,u) not in seen_maps for u in queue): report['gaps'].append('Sitemap cap reached; nested sitemap coverage partial')
        report['sitemap_urls'] = sorted(sitemap_pages)
        pending = deque([base,*sorted(sitemap_pages)]); seen=set(); referrers={}
        while pending and len(seen)<settings['pages']:
            guard(); url=pending.popleft()
            if url in seen: continue
            seen.add(url)
            try:
                response=read(url)
                if 'html' not in response.get('content_type','text/html').lower():
                    report['gaps'].append('Non-HTML resource skipped: ' + url); continue
                row=inspect(url,response); row['in_sitemap']=url in sitemap_pages
                report['pages'].append(row)
                for href in row.pop('links'):
                    target=clean_url(base,href)
                    if target:
                        referrers.setdefault(target,set()).add(url)
                        pending.append(target)
            except AuditLimit: raise
            except UserError as error:
                check(); report['gaps'].append(url + ': ' + str(error))
        unvisited=set(pending)-seen
        if unvisited: report['gaps'].append('Ten-page cap reached; ' + str(len(unvisited)) + ' discovered page URLs were not inspected')
        report['sitemap_coverage']={'discovered':len(sitemap_pages),'inspected':sum(p['requested_url'] in sitemap_pages for p in report['pages']),
                                    'remaining':len(sitemap_pages-{p['requested_url'] for p in report['pages']})}
        # Resolve canonical targets and internal links within the shared cache/request/time budgets.
        for row in report['pages']:
            if len(row['canonicals'])!=1 or not row['canonicals'][0].strip(): continue
            raw=urljoin(row['url'],row['canonicals'][0]); target=clean_url(base,raw)
            if not target:
                row['issues'].append({'priority':'P2','code':'canonical-excluded','detail':'Canonical outside permitted origin/content scope; review manually'}); continue
            if target!=row['url']:
                row['issues'].append({'priority':'P2','code':'canonical-other','detail':'Canonical points to '+target+'; verify intended consolidation'})
            try:
                resolved=read(target)
                row['canonical_target']={'url':resolved['url'],'status':resolved['status'],'redirects':resolved.get('redirects',[])}
                if resolved['status']>=400: row['issues'].append({'priority':'P1','code':'canonical-broken','detail':'Canonical target HTTP '+str(resolved['status'])})
                elif resolved.get('redirects'): row['issues'].append({'priority':'P2','code':'canonical-redirect','detail':'Canonical target redirects; prefer its intended final URL'})
                destination=SEOPage(); destination.feed(resolved['text'])
                if 'noindex' in (destination.robots+' '+resolved.get('x_robots_tag','')).lower():
                    row['issues'].append({'priority':'P1','code':'canonical-noindex','detail':'Canonical destination carries noindex; review conflicting signals'})
            except AuditLimit: raise
            except UserError:
                check(); row['issues'].append({'priority':'P2','code':'canonical-unverified','detail':'Canonical destination could not be verified'})
        targets=sorted(referrers)
        for url in targets[:settings['links']]:
            guard()
            try:
                response=read(url)
                report['links'].append({'url':url,'status':response['status'],'final_url':response['url'],
                                         'redirects':response.get('redirects',[]),'referrers':sorted(referrers[url])})
            except AuditLimit: raise
            except UserError:
                check(); report['links'].append({'url':url,'status':'unverified','referrers':sorted(referrers[url])})
                report['gaps'].append('Internal link not verified: '+url)
        if len(targets)>settings['links']: report['gaps'].append('Link-check cap reached; '+str(len(targets)-settings['links'])+' additional links unverified')
        # Duplicate metadata only across distinct final URLs; legacy redirects are not duplicates.
        for field in ('title','description'):
            groups={}
            for row in report['pages']:
                if row.get(field): groups.setdefault(row[field],[]).append(row)
            for rows in groups.values():
                if len({r['url'] for r in rows})>1:
                    for row in rows: row['issues'].append({'priority':'P2','code':'duplicate-'+field,'detail':'Metadata shared by multiple final page URLs; review intent'})
        if project['inputs'].get('pagespeed')=='yes':
            report['speed']={'status':'not_measured','reason':'Requested measurement did not complete within the run budget','rows':[]}
            report['speed']=measure_speed(base,guard,event,os.environ.get('PAGESPEED_API_KEY'))
            if report['speed']['status']!='ok': report['gaps'].append('Requested PageSpeed measurements are incomplete: '+report['speed'].get('reason','see device results'))
        else: report['speed']['reason']='Not requested. Enable PageSpeed in saved project details to send the URL to Google.'
    except AuditLimit as error:
        report['gaps'].append(str(error))
    check()
    report['status']='partial' if report['gaps'] or report['speed']['status']=='partial' else 'complete_within_scope'
    return report


def render(report):
    def safe(value): return str(value).replace('\n',' ').replace('|','/').replace('<','&lt;').replace('>','&gt;')
    lines=['# '+('DEMO ' if report['demo'] else '')+'Read-only SEO audit','', 'Generated UTC: '+report['generated_at'],
           '', 'Scope: initial HTML and bounded same-host HTTPS discovery. No analytics, SERPs, JS execution, ranking measurement or Google indexing verification. Findings are heuristics; nothing is published.',
           '', '## Coverage', '', 'Run status: '+report['status'], 'Logical site fetches: '+str(report['requests']),
           'Sitemap coverage: '+safe(report.get('sitemap_coverage','not measured')), '', '## Prioritised actions','',
           '| Priority | URL | Finding |','|---|---|---|']
    findings=[(i['priority'],r['url'],i['detail']) for r in report['pages'] for i in r['issues']]
    findings += [('P1',r['url'],('Broken internal link: HTTP ' if r['status'] in (404,410) else 'Internal link HTTP ')+str(r['status'])+'; linked from '+', '.join(r['referrers'])) for r in report['links'] if isinstance(r['status'],int) and r['status'] >= 400]
    for priority,url,detail in sorted(findings): lines.append('| '+priority+' | '+safe(url)+' | '+safe(detail)+' |')
    if not findings: lines.append('| — | — | No issues detected within checked scope; this is not a clean bill of health |')
    lines += ['', '## Findings','']
    for row in report['pages']:
        lines += ['### '+safe(row['requested_url']), 'HTTP: '+str(row['status'])+' · final URL: '+safe(row['url']),
                  'Title: '+safe(row['title']), 'Schema types: '+safe(', '.join(row['schema_types']) or 'none detected'),
                  'Redirect hops: '+safe(row['redirects']),*['- '+i['priority']+': '+safe(i['detail']) for i in row['issues']], '']
    lines += ['## Internal link checks','','| URL | HTTP | Referrers |','|---|---|---|']
    for row in report['links']: lines.append('| '+safe(row['url'])+' | '+str(row['status'])+' | '+safe(', '.join(row['referrers']))+' |')
    lines += ['', '## PageSpeed', '', 'Status: '+report['speed']['status'], report['speed'].get('reason',''),
              'Lighthouse lab measurements only. TBT is not field INP. A missing measurement is not a passing score.','',
              '| Device | Status | Score (0–1) | LCP ms | CLS | TBT ms |','|---|---|---|---|---|---|']
    for row in report['speed']['rows']:
        lines.append('| '+' | '.join(safe(row.get(k,'not measured')) for k in ('strategy','status','performance_score','lab_lcp_ms','lab_cls','lab_tbt_ms'))+' |')
    lines += ['', '## Coverage gaps',*['- '+safe(g) for g in dict.fromkeys(report['gaps'])],
              '', 'Schema checks inspect JSON-LD structure only, not full Google eligibility or visible-content consistency. FAQ and Breadcrumb markup are optional; absence is not automatically an error.',
              '', '## Required next inputs','- GSC and GA4 reporting access for traffic and sales attribution (Phase 1B).',
              '- Verified business facts before recommending content changes.',
              '- An approved PR before website code changes. No top ranking is guaranteed.']
    return '\n'.join(lines)+'\n'
