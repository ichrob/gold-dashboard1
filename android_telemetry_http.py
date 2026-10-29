"""Small HTTP boundary; browser pairing and device reporting have separate authority."""
import json
import re
from urllib.error import HTTPError
import bob_auth
from pathlib import Path

PAGE=Path(__file__).with_name('android_diagnostic_pair.html').read_bytes()

def send(h, status, value):
    body=json.dumps(value).encode()
    h.send_response(status);h.send_header('Content-Type','application/json')
    h.send_header('Cache-Control','no-store');h.send_header('Content-Length',str(len(body)))
    h.end_headers();h.wfile.write(body)

def route(h, method, path, forward):
    if path=='/handy/diagnostics' and method=='GET':
        h.send_response(200);h.send_header('Content-Type','text/html; charset=utf-8')
        h.send_header('Cache-Control','no-store');h.send_header('Referrer-Policy','no-referrer')
        h.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        h.send_header('Content-Length',str(len(PAGE)));h.end_headers();h.wfile.write(PAGE);return True
    remote=path=='/api/android-remote/exchange'
    if path not in ('/api/android-diagnostics/pair','/api/android-diagnostics/report') and not remote:return False
    if method!='POST':send(h,405,{'error':'POST required'});return True
    pairing=path.endswith('/pair')
    if pairing:
        if not h.authenticated():send(h,401,{'error':'Login required'});return True
        if not bob_auth.same_origin(h.headers):send(h,403,{'error':'Same origin required'});return True
    else:
        credential=h.headers.get('Authorization','')
        if not re.fullmatch(r'Bearer [a-f0-9]{64}',credential):send(h,401,{'error':'Device credential required'});return True
    try:
        length=h.headers.get('Content-Length','')
        if not length.isdecimal() or not 0<int(length)<=(24576 if remote else 4096):raise ValueError()
        if h.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError()
        value=json.loads(h.rfile.read(int(length)))
        if pairing:
            if not isinstance(value,dict) or value.get('action') not in ('register','revokeAll'):raise ValueError()
            request=value
        else:request={'action':'report','token':credential[7:],'report':value}
        if remote:request={'action':'exchange','token':credential[7:],'value':value}
        send(h,200,forward(request,remote=True) if remote else forward(request))
    except HTTPError as exc:
        send(h,exc.code if exc.code in (400,401,403,429) else 503,{'error':'Diagnostic request rejected'})
    except (ValueError,UnicodeError):send(h,400,{'error':'Invalid diagnostic request'})
    except Exception:send(h,503,{'error':'Diagnostics temporarily unavailable'})
    return True
