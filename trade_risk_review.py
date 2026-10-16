"""Read-only pre-entry certificate risk, fees and source-labelled trade reviews.

EUR/CHF FX means CHF per one EUR. A gold KO is NOT a product-price stop.
Calculated and observed model prices must never be treated as broker executions.
"""
import math
from datetime import datetime


def number(value, label, zero=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ' fehlt oder ist ungültig')
    if value < 0 or (not zero and value == 0):
        raise ValueError(label + ' muss positiv sein')
    return float(value)


def optional_number(payload, key, zero=False):
    value = payload.get(key)
    return number(value, key, zero) if value is not None else None


def preview(payload):
    """Compute numbers only from user-provided product-priced evidence; no orders."""
    if not isinstance(payload, dict):
        raise ValueError('Produktdaten fehlen')
    currency=payload.get('currency','EUR')
    if currency not in ('EUR','CHF'):
        raise ValueError('Nur EUR- und CHF-Produktkurse unterstützt')
    entry = number(payload.get('entry'), 'Produkt-Einstieg')
    qty = number(payload.get('quantity'), 'Stückzahl')
    if not qty.is_integer() or qty > 100000:
        raise ValueError('Ganzzahlige Stückzahl erforderlich')
    stop = optional_number(payload, 'stop')
    target = optional_number(payload, 'target')
    atr = optional_number(payload, 'atr')
    structure = optional_number(payload, 'structureStop')
    fx = 1.0 if currency == 'CHF' else optional_number(payload, 'chfPerUnit')
    buy_fee = optional_number(payload, 'buyFeeCHF', True)
    sell_fee = optional_number(payload, 'sellFeeCHF', True)
    max_risk = optional_number(payload, 'maxRiskPct')
    if max_risk is None: max_risk = 5.
    if stop is not None and stop >= entry:
        raise ValueError('Stopp eines gekauften Zertifikats muss unter Kaufkurs liegen')
    if structure is not None and structure >= entry:
        raise ValueError('Struktur-Stopp muss unter Kaufkurs liegen')
    if target is not None and target <= entry:
        raise ValueError('Ziel eines gekauften Zertifikats muss über Kaufkurs liegen')
    if not 0 < max_risk <= 100:
        raise ValueError('Maximales Risiko muss zwischen 0 und 100 Prozent liegen')
    suggested_atr = round(entry - atr * 1.5, 4) if atr is not None and entry > atr * 1.5 else None
    candidates = [x for x in (suggested_atr, structure) if x is not None]
    # The suggestion is a research anchor, NEVER an instruction to loosen an order.
    suggestion = round(min(candidates), 4) if candidates else None
    effective_stop = stop if stop is not None else suggestion
    risk_pct = 100 * (entry - effective_stop) / entry if effective_stop is not None else None
    fee_chf = buy_fee + sell_fee if buy_fee is not None and sell_fee is not None else None
    break_even = entry + fee_chf / (qty * fx) if fx and fee_chf is not None else None
    net_stop = ((effective_stop - entry) * qty * fx - fee_chf
                if effective_stop is not None and fx and fee_chf is not None else None)
    net_target = ((target - entry) * qty * fx - fee_chf
                  if target is not None and fx and fee_chf is not None else None)
    warnings = []
    if stop is None:
        warnings.append('Kein bestätigter Broker-Stopp; Vorschlag ist nur rechnerisch')
    if risk_pct is None:
        warnings.append('Ohne Produkt-Stopp kann das Verlustrisiko nicht beziffert werden')
    elif risk_pct > max_risk:
        warnings.append('Stopp-Abstand überschreitet die gewählte Produkt-Risikogrenze')
    if fx is None or fee_chf is None:
        warnings.append('CHF-Wechselkurs oder Kauf-/Verkaufsgebühren fehlen: CHF-Netto offen')
    if suggested_atr is not None and structure is not None and abs(suggested_atr - structure) > atr:
        warnings.append('ATR und Marktstruktur widersprechen sich; Stopp manuell prüfen')
    if payload.get('sourceVerified') is not True:
        warnings.append('Keine unabhängige aktuelle Anbieter-/Brokerkursbestätigung')
    return {
        'kind': 'product-price-pretrade-review', 'currency': currency,
        'entry': round(entry, 4), 'quantity': int(qty),
        'stop': stop, 'target': target, 'suggestedStop': suggestion,
        'atrStop': suggested_atr, 'structureStop': structure,
        'riskPct': round(risk_pct, 2) if risk_pct is not None else None,
        'breakEvenProduct': round(break_even, 4) if break_even is not None else None,
        'riskStopCHF': round(net_stop, 2) if net_stop is not None else None,
        'targetNetCHF': round(net_target, 2) if net_target is not None else None,
        'feesRoundtripCHF': round(fee_chf, 2) if fee_chf is not None else None,
        'riskRewardNet': round(net_target / abs(net_stop), 2)
            if net_target is not None and net_stop is not None and net_stop < 0 and net_target > 0 else None,
        'warnings': warnings, 'executable': False, 'ordersPlaced': False
    }


def evaluation(snapshot, model_prices=()):
    """Broker receipts are realized; model extremes are hypothetical and separate."""
    product = snapshot.get('product') or {}
    execution = snapshot.get('actualExecution') or {}
    settlement = snapshot.get('settlement') or {}
    purchase = snapshot.get('purchase') or {}
    receipt = snapshot.get('exitReceipt') or {}
    currency = product.get('currency', 'EUR')
    result = dict(kind='closed-trade-review-v1', tradeId=snapshot.get('tradeId'),
                  isin=product.get('isin'), currency=currency,
                  active=snapshot.get('active') is True, realizedNetCHF=None,
                  realizedNetProduct=None, modelMfePct=None, modelMaePct=None,
                  modelObservations=0, verdict='Abrechnung unvollständig',
                  executionSource='Keine vollständige bestätigte Abrechnung',
                  exitReason=(receipt.get('exitReason') or settlement.get('exitReason') or 'nicht bestätigt'))
    if result['active']:
        return result
    gross = execution.get('net' + currency)
    if type(gross) in (float, int) and math.isfinite(gross):
        result['realizedNetProduct'] = round(gross, 2)
        result['executionSource'] = execution.get('source', 'Vom Nutzer bestätigte Ausführung')
    bought = settlement.get('purchaseTotalCHF', purchase.get('totalCHF'))
    sold = settlement.get('saleTotalCHF', receipt.get('saleNetCHF'))
    if type(bought) in (int, float) and type(sold) in (int, float) and bought >= 0 and sold >= 0:
        result['realizedNetCHF'] = round(sold - bought, 2)
        result['executionSource'] = (receipt.get('source') or settlement.get('source') or result['executionSource'])
        net = result['realizedNetCHF']
        result['verdict'] = 'Gewinn' if net > 0 else 'Verlust' if net < 0 else 'Nullergebnis'
    elif result['realizedNetProduct'] is not None:
        net = result['realizedNetProduct']
        result['verdict'] = 'Gewinn' if net > 0 else 'Verlust' if net < 0 else 'Nullergebnis'
    entry = product.get('entry')
    valid = [x for x in model_prices if type(x) in (int, float) and math.isfinite(x) and x > 0]
    if type(entry) in (int, float) and entry > 0 and valid:
        result['modelObservations'] = len(valid)
        result['modelMfePct'] = round((max(valid) / entry - 1) * 100, 2)
        result['modelMaePct'] = round((min(valid) / entry - 1) * 100, 2)
        result['modelOnly'] = True
    try:
        opened = purchase.get('at')
        closed = receipt.get('executedAt') or settlement.get('soldAt')
        if opened and closed:
            a = datetime.fromisoformat(opened.replace('Z', '+00:00'))
            b = datetime.fromisoformat(closed.replace('Z', '+00:00'))
            if a.tzinfo and b.tzinfo and b >= a:
                result['holdingMinutes'] = round((b-a).total_seconds() / 60, 1)
    except (TypeError, ValueError):
        pass
    return result
