"""Public Onvista quote fallback. Keep source clocks and issuer contract terms."""
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

# Previously verified Onvista instrument identities from sg_quotes.PRODUCT_IDS.
IDS = {'DE000FG5GUX2':335999756, 'DE000FG5GUT0':336000321, 'DE000FG4JXV7':340459583, 'DE000FG7EPT1':341071258, 'DE000FG6XB39':339841792, 'DE000FC1CHB7':309138945}
PAGES = {isin:'https://www.onvista.de/derivate/Knock-Outs/handelsplaetze/'+str(id)+'-'+isin[5:11]+'-'+isin for isin,id in IDS.items()}
_CACHE = {}
_FAILURES = {}
_MODEL = {}
_LOCK = threading.Lock()
ANALYSIS_MAX_AGE_SECONDS = 300

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
        if not (0 < bid <= ask and math.isfinite(ask)) or any(not 0 <= (now-d).total_seconds() <= ANALYSIS_MAX_AGE_SECONDS for d in dates):
            continue
        candidates.append((min(dates), q))
    if not candidates:
        raise ValueError('Kein aktuelles Geld-/Briefpaar')
    _, q = max(candidates, key=lambda item: item[0])
    figure = data.get('derivativesFigure') or {}
    leverage, leverage_at = None, None
    try:
        candidate = float(figure['gearingAsk'])
        dates = [clock(figure[k]) for k in ('datetimeCalculation', 'datetimeAskPrice', 'datetimePriceUnderlyingCalculation')]
        if math.isfinite(candidate) and candidate >= 1 and all(d <= now for d in dates):
            leverage, leverage_at = candidate, min(dates).isoformat()
    except (KeyError, TypeError, ValueError):
        pass
    return dict(isin=isin, direction='LONG' if details['nameExerciseRight']=='CALL' else 'SHORT', bid=float(q['bid']), ask=float(q['ask']), price=float(q['ask']),
                spread=float(q['ask'])-float(q['bid']), currency='EUR',
                bidAt=q['datetimeBid'], askAt=q['datetimeAsk'], quoteAt=min(clock(q['datetimeBid']), clock(q['datetimeAsk'])).isoformat(),
                leverage=leverage, leverageAt=leverage_at,
                leverageCalculatedAt=figure.get('datetimeCalculation'),
                source='Onvista · '+q['market']['name'], sourceUrl=PAGES[isin],
                priceKind='secondary-market', isDegiroQuote=False, analysisMaxAgeSeconds=ANALYSIS_MAX_AGE_SECONDS)

def parse_knockout_evidence(html, isin, now=None):
    now = now or datetime.now(timezone.utc)
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(match[1])['props']['pageProps']['data']['snapshot']
    i, d = data['instrument'], data['derivativesDetails']
    u = data['derivativesUnderlyingList']['list']
    if (i.get('isin') != isin or i.get('wkn') != isin[5:11]
            or str(i.get('entityValue')) != str(IDS[isin])
            or i.get('entitySubType') != 'KNOCKOUT_CERTIFICATE'
            or len(u) != 1 or u[0]['instrument'].get('isin') != 'XC0009655157'
            or d.get('nameExerciseRight') not in ('CALL','PUT')
            or d.get('hasBarrierBeenHit') is not True):
        return None
    return dict(isin=isin, direction='LONG' if d['nameExerciseRight']=='CALL' else 'SHORT',
                knockoutReported=True, source=PAGES[isin], checkedAt=now.isoformat())


def parse_model_evidence(html, isin, now=None):
    """Static conversion terms are independent of the age of price fields."""
    now = now or datetime.now(timezone.utc)
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(match[1])['props']['pageProps']['data']['snapshot']
    i, d = data['instrument'], data['derivativesDetails']
    u = data['derivativesUnderlyingList']['list']
    if (i.get('isin') != isin or i.get('wkn') != isin[5:11]
            or str(i.get('entityValue')) != str(IDS[isin])
            or i.get('entitySubType') != 'KNOCKOUT_CERTIFICATE'
            or d.get('quanto') is not False or d.get('hasIndicativeDetails') is not False
            or d.get('numberUnderlyings') != 1 or d.get('isoCurrency') != 'EUR'
            or d.get('dataStatus') != 1 or d.get('hasBarrierBeenHit') is not False
            or d.get('nameExerciseRight') not in ('CALL','PUT') or len(u) != 1
            or u[0]['instrument'].get('isin') != 'XC0009655157'
            or u[0].get('isoCurrency') != 'USD'):
        raise ValueError('Währungsmodell nicht bestätigt')
    ratio = float(u[0]['coverRatio'])
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError('Bezugsverhältnis nicht bestätigt')
    return dict(isin=isin, quanto=False, ratio=ratio,
                direction='LONG' if d['nameExerciseRight']=='CALL' else 'SHORT',
                source=PAGES[isin], sourceField='derivativesDetails.quanto',
                reviewedAt=now.isoformat())


def apply_model(primary, isin, now):
    with _LOCK:
        cached = _MODEL.get(isin)
    m = primary.get('metadata', {})
    if (not cached or time.monotonic()-cached[0] > 900
            or m.get('quantoState') != 'unknown' or not m.get('simpleTurbo')):
        return primary
    evidence = cached[1]
    if (evidence['isin'] != isin or evidence['direction'] != m.get('direction')
            or evidence['ratio'] != m.get('ratio')
            or not 0 <= (now-clock(evidence['reviewedAt'])).total_seconds() <= 900):
        return primary
    return dict(primary, metadata=dict(m, simpleNonQuantoTurbo=True,
                quantoState='non-quanto', currencyModelEvidence=dict(evidence)))


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
            body = response.read(4000001)
            if len(body) > 4000000:
                raise ValueError('Antwort zu groß')
            html = body.decode('utf-8')
            # Replace model evidence even when new data contradicts an old value.
            with _LOCK:
                _MODEL.pop(isin, None)
            try:
                model = parse_model_evidence(html, isin)
                with _LOCK:
                    _MODEL[isin] = (time.monotonic(), model)
            except (KeyError, TypeError, ValueError, IndexError):
                pass
            result = parse_knockout_evidence(html, isin) or parse_page(html, isin)
        ttl = 30
        with _LOCK:
            _FAILURES.pop(isin, None)
    except Exception as exc:
        code = 'HTTP_'+str(exc.code) if hasattr(exc,'code') else type(exc).__name__
        known = {'Quellenzeit fehlt','Produktidentität stimmt nicht überein','Status oder Gold-Spot-Basiswert nicht bestätigt','Kein aktuelles Geld-/Briefpaar','Unerwartete Weiterleitung'}
        if isinstance(exc, ValueError) and str(exc) in known:
            code = str(exc)
        with _LOCK:
            _FAILURES[isin] = dict(state='unavailable', code=code, checkedAt=datetime.now(timezone.utc).isoformat())
        result, ttl = None, (30 if code == 'Kein aktuelles Geld-/Briefpaar' else 300)
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
    primary = apply_model(primary, isin, now or datetime.now(timezone.utc))
    meta = primary.get('metadata', {})
    if not backup:
        return dict(primary, backupStatus=_FAILURES.get(isin, {'state':'unavailable','code':'NO_CURRENT_PAIR'}))
    if backup.get('direction') != meta.get('direction'):
        return dict(primary, backupStatus={'state':'rejected','code':'DIRECTION_MISMATCH'})
    now = now or datetime.now(timezone.utc)
    if backup.get('knockoutReported'):
        if not 0 <= (now-clock(backup['checkedAt'])).total_seconds() <= 300:
            return primary
        result = dict(primary, metadata=dict(meta, status=2), found=False, eligible=False,
                      fresh=False, marketOpen=False, lifecycleEvidence=backup,
                      reason='Onvista meldet Knock-out; SG-Stammdaten widersprechen. Produkt gesperrt, keine Kursbilder erforderlich.')
        for key in ('analysisQuote','chartEvidence','leverage','leverageCalculation','calculatedProduct'):
            result.pop(key, None)
        return result
    # Every use rechecks cache age; never renew quote clocks on retrieval.
    try:
        if any(not 0 <= (now-clock(backup[k])).total_seconds() <= ANALYSIS_MAX_AGE_SECONDS for k in ('bidAt', 'askAt')):
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
                  snapshotAt=min(clock(backup[k]) for k in ('bidAt','askAt','leverageAt') if backup.get(k)).isoformat(),
                  reason='Backup-Kurse von Onvista; Hebel mit eigenem älteren Datenstand – rechnerische Empfehlung, keine Live-Freigabe',
                  leverageNote='Onvista-Hebel mit separatem Berechnungs- und Eingangsdatenstand; kann vom Hebel beim aktuellen Briefkurs abweichen.')
    # The backup is used for indicative analysis only until complete live validation.
    return result
