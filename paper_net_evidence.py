"""Conservative, bounded read-only evidence for paper product-model net results.

Never infer executions from a spot proxy or a balance. Original product ask/bid
observations and assumed fees are inspected without exposing private quotes,
ISINs or raw events. Broker net P/L and a strategy winner remain UNVERIFIED.
"""
import math
import paper_costs

LIMIT = 5
REASONS = (
    "not-closed-or-unsettled", "original-selection-or-clock-not-proven",
    "missing-product-price-evidence", "incomplete-sale-unit-accounting",
    "cost-model-or-ledger-not-reconciled", "non-eligible-or-synthetic",
)
MODEL_SCOPE = "last-five-paper-cases-per-profile-model-costs-not-broker-net"


def _num(v):
    return type(v) in (int, float) and math.isfinite(v)


def _positive(v):
    return _num(v) and v > 0


def _close(a, b, tolerance=.02):
    return _num(a) and _num(b) and abs(a - b) <= tolerance


def _reason(case):
    """Exactly one allowlisted reason. No raw financial records leave here."""
    if (not isinstance(case, dict) or case.get("demonstration")
            or case.get("modelOnly") is not True
            or case.get("performanceEligible") is False):
        return "non-eligible-or-synthetic", None
    if (case.get("status") != "closed" or case.get("productReturnKnown") is not True
            or case.get("pendingUnits") != 0 or case.get("remainingUnits") != 0):
        return "not-closed-or-unsettled", None
    # A later deferred model sale after a missing quote is not the original
    # exit execution and may not certify a complete same-time strategy trade.
    if any(isinstance(e, dict) and e.get('kind') in (
            'data-gap', 'deferred-sale', 'ko-barrier-crossed-observed',
            'product-terminated', 'knockout-confirmed')
            for e in (case.get('events') or [])):
        return "non-eligible-or-synthetic", None
    try:
        from paper_evidence_chain import review
        chain = review(case)
    except (TypeError, ValueError, AttributeError, KeyError):
        return "original-selection-or-clock-not-proven", None
    if chain.get("complete") is not True:
        return "original-selection-or-clock-not-proven", None
    product = case.get("product") or {}
    entry = case.get("entryQuote") or {}
    n = case.get("quantity")
    start = case.get("startedAt")
    if (not isinstance(product, dict) or not isinstance(entry, dict)
            or not isinstance(product.get("isin"), str)
            or product.get("isin") != entry.get("isin")
            or entry.get("currency") != "EUR"
            or not isinstance(entry.get("source"), str) or not entry.get("source")
            or not _positive(entry.get("ask")) or not _positive(entry.get("askAt"))
            or not _positive(start) or not 0 <= start-entry["askAt"] <= 90000):
        return "missing-product-price-evidence", None
    if type(n) is not int or not 1 <= n <= 100000:
        return "incomplete-sale-unit-accounting", None
    if not _close(case.get("allocated"), n*entry["ask"]):
        return "incomplete-sale-unit-accounting", None
    end = case.get("settledAt") or case.get("closedAt")
    if not _positive(end) or end < start:
        return "not-closed-or-unsettled", None
    sale_events = []
    for event in case.get("events") or []:
        if not isinstance(event, dict) or event.get("kind") == "entry":
            continue
        if _num(event.get("units")) and event["units"] > 0:
            sale_events.append(event)
    if not sale_events or sum(e["units"] for e in sale_events) != n:
        return "incomplete-sale-unit-accounting", None
    proceeds = 0.
    for event in sale_events:
        quote = event.get("quote") or {}
        when = event.get("recordedAt")
        if (not isinstance(quote, dict)
                or quote.get("isin") != product["isin"]
                or quote.get("currency") != "EUR"
                or not isinstance(quote.get("source"), str) or not quote.get("source")
                or not _positive(quote.get("bid"))
                or not _positive(quote.get("bidAt"))
                or not _positive(when)
                or not start <= when <= end
                or not 0 <= when-quote["bidAt"] <= 90000):
            return "missing-product-price-evidence", None
        proceeds += event["units"]*quote["bid"]
    if not _close(case.get("cashReleased"), proceeds):
        return "incomplete-sale-unit-accounting", None
    model = case.get("ledgerCostModel")
    if (not isinstance(model, dict) or model.get("version") != "cash-costs-v1"
            or not all(_num(model.get(k)) and model[k] >= 0
                       for k in ("feeEurPerOrder", "slippageBpsPerSide",
                                 "extraHoldingBpsPerDay"))
            or not _close(model["extraHoldingBpsPerDay"], 0)):
        return "cost-model-or-ledger-not-reconciled", None
    estimated = paper_costs.evaluate(case, model)
    if (estimated is None or
            not _close(case.get("ledgerCostsDebited"),
                       estimated["feesEur"]+estimated["slippageEur"]) or
            not _close(case.get("ledgerModelNetEur"), estimated["modelNetEur"])):
        return "cost-model-or-ledger-not-reconciled", None
    return None, estimated["modelNetEur"]


def sample(cases):
    """Fail closed on missing samples; never claim complete history coverage."""
    if not isinstance(cases, list):
        return dict(status="unavailable", reason="recent-cases-not-available",
                    readOnly=True, realOrders=False, brokerNetVerified=False,
                    fullHistoryRead=False, scope=MODEL_SCOPE)
    if len(cases) > LIMIT:
        return dict(status="partial", reason="sample-exceeds-limit",
                    readOnly=True, realOrders=False, brokerNetVerified=False,
                    fullHistoryRead=False, scope=MODEL_SCOPE)
    reasons = {k: 0 for k in REASONS}
    verified = []
    for c in cases:
        code, net = _reason(c)
        if code:
            reasons[code] += 1
        else:
            verified.append(net)
    return dict(
        status="observed" if cases else "not-yet-observed",
        readOnly=True, realOrders=False, fullHistoryRead=False,
        brokerNetVerified=False, modelCostsOnly=True,
        sampled=len(cases),
        modelEvidenceEligible=len(verified),
        excluded=len(cases)-len(verified),
        excludedReasonCounts={k: v for k, v in reasons.items() if v},
        sampleModelNetEur=round(sum(verified), 4) if verified else None,
        positiveSampleModelCases=sum(n > 0 for n in verified),
        scope=MODEL_SCOPE,
        note="Originale Produktkurse und eingefrorene Beispielkosten koennen "
             "einen begrenzten Paper-Fall nachvollziehbar machen. Kein "
             "ausfuehrbarer DEGIRO-Kurs, kein bestaetigter Gebuehrentarif, "
             "kein vollstaendiger Historien-/Strategie-Nettogewinn.")
