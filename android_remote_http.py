"""Separate browser consent and phone-only polling; diagnostic tokens do not apply."""
import json
import re
from pathlib import Path
from urllib.error import HTTPError
import bob_auth
from android_telemetry_http import send
PAGE=Path(__file__).with_name('android_remote_pair.html').read_bytes()

def route(h, method, path, forward):
    if path=='/handy/remote' and method=='GET':
        h.send_response(200)
        for key,value in [('Content-Type','text/html; charset=utf-8'),('Cache-Control','no-store'),('Referrer-Policy','no-referrer'),('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"),('Content-Length',str(len(PAGE)))]:h.send_header(key,value)
        h.end_headers();h.wfile.write(PAGE);return True
    if path not in ('/api/android-remote/pair','/api/android-remote/device'):return False
    if method!='POST':send(h,405,{'error':'POST required'});return True
    pair=path.endswith('/pair')
    if pair:
        if not h.authenticated():send(h,401,{'error':'Login required'});return True
        if not bob_auth.same_origin(h.headers):send(h,403,{'error':'Same origin required'});return True
    else:
        credential=h.headers.get('Authorization','')
        if not re.fullmatch(r'Bearer [a-f0-9]{64}',credential):send(h,401,{'error':'Session credential required'});return True
    try:
        size=h.headers.get('Content-Length','')
        if not size.isdecimal() or not 0<int(size)<=8192:raise ValueError()
        if h.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError()
        value=json.loads(h.rfile.read(int(size)))
        if not isinstance(value,dict):raise ValueError()
        if pair:
            if set(value)!={'tokenHash'}:raise ValueError()
            payload={'op':'pair',**value}
        else:
            if value.get('op') not in ('poll','revoke') or 'token' in value:raise ValueError()
            payload={**value,'token':credential[7:]}
        send(h,200,forward(payload))
    except HTTPError as e:send(h,e.code if e.code in (400,401,403,429) else 503,{'error':'Remote session request rejected'})
    except (ValueError,UnicodeError):send(h,400,{'error':'Invalid remote session request'})
    except Exception:send(h,503,{'error':'Remote session unavailable'})
    return True
