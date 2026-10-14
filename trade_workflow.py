"""Read-only execution receipts to Bob records; never places broker orders."""
import hashlib
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def receipt_clock(receipt):
    if receipt.get('executedAt'):
        value = datetime.fromisoformat(receipt['executedAt'].replace('Z', '+00:00'))
        if value.tzinfo is None:
            raise ValueError('Ausführungszeit ohne Zeitzone')
        return value.astimezone(ZoneInfo('Europe/Zurich')).replace(tzinfo=None)
    return datetime.strptime(receipt['executedLocal'], '%d.%m.%Y %H:%M:%S')


def eligible_purchase(receipt, receipts, now=None):
    """Do not resurrect historic purchases or choose between several fills."""
    from trade_email_import import isin_ok
    now = now or datetime.now(timezone.utc)
    if receipt.get('status') != 'pending-review' or receipt.get('side') != 'BUY':
        return False
    try:
        at = receipt_clock(receipt)
        local = now.astimezone(ZoneInfo('Europe/Zurich')).replace(tzinfo=None)
        if at.date() != local.date() or at > local:
            return False
        if not isin_ok(receipt['isin']):
            return False
        for key in ('quantity', 'priceEur'):
            v = receipt[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                return False
        if not float(receipt['quantity']).is_integer():
            return False
        # Any later sale or another purchase in this product requires reconciliation.
        for other in receipts:
            if other is receipt or other == receipt or other.get('status') != 'pending-review' or other.get('isin') != receipt['isin']:
                continue
            if other.get('side') == 'SELL' and receipt_clock(other) >= at:
                return False
            if other.get('side') == 'BUY' and receipt_clock(other).date() == at.date():
                return False
        return True
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def import_purchase(conn, payload):
    import json
    import real_trade_journal as journal
    mid = payload.get('emailReceiptId')
    direction = payload.get('direction')
    if not isinstance(mid, str) or not 1 <= len(mid) <= 200 or direction not in ('LONG', 'SHORT'):
        raise ValueError('E-Mail-ID oder geprüfte Produktrichtung fehlt')
    conn.execute('SELECT pg_advisory_xact_lock(72143619)')
    rows = conn.execute('SELECT message_id,payload FROM bob_trade_email_import ORDER BY imported_at DESC LIMIT 100').fetchall()
    records = [p.get('result') or {} for _, p in rows]
    receipt = next((records[i] for i, (key, _) in enumerate(rows) if key == mid), None)
    if not receipt or not eligible_purchase(receipt, records):
        raise ValueError('Kaufbeleg nicht eindeutig aktuell oder Verkauf vorhanden; Ausführung bitte prüfen')
    digest = receipt.get('orderIdDigest') or hashlib.sha256((receipt['isin'] + '|' + str(receipt_clock(receipt)) + '|' + str(receipt['quantity']) + '|' + str(receipt['priceEur'])).encode()).hexdigest()
    tid = 'degiro-email-' + digest
    existing = conn.execute('SELECT id,snapshot FROM bob_real_trades').fetchall()
    for key, snapshot in existing:
        p = snapshot.get('product') or {}
        if key == tid:
            return {'ok': True, 'tradeId': key, 'duplicate': True}
        if snapshot.get('active') or (p.get('isin') == receipt['isin'] and p.get('entry') == receipt['priceEur'] and p.get('quantity') == receipt['quantity']):
            raise ValueError('Vorhandener Trade oder gleicher Kauf bereits gespeichert; keine doppelte Übernahme')
    purchase = {'transactionId': digest, 'at': receipt.get('executedAt'), 'executedLocal': receipt.get('executedLocal'),
                'feesCHF': receipt.get('costsChf'), 'totalCHF': None,
                'source': 'Weitergeleitete DEGIRO-Ausführungsbestätigung; keine unabhängige Brokerabfrage', 'messageId': mid}
    snapshot = {'tradeId': tid, 'active': False, 'recordOnly': True, 'dir': direction,
                'product': {'isin': receipt['isin'], 'entry': receipt['priceEur'], 'quantity': receipt['quantity']},
                'purchase': purchase, 'monitoringStatus': 'pending-evidence'}
    inserted = conn.execute("INSERT INTO bob_real_trades(id,active,snapshot,settings) VALUES(%s,FALSE,%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING RETURNING id",
                           (tid, json.dumps(snapshot), json.dumps({'timeframe': '15m', 'trade': None}))).fetchone()
    if inserted:
        journal.event(conn, tid, 'purchase-email-recorded', snapshot)
    return {'ok': True, 'tradeId': tid, 'recordOnly': True, 'duplicate': not bool(inserted)}
