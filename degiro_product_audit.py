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
    "direction": "Richtung nicht übereinstimmend bestätigt",
    "underlying": "Gold-Spot-Basiswert oder Produktwährung nicht bestätigt",
    "factor": "Faktorprodukt ausgeschlossen",
    "future": "Anderer Basiswert/Future-Kontrakt: nicht als Spotprodukt freigegeben",
    "terminated": "Produkt vom Emittenten als beendet gemeldet",
    "quote": "Kein bestätigtes Geld-/Briefkurspaar des Emittenten",
    "quote-time": "Geld-/Briefkurs-Zeitstempel fehlen oder sind veraltet",
    "leverage": "Emittentenhebel fehlt",
    "leverage-time": "Unabhängiger aktueller Zeitstempel für den Emittentenhebel fehlt",
    "ko": "KO-Schwelle fehlt",
    "ko-time": "KO-Gültigkeitsnachweis fehlt oder ist älter als acht Stunden",
    "strike": "Basispreis fehlt",
    "ratio": "Bezugsverhältnis fehlt",
    "maturity": "Laufzeit oder ausdrücklich unbegrenzte Laufzeit fehlt",
    "market-closed": "Emittentenhandel momentan geschlossen",
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


def examine(product, quote, now_ms):
    """Return diagnostic evidence, not a new eligibility verdict."""
    isin = str(product.get("isin") or "").upper()
    direction = product.get("productDirection") or product.get("direction")
    quote = quote if isinstance(quote, dict) else {}
    metadata = quote.get("metadata") if isinstance(quote.get("metadata"), dict) else {}
    missing = []
    if not valid_isin(isin) or not product.get("isinConfirmed"):
        missing.append("identity")
    verified = quote.get("isin") == isin and quote.get("productVerified") is True
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
    if not _positive(quote.get("leverage")):
        missing.append("leverage")
    if not _recent(quote.get("leverageAt"), now_ms, QUOTE_MAX_MS):
        missing.append("leverage-time")
    if not _positive(metadata.get("ko") or quote.get("ko")):
        missing.append("ko")
    if not _dated_barrier(quote, metadata, now_ms):
        missing.append("ko-time")
    if not _positive(metadata.get("strike") or metadata.get("basisPrice") or quote.get("basisPrice")):
        missing.append("strike")
    if not _positive(metadata.get("ratio") or quote.get("ratio")):
        missing.append("ratio")
    if not (metadata.get("termsFixed") and (metadata.get("maturity") or metadata.get("expiry"))) and not (
            metadata.get("openEnded") is True or metadata.get("maturity") or
            metadata.get("expiry") or metadata.get("maturityDate")):
        missing.append("maturity")
    if quote.get("marketOpen") is not True:
        missing.append("market-closed")
    # No independent DEGIRO feed exists: even a perfect issuer audit can NEVER
    # validate actual DEGIRO executable quotes/tradability.
    codes = list(dict.fromkeys(missing))
    return {
        "isin": isin if valid_isin(isin) else None,
        "direction": direction if direction in ("LONG", "SHORT") else None,
        "state": "issuer-evidence-complete" if not codes else "incomplete",
        "missing": codes,
        "messages": [CODES[code] for code in codes],
        "quoteSourceAt": quote.get("bidAt") if "quote-time" not in codes else None,
        "leverageSourceAt": quote.get("leverageAt") if "leverage-time" not in codes else None,
        "source": str(quote.get("source") or "Emittenten- und Ersatzquellen")[:80],
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
