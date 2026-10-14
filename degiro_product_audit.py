"""Private, fail-closed audit of the ACTIVE screenshot product universe.

Runs alongside existing paper quote refreshes. Never queries DEGIRO, makes
orders, promotes research quotes to execution, or replaces screenshot lists.
All per-ISIN details stay in the authenticated private database/API.
"""
import json
import math
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
    "underlying": "Gold-Spot-Basiswert oder Produktwährung nicht bestätigt",
    "factor": "Faktorprodukt ausgeschlossen",
    "future": "Anderer Basiswert/Future-Kontrakt: nicht als Spotprodukt freigegeben",
    "venue": "Swiss DOTS ist ein eigener, exklusiver OTC-Handelsplatz. Ein Kurs dort ist kein DEGIRO-Ausführungsnachweis; nur eine gesondert belegte DEGIRO-Handelsroute zählt.",
    "terminated": "Produkt vom Emittenten als beendet gemeldet",
    "quote": "Ausführbarer Geld-/Briefnachweis fehlt; vorhandene Chartwerte stehen separat unter Quellenbeobachtungen",
    "quote-time": "Zeitbezug des ausführbaren Geld-/Briefnachweises fehlt oder ist veraltet",
    "leverage": "Emittentenhebel fehlt",
    "leverage-time": "Aktueller eigener oder eindeutig gemeinsamer Zeitbezug für den Emittentenhebel fehlt",
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
        ("SG-Chart", quote.get("chartEvidence")),
        ("Vorhandene Vergleichsquelle", quote.get("secondaryQuote")),
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
            "isinBound": row.get("isin") == isin if label == "Vorhandene Vergleichsquelle" else
                         quote.get("isin") == isin and quote.get("productVerified") is True,
            "venue": str(row.get("venue") or row.get("exchange") or "")[:80],
            "upstream": row.get("upstream") or ("SG" if chart else None),
            "researchOnly": True, "degiroExecutable": False,
            "note": ("Ein SG-Chartpunkt ist keine handelbare Geld-/Briefquote."
                     if chart else "Börsen-/Anbieterkurs ist kein verbindlicher DEGIRO-Ausführungskurs."),
        })
    return observations[:3]


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
    if secondary.get("upstream") == "SG" and (primary.get("upstream") == "SG" or "SG" in primary["source"]):
        result["reasons"].append("Zwei Abrufwege, aber derselbe SG-Kursgeber; keine unabhängige Preisbestätigung.")
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


def _shared_leverage(quote, isin, now_ms):
    """Accept the same verified observation series as the product cards."""
    ref = quote.get("issuerLeverageReference") or {}
    ctx = quote.get("sharedTimeContext") or {}
    obs = (quote.get("sharedValueObservations") or {}).get("Referenzhebel") or {}
    chart = quote.get("chartEvidence") or quote.get("nativeChartEvidence") or {}
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


def examine(product, quote, now_ms):
    """Return diagnostic evidence, not a new eligibility verdict."""
    isin = str(product.get("isin") or "").upper()
    direction = product.get("productDirection") or product.get("direction")
    quote = quote if isinstance(quote, dict) else {}
    metadata = quote.get("metadata") if isinstance(quote.get("metadata"), dict) else {}
    missing = []
    if not valid_isin(isin) or not product.get("isinConfirmed"):
        missing.append("list-identity")
    verified = quote.get("isin") == isin and quote.get("productVerified") is True
    # This exact ISIN is independently listed as SG's CHF Swiss DOTS
    # knock-out, not as an EUWAX/Frankfurt security. Swissquote describes
    # Swiss DOTS as its exclusive OTC platform. Even an issuer snapshot
    # cannot establish availability at DEGIRO.
    swiss_dots = (
        isin == "DE000FG8NHQ3" and verified
        and metadata.get("issuerExchangeCode") == "CBSW"
        and (quote.get("currency") or metadata.get("currency")) == "CHF"
    )
    if swiss_dots:
        missing.append("venue")
    if not verified:
        missing.append("identity") if "identity" not in missing else None
    if direction not in ("LONG", "SHORT") or metadata.get("direction", quote.get("direction")) != direction:
        missing.append("direction")
    if metadata.get("type") == "FACTOR":
        missing.append("factor")
    status = metadata.get("status")
    if (type(status) is int and (status & (2 | 8 | 16 | 32) or not status & 1)) or quote.get("terminated") is True:
        missing.append("terminated")
    if metadata.get("underlyingType") == "FUTURE":
        missing.append("future")
    if (metadata.get("underlyingType") != "SPOT" or
            metadata.get("underlying") not in ("XAU/USD", "Gold", "Gold Spot") or
            (quote.get("currency") or metadata.get("currency")) != "EUR"):
        missing.append("underlying")
    quote_ok = (verified and quote.get("found") is True and
                quote.get("priceKind") not in ("calculated", "issuer-chart") and
                quote.get("isExecutableQuote") is not False and
                _positive(quote.get("bid")) and _positive(quote.get("ask")) and
                quote["ask"] >= quote["bid"])
    if not quote_ok:
        missing.append("quote")
    # Do not use quoteAt as a substitute for independent bid/ask stamps.
    quote_times = (quote.get("bidAt"), quote.get("askAt"))
    if not all(_recent(at, now_ms, QUOTE_MAX_MS) for at in quote_times):
        missing.append("quote-time")
    shared_leverage = _shared_leverage(quote, isin, now_ms) if verified else None
    if not _positive(quote.get("leverage")) and not shared_leverage:
        missing.append("leverage")
    if not _recent(quote.get("leverageAt"), now_ms, QUOTE_MAX_MS) and not (
            shared_leverage and shared_leverage["current"]):
        missing.append("leverage-time")
    if not _positive(metadata.get("ko") or quote.get("ko")):
        missing.append("ko")
    if not _dated_barrier(quote, metadata, now_ms):
        missing.append("ko-time")
    if not _positive(metadata.get("strike") or metadata.get("basisPrice") or quote.get("basisPrice")):
        missing.append("strike")
    if not _positive(metadata.get("ratio") or quote.get("ratio")):
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
    elif quote.get("marketOpen") is not True:
        missing.append("market-status")
    # No independent DEGIRO feed exists: even a perfect issuer audit can NEVER
    # validate actual DEGIRO executable quotes/tradability.
    codes = list(dict.fromkeys(missing))
    observations = _observed_prices(quote, isin, now_ms) if verified else []
    cross_check = _market_cross_check(observations)
    return {
        "isin": isin if valid_isin(isin) else None,
        "direction": direction if direction in ("LONG", "SHORT") else None,
        "state": "issuer-evidence-complete" if not codes else "incomplete",
        "missing": codes,
        "messages": [CODES[code] for code in codes],
        "quoteSourceAt": quote.get("bidAt") if "quote-time" not in codes else None,
        "leverageObservation": shared_leverage,
        "leverageSourceAt": quote.get("leverageAt") if "leverage-time" not in codes else None,
        "source": str(quote.get("source") or "Emittenten- und Ersatzquellen")[:80],
        "sourceObservations": observations,
        "marketCrossCheck": cross_check,
        "researchLinks": _research_links(isin),
        "issuerVenue": "Swiss DOTS (CHF)" if swiss_dots else None,
        "venueEvidence": "https://www.finanzen.ch/derivate/de000fg8nhq3" if swiss_dots else None,
        "venueAction": ("Keine Swiss-DOTS-Quotierung als DEGIRO-Kurs verwenden. "
                        "Nur eine bei DEGIRO selbst nachgewiesene Handelsroute "
                        "oder ein dort handelbares EUR-Produkt zum Vergleich heranziehen."
                        if swiss_dots else None),
        "autoRecovery": "Vorhandene Emittenten- und Ersatzquellen werden bei der nächsten Aktualisierung erneut geprüft",
        "degiroVerified": False,
        "tradeApproved": False,
    }


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
        item = examine(product, quotes.get(isin), now_ms)
        before = old.get(isin, {})
        same = before.get("missing") == item["missing"] and item["missing"]
        item["consecutiveChecks"] = min(99999, int(before.get("consecutiveChecks",0)) + 1) if same else (1 if item["missing"] else 0)
        item["firstSeenAt"] = before.get("firstSeenAt") if same else datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat()
        item["needsKiHelp"] = item["consecutiveChecks"] >= 3 and bool(item["missing"])
        items.append(item)
    checked = datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat()
    incomplete = sum(item["state"] != "issuer-evidence-complete" for item in items)
    return {"status": "ok" if items else "waiting-for-screenshot", "lastCheckedAt": checked,
            "listUploadedAt": generation, "total": len(items), "incomplete": incomplete,
            "needsHelp": sum(item["needsKiHelp"] for item in items), "items": items,
            "readOnly": True, "degiroConnected": False,
            "sourcePolicy": "issuer-and-existing-authorised-backups",
            "note": "Ausführbare DEGIRO-Kurse und Kontoverfügbarkeit sind nicht angeschlossen. Fehlende Nachweise sperren die Freigabe. Kein Echtgeldhandel."}


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_degiro_product_audit (
        id INTEGER PRIMARY KEY CHECK(id=1), payload JSONB NOT NULL,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")


def store(conn, feed, quotes, now_ms):
    row = conn.execute("SELECT payload FROM bob_degiro_product_audit WHERE id=1").fetchone()
    report = build(feed, quotes, now_ms, row[0] if row else None)
    conn.execute("""INSERT INTO bob_degiro_product_audit(id,payload,checked_at)
        VALUES(1,%s::jsonb,NOW()) ON CONFLICT(id)
        DO UPDATE SET payload=EXCLUDED.payload, checked_at=EXCLUDED.checked_at""",
        (json.dumps(report, ensure_ascii=False),))
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
    if not _recent(report.get("lastCheckedAt"), now_ms, REPORT_MAX_MS):
        report.update(status="stale", needsHelp=None, incomplete=None)
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
    if not isinstance(report, dict) or report.get("status") not in ("ok", "stale"):
        return []
    codes = set()
    for item in report.get("items", [])[:12]:
        if not isinstance(item, dict) or item.get("needsKiHelp") is not True:
            continue
        missing = set(item.get("missing") or [])
        if missing & {"factor", "future", "terminated", "venue"}:
            continue
        if missing & {"quote", "quote-time"}:
            codes.add("product-quote-evidence-missing")
        if missing & {"leverage", "leverage-time"}:
            codes.add("product-leverage-clock-missing")
        if missing & {"ko", "ko-time"}:
            codes.add("product-ko-validity-missing")
        if missing & {"identity", "list-identity", "direction", "underlying", "strike", "ratio", "maturity"}:
            codes.add("product-terms-evidence-missing")
    return sorted(codes & PUBLIC_HELP_CODES)
