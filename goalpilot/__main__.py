import argparse
import hmac
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .core import ROOT,UserError,model_ready
from .service import Service


def handler(service,token=''):
    class Handler(BaseHTTPRequestHandler):
        server_version='GoalPilot/0.1'
        def log_message(self,*args):pass # Goal text, query strings and credentials never enter stdout logs.
        def reply(self,status,data,kind='application/json'):
            raw=json.dumps(data).encode() if kind=='application/json' else data if isinstance(data,bytes) else data.encode()
            self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'self'")
            self.end_headers();self.wfile.write(raw)
        def dispatch(self,method):
            path=urlsplit(self.path).path
            try:
                host=self.headers.get('Host','')
                if host not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):return self.reply(403,{'error':'Local host required'})
                origin=self.headers.get('Origin')
                if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):return self.reply(403,{'error':'Cross-origin access blocked'})
                if path.startswith('/api/') and token and not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return self.reply(401,{'error':'Enter the access token configured on your local server'})
                body={}
                if method in ('POST','PATCH'):
                    try:length=int(self.headers.get('Content-Length','0'))
                    except ValueError:raise UserError('Invalid request size')
                    if not 0<length<=100_000:raise UserError('JSON body must be under 100 KB')
                    try:body=json.loads(self.rfile.read(length))
                    except ValueError:raise UserError('Invalid JSON')
                    if not isinstance(body,dict):raise UserError('JSON object required')
                if path=='/api/status' and method=='GET':
                    from urllib.parse import urlsplit as split
                    return self.reply(200,{'paused':(service.root/'PAUSE').exists(),'model_configured':model_ready(),
                                           'provider_host':split(os.environ.get('LLM_BASE_URL','')).hostname,
                                           'model':os.environ.get('LLM_MODEL'),'version':'0.1.0','publication_enabled':False})
                if path=='/api/projects':
                    if method=='GET':return self.reply(200,service.list_projects())
                    if method=='POST':return self.reply(201,service.create(body))
                parts=path.strip('/').split('/')
                if len(parts)>=3 and parts[:2]==['api','projects']:
                    id=parts[2]
                    if len(parts)==3:
                        if method=='GET':return self.reply(200,service.view(id))
                        if method=='PATCH':return self.reply(200,service.update(id,body))
                    if len(parts)==4 and method=='POST':
                        if parts[3]=='runs':return self.reply(202,service.run(id,body))
                        if parts[3]=='schedules':return self.reply(201,service.schedule(id,body))
                if len(parts)==4 and parts[:2]==['api','artifacts']:
                    if parts[3]=='approve' and method=='POST':return self.reply(200,service.approve(parts[2],body))
                    if parts[3]=='export' and method=='GET':return self.reply(200,service.store.get('artifacts',parts[2])['text'],'text/markdown')
                if len(parts)==4 and parts[:2]==['api','schedules'] and parts[3]=='disable' and method=='POST':return self.reply(200,service.disable_schedule(parts[2]))
                if path.startswith('/api/'):return self.reply(404,{'error':'Endpoint not implemented'})
                files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
                if method=='GET' and path in files:
                    file=ROOT/'goalpilot/static'/files[path]
                    return self.reply(200,file.read_bytes(),mimetypes.guess_type(file)[0] or 'text/plain')
                return self.reply(404,{'error':'Not found'})
            except UserError as e:return self.reply(400,{'error':str(e)})
            except Exception:return self.reply(500,{'error':'Server error; details withheld to protect project data'})
        def do_GET(self):self.dispatch('GET')
        def do_POST(self):self.dispatch('POST')
        def do_PATCH(self):self.dispatch('PATCH')
    return Handler


def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);p.add_argument('--no-worker',action='store_true');args=p.parse_args()
    service=Service(os.environ.get('GOALPILOT_DB'));server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(service,os.environ.get('GOALPILOT_TOKEN','')))
    if not args.no_worker:threading.Thread(target=service.loop,daemon=True).start()
    print(f'GoalPilot: http://127.0.0.1:{server.server_port} — local-only; no publisher enabled',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:service.stop.set();server.server_close()

if __name__=='__main__':main()
