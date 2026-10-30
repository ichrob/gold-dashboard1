"""Private Google consent bootstrap. Never enables archiving or deletes evidence."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPSHandler
import bob_auth

ORIGIN = 'https://bob-private-scanner.onrender.com'
CALLBACK = ORIGIN + '/archive/connect/callback'
SCOPE = 'https://www.googleapis.com/auth/drive.file'
KEY = 'bob_archive_connection_v1'


def cipher():
    from cryptography.fernet import Fernet
    secret = os.environ.get('PUSH_SERVICE_TOKEN', '')
    if not secret:
        raise ValueError('Connection storage unavailable')
    key = hashlib.sha256(('bob-archive-connection-v1\0' + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def client_config(value):
    if not isinstance(value, dict) or not isinstance(value.get('web'), dict):
        raise ValueError('Web client required')
    web = value['web']
    cid, secret = web.get('client_id'), web.get('client_secret')
    if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,220}\.apps\.googleusercontent\.com', cid):
        raise ValueError('Invalid client')
    if not isinstance(secret, str) or not 16 <= len(secret) <= 256 or any(ord(c) < 33 for c in secret):
        raise ValueError('Invalid secret')
    # Uploaded endpoint/redirect fields are never trusted or followed.
    return {'client_id': cid, 'client_secret': secret}


def exchange(config, pending, code):
    if not isinstance(code, str) or not 1 <= len(code) <= 4096:
        raise ValueError('Invalid code')
    req = Request('https://oauth2.googleapis.com/token', data=urlencode({
        **config, 'code': code, 'code_verifier': pending['verifier'],
        'redirect_uri': CALLBACK, 'grant_type': 'authorization_code'}).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    with build_opener(bob_auth.NoRedirect(), HTTPSHandler(context=bob_auth.verified_tls_context())).open(req, timeout=20) as response:
        raw = response.read(32769)
    if len(raw) > 32768:
        raise ValueError('Invalid token response')
    tokens = json.loads(raw)
    if (not isinstance(tokens, dict) or tokens.get('token_type', '').lower() != 'bearer' or
            set(tokens.get('scope', '').split()) != {SCOPE} or
            not isinstance(tokens.get('refresh_token'), str) or not 16 <= len(tokens['refresh_token']) <= 8192):
        raise ValueError('Offline file permission required')
    return dict(config, type='authorized_user', refresh_token=tokens['refresh_token'],
                token_uri='https://oauth2.googleapis.com/token', scopes=[SCOPE])


def transition(state, action, payload, now=None, exchanger=exchange):
    now = time.time() if now is None else now
    binding = payload.get('binding', '')
    if not isinstance(binding, str) or not re.fullmatch('[a-f0-9]{64}', binding):
        raise ValueError('Browser binding required')
    if action == 'status':
        return {'configured': bool(state.get('client')), 'connected': bool(state.get('credentials')),
                'archiveEnabled': False, 'folderSelectionRequired': True, 'callback': CALLBACK}
    if action == 'configure':
        config = client_config(payload.get('config'))
        if state.get('credentials'):
            raise ValueError('Disconnect before replacing a connected client')
        state.clear()
        state['client'] = config
        return {'configured': True}
    if action == 'begin':
        if not state.get('client'):
            raise ValueError('Client required')
        nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        state['attempt'] = hashlib.sha256(nonce.encode()).hexdigest()
        state['pending'] = dict(hash=hashlib.sha256(nonce.encode()).hexdigest(), verifier=verifier,
                                binding=binding, expires=now + 600)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return {'url': 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(dict(
            client_id=state['client']['client_id'], redirect_uri=CALLBACK, response_type='code',
            scope=SCOPE, access_type='offline', prompt='consent', state=nonce,
            code_challenge=challenge, code_challenge_method='S256'))}
    if action == 'complete':
        p = state.get('pending', {})
        nonce = payload.get('state', '')
        if (not isinstance(nonce, str) or not re.fullmatch('[A-Za-z0-9_-]{43}', nonce) or
                p.get('expires', 0) <= now or not hmac.compare_digest(p.get('binding', ''), binding) or
                not hmac.compare_digest(p.get('hash', ''), hashlib.sha256(nonce.encode()).hexdigest())):
            raise ValueError('Expired or invalid consent')
        # Caller persists this consumption before contacting Google.
        del state['pending']
        return {'pending': p}
    raise ValueError('Invalid connection action')


def handle(conn, action, payload):
    # Serialize setup across replicas and commit consumed state before network I/O.
    conn.execute('SELECT pg_advisory_xact_lock(736981024)')
    row = conn.execute('SELECT value FROM bob_settings WHERE key=%s', (KEY,)).fetchone()
    state = json.loads(cipher().decrypt(row[0].encode())) if row else {}
    result = transition(state, action, payload)
    def save():
        sealed = cipher().encrypt(json.dumps(state).encode()).decode()
        conn.execute('INSERT INTO bob_settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (KEY, sealed))
    if action != 'status':
        save()
    if action == 'complete':
        config = state['client'].copy()
        pending = result['pending']
        conn.commit()
        credentials = exchange(config, pending, payload.get('code'))
        conn.execute('SELECT pg_advisory_xact_lock(736981024)')
        row = conn.execute('SELECT value FROM bob_settings WHERE key=%s', (KEY,)).fetchone()
        state = json.loads(cipher().decrypt(row[0].encode()))
        if state.get('client') != config or state.get('pending') or state.get('attempt') != pending['hash']:
            raise ValueError('Setup changed; restart consent')
        state['credentials'] = credentials
        save()
        result = {'connected': True, 'archiveEnabled': False, 'folderSelectionRequired': True}
    return result
