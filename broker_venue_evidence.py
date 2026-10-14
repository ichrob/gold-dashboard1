"""Owner-reviewed DEGIRO screenshots prove listing/venue, never execution."""
import copy
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Zurich')
VENUE = 'Societe Generale OTC'


def init(conn):
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
    if payload.get('venue') != VENUE or payload.get('currency') not in ('EUR', 'CHF'):
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
    return dict(isin=isin, broker='DEGIRO', venue=VENUE, currency=payload['currency'],
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
            and evidence.get('broker') == 'DEGIRO' and evidence.get('venue') == VENUE
            and evidence.get('kind') == 'owner-reviewed-screenshot'
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
    return dict(ok=True, evidence=record, message='Handelsplatznachweis gespeichert · keine Order ausgelöst')


def attach(conn, feed):
    out = copy.deepcopy(feed)
    rows = conn.execute('SELECT isin,payload FROM bob_broker_venue_evidence').fetchall()
    evidence = {isin: row for isin, row in rows if row.get('listUploadedAt') == feed.get('listUploadedAt')}
    for product in out.get('products') or []:
        product.pop('brokerVenueEvidence', None)
        if product.get('isin') in evidence:
            product['brokerVenueEvidence'] = evidence[product['isin']]
    return out
