"""Bounded import assessment, not a trade plan or a source of ranking penalties.

The reader does not receive the browser's CHF budget or independent model stop.
Record that absence explicitly instead of silently inventing a position size.
Only validated observations from android_observations.prepare enter this module.
"""
from decimal import Decimal, InvalidOperation

VERSION = 3


def positive(value):
    if not isinstance(value, str):
        return None
    try:
        number = Decimal(value.replace(',', '.'))
        return number if number.is_finite() and number > 0 else None
    except InvalidOperation:
        return None


def assess(run):
    rows = {r['isin']: r for r in run['results']}
    items = []
    for isin in run['isins']:
        row = rows.get(isin) or {}
        observation = row.get('observation') or {}
        fields = observation.get('fields') or {}
        bid, ask = positive(fields.get('Geld')), positive(fields.get('Brief'))
        currency = fields.get('Währung')
        reasons = []
        if not row:
            reasons.append('READ_PENDING')
        elif not observation:
            reasons.append('READ_NOT_AVAILABLE')
        if row.get('matchedCurrentList') is not True:
            reasons.append('CURRENT_LIST_MATCH_MISSING')
        pair = bid is not None and ask is not None and ask >= bid and currency in ('EUR', 'CHF')
        if not pair:
            reasons.append('DISPLAY_PAIR_INVALID_OR_MISSING')
        if fields.get('Hinweis') != 'Keine Aussage zur Handelbarkeit':
            reasons.append('DISPLAY_RESTRICTED_OR_UNCONFIRMED')
        # A displayed minute has no verified timezone. Never substitute capture
        # or receipt time, nor interpret an old stored observation as a live quote.
        # This projection cannot inspect saved planning settings. Absence from
        # a reader receipt must not be reported as a missing user configuration.
        reasons += ['SOURCE_CLOCK_UNCONFIRMED', 'INDEPENDENT_MODEL_STOP_NOT_IN_IMPORT',
                    'CHF_CAPITAL_NOT_IN_IMPORT', 'CHF_RISK_BUDGET_NOT_IN_IMPORT',
                    'CHF_FEES_NOT_IN_IMPORT']
        if currency == 'EUR':
            reasons.append('DATED_EUR_CHF_REFERENCE_NOT_IN_IMPORT')
        items.append(dict(isin=isin, readCode=row.get('code'),
            observedAt=observation.get('observedAt'), displayedTime=fields.get('Anzeigezeit'),
            sourceTime=None, currency=currency, bid=float(bid) if pair else None,
            ask=float(ask) if pair else None, spread=float(ask-bid) if pair else None,
            displayedBid=float(bid) if bid is not None else None,
            displayedAsk=float(ask) if ask is not None else None,
            displayPairValid=pair,
            displayedLeverage=float(positive(fields.get('Hebel'))) if positive(fields.get('Hebel')) else None,
            displayedKo=float(positive(fields.get('KO-Schwelle'))) if positive(fields.get('KO-Schwelle')) else None,
            unitPurchaseCHF=float(ask) if pair and currency == 'CHF' else None,
            unitPurchaseIncludesFees=False, quantity=None, modelStop=None,
            totalCHF=None, lossCHF=None, riskUsagePct=None,
            calculationStatus='inputs-missing', reasons=reasons,
            rankingPenalty=False, tradeApproved=False))
    return dict(version=VERSION, assessedAt=run['receivedAt'], batchId=run['batchId'],
                revision=run['revision'], items=items, researchOnly=True,
                scope='reader-receipt-only-not-current-planning-settings',
                planningSettingsChecked=False,
                realOrders=False, rankingUpdated=False,
                note='Import-Auswertung: gespeicherte Anzeigewerte, kein aktueller Handelsplan. '
                     'CHF-Vorgaben und Modellplan sind nicht Teil dieses Imports. '
                     'Gespeicherte Planungsvorgaben werden hier nicht geprüft; '
                     'ihr Fehlen im Import bedeutet nicht, dass sie in Bob fehlen. '
                     'Keine Stückzahlberechnung oder Ranking-Abwertung.')
