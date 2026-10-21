"""Store only an encrypted Personal configuration in the existing private DB."""
import re

KEY = 'snaptrade_personal_v1'
STATE_KEY = 'snaptrade_portfolio_v1'


def handle(conn, action, payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid settings')
    key = STATE_KEY if action in ('state-read', 'state-save') else KEY
    if action in ('read', 'state-read') and not payload:
        row = conn.execute('SELECT value FROM bob_settings WHERE key=%s', (key,)).fetchone()
        return {'sealed': row[0] if row else None}
    if action in ('save', 'state-save') and set(payload) == {'sealed'}:
        value = payload['sealed']
        if not isinstance(value, str) or not 100 <= len(value) <= (900000 if action == 'state-save' else 8192) or not re.fullmatch(r'[A-Za-z0-9_=-]+', value):
            raise ValueError('Invalid sealed settings')
        conn.execute('INSERT INTO bob_settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        return {'saved': True}
    if action == 'delete' and not payload:
        conn.execute('DELETE FROM bob_settings WHERE key IN (%s,%s)', (KEY, STATE_KEY))
        return {'deleted': True}
    raise ValueError('Invalid settings action')
