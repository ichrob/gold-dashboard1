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
import re
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
HISTORY_SAMPLE_LIMIT = 2  # Additional issuer requests per 5-minute cycle.
# Historical user-reviewed BNP identities, not a current broker/portfolio list.
HISTORICAL_BNP = frozenset(("DE000PJ9NCK0", "DE000PJ9NB98", "DE000PG0XK25"))
_LOCK = threading.Lock()
_THREAD = None
_RESEARCH_CURSOR = 0
_CURRENT = {
    "status": "pending", "lastScanAt": None, "lastDay": None,
    "lastSession": None, "running": False, "errors": 0, "candidates": [],
    "excluded": [], "attempted": 0, "scanHistory": [],
    "historyResearch": {"code":"NO_HISTORY", "available":0, "sampled":0, "items":[]},
}


def _same_spot(metadata):
    return (isinstance(metadata, dict)
            and metadata.get("underlyingType") == "SPOT"
            and metadata.get("underlying") in ("Gold", "XAU/USD", "Gold Spot")
            and metadata.get("currency") in ("EUR", "CHF"))


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


def _failed_source(response, raised=False):
    return (raised or not isinstance(response, dict)
            or any(response.get(key) for key in
                   ("sourceFailure", "sourceDisabled", "quoteFailureCode",
                    "sourceFailureCode")))


def _retryable_bnp_failure(isin, response, raised=False):
    if isin not in HISTORICAL_BNP or (isinstance(response, dict)
                                      and response.get("sourceDisabled")):
        return False
    if raised or not isinstance(response, dict) or response.get("sourceFailure"):
        return True
    code = str(response.get("quoteFailureCode") or
               response.get("sourceFailureCode") or "")
    if code == "STALE_OR_INVALID_SOURCE_TIME":
        # A stale original BNP bid/ask/leverage is not a healthy quote, but
        # the same authorised endpoint may deliver a newer issuer snapshot on
        # the next bounded request. Do not retry closed/ended products, a
        # different ISIN or a non-BNP research/model quote.
        return (response.get("isin") == isin
                and response.get("productVerified") is True
                and response.get("found") is True
                and response.get("marketOpen") is True
                and str(response.get("source") or "").startswith("BNP Paribas ·"))
    return code in ("CONNECTION", "MISSING_QUOTE_TIME") or code.startswith("HTTP_")


def build(lookup, now=None, *, retry_limit=0, retry_wait_seconds=16, sleeper=time.sleep):
    """One bounded issuer refresh, no credentials or public DEGIRO calls."""
    now = now or datetime.now(ZONE)
    candidates, excluded, errors = [], [], 0
    retry_attempts = retry_recovered = bnp_stale = 0
    source_checks = {
        "historicalBNP": dict(attempted=0, verified=0, datedFreshQuote=0, sourceErrors=0),
        "otherHistorical": dict(attempted=0, verified=0, datedFreshQuote=0, sourceErrors=0),
    }
    for isin, direction in SEEDS:
        group = source_checks["historicalBNP" if isin in HISTORICAL_BNP else "otherHistorical"]
        group["attempted"] += 1
        had_error = False
        response = {}
        if not valid_isin(isin):
            errors += 1
            group["sourceErrors"] += 1
            continue
        try:
            response = lookup(isin)
            raised = False
        except Exception:
            response, raised = {}, True
        # BNP responses are cached for 15 seconds. Retry only transient failures,
        # at most retry_limit products per scan, after crossing that cache window.
        # The repeated response is accepted only after the normal source checks.
        if (_retryable_bnp_failure(isin, response, raised)
                and retry_attempts < retry_limit):
            retry_attempts += 1
            sleeper(retry_wait_seconds)
            try:
                response = lookup(isin)
                raised = False
            except Exception:
                response, raised = {}, True
            if not _failed_source(response, raised):
                retry_recovered += 1
        had_error = _failed_source(response, raised)
        if isin in HISTORICAL_BNP and isinstance(response, dict) and response.get("quoteFailureCode") == "STALE_OR_INVALID_SOURCE_TIME":
            # Diagnostic only: a delayed issuer clock is NOT cured by a new
            # local fetch time. Always preserve original issuer timestamps.
            bnp_stale += 1
        if had_error:
            errors += 1
        item, exclusion = normalize(isin, direction, response)
        if raised and item:
            item["issuerReason"] = "Emittentenabruf momentan fehlgeschlagen; nicht als aktuell bestätigt"
        if had_error:
            group["sourceErrors"] += 1
        if (isinstance(response, dict) and response.get("productVerified") is True
                and response.get("isin") == isin):
            group["verified"] += 1
            # Count original issuer clocks only, never chart/research observations
            # as executable DEGIRO quotes. Existing eligible/fresh gates stay.
            if (not had_error and response.get("found") is True
                    and response.get("eligible") is True and response.get("fresh") is True
                    and all(isinstance(response.get(k), str)
                            and re.search(r"(?:Z|[+-]\d{2}:\d{2})$", response[k])
                            for k in ("bidAt", "askAt", "leverageAt", "snapshotAt"))):
                group["datedFreshQuote"] += 1
        if exclusion:
            excluded.append(exclusion)
        elif item:
            candidates.append(item)
    return dict(status=("ok" if errors == 0 else "partial"), queriedAt=now.isoformat(),
                lastScanAt=now.isoformat(), lastDay=now.date().isoformat(),
                attempted=len(SEEDS), errors=errors, sourceChecks=source_checks,
                retryAttempts=retry_attempts, retryRecovered=retry_recovered,
                bnpStaleSourceClocks=bnp_stale,
                candidates=candidates[:LIMIT], excluded=excluded,
                sourceType="historic-user-list-plus-issuer-research",
                completeDegiroCatalog=False, degiroAccountConnected=False,
                canAutoImportVerifiedDegiroList=False, automaticOrders=False,
                warning=("Keine offizielle DEGIRO-API: Die frühere DEGIRO-Auswahl wird "
                         "automatisch bei Emittenten nachgeprüft. Das ist KEINE "
                         "aktuelle/vollständige DEGIRO-Produktliste. "
                         "Handelbarkeit, Broker-Suchbarkeit und Tageszugehörigkeit "
                         "müssen separat in DEGIRO bestätigt werden."))



def study_history(history, lookup, offset=0, limit=HISTORY_SAMPLE_LIMIT):
    """Issuer-check a rotating, bounded subset of historically traded instruments."""
    history = history if isinstance(history, dict) else {}
    records = history.get('items')
    records = records if isinstance(records, list) else []
    historic = {isin for isin, _ in SEEDS}
    eligible = [x for x in records[:24] if isinstance(x, dict)
                and valid_isin(x.get('isin')) and x.get('direction') in ('LONG', 'SHORT')
                and x['isin'] not in historic and x.get('brokerHistoricallyTransacted') is True
                and x.get('eligibleForTop3') is False]
    n = len(eligible)
    if not n:
        return dict(code=history.get('code','NO_HISTORY'), available=0, sampled=0,
                    items=[], historyComplete=False, tradeApproved=False)
    picked = (eligible[offset%n:] + eligible[:offset%n])[:max(0,min(limit,HISTORY_SAMPLE_LIMIT))]
    observed = []
    for x in picked:
        isin, side = x['isin'], x['direction']
        try:
            quote = lookup(isin)
        except Exception:
            quote = {}
        quote = quote if isinstance(quote, dict) else {}
        meta = quote.get('metadata') if isinstance(quote.get('metadata'),dict) else {}
        verified = (quote.get('isin') == isin and quote.get('productVerified') is True
                    and meta.get('status') == 1 and meta.get('type') != 'FACTOR'
                    and _same_spot(meta) and meta.get('direction') == side)
        observed.append({
            'isin':isin, 'direction':side, 'name':str(x.get('name') or '')[:120],
            'lastTradeDate':x.get('lastTradeDate'),
            'brokerHistoricallyTransacted':True, 'issuerIdentityMatched':bool(verified),
            'issuerChecked':True, 'researchOnly':True, 'currentlyDegiroListed':None,
            'originalDegiroQuoteVerified':False, 'liveApproved':False,
            'screenshotToday':False, 'eligibleForTop3':False, 'tradeApproved':False})
    return dict(code=history.get('code','HISTORICAL_PARTIAL'),available=n,
                sampled=len(observed),items=observed,
                historyComplete=history.get('historyComplete') is True,
                completeDegiroCatalog=False, tradeApproved=False,
                note='Historische Transaktionen sind kein Nachweis aktueller DEGIRO-Handelbarkeit.')


def diagnostics(now=None):
    now = now or datetime.now(ZONE)
    report = snapshot()
    events = report.get('scanHistory') or []
    recent = report.get('lastScanAt')
    age = None
    if isinstance(recent,str):
        try:
            age = max(0,(now-datetime.fromisoformat(recent)).total_seconds())
        except (ValueError,TypeError):
            pass
    active = session(now) is not None
    elapsed = events[-1].get('elapsedSeconds') if events else None
    return dict(targetSeconds=300, scanCountObserved=len(events),
                lastScanAt=recent, lastScanAgeSeconds=round(age) if age is not None else None,
                recentIntervalsSeconds=[e['elapsedSeconds'] for e in events[-6:]
                                        if e.get('elapsedSeconds') is not None],
                latestOutcome=report.get('status'), latestErrors=report.get('errors'),
                workerStarted=bool(_THREAD and _THREAD.is_alive()),
                activeMarketSession=active, sessionMode='weekday' if active else 'paused',
                healthyCadenceProven=bool(active and len(events)>=2
                                       and elapsed is not None and elapsed <= 480
                                       and age is not None and age <= 480),
                historyAvailable=(report.get('historyResearch') or {}).get('available',0),
                historySampled=(report.get('historyResearch') or {}).get('sampled',0),
                historySourceCode=(report.get('historyResearch') or {}).get('code'),
                completeDegiroCatalog=False, tradeApproved=False)



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
    if now.weekday() >= 5 or not 8 <= now.hour < 22:
        return None
    return (now.date().isoformat(), "morning" if now.hour < 18 else "evening")


def _loop():
    import product_quotes
    import snaptrade_bridge
    global _RESEARCH_CURSOR
    last_retry = 0.
    while True:
        try:
            period=session()
            if period:
                # A successful snapshot is not a session-long health guarantee.
                # Continue checking after recovery so a later issuer outage is
                # detected without requiring a restart or a session change.
                if time.monotonic() >= last_retry:
                    with _LOCK:
                        _CURRENT["running"] = True
                    result=build(product_quotes.get_issuer_quote, retry_limit=3,
                                 retry_wait_seconds=16)
                    # Historical matches are privately derived from already saved
                    # trades; at most two additional issuer lookups, no broker API.
                    research=study_history(snaptrade_bridge.historical_gold_candidates(),
                                           product_quotes.get_issuer_quote, _RESEARCH_CURSOR)
                    _RESEARCH_CURSOR+=research['sampled']
                    with _LOCK:
                        prior=_CURRENT.get('scanHistory') or []
                        previous=prior[-1]['at'] if prior else None
                        at=datetime.now(ZONE)
                        elapsed=None
                        if previous:
                            try:
                                elapsed=round((at-datetime.fromisoformat(previous)).total_seconds())
                            except ValueError:
                                pass
                        history=(prior+[{'at':at.isoformat(),'elapsedSeconds':elapsed,
                                         'outcome':result['status'],'errors':result['errors']}])[-12:]
                        _CURRENT.update(result, lastSession=period[1], running=False,
                                        scanHistory=history, historyResearch=research)
                    bnp = result["sourceChecks"]["historicalBNP"]
                    other = result["sourceChecks"]["otherHistorical"]
                    print("BOB_ISSUER_CATALOG status="+result["status"]
                          +" checked="+str(result["attempted"])+" errors="+str(result["errors"])
                          +" bnpChecked="+str(bnp["attempted"])
                          +" bnpVerified="+str(bnp["verified"])
                          +" bnpDatedQuotes="+str(bnp["datedFreshQuote"])
                          +" bnpErrors="+str(bnp["sourceErrors"])
                          +" otherErrors="+str(other["sourceErrors"])
                          +" retries="+str(result["retryAttempts"])
                          +" recovered="+str(result["retryRecovered"])
                          +" bnpStaleClocks="+str(result["bnpStaleSourceClocks"]),flush=True)
                    # Recheck the fixed historical ISIN set every five minutes
                    # during the existing weekday session only. This is issuer
                    # research, NOT a SnapTrade/DEGIRO holdings poll, tradeability
                    # proof, or permission to promote candidates into Top 3.
                    last_retry=time.monotonic()+300
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
