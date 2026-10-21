"""Store only an encrypted Personal configuration in the existing private DB."""
import re

KEY = 'snaptrade_personal_v1'


def handle(conn, action, payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid settings')
    if action == 'read' and not payload:
        row = conn.execute('SELECT value FROM bob_settings WHERE key=%s', (KEY,)).fetchone()
        return {'sealed': row[0] if row else None}
    if action == 'save' and set(payload) == {'sealed'}:
        value = payload['sealed']
        if not isinstance(value, str) or not 100 <= len(value) <= 8192 or not re.fullmatch(r'[A-Za-z0-9_=-]+', value):
            raise ValueError('Invalid sealed settings')
        conn.execute('INSERT INTO bob_settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (KEY, value))
        return {'saved': True}
    if action == 'delete' and not payload:
        conn.execute('DELETE FROM bob_settings WHERE key=%s', (KEY,))
        return {'deleted': True}
    raise ValueError('Invalid settings action')
