"""Compact read-only view of existing virtual account controls.

This is *not* a historical trade replay and never certifies a profitable strategy.
No SQL, product IDs, raw case payloads, broker records or new market assumptions.
"""
import math

PROFILES = ('conservative', 'balanced', 'offensive', 'early100', 'trend800',
            'early1000oct', 'normal1000oct', 'trend800nov', 'normal1000nov')
STATUSES = ('scheduled', 'running', 'completed', 'ending-pending-quotes',
            'night-paused', 'market-closed', 'preparing', 'stopped', 'unavailable')


def number(value, *, positive=False, timestamp=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    if timestamp:
        if not 0 < value <= 1e15:
            return None
    elif abs(value) > 1e12 or (positive and value < 0.01):
        return None
    return float(value)


def entry_block_code(value):
    """Classify the latest saved gate without exposing raw product or private data.

    A reason is a current-control observation only. No historical blocker
    counts, missed-profit estimate or assumption that a trade was possible.
    """
    if not isinstance(value,str) or not value.strip():
        return 'not-observed'
    reason=value.lower()
    if any(word in reason for word in ('goldkurs nicht aktuell','quellenzeit','marktdaten',
                                      'daten fehlen','quellenlücke')):
        return 'source-not-fresh'
    if any(word in reason for word in ('außerhalb','nachtmodus','markt geschlossen',
                                      'börsenpause','einstiegszeit')):
        return 'session-paused'
    if any(word in reason for word in ('kein bestätigter gültiger goldplan',
                                      'stopp-/zielplan','risikoplan','kein gültiger goldplan',
                                      'kein bestätigter stopp')):
        return 'plan-not-ready'
    if any(word in reason for word in ('geld-/brief','geldkurs','briefkurs','kursart',
                                      'ausführungskurs','quote')):
        return 'product-quote-missing'
    if any(word in reason for word in ('ko-schutz','knock-out','ko-barriere',
                                      'ko-schwelle')):
        return 'knockout-protection'
    if any(word in reason for word in ('kein passendes belegtes produkt','kein geeigneter',
                                      'produkteeinstieg','produktfreigabe','nicht freigegeben')):
        return 'product-not-approved'
    if any(word in reason for word in ('kollektivrichtungswert','score zu schwach')):
        return 'signal-score-weak'
    if any(word in reason for word in ('tagesrisiko','risikolimit','verlustgrenze')):
        return 'risk-limit'
    if any(word in reason for word in ('abwarten','keine bestätigte richtung',
                                      'keine einstiegsrichtung','signal neutral')):
        return 'no-direction'
    return 'other-or-unclassified'


def snapshot(accounts):
    """Project only explicitly allowlisted account-control numbers already read."""
    unavailable = dict(status='unavailable', readOnly=True, realOrders=False,
                       strategyWinnerConfirmed=False, netProductReturnsVerified=False,
                       fullHistoryRead=False,
                       scope='existing-paper-account-controls-not-trade-outcome-proof')
    if not isinstance(accounts, list):
        return dict(unavailable, reason='paper-account-controls-not-observed')
    by_profile = {a.get('profile'): a for a in accounts[:20]
                  if isinstance(a, dict) and a.get('profile') in PROFILES}
    rows = []
    for profile in PROFILES:
        a = by_profile.get(profile)
        if a is None:
            rows.append(dict(profile=profile, source='missing-account-control',
                             initialCapitalEur=None, equityEur=None,
                             modelProfitEur=None, modelReturnPct=None))
            continue
        initial = number(a.get('initialCapital'), positive=True)
        equity = number(a.get('equity'))
        total = number(a.get('totalProfit'))
        model_pct = (round((equity / initial - 1) * 100, 4)
                     if initial is not None and equity is not None else None)
        status = a.get('status') if a.get('status') in STATUSES else 'unavailable'
        rows.append(dict(
            profile=profile, source='saved-virtual-control',
            status=status,
            checkedAt=number(a.get('checkedAt'), timestamp=True),
            startAt=number(a.get('startAt'), timestamp=True),
            endAt=number(a.get('endAt'), timestamp=True),
            initialCapitalEur=initial,
            cashEur=number(a.get('cash')),
            equityEur=equity,
            modelProfitEur=total,
            modelReturnPct=model_pct,
            realizedModelProfitEur=number(a.get('realizedProfit')),
            exampleCostsDebitedEur=number(a.get('costsDebitedEur')),
            tradeOutcomeVerified=False,
            latestEntryBlockCode=(entry_block_code(a.get('reason'))
                                  if profile in ('trend800nov','normal1000nov')
                                  else None)))
    complete = all(r.get('source') == 'saved-virtual-control'
                   and r.get('initialCapitalEur') is not None
                   and r.get('equityEur') is not None for r in rows)
    return dict(
        status='observed' if complete else 'partial',
        readOnly=True, realOrders=False,
        strategyWinnerConfirmed=False, netProductReturnsVerified=False,
        fullHistoryRead=False, rows=rows,
        scope='existing-paper-account-controls-not-trade-outcome-proof',
        note='Nur gespeicherte virtuelle Kontostände und angenommene Kosten, '
             'keine geprüften historischen Trade-Abschlüsse oder ausführbaren '
             'Produktkurse. Eine höhere Modellrendite beweist keinen '
             'profitablen Strategievorteil. Fehlende Werte bleiben unbekannt.')
