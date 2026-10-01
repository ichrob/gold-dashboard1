"""PostgreSQL session metadata; no passwords or raw browser cookies."""
import math
import re
import time

MAX_TTL = 7 * 24 * 60 * 60


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_browser_sessions (
        token_hash TEXT PRIMARY KEY,
        binding TEXT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL
    )''')


def handle(conn, action, payload, now=None):
    now = time.time() if now is None else now
    digest = payload.get('tokenHash')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Ungültige Sitzungskennung')
    if action == 'revoke':
        conn.execute('DELETE FROM bob_browser_sessions WHERE token_hash=%s', (digest,))
        return {'ok': True}
    binding = payload.get('binding')
    if not isinstance(binding, str) or not re.fullmatch(r'[0-9a-f]{64}', binding):
        raise ValueError('Ungültige Sitzungsbindung')
    if action == 'create':
        expiry = payload.get('expiresAt')
        if (isinstance(expiry, bool) or not isinstance(expiry, (int, float))
                or not math.isfinite(expiry) or not now < expiry <= now + MAX_TTL):
            raise ValueError('Ungültige Sitzungsdauer')
        conn.execute('DELETE FROM bob_browser_sessions WHERE expires_at <= now()')
        conn.execute('''INSERT INTO bob_browser_sessions(token_hash,binding,expires_at)
            VALUES(%s,%s,to_timestamp(%s))''', (digest, binding, expiry))
        return {'ok': True}
    if action == 'check':
        row = conn.execute('''SELECT 1 FROM bob_browser_sessions
            WHERE token_hash=%s AND binding=%s AND expires_at > now()''', (digest, binding)).fetchone()
        return {'valid': bool(row)}
    raise ValueError('Unbekannte Sitzungsaktion')
