"""Public Onvista quote fallback. Keep source clocks and issuer contract terms."""
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

# Previously verified Onvista instrument identities from sg_quotes.PRODUCT_IDS.
IDS = {'DE000FG5GUT0':336000321, 'DE000FG4JXV7':340459583, 'DE000FG7EPT1':341071258, 'DE000FG6XB39':339841792, 'DE000FC1CHB7':309138945}
PAGES = {isin:'https://www.onvista.de/derivate/Knock-Outs/handelsplaetze/'+str(id)+'-'+isin[5:11]+'-'+isin for isin,id in IDS.items()}
_CACHE = {}
_FAILURES = {}
_LOCK = threading.Lock()

def clock(value):
    if not isinstance(value, str) or not re.search(r'(Z|[+-]\d{2}:\d{2})$', value):
        raise ValueError('Quellenzeit fehlt')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

def parse_page(html, isin, now=None):
    now = now or datetime.now(timezone.utc)
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(match[1])['props']['pageProps']['data']['snapshot']
    instrument = data['instrument']
    if instrument['isin'] != isin or instrument['wkn'] != isin[5:11] or instrument['entitySubType'] != 'KNOCKOUT_CERTIFICATE':
        raise ValueError('Produktidentität stimmt nicht überein')
    details = data['derivativesDetails']
    underlying = data['derivativesUnderlyingList']['list']
    if (str(instrument['entityValue']) != str(IDS[isin]) or details.get('dataStatus') != 1
            or details.get('hasBarrierBeenHit') is not False or details.get('numberUnderlyings') != 1
            or details.get('isoCurrency') != 'EUR' or len(underlying) != 1
            or underlying[0]['instrument'].get('isin') != 'XC0009655157'
            or details.get('nameExerciseRight') not in ('CALL', 'PUT')):
        raise ValueError('Status oder Gold-Spot-Basiswert nicht bestätigt')
    candidates = []
    for q in data['quoteList']['list']:
        if str(q['idInstrument']) != str(instrument['entityValue']) or q['isoCurrency'] != 'EUR' or q.get('codeQualityPriceBidAsk') != 'RLT':
            continue
        bid, ask = float(q['bid']), float(q['ask'])
        dates = [clock(q['datetimeBid']), clock(q['datetimeAsk'])]
        if not (0 < bid <= ask and math.isfinite(ask)) or any(not 0 <= (now-d).total_seconds() <= 90 for d in dates):
            continue
        candidates.append((min(dates), q))
    if not candidates:
        raise ValueError('Kein aktuelles Geld-/Briefpaar')
    _, q = max(candidates, key=lambda item: item[0])
    figure = data['derivativesFigure']
    leverage = float(figure['gearingAsk'])
    if not math.isfinite(leverage) or leverage < 1:
        raise ValueError('Hebel fehlt')
    # Calculation time is not the age of its inputs; preserve both explicitly.
    dates = [clock(figure[k]) for k in ('datetimeCalculation', 'datetimeAskPrice', 'datetimePriceUnderlyingCalculation')]
    if any(d > now for d in dates):
        raise ValueError('Hebelzeit liegt in der Zukunft')
    return dict(isin=isin, direction='LONG' if details['nameExerciseRight']=='CALL' else 'SHORT', bid=float(q['bid']), ask=float(q['ask']), price=float(q['ask']),
                spread=float(q['ask'])-float(q['bid']), currency='EUR',
                bidAt=q['datetimeBid'], askAt=q['datetimeAsk'], quoteAt=min(clock(q['datetimeBid']), clock(q['datetimeAsk'])).isoformat(),
                leverage=leverage, leverageAt=min(dates).isoformat(),
                leverageCalculatedAt=figure['datetimeCalculation'],
                source='Onvista · '+q['market']['name'], sourceUrl=PAGES[isin],
                priceKind='secondary-market', isDegiroQuote=False)

def fetch(isin):
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic() < cached[0]:
            return cached[1]
    try:
        req = Request(PAGES[isin], headers={'User-Agent': 'Bob public product research', 'Accept': 'text/html'})
        with urlopen(req, timeout=20) as response:
            if not response.url.startswith('https://www.onvista.de/'):
                raise ValueError('Unerwartete Weiterleitung')
            result = parse_page(response.read(4000000).decode('utf-8'), isin)
        ttl = 30
        with _LOCK:
            _FAILURES.pop(isin, None)
    except Exception as exc:
        code = 'HTTP_'+str(exc.code) if hasattr(exc,'code') else type(exc).__name__
        with _LOCK:
            _FAILURES[isin] = dict(state='unavailable', code=code, checkedAt=datetime.now(timezone.utc).isoformat())
        result, ttl = None, 300
    with _LOCK:
        _CACHE[isin] = (time.monotonic()+ttl, result)
    return result

def apply_backup(primary, isin, now=None):
    meta = primary.get('metadata', {})
    if (isin not in PAGES or primary.get('isin') != isin or not primary.get('productVerified')
            or meta.get('status') != 1 or meta.get('underlyingType') != 'SPOT'
            or primary.get('eligible') or primary.get('sourceDisabled')):
        return primary
    backup = fetch(isin)
    if not backup:
        return dict(primary, backupStatus=_FAILURES.get(isin, {'state':'unavailable','code':'NO_CURRENT_PAIR'}))
    if backup.get('direction') != meta.get('direction'):
        return dict(primary, backupStatus={'state':'rejected','code':'DIRECTION_MISMATCH'})
    now = now or datetime.now(timezone.utc)
    # Every use rechecks cache age; never renew quote clocks on retrieval.
    try:
        if any(not 0 <= (now-clock(backup[k])).total_seconds() <= 90 for k in ('bidAt', 'askAt')):
            return primary
    except (KeyError, ValueError, TypeError):
        return primary
    try:
        if primary.get('found') and all(clock(primary[k]) >= clock(backup[k]) for k in ('bidAt','askAt')):
            return primary
    except (KeyError, ValueError, TypeError):
        pass
    result = dict(primary, **backup)
    result.update(found=True, eligible=False, fresh=False, backupActive=True, backupStatus={'state':'active'},
                  issuerSource=primary.get('source'), issuerSourceUrl=primary.get('sourceUrl'),
                  direction=meta.get('direction'), ko=meta.get('ko'),
                  snapshotAt=min(clock(backup[k]) for k in ('bidAt','askAt','leverageAt')).isoformat(),
                  reason='Backup-Kurse von Onvista; Hebel mit eigenem älteren Datenstand – rechnerische Empfehlung, keine Live-Freigabe',
                  leverageNote='Onvista-Hebel mit separatem Berechnungs- und Eingangsdatenstand; kann vom Hebel beim aktuellen Briefkurs abweichen.')
    # The backup is used for indicative analysis only until complete live validation.
    return result
