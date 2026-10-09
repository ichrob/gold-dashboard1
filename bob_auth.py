"""Password-backed browser sessions; no credentials in cookies or URLs."""
import bob_recovery
import base64
import hmac
import hashlib
import html
import json
import os
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

COOKIE = '__Host-bob_session'
CSRF_COOKIE = '__Host-bob_login'
TTL = 8 * 60 * 60
REMEMBER_TTL = 7 * 24 * 60 * 60
STORE_URL = os.environ.get('PUSH_SERVICE_URL', '')
STORE_TOKEN = os.environ.get('PUSH_SERVICE_TOKEN', '')
LOCK = threading.Lock()
SESSIONS = {}
PENDING = {}
FAILURES = []


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def persistent_configured():
    return bool(STORE_URL and STORE_TOKEN)


def session_request(action, token, user='', password='', expiry=None):
    base = STORE_URL.rstrip('/')
    if not persistent_configured():
        raise OSError('Sitzungsspeicher nicht konfiguriert')
    if not base.startswith(('http://', 'https://')):
        base = 'http://' + base
    payload = {'tokenHash': hashlib.sha256(token.encode()).hexdigest()}
    if action != 'revoke':
        payload['binding'] = hmac.new(password.encode(),
            ('bob-browser-session-v1\0'+user+'\0'+token).encode(), hashlib.sha256).hexdigest()
    if expiry is not None:
        payload['expiresAt'] = expiry
    request = Request(base+'/auth-session/'+action, data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json', 'X-Bob-Push-Token':STORE_TOKEN}, method='POST')
    # A sleeping free Render backend takes about a minute to start. Keep the
    # authenticated request pending through that start instead of falsely rejecting
    # a valid browser session after twelve seconds. No redirect or auth bypass.
    try:
        with build_opener(NoRedirect()).open(request, timeout=75) as response:
            data = response.read(4097)
        if len(data)>4096:
            raise ValueError('Sitzungsantwort zu groß')
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError('Ungültige Sitzungsantwort')
        return result
    except (OSError, ValueError, TypeError) as exc:
        # Fixed labels and numeric HTTP status only: never log a URL, request,
        # response body, cookie, binding, password or service token.
        label = action if action in ('create', 'check', 'revoke') else 'unknown'
        code = exc.code if isinstance(exc, HTTPError) else '-'
        print(f'BOB_SESSION action={label} error={type(exc).__name__} status={code}', flush=True)
        raise


def persistent_token(token):
    return bool(re.fullmatch(r'v1_[A-Za-z0-9_-]{43}', token))


def cookie(headers, name):
    try:
        jar = SimpleCookie(headers.get('Cookie', ''))
        return jar[name].value if name in jar else ''
    except CookieError:
        return ''


def authenticated(headers, user, password):
    if not user or not password:
        return False
    try:
        current = bob_recovery.state(user)
        key = bob_recovery.binding_key(password, current)
        authorization = headers.get('Authorization', '')
        if authorization.startswith('Basic '):
            try:
                supplied_user, candidate = base64.b64decode(authorization[6:], validate=True).decode().split(':', 1)
                if len(candidate) <= 1024 and hmac.compare_digest(supplied_user.encode(), user.encode()) and bob_recovery.matches(candidate, password, current):
                    return True
            except (ValueError, UnicodeError):
                pass
        token = cookie(headers, COOKIE)
        if persistent_token(token):
            return session_request('check', token, user, key).get('valid') is True
        with LOCK:
            expiry, version = SESSIONS.get(token, (0, -1))
            return expiry > time.time() and version == current['version']
    except (OSError, ValueError, TypeError, KeyError):
        return False


def same_origin(headers):
    return headers.get('Origin', '') == 'https://' + headers.get('Host', '')


def send(handler, status, body=b'', location=None, cookies=()):
    handler.send_response(status)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('X-Frame-Options', 'DENY')
    handler.send_header('Referrer-Policy', 'no-referrer')
    handler.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
    if location:
        handler.send_header('Location', location)
    for value in cookies:
        handler.send_header('Set-Cookie', value)
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    if handler.command != 'HEAD':
        handler.wfile.write(body)


def set_cookie(name, value, age):
    return f'{name}={value}; Path=/; Max-Age={age}; Secure; HttpOnly; SameSite=Strict'


def login_page(handler, error='', status=200):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with LOCK:
        for key, expiry in list(PENDING.items()):
            if expiry <= now:
                del PENDING[key]
        if len(PENDING) >= 512:
            PENDING.pop(next(iter(PENDING)))
        PENDING[token] = now + 600
    remember = '<label style="display:flex;align-items:center;gap:10px"><input style="width:auto;margin:0" type="checkbox" name="remember" value="1"> Angemeldet bleiben (7 Tage)</label><p>Nur auf deinem eigenen Gerät verwenden. Abmelden beendet die Sitzung auch nach einem Serverneustart.</p>' if persistent_configured() else ''
    body = f'''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Bob – Anmeldung</title><style>body{{font-family:system-ui;background:#f3f5f8;margin:0;padding:24px}}main{{max-width:360px;margin:8vh auto;background:white;border-radius:18px;padding:28px}}label,input,button{{display:block;box-sizing:border-box;width:100%;margin-top:12px}}input,button{{padding:13px;border:1px solid #ccd3dd;border-radius:9px;font:inherit}}button{{background:#2358b6;color:white}}p{{color:#49566a}}.error{{color:#a12222}}</style><main><h1>Bob anmelden</h1><p>Nutze deine bestehenden Bob-Zugangsdaten.</p><p class="error">{html.escape(error)}</p><form method="post" action="/login"><input type="hidden" name="csrf" value="{token}"><label for="username">Benutzername</label><input id="username" name="username" type="text" autocomplete="username" required maxlength="256"><label for="password">Passwort</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="1024">{remember}<button type="submit">Anmelden</button></form><p><a href="/forgot-password">Passwort vergessen?</a></p></main></html>'''.encode()
    send(handler, status, body, cookies=[set_cookie(CSRF_COOKIE, token, 600)])


def login(handler, user, password):
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 4096 or not same_origin(handler.headers):
            send(handler, 403, b'Anmeldung nicht akzeptiert.')
            return
        if handler.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            send(handler, 415)
            return
        fields = parse_qs(handler.rfile.read(length).decode('utf-8'), max_num_fields=8)
        csrf = fields.get('csrf', [''])[0]
        now = time.time()
        with LOCK:
            valid = bool(csrf) and hmac.compare_digest(csrf.encode(), cookie(handler.headers, CSRF_COOKIE).encode()) and PENDING.pop(csrf, 0) > now
            FAILURES[:] = [x for x in FAILURES if x > now - 60]
            limited = len(FAILURES) >= 30
        if not valid:
            login_page(handler, 'Anmeldung abgelaufen. Bitte erneut anmelden.', status=403)
            return
        if limited:
            send(handler, 429, b'Bitte eine Minute warten.')
            return
        try:
            current = bob_recovery.state(user)
        except (OSError, ValueError, TypeError):
            login_page(handler, 'Passwortspeicher momentan nicht erreichbar. Bitte später erneut versuchen.', status=503)
            return
        candidate = fields.get('password', [''])[0]
        ok = bool(user and password) and len(candidate) <= 1024 and hmac.compare_digest(fields.get('username', [''])[0].encode(), user.encode()) and bob_recovery.matches(candidate, password, current)
        if not ok:
            with LOCK:
                FAILURES.append(now)
            login_page(handler, 'Anmeldung fehlgeschlagen. Bitte Zugangsdaten prüfen.')
            return
        remember = fields.get('remember') == ['1']
        age = REMEMBER_TTL if remember else TTL
        token = ('v1_' if remember else '') + secrets.token_urlsafe(32)
        old_token = cookie(handler.headers, COOKIE)
        store_action = 'revoke' if persistent_token(old_token) else 'create'
        try:
            if persistent_token(old_token):
                if session_request('revoke', old_token).get('ok') is not True:
                    raise ValueError('Sitzung nicht beendet')
            store_action = 'create'
            if remember and session_request('create', token, user, bob_recovery.binding_key(password, current), now+age).get('ok') is not True:
                raise ValueError('Sitzung nicht gespeichert')
        except (OSError, ValueError, TypeError):
            if store_action == 'revoke':
                error = 'Die bisherige Sieben-Tage-Sitzung konnte nicht beendet werden. Der Sitzungsspeicher ist momentan nicht erreichbar. Bitte später erneut anmelden.'
            else:
                error = 'Dauerhafte Anmeldung momentan nicht verfügbar. Bitte später erneut versuchen oder ohne „Angemeldet bleiben“ anmelden.'
            login_page(handler, error)
            return
        with LOCK:
            for key, (expiry, version) in list(SESSIONS.items()):
                if expiry <= now:
                    del SESSIONS[key]
            SESSIONS.pop(cookie(handler.headers, COOKIE), None)
            if len(SESSIONS) >= 512:
                SESSIONS.pop(next(iter(SESSIONS)))
            if not remember:
                SESSIONS[token] = (now + age, current['version'])
        send(handler, 303, location='/', cookies=[set_cookie(COOKIE, token, age), set_cookie(CSRF_COOKIE, '', 0)])
    except (ValueError, UnicodeError):
        send(handler, 400, b'Ungueltige Anmeldung.')


def logout(handler):
    if not same_origin(handler.headers):
        send(handler, 403)
        return
    token = cookie(handler.headers, COOKIE)
    if persistent_token(token):
        try:
            if session_request('revoke', token).get('ok') is not True:
                raise ValueError('Sitzung nicht beendet')
        except (OSError, ValueError, TypeError):
            send(handler, 503, 'Abmelden momentan nicht möglich: Sitzungsspeicher nicht erreichbar. Bitte erneut versuchen.'.encode())
            return
    with LOCK:
        SESSIONS.pop(token, None)
    send(handler, 303, location='/login', cookies=[set_cookie(COOKIE, '', 0)])

