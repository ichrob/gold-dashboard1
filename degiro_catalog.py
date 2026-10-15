"""Read-only, unattended issuer candidate catalogue for Bob.

DEGIRO does not provide an authorised catalogue/account API. The seed identities
come ONLY from historical user-reviewed DEGIRO list screenshots. No current
DEGIRO tradability is inferred; all candidates remain external research and
cannot be inserted into the verified DEGIRO selection by this module.

Reuses Bobs existing issuer adapters; does not crawl DEGIRO, sign in, execute
orders, modify a manual list, or add an unlicensed feed.
"""
import copy
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from product_quotes import valid_isin

ZONE = ZoneInfo("Europe/Zurich")
# Historical user-reviewed DEGIRO list identities, including the BNP products
# confirmed in the 30 September/October screenshot records. This is NOT a
# current DEGIRO list and never grants broker tradability.
# Deliberately skip FG5NMF2 (issuer-confirmed ended) and FE4UF01 (factor).
# Future-linked FG309G0 is retained only as a separately excluded diagnostic.
SEEDS = (
    ("DE000FG4JXV7", "SHORT"),
    ("DE000FC1CHB7", "LONG"),
    ("DE000FG7EPT1", "SHORT"),
    ("DE000FG5GUT0", "LONG"),
    ("DE000PJ9NCK0", "LONG"),
    ("DE000PJ9NB98", "LONG"),
    ("DE000PG0XK25", "LONG"),
    ("DE000FG6XB39", "SHORT"),
    ("DE000FG7K3L2", "SHORT"),
    ("DE000FG309G0", "SHORT"),
)
LIMIT = 12
_LOCK = threading.Lock()
_THREAD = None
_CURRENT = {
    "status": "pending", "lastScanAt": None, "lastDay": None,
    "lastSession": None, "running": False, "errors": 0, "candidates": [],
    "excluded": [], "attempted": 0,
}


def _same_spot(metadata):
    return (isinstance(metadata, dict)
            and metadata.get("underlyingType") == "SPOT"
            and metadata.get("underlying") in ("Gold", "XAU/USD", "Gold Spot")
            and metadata.get("currency") == "EUR")


def normalize(isin, expected_direction, raw):
    """Never convert a research candidate into a verified DEGIRO listing."""
    if not valid_isin(isin) or expected_direction not in ("LONG", "SHORT"):
        raise ValueError("Invalid fixed issuer seed")
    raw = raw if isinstance(raw, dict) else {}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    response_isin = raw.get("isin")
    product_verified = raw.get("productVerified") is True and response_isin == isin
    if product_verified and (meta.get("status") != 1 or meta.get("type") == "FACTOR"):
        return None, dict(isin=isin, reason="Emittent meldet beendet oder nicht zugelassen")
    if product_verified and (not _same_spot(meta) or meta.get("direction") != expected_direction):
        return None, dict(isin=isin, reason="Basiswert/Währung/Richtung weicht ab; keine Gold-Spot-Kandidatur")
    # Fail closed: absence of a quote means unknown, not removal from DEGIRO.
    item = dict(isin=isin, direction=expected_direction,
        name=str(raw.get("name") or "Gold-Knock-out · historischer Listenfund")[:120],
        source="Historische DEGIRO-Listenbilder + Emittentenprüfung",
        sourceUrl=(raw.get("sourceUrl") if product_verified and
                   isinstance(raw.get("sourceUrl"), str) and
                   raw["sourceUrl"].startswith("https://") else None),
        issuerVerified=product_verified, issuerStatus="verified" if product_verified else "unconfirmed",
        issuerReason=str(raw.get("reason") or
                         ("Produktmerkmale beim Emittenten bestätigt" if product_verified
                          else "Emittentendaten zurzeit unvollständig"))[:220],
        quoteSourceAt=raw.get("quoteAt") if raw.get("found") is True and product_verified else None,
        issuerQuoteFresh=bool(product_verified and raw.get("found") is True
                              and raw.get("eligible") is True and raw.get("fresh") is True),
        degiroListed=None, degiroTradingEnabled=None,
        screenshotToday=False, liveApproved=False, eligibleForTop3=False)
    return item, None


def build(lookup, now=None):
    """One bounded issuer refresh, no credentials or public DEGIRO calls."""
    now = now or datetime.now(ZONE)
    candidates, excluded, errors = [], [], 0
    for isin, direction in SEEDS:
        if not valid_isin(isin):
            errors += 1
            continue
        try:
            response = lookup(isin)
            # Existing issuer adapters usually return a structured source failure
            # instead of raising. Treat it as degraded and retry: never label an
            # unverified/provider-disabled universe as a successful full scan.
            if not isinstance(response, dict) or any(response.get(key) for key in
                ("sourceFailure", "sourceDisabled", "quoteFailureCode", "sourceFailureCode")):
                errors += 1
            item, exclusion = normalize(isin, direction, response)
        except Exception:
            errors += 1
            item, exclusion = normalize(isin, direction, {})
            item["issuerReason"] = "Emittentenabruf momentan fehlgeschlagen; nicht als aktuell bestätigt"
        if exclusion:
            excluded.append(exclusion)
        elif item:
            candidates.append(item)
    return dict(status=("ok" if errors == 0 else "partial"), queriedAt=now.isoformat(),
                lastScanAt=now.isoformat(), lastDay=now.date().isoformat(),
                attempted=len(SEEDS), errors=errors,
                candidates=candidates[:LIMIT], excluded=excluded,
                sourceType="historic-user-list-plus-issuer-research",
                completeDegiroCatalog=False, degiroAccountConnected=False,
                canAutoImportVerifiedDegiroList=False, automaticOrders=False,
                warning=("Keine offizielle DEGIRO-API: Die frühere DEGIRO-Auswahl wird "
                         "automatisch bei Emittenten nachgeprüft. Das ist KEINE "
                         "aktuelle/vollständige DEGIRO-Produktliste. "
                         "Handelbarkeit, Broker-Suchbarkeit und Tageszugehörigkeit "
                         "müssen separat in DEGIRO bestätigt werden."))


def snapshot():
    with _LOCK:
        status=copy.deepcopy(_CURRENT)
    status.update(sourceType="historic-user-list-plus-issuer-research",
        completeDegiroCatalog=False, degiroAccountConnected=False,
        canAutoImportVerifiedDegiroList=False, automaticOrders=False,
        warning="Nur historische ISIN-Kandidaten und Emittentenrecherche; nicht die aktuelle DEGIRO-Produktliste.")
    return status


def session(now=None):
    now = (now or datetime.now(ZONE)).astimezone(ZONE)
    if now.weekday() >= 5 or not 8 <= now.hour < 21:
        return None
    return (now.date().isoformat(), "morning" if now.hour < 18 else "evening")


def _loop():
    import product_quotes
    last_retry = 0.
    while True:
        try:
            period=session()
            if period:
                with _LOCK:
                    is_current = _CURRENT["lastDay"] == period[0] and _CURRENT["lastSession"] == period[1] and _CURRENT["status"] == "ok"
                if not is_current and time.monotonic() >= last_retry:
                    with _LOCK:
                        _CURRENT["running"] = True
                    result=build(product_quotes.get_issuer_quote)
                    with _LOCK:
                        _CURRENT.update(result, lastSession=period[1], running=False)
                    print("BOB_ISSUER_CATALOG status="+result["status"]+" checked="+str(result["attempted"])+" errors="+str(result["errors"]),flush=True)
                    last_retry=time.monotonic()+(1800 if result["status"]=="partial" else 7200)
        except Exception as exc:
            with _LOCK:
                _CURRENT.update(status="error",running=False,errors=_CURRENT["errors"]+1)
            print("BOB_ISSUER_CATALOG error="+type(exc).__name__,flush=True)
            last_retry=time.monotonic()+1800
        time.sleep(300)


def start():
    global _THREAD
    if os.environ.get("BOB_AUTO_COLLECTION") != "1":
        return False
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            return True
        _THREAD=threading.Thread(target=_loop,daemon=True,name="bob-issuer-catalog")
        _THREAD.start()
    return True
