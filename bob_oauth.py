"""OAuth HTTP boundary for scoped private MCP tools, not a browser login.

Public discovery/registration never returns product data. Approval requires the
existing browser session, daily factor when enrolled, same-origin POST and CSRF.
"""
import hashlib
import hmac
import html
import json
import os
import re
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, build_opener, HTTPSHandler
import bob_auth
import bob_passkey
from bob_oauth_store import ORIGIN, RESOURCE, SCOPE, DIAGNOSTICS_SCOPE, PUSH_TEST_SCOPE, HANDY_SCOPE, REDIRECT

COOKIE = '__Host-bob_oauth'
UNTIL = '2026-11-16T23:59:59+01:00'


def configured():
    return bool(bob_auth.persistent_configured())


def rpc(action, user, **fields):
    if not configured():
        raise OSError('OAuth store unavailable')
    base = bob_auth.STORE_URL.rstrip('/')
    if not base.startswith(('http://','https://')):
        base = 'http://' + base  # Existing Render private network address.
    req = Request(base+'/auth-oauth/'+action,
                  data=json.dumps({**fields,'account':hashlib.sha256(user.encode()).hexdigest()}).encode(),
                  headers={'Content-Type':'application/json','X-Bob-Push-Token':bob_auth.STORE_TOKEN},method='POST')
    with build_opener(bob_auth.NoRedirect(),HTTPSHandler(context=bob_auth.verified_tls_context())).open(req,timeout=15) as response:
        data = response.read(32769)
    if len(data)>32768:
        raise ValueError('Oversized OAuth reply')
    value = json.loads(data)
    if not isinstance(value,dict):
        raise ValueError('Invalid OAuth reply')
    return value


def bearer_authenticated(headers, user, required_scope=SCOPE):
    authorization = headers.get('Authorization','')
    if not re.fullmatch(r'Bearer boa_[A-Za-z0-9_-]{43}',authorization):
        return False
    try:
        result = rpc('check',user,token=authorization[7:])
        return result.get('valid') is True and required_scope in str(result.get('scope', '')).split()
    except (OSError,ValueError):
        raise bob_auth.AuthenticationUnavailable() from None


def challenge_header():
    return 'Bearer resource_metadata="'+ORIGIN+'/.well-known/oauth-protected-resource", scope="'+SCOPE+'"'


def resume_location(headers):
    return '/oauth/resume' if re.fullmatch('[A-Za-z0-9_-]{43}',bob_auth.cookie(headers,COOKIE)) else '/'


def cookie(value, age=900):
    return f'{COOKIE}={value}; Path=/; Max-Age={age}; Secure; HttpOnly; SameSite=Lax'


def respond(handler, status, value=None, *, location=None, cookies=(), page=False):
    body = (value.encode() if page else json.dumps(value).encode()) if value is not None else b''
    handler.send_response(status)
    handler.send_header('Content-Type','text/html; charset=utf-8' if page else 'application/json')
    for name,val in [('Cache-Control','no-store'),('Pragma','no-cache'),('X-Content-Type-Options','nosniff'),
                     ('Referrer-Policy','same-origin'),('X-Frame-Options','DENY'),
                     ('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self' "+REDIRECT+"; frame-ancestors 'none'; base-uri 'none'")]:
        handler.send_header(name,val)
    if location:
        handler.send_header('Location',location)
    for val in cookies:
        handler.send_header('Set-Cookie',val)
    handler.send_header('Content-Length',str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def page(title, body):
    return ('<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+html.escape(title)+'</title><style>body{font:18px system-ui;background:#f3f5f8;padding:20px;color:#182430}'
            'main{max-width:520px;margin:4vh auto;padding:24px;background:white;border-radius:18px}button,a{font:inherit}'
            'button{padding:14px;margin:8px 0;width:100%;border-radius:10px;border:1px solid #ccd3dd;background:#2358b6;color:white}'
            '.secondary{background:white;color:#182430}p{line-height:1.5}</style><main><h1>'+html.escape(title)+'</h1>'+body+'</main></html>')


def form_fields(raw):
    values = parse_qs(raw,keep_blank_values=True,strict_parsing=True,max_num_fields=20)
    if any(len(v)!=1 for v in values.values()):
        raise ValueError('Duplicate OAuth parameter')
    return {k:v[0] for k,v in values.items()}


def read_body(handler, json_body=False):
    expected = 'application/json' if json_body else 'application/x-www-form-urlencoded'
    length = handler.headers.get('Content-Length','')
    if (handler.headers.get('Content-Type','').split(';')[0] != expected or
            not length.isdecimal() or not 0<int(length)<=8192):
        raise ValueError('Invalid OAuth body')
    raw = handler.rfile.read(int(length)).decode()
    value = json.loads(raw) if json_body else form_fields(raw)
    if not isinstance(value,dict):
        raise ValueError('Invalid OAuth body')
    return value


def browser_ready(handler, user, password):
    if not bob_passkey.browser_authenticated(handler.headers,user,password):
        respond(handler,303,location='/login')
        return False
    try:
        bob_passkey.require(handler.headers,user,password)
    except bob_passkey.PasskeyRequired:
        respond(handler,303,location='/passkey?oauth=1')
        return False
    return True


def csrf(headers):
    return hmac.new(bob_auth.STORE_TOKEN.encode(),
                    ('bob-oauth-revoke\0'+bob_auth.cookie(headers,bob_auth.COOKIE)).encode(),hashlib.sha256).hexdigest()


def route(handler,user,password):
    path = urlparse(handler.path).path
    if not (path.startswith('/oauth/') or path.startswith('/.well-known/oauth-')):
        return False
    if not user or not password or not configured():
        respond(handler,503,{'error':'temporarily_unavailable'}); return True
    try:
        if handler.command=='GET':
            if path in ('/.well-known/oauth-protected-resource','/.well-known/oauth-protected-resource/mcp'):
                respond(handler,200,{'resource':RESOURCE,'authorization_servers':[ORIGIN],
                                    'scopes_supported':[SCOPE, DIAGNOSTICS_SCOPE, PUSH_TEST_SCOPE, HANDY_SCOPE],'bearer_methods_supported':['header']})
            elif path=='/.well-known/oauth-authorization-server':
                respond(handler,200,{'issuer':ORIGIN,'authorization_endpoint':ORIGIN+'/oauth/authorize',
                    'token_endpoint':ORIGIN+'/oauth/token','registration_endpoint':ORIGIN+'/oauth/register',
                    'revocation_endpoint':ORIGIN+'/oauth/revoke','response_types_supported':['code'],
                    'grant_types_supported':['authorization_code','refresh_token'],'scopes_supported':[SCOPE, DIAGNOSTICS_SCOPE, PUSH_TEST_SCOPE, HANDY_SCOPE],
                    'token_endpoint_auth_methods_supported':['none'],'code_challenge_methods_supported':['S256'],
                    'authorization_response_iss_parameter_supported':True})
            elif path=='/oauth/authorize':
                if len(handler.path)>8192:raise ValueError('Oversized authorization request')
                result = rpc('begin',user,**form_fields(urlparse(handler.path).query))
                if 'error' in result:respond(handler,400,{'error':result['error']})
                else:respond(handler,303,location='/oauth/resume',cookies=[cookie(result['request'])])
            elif path=='/oauth/resume':
                nonce = bob_auth.cookie(handler.headers,COOKIE)
                pending = rpc('pending',user,request=nonce)
                if not pending.get('ok'):
                    respond(handler,400,page('Verbindung erneut starten','<p>Die Anfrage ist abgelaufen. Starte die Verbindung erneut in ChatGPT.</p>'),page=True)
                elif browser_ready(handler,user,password):
                    until = datetime.fromisoformat(UNTIL).strftime('%d.%m.%Y')
                    respond(handler,200,page('ChatGPT mit Bob verbinden',
                        ('<p>ChatGPT darf deine privaten Produktprüfberichte mit ISINs, Quellen, Zeitstempeln und fehlenden Nachweisen lesen.</p>' if SCOPE in pending.get('scope', SCOPE).split() else '') +
                        ('<p>Zusätzlich freigegeben: Diagnoseberichte zu Marktanalyse, Hintergrundjobs, Simulationen, Push-Überwachung, Recherche und offenen Problemen. Keine Zugangsdaten oder vollständigen Protokolle.</p>' if DIAGNOSTICS_SCOPE in pending.get('scope', SCOPE).split() else '') +
                        ('<p>Zusätzliche Schreibberechtigung: klar gekennzeichnete TEST-Pushs für bereits registrierte Geräte auslösen (maximal einer je fünf Minuten und zehn pro Tag/Gerät). Keine freie Nachricht, Registrierung, Änderung der Push-Kanäle oder Android-Berechtigungen.</p>' if PUSH_TEST_SCOPE in pending.get('scope', SCOPE).split() else '') +
                        ('<p>Zusätzliche Bedienberechtigung: In separat am Handy freigegebenen 15-Minuten-Sitzungen Produktlesen, feste Goldsuche oder STOPP auslösen und feste Lesediagnosen lesen. Kein Livebild, keine freien Klicks, kein Login und keine Orders.</p>' if HANDY_SCOPE in pending.get('scope',SCOPE).split() else '') +
                        '<p>Keine Orders und kein Zugriff auf dein DEGIRO-Konto.</p>'
                        '<p>Gültig höchstens 28 Tage, längstens bis '+until+'. In Bob jederzeit widerrufbar.</p>'
                        '<form method="post" action="/oauth/consent"><input type="hidden" name="request" value="'+html.escape(nonce)+'">'
                        '<button name="decision" value="approve">'+('Handy-Fernhilfe erlauben' if HANDY_SCOPE in pending.get('scope',SCOPE).split() else 'Push-Test-Berechtigung erlauben' if PUSH_TEST_SCOPE in pending.get('scope',SCOPE).split() else 'Lesezugriff erlauben')+'</button>'
                        '<button class="secondary" name="decision" value="deny">Abbrechen</button></form>'),page=True)
            elif path=='/oauth/connections':
                if browser_ready(handler,user,password):
                    grants = rpc('list',user).get('grants',[])
                    respond(handler,200,page('ChatGPT-Zugriff',
                        '<p>Aktive Freigaben: '+str(len(grants))+'</p><p>Hier kannst du alle OAuth-Freigaben sofort beenden. Dein Bob-Login bleibt bestehen.</p>'
                        '<form method="post" action="/oauth/disconnect"><input type="hidden" name="csrf" value="'+csrf(handler.headers)+'">'
                        '<button>Alle Freigaben widerrufen</button></form><p><a href="/">Zurück zu Bob</a></p>'),page=True)
            else:respond(handler,404,{'error':'not_found'})
        elif handler.command=='POST':
            if path=='/oauth/register':
                result = rpc('register',user,**read_body(handler,True))
                respond(handler,400 if 'error' in result else 201,result)
            elif path in ('/oauth/token','/oauth/revoke'):
                fields = read_body(handler)
                if handler.headers.get('Authorization') or 'client_secret' in fields or 'client_assertion' in fields:
                    respond(handler,400,{'error':'invalid_client'})
                else:
                    result = rpc('token' if path.endswith('/token') else 'revoke',user,**fields)
                    respond(handler,400 if 'error' in result else 200,result)
            elif path in ('/oauth/consent','/oauth/disconnect'):
                if handler.headers.get('Origin') != ORIGIN:
                    respond(handler,403,{'error':'origin_required'}); return True
                if not browser_ready(handler,user,password):return True
                fields = read_body(handler)
                if path=='/oauth/disconnect':
                    if not hmac.compare_digest(fields.get('csrf',''),csrf(handler.headers)):
                        respond(handler,403,{'error':'invalid_csrf'}); return True
                    rpc('revoke-all',user)
                    respond(handler,303,location='/oauth/connections')
                else:
                    nonce = bob_auth.cookie(handler.headers,COOKIE)
                    if not nonce or not hmac.compare_digest(nonce,fields.get('request','')) or fields.get('decision') not in ('approve','deny'):
                        respond(handler,403,{'error':'invalid_csrf'}); return True
                    result = rpc(fields['decision'],user,request=nonce,until=datetime.fromisoformat(UNTIL).timestamp())
                    if 'redirect_uri' not in result:
                        respond(handler,400,{'error':'invalid_request'})
                    else:
                        if result.get('redirect_uri') != REDIRECT:
                            raise ValueError('Unexpected OAuth callback')
                        destination = result.pop('redirect_uri')+'?'+urlencode(result)
                        # A form redirect remains subject to form-action across the
                        # client's redirect chain (including Android app links).
                        # A user-activated link completes the same PKCE flow without
                        # broadening CSP or resubmitting the consumed consent form.
                        respond(handler,200,page('Zurück zu ChatGPT',
                            '<p>Deine Entscheidung wurde gespeichert. Schließe die Verbindung jetzt in ChatGPT ab.</p>'
                            '<p><a rel="noreferrer" referrerpolicy="no-referrer" style="display:block;padding:14px;border-radius:10px;background:#2358b6;color:white;text-align:center;text-decoration:none" href="'+html.escape(destination,quote=True)+'">Zurück zu ChatGPT</a></p>'
                            '<p>Tippe jetzt auf den Button. Der Rückkehrlink gilt zwei Minuten. Diese Seite nicht neu laden und das Freigabeformular nicht erneut absenden.</p>'),
                            cookies=[cookie('',0)],page=True)
            else:respond(handler,404,{'error':'not_found'})
        else:respond(handler,405,{'error':'method_not_allowed'})
    except (ValueError,TypeError,UnicodeError):
        respond(handler,400,{'error':'invalid_request'})
    except OSError:
        respond(handler,503,{'error':'temporarily_unavailable'})
    return True
