"""Bounded, process-local browser reports; never evidence of trading readiness."""
import re
import threading
import time

_lock = threading.Lock()
_tabs = {}
CODES = {'ok', 'data-unavailable', 'spot-mismatch', 'spot-hidden', 'warning-unrendered'}


def record(details, now=None):
    now = time.time() if now is None else now
    if not isinstance(details, dict):
        raise ValueError('Invalid UI observation')
    tab, code = details.get('tab'), details.get('code')
    if not isinstance(tab, str) or not re.fullmatch(r'[a-f0-9-]{16,64}', tab) or code not in CODES:
        raise ValueError('Invalid UI observation')
    with _lock:
        previous = _tabs.get(tab, {})
        failure = code in {'spot-mismatch', 'spot-hidden', 'warning-unrendered'}
        _tabs[tab] = {'code':code, 'observedAt':now,
                      'lastFailureAt':now if failure else previous.get('lastFailureAt'),
                      'lastRecoveryAt':now if code == 'ok' and previous.get('code') in {'spot-mismatch','spot-hidden','warning-unrendered'} else previous.get('lastRecoveryAt')}
        for key in sorted(_tabs, key=lambda k:_tabs[k]['observedAt'])[:-32]:
            del _tabs[key]


def snapshot(now=None):
    now = time.time() if now is None else now
    with _lock:
        recent = [dict(v) for v in _tabs.values() if 0 <= now-v['observedAt'] <= 180]
    faults = sorted({v['code'] for v in recent if v['code'] in {'spot-mismatch','spot-hidden','warning-unrendered'}})
    return {'status':'observed' if recent else 'unavailable',
            'state':'error' if faults else 'observed' if recent else 'not-observed',
            'activeReports':len(recent), 'codes':faults,
            'healthyReports':sum(v['code']=='ok' for v in recent),
            'dataUnavailableReports':sum(v['code']=='data-unavailable' for v in recent),
            'lastObservedAt':max((v['observedAt'] for v in recent),default=None),
            'lastFailureAt':max((v['lastFailureAt'] for v in recent if v['lastFailureAt']),default=None),
            'lastRecoveryAt':max((v['lastRecoveryAt'] for v in recent if v['lastRecoveryAt']),default=None),
            'scope':'authenticated-visible-page-DOM-reports-not-screenshot-or-trade-approval',
            'note':'Keine Meldung nach 180 Sekunden: nicht beobachtet; geschlossene oder ältere Seiten gelten nicht als erfolgreich geprüft.'}
