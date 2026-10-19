"""Browser second factor, staged behind an explicit deployment feature gate."""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPSHandler
import bob_auth
import bob_recovery

class PasskeyRequired(Exception):
    pass

def enabled():
    return os.environ.get('BOB_PASSKEY_AVAILABLE') == '1'

def binding(headers, user):
    # Only a real validated browser session can hold a second-factor grant.
    token=bob_auth.cookie(headers,bob_auth.COOKIE)
    return hashlib.sha256((user+'\0'+token).encode()).hexdigest()

def rpc(action, headers, user, **fields):
    base=os.environ.get('BOB_PASSKEY_STORE_URL','https://bob-push-service.onrender.com').rstrip('/')
    if not base.startswith('https://'):
        raise OSError('Passkey storage requires HTTPS')
    data={'account':hashlib.sha256(user.encode()).hexdigest(),'binding':binding(headers,user),**fields}
    req=Request(base+'/auth-passkey/'+action,data=json.dumps(data).encode(),method='POST',
        headers={'Content-Type':'application/json','X-Bob-Push-Token':bob_auth.STORE_TOKEN})
    with build_opener(bob_auth.NoRedirect(),HTTPSHandler(context=bob_auth.verified_tls_context())).open(req,timeout=12) as response:
        raw=response.read(32769)
    if len(raw)>32768: raise ValueError('Oversized response')
    result=json.loads(raw)
    if not isinstance(result,dict):raise ValueError('Invalid response')
    return result

def browser_authenticated(headers,user,password):
    # Basic credentials must never turn an arbitrary cookie into a browser grant.
    browser_headers={k:v for k,v in headers.items() if k.lower()!='authorization'}
    return bool(bob_auth.cookie(browser_headers,bob_auth.COOKIE)) and bob_auth.primary_authenticated(browser_headers,user,password)

def require(headers,user,password):
    if not enabled():return
    try: result=rpc('status',headers,user)
    except Exception:raise bob_auth.AuthenticationUnavailable() from None
    if result.get('enabled') and (not result.get('verified') or not browser_authenticated(headers,user,password)):
        raise PasskeyRequired()

def respond(handler, status, value, html=False):
    body=value.encode() if html else json.dumps(value).encode()
    handler.send_response(status)
    handler.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json')
    handler.send_header('Cache-Control','no-store')
    handler.send_header('X-Content-Type-Options','nosniff')
    handler.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    handler.send_header('Content-Length',str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)

def route(handler,user,password):
    path=urlparse(handler.path).path
    if path not in ('/passkey','/passkey.js') and not path.startswith('/api/passkey/'):
        return False
    if not enabled():respond(handler,404,{'error':'NOT_AVAILABLE'});return True
    if not browser_authenticated(handler.headers,user,password):
        bob_auth.send(handler,303,location='/login') if handler.command=='GET' else respond(handler,401,{'error':'LOGIN_REQUIRED'})
        return True
    if handler.command=='GET' and path=='/passkey':
        respond(handler,200,Path(__file__).with_name('passkey.html').read_text(),html=True);return True
    if handler.command=='GET' and path=='/passkey.js':
        body=Path(__file__).with_name('passkey.js').read_bytes()
        handler.send_response(200);handler.send_header('Content-Type','text/javascript');handler.send_header('Cache-Control','no-store')
        handler.send_header('Content-Length',str(len(body)));handler.end_headers();handler.wfile.write(body);return True
    if handler.command!='POST' or not bob_auth.same_origin(handler.headers):
        respond(handler,403,{'error':'ORIGIN_REQUIRED'});return True
    try:
        length=int(handler.headers.get('Content-Length','0'))
        if not 0<length<=16384 or handler.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError()
        payload=json.loads(handler.rfile.read(length))
        if not isinstance(payload,dict):raise ValueError()
        action=path.rsplit('/',1)[-1]
        if action not in ('status','register-options','register-verify','authenticate-options','authenticate-verify','recover','revoke-credential','rotate-recovery','confirm-recovery','machine-token'):raise ValueError()
        if action in ('register-options','revoke-credential','rotate-recovery','machine-token'):
            candidate=payload.get('password','')
            if not isinstance(candidate,str):raise ValueError()
            current=bob_recovery.state(user)
            if bob_auth.check_password(user,candidate,user,password,current) is not True:
                respond(handler,403,{'error':'PASSWORD_REQUIRED'});return True
        fields={k:payload[k] for k in ('credential','code','credentialId','name') if k in payload}
        if action=='machine-token':
            result=rpc('machine-authorize',handler.headers,user)
            if result.get('ok'):
                token=os.environ.get('BOB_MCP_SERVICE_TOKEN','')
                if len(token)<32:raise OSError('Not configured')
                result={'ok':True,'token':token}
        else:
            result=rpc(action,handler.headers,user,**fields)
        respond(handler,200 if result.get('ok',True) else 403,result)
    except (ValueError,TypeError,KeyError):respond(handler,400,{'error':'INVALID_REQUEST'})
    except Exception:respond(handler,503,{'error':'PASSKEY_UNAVAILABLE'})
    return True
