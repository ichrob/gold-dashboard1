"""DEGIRO detail screenshots prove listing/venue, never execution."""
import copy
import json
import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Zurich')
VENUE = 'Societe Generale OTC'
REVIEWED_VENUES = (VENUE, 'BNP OTC', 'BNP Paribas OTC')


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_broker_venue_history (
        isin TEXT NOT NULL, currency TEXT NOT NULL, venue TEXT NOT NULL,
        observed_minute TEXT NOT NULL, payload JSONB NOT NULL,
        PRIMARY KEY(isin,currency,venue))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_broker_venue_evidence (
        isin TEXT PRIMARY KEY, payload JSONB NOT NULL)''')


def validate(payload, feed, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, dict) or payload.get('reviewed') is not True:
        raise ValueError('ISIN und Handelsplatz am Original bestätigen')
    isin = payload.get('isin')
    products = feed.get('products') or []
    if (feed.get('listOrigin') != 'degiro-screenshot' or not feed.get('listUploadedAt')
            or isin not in [p.get('isin') for p in products]):
        raise ValueError('Produkt fehlt in der aktiven DEGIRO-Liste')
    if payload.get('venue') not in REVIEWED_VENUES or payload.get('currency') not in ('EUR', 'CHF'):
        raise ValueError('Handelsplatz oder Währung nicht unterstützt')
    raw = payload.get('observedMinute', '')
    if not isinstance(raw, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', raw):
        raise ValueError('Datum und Minute aus dem Screenshot fehlen')
    local = datetime.strptime(raw, '%Y-%m-%dT%H:%M').replace(tzinfo=ZONE)
    if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset():
        raise ValueError('Mehrdeutige Ortszeit')
    end = local.replace(hour=22, minute=0, second=0, microsecond=0)
    if local.date() != now.astimezone(ZONE).date() or not local <= now < end:
        raise ValueError('Nachweis liegt in der Zukunft oder ist abgelaufen')
    reference = payload.get('imageReference', '')
    if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 200:
        raise ValueError('Bildreferenz fehlt')
    return dict(isin=isin, broker='DEGIRO', venue=payload['venue'], currency=payload['currency'],
        kind='owner-reviewed-screenshot', observedMinute=raw, timezone='Europe/Zurich',
        timePrecision='minute', validUntil=end.isoformat(), reviewedAt=now.isoformat(),
        imageReference=reference.strip(), listUploadedAt=feed['listUploadedAt'],
        listingConfirmed=True, executionConfirmed=False)


def confirmed(evidence, isin, currency, now_ms):
    if not isinstance(evidence, dict):
        return False
    try:
        at = datetime.strptime(evidence['observedMinute'], '%Y-%m-%dT%H:%M').replace(tzinfo=ZONE)
        now = datetime.fromtimestamp(now_ms/1000, timezone.utc)
        end = at.replace(hour=22, minute=0)
        return (evidence.get('isin') == isin and evidence.get('currency') == currency
            and evidence.get('broker') == 'DEGIRO'
            and ((evidence.get('kind') == 'owner-reviewed-screenshot' and evidence.get('venue') in REVIEWED_VENUES)
                 or (evidence.get('kind') in ('automatic-detail-screenshot', 'automatic-list-screenshot') and valid_venue(evidence.get('venue'))))
            and evidence.get('listingConfirmed') is True and evidence.get('executionConfirmed') is False
            and evidence.get('timezone') == 'Europe/Zurich' and evidence.get('timePrecision') == 'minute'
            and bool(evidence.get('imageReference')) and bool(evidence.get('listUploadedAt'))
            and evidence.get('validUntil') == end.isoformat()
            and at.date() == now.astimezone(ZONE).date() and at <= now < end)
    except (ValueError, KeyError, TypeError):
        return False


def save(conn, payload, now=None):
    row = conn.execute('SELECT payload FROM bob_paper_products WHERE id=1 FOR SHARE').fetchone()
    record = validate(payload, row[0] if row else {}, now)
    conn.execute('''INSERT INTO bob_broker_venue_evidence(isin,payload) VALUES(%s,%s::jsonb)
        ON CONFLICT(isin) DO UPDATE SET payload=EXCLUDED.payload''',
        (record['isin'], json.dumps(record)))
    archive(conn, record, now or datetime.now(timezone.utc))
    return dict(ok=True, evidence=record, message='Handelsplatznachweis gespeichert · keine Order ausgelöst')


def valid_venue(value):
    return (isinstance(value, str) and 1 <= len(value.strip()) <= 100
            and value.strip().lower() not in ('-', '—', 'unbekannt', 'unknown')
            and not any(ord(c) < 32 for c in value))


def automatic(product, feed, now=None):
    """Use the identity-bound detail parser output; never infer from a title/list.

    The authenticated screenshot feed is the input boundary, just as for manual
    confirmation. This proves a broker display, never executable prices.
    """
    from product_quotes import valid_isin
    now = now or datetime.now(timezone.utc)
    snapshot = product.get('snapshot') or {}
    venue_only = isinstance(snapshot, dict) and isinstance(snapshot.get('degiroVenueEvidence'), dict)
    q = (snapshot.get('degiroVenueEvidence') if venue_only else snapshot.get('degiroDisplayedQuote')) if isinstance(snapshot, dict) else None
    isin = product.get('isin')
    if (not isinstance(q, dict) or not isinstance(isin, str) or not valid_isin(isin)
            or snapshot.get('isin') != isin or q.get('isin') != isin
            or feed.get('listOrigin') != 'degiro-screenshot' or not feed.get('listUploadedAt')
            or q.get('source') != 'DEGIRO-Produktdetail' or not valid_venue(q.get('venue'))
            or q.get('currency') not in ('EUR', 'CHF')
            or q.get('brokerDisplayConfirmed') is not True
            or any(q.get(k) is not False for k in ('orderWindowVerified', 'orderSubmitted',
                   'executionGuaranteed', 'isExecutableQuote'))):
        return None
    bid, ask = q.get('bid'), q.get('ask')
    if not venue_only and (not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (bid, ask)) or ask < bid):
        return None
    raw = q.get('sourceTime')
    if not isinstance(raw, str) or not re.fullmatch(r'\d{2}[/.]\d{2}[/.]\d{4} \d{2}:\d{2}(?::\d{2})?', raw):
        return None
    try:
        local = datetime.strptime(raw.replace('/', '.'), '%d.%m.%Y %H:%M:%S' if len(raw) == 19 else '%d.%m.%Y %H:%M').replace(tzinfo=ZONE)
        if local > now:
            return None
        record = validate(dict(isin=isin, reviewed=True, venue=VENUE, currency=q['currency'],
            observedMinute=local.strftime('%Y-%m-%dT%H:%M'),
            imageReference='DEGIRO-Produktdetail · strukturierter Screenshotnachweis'), feed, now)
    except (ValueError, TypeError):
        return None
    record.update(kind='automatic-detail-screenshot', venue=q['venue'].strip(),
                  sourceTime=raw, timezoneBasis='Europe/Zurich assumed from broker display')
    record.pop('reviewedAt', None)
    return record


def corrected_list(product, feed, now):
    """Recover the explicit, reviewed listing row, independently of live quotes.

    listCorrection is written only by the authenticated correction handler; the
    normal product-sync allowlist does not accept it. No issuer inference.
    """
    correction = feed.get('listCorrection') or {}
    if (not correction.get('previousVersion') or not correction.get('at')
            or product.get('listingVenue') not in REVIEWED_VENUES):
        return None
    try:
        record = validate(dict(isin=product.get('isin'), reviewed=True,
            currency=product.get('currency'), venue=product['listingVenue'],
            observedMinute=correction.get('observedMinute'),
            imageReference=correction.get('imageReference') or
                'Geprüfte DEGIRO-Listenkorrektur · '+correction['at']), feed, now)
        # Keep the actual review clock, never replace it with today's retrieval.
        record['reviewedAt'] = correction['at']
        return record
    except (ValueError, TypeError, KeyError):
        return None


def attach(conn, feed, now=None):
    out = copy.deepcopy(feed)
    now = now or datetime.now(timezone.utc)
    rows = conn.execute('SELECT isin,payload FROM bob_broker_venue_evidence').fetchall()
    evidence = {isin: row for isin, row in rows if row.get('listUploadedAt') == feed.get('listUploadedAt')}
    history_rows = conn.execute('SELECT isin,payload FROM bob_broker_venue_history').fetchall()
    history = {}
    for isin, row in history_rows:
        if isinstance(row, dict):history.setdefault(isin, []).append(row)
    for isin, row in rows:
        if archive(conn, row, now):history.setdefault(isin, []).append(row)
    for product in out.get('products') or []:
        product.pop('brokerVenueEvidence', None)
        product.pop('brokerVenueHistory', None)
        record = automatic(product, feed, now)
        listed = automatic_list(product, feed, now) or corrected_list(product, feed, now)
        if listed and (not record or listed['observedMinute'] >= record['observedMinute']):
            record = listed
        manual = evidence.get(product.get('isin'))
        # A fresh automatic observation can replace an expired manual proof.
        if manual and (not record or manual.get('observedMinute', '') >= record['observedMinute']):
            record = manual
        if record:
            product['brokerVenueEvidence'] = record
            if archive(conn, record, now):history.setdefault(product['isin'], []).append(record)
        currency = product.get('currency') or (product.get('snapshot') or {}).get('currency')
        candidates = [r for r in history.get(product.get('isin'), [])
                      if r.get('currency') == currency and historical(r, now)]
        if candidates:
            product['brokerVenueHistory'] = max(candidates, key=lambda r:r['observedMinute'])
    return out


def historical(record, now):
    """Validate at the original observation, never refresh its time or validity."""
    if not isinstance(record, dict):return False
    try:
        at = datetime.strptime(record['observedMinute'], '%Y-%m-%dT%H:%M').replace(tzinfo=ZONE)
        return at <= now and confirmed(record, record.get('isin'), record.get('currency'), at.timestamp()*1000)
    except (ValueError, TypeError, KeyError):return False


def archive(conn, record, now):
    if not historical(record, now):return False
    conn.execute("""INSERT INTO bob_broker_venue_history(isin,currency,venue,observed_minute,payload)
        VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT(isin,currency,venue) DO UPDATE
        SET observed_minute=excluded.observed_minute,payload=excluded.payload
        WHERE excluded.observed_minute>bob_broker_venue_history.observed_minute""",
        (record['isin'],record['currency'],record['venue'],record['observedMinute'],json.dumps(record)))
    return True


def assessment(product, currency, now_ms):
    """One listing decision shared by report, cards and selection; no execution permission."""
    record = product.get('brokerVenueEvidence')
    current = confirmed(record, product.get('isin'), currency, now_ms)
    old = product.get('brokerVenueHistory') or record
    now = datetime.fromtimestamp(now_ms/1000, timezone.utc)
    old = old if historical(old, now) and old.get('isin') == product.get('isin') and old.get('currency') == currency else None
    return dict(version=1, state='current' if current else 'historical' if old else 'missing',
                current=current, evidence=record if current else None, historicalEvidence=old,
                checkedAt=now.isoformat(), executionConfirmed=False)


def archive_feed(conn, feed, now=None):
    """Capture outgoing screenshots at their original clock, including expired ones."""
    now = now or datetime.now(timezone.utc)
    for product in feed.get('products') or []:
        try:
            uploaded=datetime.fromisoformat(str(feed.get('listUploadedAt','')).replace('Z','+00:00'))
            if uploaded.tzinfo is not None and uploaded<=now:
                listed=automatic_list(product,feed,uploaded)
                if listed:archive(conn,listed,now)
        except (ValueError,TypeError):pass
        snap = product.get('snapshot') or {}
        q = snap.get('degiroVenueEvidence') or snap.get('degiroDisplayedQuote') or {}
        raw = q.get('sourceTime', '')
        try:
            at = datetime.strptime(raw.replace('/', '.'), '%d.%m.%Y %H:%M:%S' if len(raw)==19 else '%d.%m.%Y %H:%M').replace(tzinfo=ZONE)
            if at > now:continue
            record = automatic(product, feed, at)
            if record:archive(conn, record, now)
        except (ValueError, TypeError):continue


def automatic_list(product, feed, now=None):
    """Use the twice-read list footer. Upload time dates list observation, never prices."""
    from product_quotes import valid_isin
    now = now or datetime.now(timezone.utc)
    e = product.get('listVenueEvidence')
    if (not isinstance(e, dict) or e.get('version') != 1
        or not valid_isin(product.get('isin', '')) or e.get('isin') != product.get('isin')
        or feed.get('listOrigin') != 'degiro-screenshot'
        or not feed.get('listUploadedAt') or e.get('listUploadedAt') != feed.get('listUploadedAt')
        or e.get('source') != 'DEGIRO-Listenbild' or e.get('complete') is not True
        or e.get('crossChecked') is not True or e.get('isExecutableQuote') is not False
        or e.get('currency') not in ('EUR','CHF')
        or product.get('currency') != e.get('currency')
        or not isinstance(e.get('reference'), str) or not 1 <= len(e['reference']) <= 200):return None
    venue = e.get('venue', '')
    if not isinstance(venue, str):return None
    if re.fullmatch(r'Soci[eé]t[eé]\s+G[eé]n[eé]rale\s+OTC', venue, re.I):venue=VENUE
    elif re.fullmatch(r'BNP\s+(?:Paribas\s+)?OTC', venue, re.I):venue='BNP OTC'
    else:return None
    try:
        uploaded = datetime.fromisoformat(feed['listUploadedAt'].replace('Z','+00:00'))
        if uploaded.tzinfo is None or uploaded > now:return None
        record=validate(dict(isin=product['isin'],reviewed=True,venue=venue,currency=e['currency'],
            observedMinute=uploaded.astimezone(ZONE).strftime('%Y-%m-%dT%H:%M'),
            imageReference=e['reference']),feed,now)
    except (ValueError,TypeError):return None
    record.update(kind='automatic-list-screenshot', timeBasis='list-upload-observation',
                  sourceTime=None, note='Listenstand anhand Uploadzeit; keine Kurs- oder Screenshot-Aufnahmezeit.')
    record.pop('reviewedAt',None)
    return record
