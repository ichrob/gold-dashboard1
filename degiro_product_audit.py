"""Private, fail-closed audit of the ACTIVE screenshot product universe.

Runs alongside existing paper quote refreshes. Never queries DEGIRO, makes
orders, promotes research quotes to execution, or replaces screenshot lists.
All per-ISIN details stay in the authenticated private database/API.
"""
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from product_quotes import valid_isin

ZURICH = ZoneInfo("Europe/Zurich")
QUOTE_MAX_MS = 90_000
BARRIER_MAX_MS = 8 * 3_600_000
REPORT_MAX_MS = 180_000
CODES = {
    "identity": "Produktidentität beim Emittenten fehlt oder ist widersprüchlich",
    "list-identity": "ISIN-Bestätigung der gespeicherten Produktliste fehlt; Emittentennachweis wird separat geprüft",
    "direction": "Richtung nicht übereinstimmend bestätigt",
    "underlying": "Gold-Spot-Basiswert nicht bestätigt",
    "currency": "Produktwährung fehlt, ist nicht unterstützt oder widerspricht der Produktliste",
    "factor": "Faktorprodukt ausgeschlossen",
    "future": "Anderer Basiswert/Future-Kontrakt: nicht als Spotprodukt freigegeben",
    "venue": "Swiss DOTS ist ein eigener, exklusiver OTC-Handelsplatz. Ein Kurs dort ist kein DEGIRO-Ausführungsnachweis; nur eine gesondert belegte DEGIRO-Handelsroute zählt.",
    "terminated": "Produkt vom Emittenten als beendet gemeldet",
    "source-status-conflict": "Quellenkonflikt: comdirect meldet Knock-out/inaktiv, SG bestätigt den Endstatus nicht. Laufende Kurs-/Hebelnachweise bleiben bis zur Klärung ungültig; keine Handelsfreigabe.",
    "quote": "Belegtes Geld-/Briefpaar aus Produkt- oder Ersatzquelle fehlt; Chartwerte bleiben separat",
    "quote-time": "Originalzeit des Geld-/Briefpaares fehlt oder ist veraltet",
    "leverage": "Emittentenhebel fehlt",
    "leverage-time": "Aktueller Zeitnachweis für Originalhebel, gemeinsamen Quellenbezug oder gültige Hebelberechnung fehlt",
    "ko": "KO-Schwelle fehlt",
    "ko-time": "KO-Gültigkeitsnachweis fehlt oder ist älter als acht Stunden",
    "strike": "Basispreis fehlt",
    "ratio": "Bezugsverhältnis fehlt",
    "maturity": "Laufzeit oder ausdrücklich unbegrenzte Laufzeit fehlt",
    "market-closed": "Emittentenhandel momentan geschlossen",
    "market-status": "Handelsstatus vom Emittenten nicht bestätigt",
}


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _time_ms(value):
    if type(value) in (int, float) and math.isfinite(value) and value > 1_600_000_000_000:
        return value
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d.timestamp() * 1000 if d.tzinfo is not None else None
    except ValueError:
        return None


def _recent(value, now_ms, max_age):
    t = _time_ms(value)
    return t is not None and 0 <= now_ms - t <= max_age



def _observed_prices(quote, isin, now_ms):
    """Read-only provenance. Independent bid/ask clocks, never an execution feed."""
    observations = []
    quote = quote if isinstance(quote, dict) else {}
    variants = [
        ("Produktquelle", quote),
        ("SG-Chart", quote.get("nativeChartEvidence") or quote.get("chartEvidence")),
        ("Vorhandene Vergleichsquelle", quote.get("secondaryQuote")),
        ("Dritte Quelle", quote.get("thirdQuote")),
    ]
    seen = set()
    for label, row in variants:
        if not isinstance(row, dict):
            continue
        if label == "Produktquelle" and quote.get("found") is not True:
            continue
        # The issuer chart has one genuine chart-point clock for both plotted
        # values; it is NOT independent bid- and ask-execution evidence.
        chart = label == "SG-Chart"
        bid_at = row.get("pointAt") if chart else row.get("bidAt")
        ask_at = row.get("pointAt") if chart else row.get("askAt")
        bid, ask = row.get("bid"), row.get("ask")
        if not (_positive(bid) and _positive(ask) and ask >= bid):
            continue
        bts, ats = _time_ms(bid_at), _time_ms(ask_at)
        if bts is None or ats is None or bts > now_ms + 5000 or ats > now_ms + 5000:
            continue
        source = "SG · datierter Chartpunkt" if chart else str(row.get("source") or quote.get("source") or "Unbekannt")[:90]
        currency = row.get("currency") or quote.get("currency") or (quote.get("metadata") or {}).get("currency")
        if currency not in ("EUR", "CHF"):
            continue
        key = (source, currency, bid, ask, bts, ats)
        if key in seen:
            continue
        seen.add(key)
        observations.append({
            "label": label, "source": source, "currency": currency,
            "bid": bid, "ask": ask, "bidAt": bid_at, "askAt": ask_at,
            "ageSeconds": round(max(now_ms - bts, now_ms - ats) / 1000, 1),
            "current": _recent(bid_at, now_ms, QUOTE_MAX_MS)
                       and _recent(ask_at, now_ms, QUOTE_MAX_MS),
            "isinBound": row.get("isin") == isin if label in ("Vorhandene Vergleichsquelle", "Dritte Quelle") else
                         quote.get("isin") == isin and quote.get("productVerified") is True,
            "venue": str(row.get("venue") or row.get("exchange") or "")[:80],
            "upstream": row.get("upstream") or ("SG" if chart else None),
            "researchOnly": True, "degiroExecutable": False,
            "note": ("Ein SG-Chartpunkt ist keine handelbare Geld-/Briefquote."
                     if chart else "Börsen-/Anbieterkurs ist kein verbindlicher DEGIRO-Ausführungskurs."),
        })
    return observations


def _market_cross_check(observations):
    """Read-only, synchronous issuer/secondary-market price plausibility test.

    No DEGIRO login, no order, no actual DEGIRO executable quote.
    """
    result = dict(status="unverified", checked=False, degiroExecutable=False,
                  brokerConnected=False, deviationPct=None, reasons=[])
    primary = next((x for x in observations if x["label"] == "Produktquelle"
                    and x["isinBound"]), None)
    if primary is None:
        primary = next((x for x in observations if x["label"] == "SG-Chart"
                        and x["isinBound"]), None)
    secondary = next((x for x in observations if x["label"] == "Vorhandene Vergleichsquelle"), None)
    if primary is None or secondary is None:
        result["reasons"].append("Kein zweites zeitlich belegtes Kurspaar. DEGIRO-Ausführung ohne Brokerdaten nicht nachweisbar.")
        return result
    if not secondary["isinBound"]:
        result["reasons"].append("Vergleichsquelle ist nicht durch eigene ISIN eindeutig gebunden.")
    if not secondary["venue"]:
        result["reasons"].append("Handelsplatz der Vergleichsquelle fehlt.")
    if primary["source"] == secondary["source"]:
        result["reasons"].append("Quellen sind nicht unabhängig.")
    if secondary.get("upstream") in ("SG", "BNP") and (primary.get("upstream") == secondary["upstream"] or secondary["upstream"] in primary["source"]):
        result["reasons"].append("Zwei Abrufwege, aber derselbe "+secondary["upstream"]+"-Kursgeber; keine unabhängige Preisbestätigung.")
    if primary["currency"] != secondary["currency"]:
        result["reasons"].append("Unterschiedliche Währungen; datierte Umrechnung fehlt.")
    if not primary["current"] or not secondary["current"]:
        result["reasons"].append("Mindestens ein Kurs älter als 90 Sekunden.")
    if result["reasons"]:
        return result
    stamps = [_time_ms(x[k]) for x in (primary, secondary) for k in ("bidAt", "askAt")]
    if any(x is None for x in stamps) or max(stamps)-min(stamps) > 30_000:
        result["reasons"].append("Kurszeiten der Quellen liegen mehr als 30 Sekunden auseinander.")
        return result
    primary_mid = (primary["bid"]+primary["ask"])/2
    secondary_mid = (secondary["bid"]+secondary["ask"])/2
    pct = abs(secondary_mid-primary_mid)/primary_mid*100
    result.update(checked=True, status="outlier" if pct > 1 else "price-comparable",
                  deviationPct=round(pct, 4), sourceA=primary["source"],
                  sourceB=secondary["source"], currency=primary["currency"],
                  venue=secondary["venue"], timeSkewSeconds=round((max(stamps)-min(stamps))/1000, 1))
    result["reasons"].append(
        ("Preisabweichung über 1 %; Börsenplatz und Kursart genauer prüfen."
         if pct > 1 else "Zeitnaher Quellenvergleich gelungen.")
        + " Keine Bestätigung eines ausführbaren DEGIRO-Kurses.")
    return result


def _research_links(isin):
    """Only identity-verified destination URLs; links never run a crawler."""
    if isin == "DE000FG7N6Z2":
        return [{
            "name": "Onvista – SG OTC / Frankfurt / Stuttgart",
            "url": "https://www.onvista.de/derivate/Knock-Outs/341942224-FG7N6Z-DE000FG7N6Z2",
            "mode": "manual-only",
            "note": "Geld/Brief, Originaluhrzeit, Stückzahl und Handelsplatz im Browser vergleichen. Automatische Onvista-Abfragen sind ohne Anbietergenehmigung gesperrt.",
        }]
    return []


def _dated_barrier(quote, metadata, now_ms):
    """Source-specific effective date PLUS recent issuer recheck, never receipt alone."""
    term = (quote.get("conditions") or {}).get("ko") or {}
    if not isinstance(term, dict):
        term = {}
    if any(term.get(k) for k in ('conflict', 'revoked', 'ocrCorrection')):
        return False
    # Same declared-series policy used by the product cards, with the original
    # observation time and exact eight-hour expiry, not the latest request time.
    series = term.get('validitySeries') or {}
    if (quote.get('productVerified') is True and _positive(term.get('value'))
            and not any(term.get(k) for k in ('at', 'dateText', 'sourceTimeRaw'))
            and series.get('policy') == 'declared-series-v1'
            and series.get('origin') == 'automatic'
            and series.get('isin') == quote.get('isin')
            and term.get('source') and series.get('source') == term['source']
            and (metadata.get('ko') is None or metadata['ko'] == term['value'])):
        age = now_ms - (_time_ms(series.get('observedAt')) or 0)
        return 0 <= age < BARRIER_MAX_MS
    checked = quote.get("termsCheckedAt") or quote.get("checkedAt")
    if not _recent(checked, now_ms, BARRIER_MAX_MS):
        return False
    # A verified source-specific effective calendar date can be safely reused
    # for the user's eight-hour re-verification policy.
    today = datetime.fromtimestamp(now_ms/1000, ZURICH).date()
    raw = metadata.get("termsDate") if metadata.get("termsDated") is True else None
    if raw:
        try:
            if datetime.fromisoformat(str(raw)[:10]).date() == today:
                return True
        except ValueError:
            pass
    if term.get("conditionVerified") is True and _recent(term.get("at") or term.get("reviewedAt"), now_ms, BARRIER_MAX_MS):
        return True
    if metadata.get("termsFixed") is True and quote.get("productVerified") is True:
        # Fixed-contract verification still expires after 8h of rechecks.
        return True
    return False


def _condition_value(quote, key, now_ms):
    """Use verified field-local fallback evidence without rewriting metadata."""
    item = (quote.get('conditions') or {}).get(key) or {}
    if (quote.get('productVerified') is not True or not isinstance(item, dict)
            or not item.get('source')
            or any(item.get(k) for k in ('conflict', 'revoked', 'ocrCorrection'))
            or not _recent(item.get('reviewedAt'), now_ms, BARRIER_MAX_MS)):
        return None
    if item.get('conditionVerified') is not True:
        series = item.get('validitySeries') or {}
        if (key not in ('strike', 'ko') or any(item.get(k) for k in ('at', 'dateText', 'sourceTimeRaw'))
                or series.get('policy') != 'declared-series-v1' or series.get('origin') != 'automatic'
                or series.get('isin') != quote.get('isin') or series.get('source') != item['source']
                or not 0 <= now_ms - (_time_ms(series.get('observedAt')) or 0) < BARRIER_MAX_MS):
            return None
    return item.get('value')


def _term_time_evidence(quote, key, now_ms):
    """Expose the accepted series basis without inventing an issuer date."""
    condition = (quote.get('conditions') or {}).get(key) or {}
    out = {name: condition[name] for name in
           ('value', 'source', 'at', 'dateText', 'sourceTimeRaw', 'sourceField',
            'reviewedAt', 'conditionVerified', 'validityUnconfirmed') if name in condition}
    series = condition.get('validitySeries') or {}
    accepted = (condition.get('validityUnconfirmed') is True
                and _condition_value(quote, key, now_ms) is not None
                and (key != 'ko' or _dated_barrier(quote, quote.get('metadata') or {}, now_ms)))
    if accepted:
        observed = _time_ms(series.get('observedAt'))
        if observed is not None:
            out.update(validityBasis='declared-series-v1', policyAccepted=True,
                       policyObservedAt=series['observedAt'],
                       policyValidUntil=datetime.fromtimestamp(
                           (observed + BARRIER_MAX_MS)/1000, timezone.utc).isoformat())
    return out


def _backup_pair(quote, isin, now_ms):
    """A dated issuer LiveTrading pair supplies data, never DEGIRO execution."""
    from swissquote_quotes import current_pair
    swiss = current_pair(quote, datetime.fromtimestamp(now_ms/1000, timezone.utc))
    if quote.get('isin') == isin and swiss:
        return swiss
    from comdirect_quotes import matches_primary
    row = quote.get('secondaryQuote') or {}
    meta = quote.get('metadata') or {}
    backup = quote.get('comdirectFieldsBackup') or {}
    if (quote.get('isin') != isin or quote.get('productVerified') is not True
            or quote.get('sourceDisabled') or meta.get('status') != 1
            or backup.get('state') == 'inactive'
            or set(backup.get('conflicts') or []) & {'direction', 'currency', 'underlying'}
            or not matches_primary(quote, row)
            or row.get('isin') != isin
            or row.get('priceKind') != 'market-observation' or row.get('delayed')
            or row.get('isExecutableQuote') is not False
            or row.get('degiroExecutable') is not False
            or not _positive(row.get('bid')) or not _positive(row.get('ask'))
            or row['ask'] < row['bid']
            or row.get('bidAt') != row.get('askAt')
            or not _recent(row.get('bidAt'), now_ms, QUOTE_MAX_MS)):
        return None
    return row


def _shared_leverage(quote, isin, now_ms):
    """Accept the same verified observation series as the product cards."""
    ref = quote.get("issuerLeverageReference") or {}
    ctx = quote.get("sharedTimeContext") or {}
    obs = (quote.get("sharedValueObservations") or {}).get("Referenzhebel") or {}
    chart = quote.get("nativeChartEvidence") or quote.get("chartEvidence") or {}
    at = ctx.get("at")
    if (quote.get("isin") != isin or quote.get("productVerified") is not True
            or (quote.get("metadata") or {}).get("status") != 1
            or ctx.get("kind") != "issuer-collection" or ctx.get("isin") != isin
            or not at or at != chart.get("pointAt") or at != ref.get("sharedContextAt")
            or "Referenzhebel" not in (ctx.get("fields") or [])
            or obs.get("isin") != isin or obs.get("contextAt") != at
            or not _positive(ref.get("value")) or obs.get("value") != ref["value"]
            or ref.get("dated") is not False or ref.get("eligible") is not False):
        return None
    # Never override a contradictory separately published source timestamp.
    if ref.get("sourceAt") is not None and not _recent(ref["sourceAt"], now_ms, QUOTE_MAX_MS):
        return None
    return {"value": ref["value"], "at": at,
            "current": _recent(at, now_ms, 300_000),
            "kind": "shared-issuer-observation", "researchOnly": True}


def examine(product, quote, now_ms, list_uploaded_at=None):
    """Return diagnostic evidence, not a new eligibility verdict."""
    isin = str(product.get("isin") or "").upper()
    direction = product.get("productDirection") or product.get("direction")
    quote = quote if isinstance(quote, dict) else {}
    metadata = quote.get("metadata") if isinstance(quote.get("metadata"), dict) else {}
    missing = []
    verified = quote.get("isin") == isin and quote.get("productVerified") is True
    # SG's verified factor response intentionally has no live quote/term fields.
    # Accept its existing productType spelling as well as the canonical type;
    # an excluded factor is not fifteen independent missing-data incidents.
    if verified and 'FACTOR' in (metadata.get('type'), metadata.get('productType')):
        return dict(isin=isin, direction=direction, state='excluded-factor', excluded=True,
            missing=['factor'], messages=[CODES['factor']],
            source=str(quote.get('source') or 'Emittent')[:80],
            sourceStatusEvidence=dict(issuerVerified=True, issuerProductType='FACTOR',
                                      issuerStatus=metadata.get('status')),
            timeEvidence=dict(missing=[], leverageBasis='unavailable', terms={}),
            quoteSourceAt=None, leverageSourceAt=None, issuerLeverageObservation=None,
            leverageObservation=None, sourceObservations=[],
            dataQuoteSource=None, dataQuoteKind=None, identityEvidence='issuer-confirmed-excluded',
            tradeApproved=False, degiroVerified=False,
            autoRecovery='Faktorprodukt ausgeschlossen; keine laufenden Kurs-, Hebel- oder KO-Nachweise erforderlich.')
    snapshot = product.get('snapshot') or {}
    identity_matches = (valid_isin(isin) and verified
        and direction in ('LONG', 'SHORT')
        and (quote.get('direction') or metadata.get('direction')) == direction
        and (not snapshot.get('isin') or snapshot['isin'] == isin)
        and (not snapshot.get('direction') or snapshot['direction'] == direction)
        and (not product.get('currency') or product['currency'] ==
             (metadata.get('currency') or quote.get('currency'))))
    # Apply the same broker-display requirement to every verified Swiss DOTS
    # product, including newly discovered ISINs. Issuer availability alone
    # cannot establish availability at DEGIRO.
    swiss_dots = (
        verified
        and metadata.get("issuerExchangeCode") == "CBSW"
        and metadata.get("currency") == "CHF"
    )
    from broker_venue_evidence import assessment as venue_assessment
    broker_venue = product.get('brokerVenueEvidence')
    # A listing screenshot remains evidence even when the issuer lookup fails.
    venue_status = venue_assessment(product, product.get('currency') or metadata.get('currency'), now_ms)
    has_broker_venue = valid_isin(isin) and venue_status['current']
    broker_identity_matches = (has_broker_venue
        and isinstance(broker_venue, dict)
        and broker_venue.get('isin') == isin
        and bool(list_uploaded_at)
        and broker_venue.get('listUploadedAt') == list_uploaded_at)
    # The current DEGIRO listing evidence is an exact, list-generation-bound
    # ISIN confirmation even when the issuer source is temporarily unavailable.
    # It proves listing identity only: issuer fields and trade approval remain
    # independently fail-closed below.
    if not valid_isin(isin) or not (
            product.get('isinConfirmed') or identity_matches or broker_identity_matches):
        missing.append('list-identity')
    if swiss_dots and not has_broker_venue:
        missing.append("venue")
    if not verified:
        missing.append("identity") if "identity" not in missing else None
    if direction not in ("LONG", "SHORT") or metadata.get("direction", quote.get("direction")) != direction:
        missing.append("direction")
    if metadata.get("type") == "FACTOR":
        missing.append("factor")
    status = metadata.get("status")
    terminated = verified and ((type(status) is int and bool(status & (2 | 8 | 16 | 32))) or quote.get("terminated") is True)
    # A portal's confirmed full product identity is useful status evidence,
    # but only the issuer can confirm the issuer's terminal status. Do not
    # confuse 'Knock Out erreicht: Ja' with an ordinary transient quote outage.
    fallback_fields = quote.get("comdirectFieldsBackup") or {}
    secondary_inactive = (verified and not terminated and status == 1
                          and fallback_fields.get("state") == "inactive"
                          and fallback_fields.get("isin") == isin
                          and fallback_fields.get("inactive") is True)
    if terminated:
        missing.append("terminated")
    elif secondary_inactive:
        missing.append("source-status-conflict")
    if metadata.get("underlyingType") == "FUTURE":
        missing.append("future")
    if (metadata.get("underlyingType") != "SPOT" or
            metadata.get("underlying") not in ("XAU/USD", "Gold", "Gold Spot")):
        missing.append("underlying")
    # Product identity uses the native contract currency, never a converted
    # analysis quote. Both supported currencies can have complete data proofs.
    native_currency = metadata.get("currency") or quote.get("currency")
    if native_currency not in ("EUR", "CHF") or (product.get("currency") and product["currency"] != native_currency):
        missing.append("currency")
    quote_ok = (verified and quote.get("found") is True and
                quote.get("priceKind") not in ("calculated", "issuer-chart") and
                quote.get("isExecutableQuote") is not False and
                _positive(quote.get("bid")) and _positive(quote.get("ask")) and
                quote["ask"] >= quote["bid"])
    primary_current = quote_ok and all(_recent(quote.get(k), now_ms, QUOTE_MAX_MS)
                                       for k in ('bidAt', 'askAt'))
    backup_pair = _backup_pair(quote, isin, now_ms) if not primary_current else None
    if not quote_ok and not backup_pair:
        missing.append("quote")
    # Do not use quoteAt as a substitute for independent bid/ask stamps.
    data_pair = backup_pair or quote
    quote_times = (data_pair.get("bidAt"), data_pair.get("askAt"))
    if not all(_recent(at, now_ms, QUOTE_MAX_MS) for at in quote_times):
        missing.append("quote-time")
    from leverage_backup import current_evidence, historical_reference
    checked_time = datetime.fromtimestamp(now_ms/1000, timezone.utc)
    calculated_leverage = current_evidence(quote, checked_time) if verified else None
    # An old original/derived value is research metadata, not a cure for an
    # absent original leverage time. On Sunday retain its source date instead
    # of treating closed-market quotes as broken or re-stamping Friday.
    historical_leverage = historical_reference(quote, checked_time) if verified else None
    shared_leverage = _shared_leverage(quote, isin, now_ms) if verified else None
    # Bob's calculated gearing may carry a model-input timestamp in leverageAt.
    # That timestamp is NOT the issuer's original leverage clock.
    issuer_leverage_at = quote.get("leverageAt") if quote.get("leverageEstimated") is not True else None
    if not _positive(quote.get("leverage")) and not shared_leverage and not calculated_leverage:
        missing.append("leverage")
    if not _recent(issuer_leverage_at, now_ms, QUOTE_MAX_MS) and not (
            shared_leverage and shared_leverage["current"]) and not calculated_leverage:
        missing.append("leverage-time")
    if not _positive(metadata.get("ko") or quote.get("ko") or _condition_value(quote, 'ko', now_ms)):
        missing.append("ko")
    if not _dated_barrier(quote, metadata, now_ms):
        missing.append("ko-time")
    if not _positive(metadata.get("strike") or metadata.get("basisPrice") or quote.get("basisPrice")
                     or _condition_value(quote, 'strike', now_ms)):
        missing.append("strike")
    if not _positive(metadata.get("ratio") or quote.get("ratio") or _condition_value(quote, 'ratio', now_ms)):
        missing.append("ratio")
    # SG direct publishes verified contract fields in conditions, not metadata.
    # Require the same product, provenance and a recent verification; a bare
    # value or a contradicted/revoked condition is not evidence.
    maturity = (quote.get("conditions") or {}).get("maturity") or {}
    maturity_ok = (verified and isinstance(maturity, dict)
        and maturity.get("conditionVerified") is True and bool(maturity.get("source"))
        and not any(maturity.get(key) for key in ("conflict", "revoked", "ocrCorrection"))
        and isinstance(maturity.get("value"), str) and bool(maturity["value"].strip())
        and _recent(maturity.get("reviewedAt"), now_ms, BARRIER_MAX_MS))
    if not maturity_ok and not (metadata.get("termsFixed") and (metadata.get("maturity") or metadata.get("expiry"))) and not (
            metadata.get("openEnded") is True or metadata.get("maturity") or
            metadata.get("expiry") or metadata.get("maturityDate")):
        missing.append("maturity")
    if quote.get("marketOpen") is False:
        missing.append("market-closed")
    elif quote.get("marketOpen") is not True and not backup_pair:
        missing.append("market-status")
    # Once SG itself confirms termination, absent live prices, quote clocks,
    # gearing and market status are expected, not five separate repair faults.
    # The product remains permanently blocked, never promoted to analysis.
    if terminated or secondary_inactive:
        # No point escalating five dependent missing quote/clock/gearing fields
        # until the contradictory product status has been resolved. These
        # fields remain unavailable, not silently repaired or marked current.
        missing = [code for code in missing if code not in (
            "quote", "quote-time", "leverage", "leverage-time",
            "market-status", "market-closed")]
    # No independent DEGIRO feed exists: even a perfect issuer audit can NEVER
    # validate actual DEGIRO executable quotes/tradability.
    codes = list(dict.fromkeys(missing))
    observations = _observed_prices(quote, isin, now_ms) if verified else []
    cross_check = _market_cross_check(observations)
    return {
        "isin": isin if valid_isin(isin) else None,
        "direction": direction if direction in ("LONG", "SHORT") else None,
        "state": "terminated" if terminated else ("analysis-evidence-complete" if calculated_leverage and not issuer_leverage_at else "issuer-evidence-complete") if not codes else "incomplete",
        "missing": codes,
        "messages": [CODES[code] for code in codes],
        # Removing dependent missing codes must never make an old quote look current.
        "quoteSourceAt": (data_pair.get("bidAt") if not (terminated or secondary_inactive)
                          and (quote_ok or backup_pair)
                          and _recent(data_pair.get("bidAt"), now_ms, QUOTE_MAX_MS)
                          and _recent(data_pair.get("askAt"), now_ms, QUOTE_MAX_MS)
                          else None),
        "identityEvidence": ("source-matched" if identity_matches else "list-confirmed"
                             if product.get('isinConfirmed') or broker_identity_matches else "missing"),
        "dataQuoteSource": (data_pair.get('source') if (quote_ok or backup_pair)
                            and not (terminated or secondary_inactive) else None),
        "dataQuoteKind": (None if terminated or secondary_inactive else
                          "market-observation" if backup_pair else "issuer" if quote_ok else None),
        "executionNote": "Datenabgleich abgeschlossen; keine Bestätigung eines ausführbaren DEGIRO-Kurses",
        "leverageObservation": (shared_leverage if shared_leverage and shared_leverage["current"]
                                else calculated_leverage or shared_leverage),
        "leverageReference": historical_leverage if ("leverage" in codes or "leverage-time" in codes) else None,
        # Keep an absent standalone issuer clock distinct from an accepted
        # shared observation/calculation. Never copy that context into the
        # issuer's original timestamp field.
        "timeEvidence": {
            "missing": [code for code in codes if code in ('quote-time', 'leverage-time', 'ko-time')],
            "leverageBasis": ('unavailable' if terminated or secondary_inactive else
                'original-issuer-time' if _recent(issuer_leverage_at, now_ms, QUOTE_MAX_MS) else
                'shared-issuer-observation' if shared_leverage and shared_leverage['current'] else
                'calculated-input-times' if calculated_leverage else 'unconfirmed'),
            "terms": {key: _term_time_evidence(quote, key, now_ms)
                for key in ('ko', 'strike')
                if verified and isinstance(condition := (quote.get('conditions') or {}).get(key), dict)},
        },
        "leverageSourceAt": (issuer_leverage_at if not (terminated or secondary_inactive)
                              and "leverage-time" not in codes
                              and _recent(issuer_leverage_at, now_ms, QUOTE_MAX_MS)
                              else None),
        "issuerLeverageObservation": (dict(value=quote.get("leverage"), at=issuer_leverage_at,
                                           source=quote.get("source"))
                                      if _positive(quote.get("leverage"))
                                      and _recent(issuer_leverage_at, now_ms, QUOTE_MAX_MS)
                                      and quote.get("leverageEstimated") is not True else None),
        "source": str(quote.get("source") or "Emittenten- und Ersatzquellen")[:80],
        "sourceObservations": observations,
        "snapshotId": quote.get("snapshotId"),
        "sourceRecovery": quote.get("sourceRecovery", []),
        # Diagnostic-only, bounded provenance. Secondary inactive is a
        # conflict requiring issuer confirmation, NOT a new termination proof.
        "sourceStatusEvidence": {
            "issuerVerified": verified,
            "issuerStatus": status if type(status) is int else None,
            "issuerRawStatus": metadata.get("sgStatus") if type(metadata.get("sgStatus")) is int else None,
            "issuerTerminal": terminated,
            "secondaryInactive": secondary_inactive,
            "secondarySource": fallback_fields.get("source") if secondary_inactive else None,
            "secondaryCheckedAt": fallback_fields.get("checkedAt") if secondary_inactive else None,
            "sgFailureCode": str(quote.get("quoteFailureCode") or "")[:60] or None,
            "sgLastFailureStage": str(quote.get("lastSourceFailureStage") or "")[:32] or None,
            "swissquoteState": (quote.get("swissquoteBackup") or {}).get("state"),
            "swissquoteReasonCode": str((quote.get("swissquoteBackup") or {}).get("reasonCode") or "")[:60] or None,
        },
        "oneSidedQuote": deepcopy(quote.get("oneSidedQuote")) if verified and not terminated else None,
        "nativeCurrency": native_currency,
        "thirdSourceEvidence": quote.get("swissquoteBackup"),
        "fieldRecovery": quote.get("comdirectFieldsBackup"),
        "marketCrossCheck": cross_check,
        "researchLinks": _research_links(isin),
        "issuerVenue": "Swiss DOTS (CHF)" if swiss_dots else None,
        "venueEvidence": "https://www.finanzen.ch/derivate/"+isin.lower() if swiss_dots else None,
        "brokerVenueEvidence": broker_venue if has_broker_venue else None,
        "brokerVenueStatus": dict(venue_status, required=swiss_dots),
        "venueAction": ("Keine Swiss-DOTS-Quotierung als DEGIRO-Kurs verwenden. "
                        "DEGIRO-Kursdatenbild mit ISIN, Börse, Währung und Datum hochladen; "
                        "Bob übernimmt eindeutige Angaben automatisch."
                        if swiss_dots and not has_broker_venue else None),
        "autoRecovery": ("Vom Emittenten als beendet gemeldet · keine neue Handelsfreigabe; fehlende laufende Kurse sind kein Reparaturfehler"
                         if terminated else "SG stellt nur Geld; Briefkurs fehlt beim Anbieter. Quellen werden erneut geprüft, keine Handelsfreigabe."
                         if quote.get("quoteFailureCode") == "SG_BID_ONLY" else "Vorhandene Emittenten- und Ersatzquellen werden bei der nächsten Aktualisierung erneut geprüft"),
        "degiroVerified": False,
        "tradeApproved": False,
    }


def _retain_recent_issuer_leverage(item, quote, before, now_ms):
    """Keep a still-current original issuer proof across a transient fallback cycle."""
    if ("leverage-time" not in item.get("missing", []) or not isinstance(quote, dict)
            or quote.get("isin") != item.get("isin") or quote.get("productVerified") is not True
            or quote.get("leverageEstimated") is True):
        return
    prior = before.get("issuerLeverageObservation") if isinstance(before, dict) else None
    if (not isinstance(prior, dict) or not _positive(prior.get("value"))
            or not _recent(prior.get("at"), now_ms, QUOTE_MAX_MS)
            or not _positive(quote.get("leverage"))
            or not math.isclose(float(prior["value"]), float(quote["leverage"]), rel_tol=1e-9, abs_tol=1e-9)):
        return
    item["missing"] = [code for code in item["missing"] if code != "leverage-time"]
    item["messages"] = [CODES[code] for code in item["missing"]]
    item["leverageSourceAt"] = prior["at"]
    item["issuerLeverageObservation"] = dict(prior)
    item['timeEvidence']['leverageBasis'] = 'original-issuer-time'
    item['timeEvidence']['missing'] = [code for code in item['timeEvidence']['missing'] if code != 'leverage-time']
    if not item["missing"]:
        item["state"] = "issuer-evidence-complete"



def _retain_historical_leverage_reference(item, before, now_ms):
    """Keep a previously verified same-list reference, not the live leverage.

    The caller has already checked that previous belongs to the same list
    generation. A new list, issuer terminal status or expired original clock
    must never inherit this historical research observation.
    """
    if (item.get('state') in ('terminated', 'excluded-factor')
            or not any(key in item.get('missing', ()) for key in ('leverage', 'leverage-time'))
            or not valid_isin(item.get('isin')) or item.get('leverageReference')
            or not isinstance(before, dict) or before.get('isin') != item['isin']):
        return
    from leverage_backup import HISTORICAL_REFERENCE_MAX_AGE_SECONDS
    def acceptable(value):
        return (_positive(value.get('value')) and
                _recent(value.get('at'), now_ms, HISTORICAL_REFERENCE_MAX_AGE_SECONDS * 1000) and
                value.get('kind') in ('historical-issuer-leverage', 'historical-calculated-gearing') and
                value.get('researchOnly') is True and value.get('tradeApproved') is False and
                value.get('current') is False and bool(value.get('source')))
    prior = before.get('leverageReference') or {}
    if isinstance(prior, dict) and acceptable(prior):
        item['leverageReference'] = deepcopy(prior)
        return
    # Older audits predate the explicit historical field. Their own validated
    # issuer observation or time-aligned calculation may form the reference.
    status = before.get('sourceStatusEvidence') or {}
    if status.get('issuerVerified') is not True:
        return
    issuer = before.get('issuerLeverageObservation') or {}
    if (isinstance(issuer, dict) and _positive(issuer.get('value')) and
            _recent(issuer.get('at'), now_ms, HISTORICAL_REFERENCE_MAX_AGE_SECONDS * 1000)
            and issuer.get('source')):
        item['leverageReference'] = dict(value=issuer['value'], at=issuer['at'],
            source=str(issuer['source'])[:80], kind='historical-issuer-leverage',
            label='Letzter Originalhebel', current=False, researchOnly=True, tradeApproved=False,
            note='Frühere Emittenten-Originalzeit; nicht als aktueller Hebel oder Handelskurs nutzen.')
        return
    previous_observation = before.get('leverageObservation') or {}
    if (isinstance(previous_observation, dict) and previous_observation.get('kind') == 'calculated-gearing'
            and previous_observation.get('current') is True
            and (before.get('timeEvidence') or {}).get('leverageBasis') == 'calculated-input-times'
            and _positive(previous_observation.get('value'))
            and _recent(previous_observation.get('at'), now_ms, HISTORICAL_REFERENCE_MAX_AGE_SECONDS * 1000)):
        item['leverageReference'] = dict(value=previous_observation['value'],
            at=previous_observation['at'], source='Bob · früherer geprüfter Berechnungslauf',
            kind='historical-calculated-gearing', label='Historisch berechneter Hebel',
            current=False, researchOnly=True, tradeApproved=False,
            note='Früherer belegter Analysehebel; Quellenzeit bleibt historisch, Handelsfreigabe bleibt gesperrt.')

def _retain_verified_terminal(item, before, quote):
    """Carry only an exact, previously issuer-verified terminal status.

    The issuer may temporarily return no metadata after a restart. A prior
    explicit terminal SG status is not an expiring live quote, and must not
    turn into fifteen unrelated missing-price incidents. Provenance is retained;
    a new list generation or new verified issuer status does not inherit it.
    """
    if (not isinstance(before, dict) or before.get('state') != 'terminated'
            or before.get('isin') != item.get('isin')
            or item.get('state') == 'terminated'
            or not valid_isin(item.get('isin'))
            or isinstance(quote, dict) and quote.get('productVerified') is True):
        return
    previous = before.get('sourceStatusEvidence') or {}
    raw = previous.get('issuerRawStatus')
    if (previous.get('issuerVerified') is not True
            or previous.get('issuerTerminal') is not True
            or previous.get('issuerStatus') != 2
            or type(raw) is not int or not (raw & (2 | 8 | 16 | 32))
            or before.get('tradeApproved') is True):
        return
    if isinstance(quote, dict) and quote.get('isin') not in (None, item['isin']):
        return
    from copy import deepcopy
    item.update(state='terminated', missing=['terminated'],
                messages=[CODES['terminated'] +
                          ' · zuletzt mit Emittentenstatus bestätigt; neuer Abruf derzeit nicht verfügbar'],
                source=str(before.get('source') or 'Emittent')[:80],
                sourceStatusEvidence=dict(deepcopy(previous),
                    carriedForward=True, currentIssuerAvailable=False),
                quoteSourceAt=None, leverageSourceAt=None,
                dataQuoteSource=None, dataQuoteKind=None,
                leverageObservation=None, issuerLeverageObservation=None,
                timeEvidence=dict(missing=[], leverageBasis='unavailable', terms={}),
                sourceObservations=[], degiroVerified=False, tradeApproved=False,
                autoRecovery='Früheren verifizierten Endstatus beibehalten; erneute Emittentenprüfung ohne Handelsfreigabe')


def build(feed, quotes, now_ms=None, previous=None):
    now_ms = now_ms if now_ms is not None else datetime.now(timezone.utc).timestamp()*1000
    previous = previous if isinstance(previous, dict) else {}
    generation = feed.get("listUploadedAt") if isinstance(feed, dict) else None
    if not isinstance(feed, dict) or feed.get("listOrigin") != "degiro-screenshot" or not generation:
        return {"status": "waiting-for-screenshot", "lastCheckedAt": datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat(),
                "listUploadedAt": None, "total": 0, "incomplete": 0, "needsHelp": 0,
                "items": [], "readOnly": True, "degiroConnected": False}
    old = {x["isin"]: x for x in previous.get("items", []) if isinstance(x, dict) and x.get("isin")} if previous.get("listUploadedAt") == generation else {}
    items = []
    for product in feed.get("products", [])[:12]:
        if not isinstance(product, dict):
            continue
        isin = str(product.get("isin") or "").upper()
        quote = quotes.get(isin)
        item = examine(product, quote, now_ms, generation)
        before = old.get(isin, {})
        _retain_verified_terminal(item, before, quote)
        _retain_recent_issuer_leverage(item, quote, before, now_ms)
        _retain_historical_leverage_reference(item, before, now_ms)
        # Track each missing proof independently. A changing leverage clock
        # must not reset a persistent quote/identity fault and falsely close it.
        previous_counts = before.get("missingChecks")
        if not isinstance(previous_counts, dict):
            previous_counts = {code: int(before.get("consecutiveChecks", 0))
                               for code in before.get("missing", [])}
        counts = {code: min(99999, int(previous_counts.get(code, 0)) + 1)
                  for code in item["missing"] if item["state"] not in ('terminated', 'excluded-factor')}
        item["missingChecks"] = counts
        prior_since=before.get('missingSince') or {}
        stamp=datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat()
        item['missingSince']={code:prior_since.get(code) or stamp for code in counts}
        same = bool(set(before.get("missing", [])) & set(item["missing"]))
        item["consecutiveChecks"] = max(counts.values(), default=0)
        item["firstSeenAt"] = before.get("firstSeenAt") if same else datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat()
        item["needsKiHelp"] = item["consecutiveChecks"] >= 3 and bool(item["missing"])
        recovered = sorted(set(before.get('missing', [])) - set(item['missing']))
        if item['state'] == 'excluded-factor':
            # Exclusion is not recovery of the previously missing original data.
            item['lastRecoveredAt'] = None
            item['recoveredFields'] = []
        elif recovered and item['state'] != 'terminated':
            item['lastRecoveredAt'] = datetime.fromtimestamp(now_ms/1000, timezone.utc).isoformat()
            item['recoveredFields'] = recovered
        else:
            item['lastRecoveredAt'] = before.get('lastRecoveredAt')
            item['recoveredFields'] = before.get('recoveredFields', [])
        import product_repair_learning
        learning_before = before
        if not learning_before:
            prior = next((p for p in previous.get('items', []) if p.get('isin') == isin), {})
            remembered = prior.get('repairLearning') or {}
            learning_before = {'repairLearning': {k: remembered[k] for k in ('sourceSuccesses', 'history') if k in remembered}}
        item["repairLearning"] = product_repair_learning.update(item, learning_before, now_ms)
        items.append(item)
    checked = datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat()
    incomplete = sum(item["state"] == "incomplete" for item in items)
    market_closed_weekend = datetime.fromtimestamp(now_ms/1000, ZURICH).weekday() >= 5
    return {"status": "ok" if items else "waiting-for-screenshot", "lastCheckedAt": checked,
            "marketContext": ("DEGIRO-Wochenende · letzter datierter Handelswert bleibt historisch"
                              if market_closed_weekend else "Handelszeit und Quellzeit je Produkt getrennt prüfen"),
            "listUploadedAt": generation, "total": len(items), "incomplete": incomplete,
            "needsHelp": sum(item["needsKiHelp"] for item in items), "items": items,
            "terminated": sum(item["state"] == "terminated" for item in items),
            "excluded": sum(item["state"] == "excluded-factor" for item in items),
            "readOnly": True, "degiroConnected": False,
            "sourcePolicy": "issuer-and-existing-authorised-backups",
            "note": "Ausführbare DEGIRO-Kurse und Kontoverfügbarkeit sind nicht angeschlossen. Fehlende Nachweise sperren die Freigabe. Kein Echtgeldhandel."}


def init(conn):
    import broker_venue_evidence
    broker_venue_evidence.init(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_degiro_product_audit (
        id INTEGER PRIMARY KEY CHECK(id=1), payload JSONB NOT NULL,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")


def store(conn, feed, quotes, now_ms):
    import broker_venue_evidence
    feed = broker_venue_evidence.attach(conn, feed, datetime.fromtimestamp(now_ms/1000, timezone.utc))
    row = conn.execute("SELECT payload FROM bob_degiro_product_audit WHERE id=1").fetchone()
    report = build(feed, quotes, now_ms, row[0] if row else None)
    conn.execute("""INSERT INTO bob_degiro_product_audit(id,payload,checked_at)
        VALUES(1,%s::jsonb,NOW()) ON CONFLICT(id)
        DO UPDATE SET payload=EXCLUDED.payload, checked_at=EXCLUDED.checked_at""",
        (json.dumps(report, ensure_ascii=False),))
    import product_repair_learning
    product_repair_learning.install(report)
    return report


def read(conn, now_ms=None):
    now_ms = now_ms if now_ms is not None else datetime.now(timezone.utc).timestamp()*1000
    # Check against current list generation, not an old audit after a fresh upload.
    row = conn.execute("SELECT payload FROM bob_degiro_product_audit WHERE id=1").fetchone()
    feed = conn.execute("SELECT payload FROM bob_paper_products WHERE id=1").fetchone()
    if not feed or feed[0].get("listOrigin") != "degiro-screenshot":
        return build({}, {}, now_ms)
    generation = feed[0].get("listUploadedAt")
    if not row or row[0].get("listUploadedAt") != generation:
        return {"status": "checking-new-list", "total":len(feed[0].get("products") or []),
                "lastCheckedAt":None,"listUploadedAt":generation,
                "incomplete":None,"needsHelp":None, "items":[],
                "readOnly":True,"degiroConnected":False}
    report = dict(row[0])
    # Handset data is an independent, historical, non-trading display layer.
    # NEVER overwrite issuer quotes, audit missing-codes, or trade approval.
    try:
        import android_observations
        from copy import deepcopy
        seen = {p.get('isin') for p in feed[0].get('products', []) if isinstance(p, dict)}
        handset = android_observations.research_summary(
            conn, generation, seen, datetime.fromtimestamp(now_ms/1000, timezone.utc))
        if handset:
            report['items'] = [dict(deepcopy(item), handsetObservation=handset[item['isin']])
                               if item.get('isin') in handset and item.get('state') != 'terminated'
                               else item for item in report.get('items', [])]
            report['handsetResearchOnly'] = True
            report['handsetReadCount'] = len(handset)
    except Exception:
        # Missing read-only diagnostics may never block the genuine audit.
        report['handsetResearchUnavailable'] = True
    if not _recent(report.get("lastCheckedAt"), now_ms, REPORT_MAX_MS):
        report.update(status="stale", needsHelp=None, incomplete=None)
    else:
        import product_list_study
        report["priceStudy"] = product_list_study.summaries(conn, product_list_study.listed(feed[0]))
    return report


# Public health transports ONLY fixed diagnostics. Never include ISINs, product
# counts, prices, timestamps or the private screenshot list in a GitHub Issue.
PUBLIC_HELP_CODES = frozenset((
    "product-quote-evidence-missing",
    "product-leverage-clock-missing",
    "product-ko-validity-missing",
    "product-terms-evidence-missing",
))


def public_help_codes(report):
    """Strictly sanitized escalation for the independent GitHub watchdog.

    A stale check never proves that the underlying data problem disappeared.
    Closed markets alone, ended products, factors and mismatched futures are
    deliberate exclusions and not reparable missing-timestamp incidents.
    """
    if not isinstance(report, dict) or report.get("status") != "ok":
        return None  # No completed current audit: never certify recovery.
    codes = set()
    for item in report.get("items", [])[:12]:
        if not isinstance(item, dict) or item.get("needsKiHelp") is not True:
            continue
        missing = set(item.get("missing") or [])
        if missing & {"factor", "future", "terminated", "venue"}:
            continue
        if isinstance(item.get("missingChecks"), dict):
            missing = {code for code in missing if item["missingChecks"].get(code, 0) >= 3}
        if missing & {"quote", "quote-time"}:
            codes.add("product-quote-evidence-missing")
        if missing & {"leverage", "leverage-time"}:
            codes.add("product-leverage-clock-missing")
        if missing & {"ko", "ko-time"}:
            codes.add("product-ko-validity-missing")
        if missing & {"identity", "list-identity", "direction", "underlying", "currency", "strike", "ratio", "maturity"}:
            codes.add("product-terms-evidence-missing")
    return sorted(codes & PUBLIC_HELP_CODES)

