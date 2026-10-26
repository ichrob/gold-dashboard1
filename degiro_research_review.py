"""Fail-closed DEGIRO research helpers; no trade execution or broker approval.

Account-scoped SnapTrade search is a read-only provider search, NOT an official
DEGIRO catalogue, account eligibility confirmation or executable quote.
Issuer prices are retained only with separate original clocks. All suggestions
remain research-only until separately approved in an explicit manual broker flow.
"""
from datetime import datetime, timezone
import math
import re

from product_quotes import valid_isin


def _clock(value, now):
    if not isinstance(value, str) or not re.search(r'(Z|[+-][0-9]{2}:[0-9]{2})$', value):
        return None
    try:
        t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if not t.tzinfo:
        return None
    age = (now - t).total_seconds()
    return t.isoformat() if 0 <= age <= 90 else None


def summarize_symbol_search(rows, requested_isin):
    """Bounded anonymized account-search probe; never expose provider account IDs."""
    if not valid_isin(requested_isin) or not isinstance(rows, list) or len(rows) > 20:
        raise ValueError('Ungültiger oder zu großer Symbolsuchbeleg')
    exact = 0
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError('Ungültiger Symboltreffer')
        # Search can match names: only exact symbol equality is counted.
        symbol = item.get('symbol')
        raw = item.get('raw_symbol')
        if any(isinstance(x, str) and len(x) > 160 for x in (symbol, raw)):
            raise ValueError('Symbol zu lang')
        if requested_isin in (symbol, raw) or (isinstance(symbol, str)
                                                and symbol.split('.', 1)[0] == requested_isin):
            exact += 1
    return dict(code='EXACT_SYMBOL_CANDIDATE' if exact else
                ('NO_EXACT_SYMBOL' if rows else 'SEARCH_EMPTY'),
                resultCount=len(rows), exactSymbolCandidates=exact,
                accountTradabilityVerified=False, completeGoldCatalog=False,
                executableQuoteVerified=False, tradeApproved=False,
                note='Account-Suchtreffer sind keine DEGIRO-Handelsfreigabe.')


def issuer_observation(isin, direction, raw, now=None):
    """Timestamp-safe issuer snapshot. Never substitute a screenshot or model quote."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not valid_isin(isin) or direction not in ('LONG', 'SHORT'):
        return None
    if not isinstance(raw, dict) or raw.get('isin') != isin or raw.get('productVerified') is not True:
        return None
    m = raw.get('metadata') if isinstance(raw.get('metadata'), dict) else {}
    if (m.get('status') != 1 or m.get('type') == 'FACTOR'
            or m.get('underlyingType') != 'SPOT'
            or m.get('underlying') not in ('Gold', 'Gold Spot', 'XAU/USD')
            or m.get('direction') != direction or m.get('currency') not in ('EUR', 'CHF')):
        return None
    # No stale/future clocks, even if the source's overall fresh flag was set.
    if raw.get('found') is not True or raw.get('eligible') is not True or raw.get('fresh') is not True:
        return None
    timestamps = {key: _clock(raw.get(key), now) for key in ('bidAt', 'askAt', 'leverageAt', 'snapshotAt')}
    if any(v is None for v in timestamps.values()):
        return None
    bid, ask, lever = (raw.get(k) for k in ('bid', 'ask', 'leverage'))
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in (bid, ask, lever)):
        return None
    if not (bid > 0 and ask >= bid and lever >= 1):
        return None
    # The selected input is issuer research, explicitly not an executable broker quote.
    return dict(isin=isin, direction=direction, currency=m['currency'],
                bid=bid, ask=ask, leverage=lever, **timestamps,
                sourceRole='issuer-comparison-only', executable=False,
                brokerTradeApproved=False, observedAt=now.isoformat())


def preview_top3(candidates):
    """Never invent a financial ranking when KO distance/carry proof is missing."""
    qualified = []
    seen = set()
    for x in candidates[:80] if isinstance(candidates, list) else []:
        if not isinstance(x, dict):
            continue
        isin = x.get('isin')
        if not valid_isin(isin) or isin in seen:
            continue
        seen.add(isin)
        # Only independently supplied numeric evidence. No inferred cost, leverage, KO.
        ko = x.get('koDistancePercent')
        lev = x.get('issuerLeverage')
        carry = x.get('financingCostPercent')
        if (x.get('issuerVerified') is not True or x.get('issuerQuoteFresh') is not True
                or x.get('direction') not in ('LONG', 'SHORT')
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in (ko, lev, carry))):
            continue
        if not (ko > 0 and lev >= 1 and carry >= 0):
            continue
        qualified.append((isin, x['direction'], ko, lev, carry))
    # Ranking inputs: KO distance first, higher leverage and lower financing cost.
    # No spread or generic data-quality penalty; no risk/FX rating.
    qualified.sort(key=lambda x: (-x[2], -x[3], x[4], x[0]))
    return dict(status='research-only' if qualified else 'insufficient-original-evidence',
                entries=[dict(isin=i, direction=d, koDistancePercent=k,
                              issuerLeverage=l, financingCostPercent=c,
                              tradeApproved=False, executableQuote=False,
                              rankBasis='KO-Abstand, Hebel, Finanzierungskosten')
                         for i, d, k, l, c in qualified[:3]],
                liveTop3Unchanged=True, accountTradabilityVerified=False,
                note='Keine Echtgeldfreigabe; nur vollständig belegte Forschungskennzahlen.')


def proof_reuse_summary(existing, requested):
    """A valid same-ISIN screenshot identity need not be requested twice that day.

    Independent DEGIRO quote, issuer or market-time verification remains separate.
    Caller must supply already validated, presently current proof flags.
    """
    known = {x['isin'] for x in existing[:120] if isinstance(x, dict)
             and valid_isin(x.get('isin')) and x.get('listingConfirmed') is True
             and x.get('current') is True and x.get('executionConfirmed') is False}
    todo = [isin for isin in requested[:120] if valid_isin(isin) and isin not in known]
    return dict(currentIdentityCount=len(known), furtherIdentityProofNeeded=len(set(todo)),
                noNewScreenshotRequiredFor=list(sorted(known.intersection(requested)))[:120],
                quoteFreshnessExtended=False, tradeApproved=False)
