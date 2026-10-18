"""Only anonymous, allowlisted technical signals for the existing KI watchdog."""
import threading
import time
import bob_repair_store

CODES = frozenset(('trade-setup-stalled', 'screenshot-import-failed', 'training-audit-unavailable', 'training-portfolios-unavailable', 'training-repairs-unavailable', 'training-improve-unavailable'))
_lock = threading.Lock()
_pending = {}

def report(payload):
    if not isinstance(payload, dict) or set(payload) != {'code'} or payload.get('code') not in CODES:
        raise ValueError('Unknown assistance request')
    code = payload['code']
    with _lock:
        now = time.monotonic()
        first = code not in _pending
        _pending[code] = now
    if first:
        bob_repair_store.queue_event('detected', code)
        print('BOB_ASSISTANCE code=' + code, flush=True)
    return {'ok': True, 'status': 'queued', 'code': code,
            'note': 'Für die geplante KI-Prüfung vorgemerkt; noch keine ChatGPT-Antwort.'}

def pending_codes():
    # No private diagnostics, purchases or identifiers leave the authenticated UI.
    # A restart is not evidence of repair: watchdog issues require explicit review.
    with _lock:
        return sorted(_pending)
