"""Owner-only upload and OAuth callback. No credentials in replies or URLs."""
import hashlib
import hmac
import html
import json
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPSHandler
import bob_auth
import bob_oauth
from archive_connection import ORIGIN, CALLBACK

PATH = '/archive/connect'
SCRIPT = """document.getElementById('upload').addEventListener('submit',async e=>{e.preventDefault();const f=document.getElementById('file').files[0];const m=document.getElementById('message');if(!f||f.size>8192){m.textContent='Bitte eine JSON-Datei bis 8 KB auswählen.';return;}try{const config=JSON.parse(await f.text());const r=await fetch('/archive/connect/configure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf:document.getElementById('csrf').value,config})});if(!r.ok)throw Error();location.replace('/archive/connect');}catch(_){m.textContent='Datei konnte nicht gespeichert werden. Bitte Web-Client-JSON und Anmeldung prüfen.';}});"""


def binding(headers):
    cookie = bob_auth.cookie(headers, bob_auth.COOKIE)
    if not cookie:
        raise ValueError('Browser session required')
    return hashlib.sha256(cookie.encode()).hexdigest()


def csrf(headers):
    return hmac.new(bob_auth.STORE_TOKEN.encode(), ('archive-connect\0'+binding(headers)).encode(), hashlib.sha256).hexdigest()


def rpc(action, headers, **fields):
    base = bob_auth.STORE_URL.rstrip('/')
    if not base.startswith(('http://', 'https://')):
        base = 'http://' + base
    req = Request(base+'/archive-connection/'+action,
        data=json.dumps(dict(fields, binding=binding(headers))).encode(),
        headers={'Content-Type':'application/json', 'X-Bob-Push-Token':bob_auth.STORE_TOKEN}, method='POST')
    with build_opener(bob_auth.NoRedirect(), HTTPSHandler(context=bob_auth.verified_tls_context())).open(req, timeout=30) as response:
        raw = response.read(16385)
    if len(raw)>16384:
        raise ValueError('Invalid connection reply')
    return json.loads(raw)


def page(handler, body):
    data = bob_oauth.page('Bob mit Google Drive verbinden', body).encode()
    handler.send_response(200)
    for key, value in {'Content-Type':'text/html; charset=utf-8', 'Cache-Control':'no-store',
        'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY', 'X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':"default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        'Content-Length':str(len(data))}.items():
        handler.send_header(key,value)
    handler.end_headers()
    handler.wfile.write(data)


def route(handler, user, password):
    path = urlparse(handler.path).path
    if path != PATH and not path.startswith(PATH+'/'):
        return False
    try:
        if not user or not password or not bob_oauth.configured():
            bob_oauth.respond(handler,503,{'error':'unavailable'}); return True
        if not bob_oauth.browser_ready(handler,user,password):
            return True
        if handler.command == 'GET' and path == PATH+'/upload.js':
            data=SCRIPT.encode()
            handler.send_response(200)
            handler.send_header('Content-Type','application/javascript')
            handler.send_header('Cache-Control','no-store')
            handler.send_header('X-Content-Type-Options','nosniff')
            handler.send_header('Content-Length',str(len(data)))
            handler.end_headers(); handler.wfile.write(data)
        elif handler.command == 'GET' and path == PATH:
            status=rpc('status',handler.headers)
            body='<p>Die Archivierung bleibt ausgeschaltet. Originaldaten werden nicht gelöscht.</p>'
            if status.get('connected'):
                body+='<p>Google-Freigabe gespeichert. Die gesonderte Freigabe des privaten Archivordners und der erste Wiederherstellungstest stehen noch aus.</p>'
            else:
                body+='<p>1. In deinem Google-Web-Client diese autorisierte Weiterleitungs-URI eintragen und speichern:</p><p style="overflow-wrap:anywhere">'+html.escape(CALLBACK)+'</p>'
                if not status.get('configured'):
                    body+='<p>2. Die heruntergeladene Web-Client-JSON direkt an Bob übertragen. Sie wird verschlüsselt gespeichert.</p><form id="upload"><input type="file" id="file" accept=".json,application/json" required><input type="hidden" id="csrf" value="'+csrf(handler.headers)+'"><button>Datei sicher speichern</button></form><p id="message" role="status"></p><script src="/archive/connect/upload.js" defer></script>'
                else:
                    body+='<p>Web-Client gespeichert. Google erlaubt Bob nur Zugriff auf mit dieser App erstellte oder ausdrücklich ausgewählte Dateien. Wähle dein Archiv-Konto.</p><form method="post" action="/archive/connect/begin"><input type="hidden" name="csrf" value="'+csrf(handler.headers)+'"><button>Bei Google freigeben</button></form>'
            page(handler,body+'<p><a href="/">Zurück zu Bob</a></p>')
        elif handler.command == 'GET' and path == PATH+'/callback':
            if len(handler.path)>8192:
                raise ValueError('Oversized callback')
            fields=bob_oauth.form_fields(urlparse(handler.path).query)
            if 'error' in fields:
                page(handler,'<p>Google-Freigabe abgebrochen. Die Archivierung bleibt ausgeschaltet.</p><a href="/archive/connect">Erneut starten</a>')
            else:
                rpc('complete',handler.headers,state=fields.get('state',''),code=fields.get('code',''))
                bob_oauth.respond(handler,303,location=PATH)
        elif handler.command == 'POST' and path in (PATH+'/configure',PATH+'/begin'):
            if handler.headers.get('Origin') != ORIGIN:
                bob_oauth.respond(handler,403,{'error':'origin_required'}); return True
            fields=bob_oauth.read_body(handler,json_body=path.endswith('/configure'))
            if not isinstance(fields.get('csrf'),str) or not hmac.compare_digest(fields['csrf'],csrf(handler.headers)):
                bob_oauth.respond(handler,403,{'error':'invalid_csrf'}); return True
            if path.endswith('/configure'):
                rpc('configure',handler.headers,config=fields.get('config'))
                bob_oauth.respond(handler,200,{'configured':True})
            else:
                result=rpc('begin',handler.headers)
                url=result.get('url','')
                if not url.startswith('https://accounts.google.com/o/oauth2/v2/auth?'):
                    raise ValueError('Unexpected consent URL')
                bob_oauth.respond(handler,303,location=url)
        else:
            bob_oauth.respond(handler,404,{'error':'not_found'})
    except Exception:
        # Do not expose provider responses, uploaded secrets, codes or tokens.
        bob_oauth.respond(handler,400,{'error':'connection_failed_restart_from_archive_connect'})
    return True
