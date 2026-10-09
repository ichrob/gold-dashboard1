"""Single-account recovery. Raw passwords/tokens never enter persistence or logs."""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError
from urllib.request import Request, build_opener

EMAIL = os.environ.get('BOB_RECOVERY_EMAIL', 'robsimon@gmx.de').strip().lower()
ORIGIN = os.environ.get('BOB_PUBLIC_ORIGIN', 'https://bob-private-scanner.onrender.com').rstrip('/')
ITERATIONS = 600000
TOKEN_TTL = 900
RECOVERY_COOKIE = '__Host-bob_recovery'


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_recovery (
        account TEXT PRIMARY KEY, password_hash TEXT, version INTEGER NOT NULL DEFAULT 0,
        token_hash TEXT, expires_at DOUBLE PRECISION NOT NULL DEFAULT 0,
        last_request DOUBLE PRECISION NOT NULL DEFAULT 0,
        window_start DOUBLE PRECISION NOT NULL DEFAULT 0, requests INTEGER NOT NULL DEFAULT 0
    )''')


def handle(conn, action, payload, now=None):
    now = time.time() if now is None else now
    account = payload.get('account', '')
    if not isinstance(account, str) or not re.fullmatch('[a-f0-9]{64}', account):
        raise ValueError('Ungültiges Konto')
    conn.execute('INSERT INTO bob_recovery(account) VALUES(%s) ON CONFLICT DO NOTHING', (account,))
    row = conn.execute('''SELECT password_hash,version,token_hash,expires_at,last_request,window_start,requests
        FROM bob_recovery WHERE account=%s FOR UPDATE''', (account,)).fetchone()
    if action == 'state':
        return {'passwordHash': row[0], 'version': row[1]}
    digest = payload.get('tokenHash', '')
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise ValueError('Ungültiger Rücksetzlink')
    if action == 'issue':
        count = row[6] if now-row[5] < 3600 else 0
        if now-row[4] < 60 or count >= 5:
            return {'issued': False}
        window = row[5] if count else now
        conn.execute('''UPDATE bob_recovery SET token_hash=%s,expires_at=%s,last_request=%s,
            window_start=%s,requests=%s WHERE account=%s''',
            (digest, now+TOKEN_TTL, now, window, count+1, account))
        return {'issued': True}
    valid = bool(row[2]) and hmac.compare_digest(digest, row[2]) and row[3] > now
    if action == 'cancel':
        if valid:
            conn.execute('UPDATE bob_recovery SET token_hash=NULL,expires_at=0 WHERE account=%s', (account,))
        return {'ok': True}
    if action == 'reset':
        encoded = payload.get('passwordHash', '')
        if not isinstance(encoded, str) or not re.fullmatch(r'pbkdf2_sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}', encoded):
            raise ValueError('Ungültiger Passwort-Hash')
        if not valid:
            return {'ok': False}
        conn.execute('''UPDATE bob_recovery SET password_hash=%s,version=version+1,
            token_hash=NULL,expires_at=0 WHERE account=%s''', (encoded, account))
        conn.execute('DELETE FROM bob_browser_sessions')
        return {'ok': True}
    raise ValueError('Unbekannte Wiederherstellungsaktion')


def rpc(action, user, **fields):
    import bob_auth as auth
    base = auth.STORE_URL.rstrip('/')
    if not auth.persistent_configured():
        raise OSError('Passwortspeicher nicht konfiguriert')
    if not base.startswith(('https://', 'http://')):
        base = 'http://' + base
    payload = {'account': hashlib.sha256(user.encode()).hexdigest(), **fields}
    request = Request(base+'/auth-recovery/'+action, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'X-Bob-Push-Token': auth.STORE_TOKEN}, method='POST')
    with build_opener(auth.NoRedirect()).open(request, timeout=12) as response:
        data = response.read(4097)
    if len(data) > 4096:
        raise ValueError('Ungültige Antwort')
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError('Ungültige Antwort')
    return result


def state(user):
    import bob_auth as auth
    return rpc('state', user) if auth.persistent_configured() else {'passwordHash': None, 'version': 0}


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def matches(candidate, configured, current):
    encoded = current.get('passwordHash')
    if encoded is None:
        return bool(configured) and hmac.compare_digest(candidate.encode(), configured.encode())
    if not re.fullmatch(r'pbkdf2_sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}', encoded):
        return False
    _, iterations, salt, expected = encoded.split('$')
    digest = hashlib.pbkdf2_hmac('sha256', candidate.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(digest, expected)


def binding_key(configured, current):
    return current.get('passwordHash') or configured


def configured():
    import bob_auth as auth
    return bool(os.environ.get('RESEND_API_KEY') and EMAIL and auth.persistent_configured())


def page(handler, reset_token='', message='', status=200):
    import bob_auth as auth
    csrf = recovery_csrf()
    reset = bool(reset_token)
    title = 'Neues Passwort festlegen' if reset else 'Passwort vergessen?'
    if reset:
        fields = f'''<input type="hidden" name="token" value="{html.escape(reset_token, quote=True)}">
        <label>Neues Passwort (mindestens 12 Zeichen)<input name="password" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required></label>
        <label>Passwort wiederholen<input name="confirm" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required></label>'''
    else:
        fields = '<p>Gib deine hinterlegte E-Mail-Adresse ein. Du erhältst einen Link, der 15 Minuten gilt.</p><label>E-Mail-Adresse<input name="email" type="email" autocomplete="email" maxlength="254" required></label>'
    form = f'<form method="post" action="/{"reset-password" if reset else "forgot-password"}"><input type="hidden" name="csrf" value="{csrf}">{fields}<button>{"Passwort speichern" if reset else "Rücksetzlink anfordern"}</button></form>' if configured() else '<p>Der E-Mail-Versand ist noch nicht eingerichtet.</p>'
    body = f'''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Bob – {title}</title>
    <style>body{{font-family:system-ui;background:#f3f5f8;margin:0;padding:24px}}main{{max-width:380px;margin:6vh auto;background:white;border-radius:18px;padding:28px}}label,input,button{{display:block;box-sizing:border-box;width:100%;margin-top:12px}}input,button{{padding:13px;border:1px solid #ccd3dd;border-radius:9px;font:inherit}}button{{background:#2358b6;color:white}}a{{color:#2358b6}}p{{line-height:1.5}}</style>
    <main><h1>{title}</h1><p role="status">{html.escape(message)}</p>{form}<p><a href="/login">Zur Anmeldung</a></p></main></html>'''.encode()
    auth.send(handler, status, body, cookies=[auth.set_cookie(RECOVERY_COOKIE, csrf, 600)])


def recovery_csrf():
    import bob_auth as auth
    payload = str(int(time.time())) + '.' + secrets.token_urlsafe(32)
    signature = hmac.new(auth.STORE_TOKEN.encode(), ('bob-recovery-csrf-v1:'+payload).encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def valid_csrf(token, cookie_value):
    import bob_auth as auth
    if not auth.STORE_TOKEN or not isinstance(token, str) or not re.fullmatch(r'[0-9]{10}\.[A-Za-z0-9_-]{43}\.[a-f0-9]{64}', token):
        return False
    if not hmac.compare_digest(token.encode(), cookie_value.encode()):
        return False
    payload, signature = token.rsplit('.', 1)
    expected = hmac.new(auth.STORE_TOKEN.encode(), ('bob-recovery-csrf-v1:'+payload).encode(), hashlib.sha256).hexdigest()
    age = time.time()-int(payload.split('.')[0])
    return 0 <= age <= 600 and hmac.compare_digest(signature, expected)


def read_form(handler):
    import bob_auth as auth
    length = int(handler.headers.get('Content-Length', '0'))
    if not 0 < length <= 8192:
        print('BOB_RECOVERY rejected=body-size', flush=True)
        raise ValueError('Ungültige Anfrage')
    if not auth.same_origin(handler.headers):
        print('BOB_RECOVERY rejected=origin', flush=True)
        raise ValueError('Ungültige Anfrage')
    if handler.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
        raise ValueError('Ungültige Anfrage')
    fields = parse_qs(handler.rfile.read(length).decode(), max_num_fields=8)
    csrf = fields.get('csrf', [''])[0]
    if not valid_csrf(csrf, auth.cookie(handler.headers, RECOVERY_COOKIE)):
        print('BOB_RECOVERY rejected=csrf', flush=True)
        raise ValueError('Formular abgelaufen. Bitte erneut öffnen.')
    return {key: values[0] for key, values in fields.items()}


def email_link(token):
    import bob_auth as auth
    link = ORIGIN+'/reset-password?token='+token
    body = {'from': os.environ.get('BOB_RECOVERY_FROM', 'Bob <onboarding@resend.dev>'), 'to': [EMAIL],
        'subject': 'Bob: Passwort zurücksetzen',
        'text': 'Für dein Bob-Konto wurde ein neues Passwort angefordert.\n\n'+link+'\n\nDieser Link gilt 15 Minuten und kann nur einmal verwendet werden. Erst nach dem Speichern eines neuen Passworts ändert sich dein Zugang. Falls du das nicht angefordert hast, ignoriere diese E-Mail.'}
    request = Request('https://api.resend.com/emails', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+os.environ['RESEND_API_KEY'].strip(), 'User-Agent': 'Bob/1.0'}, method='POST')
    try:
        with build_opener(auth.NoRedirect()).open(request, timeout=15) as response:
            result = json.loads(response.read(4096))
    except HTTPError as exc:
        # Categorize without exposing provider text, keys, recipient or reset URL.
        detail = exc.read(4096).decode('utf-8', errors='replace').lower()
        reason = 'provider-rejected'
        if 'only send testing emails' in detail:
            reason = 'account-email-mismatch'
        elif 'api key' in detail:
            reason = 'api-key'
        elif 'domain' in detail and 'verif' in detail:
            reason = 'sender-domain'
        elif '1010' in detail or 'cloudflare' in detail:
            reason = 'provider-client-block'
        print(f'BOB_RECOVERY mail_status={exc.code} reason={reason}', flush=True)
        raise
    if not result.get('id'):
        raise OSError('Mail nicht angenommen')
    print('BOB_RECOVERY email=provider-accepted', flush=True)


def route(handler, user):
    import bob_auth as auth
    path = urlparse(handler.path).path
    if path not in ('/forgot-password', '/reset-password'):
        return False
    token = ''
    try:
        if handler.command == 'GET':
            if path == '/reset-password':
                token = parse_qs(urlparse(handler.path).query, max_num_fields=2).get('token', [''])[0]
                if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
                    page(handler, message='Rücksetzlink ungültig. Bitte einen neuen Link anfordern.', status=400)
                    return True
            page(handler, token)
            return True
        if handler.command != 'POST':
            auth.send(handler, 405)
            return True
        fields = read_form(handler)
        if not configured():
            page(handler, message='Der E-Mail-Versand ist noch nicht eingerichtet.', status=503)
            return True
        if path == '/forgot-password':
            if hmac.compare_digest(fields.get('email', '').strip().lower().encode(), EMAIL.encode()):
                token = secrets.token_urlsafe(32)
                digest = hashlib.sha256(token.encode()).hexdigest()
                if rpc('issue', user, tokenHash=digest).get('issued'):
                    try:
                        email_link(token)
                    except Exception:
                        rpc('cancel', user, tokenHash=digest)
                        raise
            page(handler, message='Falls die Adresse hinterlegt ist, wurde ein Rücksetzlink angefordert. Prüfe auch deinen Spam-Ordner. Weitere Anfragen sind begrenzt.')
        else:
            token = fields.get('token', '')
            if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
                raise ValueError('Rücksetzlink ungültig.')
            password = fields.get('password', '')
            if not 12 <= len(password) <= 1024 or password != fields.get('confirm'):
                page(handler, token, 'Bitte zweimal dasselbe Passwort mit mindestens 12 Zeichen eingeben.', 400)
                return True
            # Serialize expensive public reset requests with the existing auth limiter.
            with auth.LOCK:
                now = time.time()
                auth.FAILURES[:] = [x for x in auth.FAILURES if x > now-60]
                if len(auth.FAILURES) >= 30:
                    auth.send(handler, 429, b'Bitte eine Minute warten.')
                    return True
                auth.FAILURES.append(now)
            result = rpc('reset', user, tokenHash=hashlib.sha256(token.encode()).hexdigest(), passwordHash=hash_password(password))
            if not result.get('ok'):
                page(handler, message='Link abgelaufen oder bereits verwendet. Bitte einen neuen Link anfordern.', status=400)
            else:
                with auth.LOCK:
                    auth.SESSIONS.clear()
                print('BOB_RECOVERY password=reset', flush=True)
                auth.send(handler, 303, location='/login?reset=1', cookies=[auth.set_cookie(auth.COOKIE, '', 0), auth.set_cookie(RECOVERY_COOKIE, '', 0)])
    except (ValueError, UnicodeError):
        page(handler, message='Ungültige oder abgelaufene Anfrage. Bitte erneut versuchen.', status=400)
    except Exception as exc:
        # Never log exception text: provider bodies/URLs can contain secrets.
        print('BOB_RECOVERY error='+type(exc).__name__, flush=True)
        page(handler, message='Wiederherstellung momentan nicht möglich. Bitte später erneut versuchen.', status=503)
    return True
