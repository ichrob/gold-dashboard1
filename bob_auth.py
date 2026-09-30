"""Password-backed browser sessions; no credentials in cookies or URLs."""
import base64
import hmac
import html
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs

COOKIE = '__Host-bob_session'
CSRF_COOKIE = '__Host-bob_login'
TTL = 8 * 60 * 60
LOCK = threading.Lock()
SESSIONS = {}
PENDING = {}
FAILURES = []


def cookie(headers, name):
    try:
        jar = SimpleCookie(headers.get('Cookie', ''))
        return jar[name].value if name in jar else ''
    except CookieError:
        return ''


def authenticated(headers, user, password):
    if not user or not password:
        return False
    expected = 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()
    if hmac.compare_digest(headers.get('Authorization', '').encode(), expected.encode()):
        return True
    token = cookie(headers, COOKIE)
    with LOCK:
        return SESSIONS.get(token, 0) > time.time()


def same_origin(headers):
    return headers.get('Origin', '') == 'https://' + headers.get('Host', '')


def send(handler, status, body=b'', location=None, cookies=()):
    handler.send_response(status)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('X-Frame-Options', 'DENY')
    handler.send_header('Referrer-Policy', 'same-origin')
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


def login_page(handler, error=''):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with LOCK:
        for key, expiry in list(PENDING.items()):
            if expiry <= now:
                del PENDING[key]
        if len(PENDING) >= 512:
            PENDING.pop(next(iter(PENDING)))
        PENDING[token] = now + 600
    body = f'''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Bob – Anmeldung</title><style>body{{font-family:system-ui;background:#f3f5f8;margin:0;padding:24px}}main{{max-width:360px;margin:8vh auto;background:white;border-radius:18px;padding:28px}}label,input,button{{display:block;box-sizing:border-box;width:100%;margin-top:12px}}input,button{{padding:13px;border:1px solid #ccd3dd;border-radius:9px;font:inherit}}button{{background:#2358b6;color:white}}p{{color:#49566a}}.error{{color:#a12222}}</style><main><h1>Bob anmelden</h1><p>Nutze deine bestehenden Bob-Zugangsdaten.</p><p class="error">{html.escape(error)}</p><form method="post" action="/login"><input type="hidden" name="csrf" value="{token}"><label for="username">Benutzername</label><input id="username" name="username" type="text" autocomplete="username" required maxlength="256"><label for="password">Passwort</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="1024"><button type="submit">Anmelden</button></form></main></html>'''.encode()
    send(handler, 200, body, cookies=[set_cookie(CSRF_COOKIE, token, 600)])


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
            send(handler, 403, b'Anmeldung abgelaufen. Bitte Seite neu laden.')
            return
        if limited:
            send(handler, 429, b'Bitte eine Minute warten.')
            return
        ok = bool(user and password) and hmac.compare_digest(fields.get('username', [''])[0].encode(), user.encode()) and hmac.compare_digest(fields.get('password', [''])[0].encode(), password.encode())
        if not ok:
            with LOCK:
                FAILURES.append(now)
            login_page(handler, 'Anmeldung fehlgeschlagen. Bitte Zugangsdaten prüfen.')
            return
        token = secrets.token_urlsafe(32)
        with LOCK:
            for key, expiry in list(SESSIONS.items()):
                if expiry <= now:
                    del SESSIONS[key]
            SESSIONS.pop(cookie(handler.headers, COOKIE), None)
            if len(SESSIONS) >= 512:
                SESSIONS.pop(next(iter(SESSIONS)))
            SESSIONS[token] = now + TTL
        send(handler, 303, location='/', cookies=[set_cookie(COOKIE, token, TTL), set_cookie(CSRF_COOKIE, '', 0)])
    except (ValueError, UnicodeError):
        send(handler, 400, b'Ungueltige Anmeldung.')


def logout(handler):
    if not same_origin(handler.headers):
        send(handler, 403)
        return
    with LOCK:
        SESSIONS.pop(cookie(handler.headers, COOKIE), None)
    send(handler, 303, location='/login', cookies=[set_cookie(COOKIE, '', 0)])
