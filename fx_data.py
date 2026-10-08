"""Dated FX failover for indicative calculations; never re-date observations."""
import copy
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

PRIMARY = 'https://api.exchangerate.dev/'
BACKUP = 'https://biquote.io/'
MAX_AGE = 300


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('FX-Quellenzeit fehlt')
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('FX-Zeitzone fehlt')
    return t


def age(payload, now):
    if payload.get('result') != 'success' or payload.get('base') != 'USD':
        raise ValueError('FX-Basis nicht bestätigt')
    times = [stamp(payload['data_updated_at'])]
    for currency in ('EUR', 'CHF'):
        value = payload['rates'][currency]
        if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0:
            raise ValueError('FX-Wert ungültig')
        times.append(stamp(payload['effective_at'][currency]))
    ages = [(now-t).total_seconds() for t in times]
    if min(ages) < 0:
        raise ValueError('FX-Quellenzeit zukünftig')
    return max(ages)


def parse_tick(data, symbol, now):
    if data.get('symbol') != symbol or data.get('stale') is not False or data.get('marketState') != 'open':
        raise ValueError('FX-Backup nicht aktuell oder falsches Währungspaar')
    bid, ask = data['bid'], data['ask']
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (bid, ask)) or not 0 < bid <= ask:
        raise ValueError('FX-Backup Geld/Brief ungültig')
    # lastQuoteAt is the observation, not the response timestamp.
    at = stamp(data['lastQuoteAt'])
    if not 0 <= (now-at).total_seconds() <= MAX_AGE:
        raise ValueError('FX-Backup Quellenzeit veraltet')
    mid = (bid+ask)/2
    return (1/mid if symbol == 'EURUSD' else mid), at.isoformat()


def backup(fetch, now):
    def one(symbol):
        return parse_tick(fetch(BACKUP+'api/'+symbol, BACKUP, timeout=4), symbol, now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        eur, chf = list(pool.map(one, ('EURUSD', 'USDCHF')))
    if abs((stamp(eur[1])-stamp(chf[1])).total_seconds()) > 90:
        raise ValueError('FX-Backup Währungskurse zeitlich abweichend')
    oldest = min(stamp(eur[1]), stamp(chf[1])).isoformat()
    return dict(result='success', base='USD', rates=dict(EUR=eur[0], CHF=chf[0]),
                effective_at=dict(EUR=eur[1], CHF=chf[1]), data_updated_at=oldest,
                source='live', sources=dict(EUR='live', CHF='live'), market_session='open',
                provider='biquote · datierte Broker-FX-Mittelkurse', backupActive=True,
                indicative=True, notice='Indikative Umrechnung; kein ausführbarer Produktkurs.')


def fetch_rates(fetch, previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    candidates, errors = [], []
    try:
        primary = fetch(PRIMARY+'v1/latest/USD?symbols=EUR,CHF', PRIMARY, timeout=4)
        primary = dict(primary, provider='exchangerate.dev · USD/EUR und USD/CHF')
        a = age(primary, now)
        candidates.append((a, primary))
        if a <= 90 and primary.get('source') == 'live' and primary.get('market_session') == 'open':
            return primary
        errors.append('Hauptquelle: Quellenalter '+str(round(a))+' s')
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        errors.append('Hauptquelle: '+type(exc).__name__)
    try:
        alternative = backup(fetch, now)
        candidates.append((age(alternative, now), alternative))
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        errors.append('Backup: '+str(exc))
    if previous:
        try:
            candidates.append((age(previous, now), copy.deepcopy(previous)))
        except (ValueError, KeyError, TypeError, OverflowError):
            pass
    if not candidates:
        raise ValueError('FX-Abruf nicht verfügbar · '+' · '.join(errors))
    selected = copy.deepcopy(min(candidates, key=lambda x:x[0])[1])
    selected['fetchDiagnostics'] = errors
    return selected
