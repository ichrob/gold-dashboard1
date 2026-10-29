import sys
if __name__ == '__main__':
    sys.modules.setdefault('server', sys.modules[__name__])
import candle_reliability
import bob_passkey
import bob_handy_landing
import bob_app_links
import degiro_readonly
import degiro_preflight
import degiro_sync
import degiro_sandbox
import degiro_sandbox_panel
import snaptrade_bridge
import snaptrade_panel
import vollautomatisch_panel
import vollautomatisch_engine
import strategy_lab
import strategy_lab_background
import degiro_catalog
import degiro_product_audit_panel
import broker_bridge
import trade_email_panel
import trade_review_panel
import intraday_comparison
import os
import base64
import hmac
import json
import math
import time
import threading
import uuid
import bob_auth
import bob_mcp
import bob_diagnostics
import bob_oauth
import bob_recovery
import bob_self_healing
import bob_problems
import bob_area_checks
import bob_repair_store
import bob_assistance
import auto_collection
import background_push
import ocr_assets
import product_quotes
import future_chart
import market_cards
import candle_shadow
import spot_daily_change
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import economic_calendar
from datetime import datetime, timezone
import technical_candles
import gold_research
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from bob_http import BobHTTPServer

USER = os.environ.get("BOB_USER", "")
PASSWORD = os.environ.get("BOB_PASSWORD", "")
PUSH_SERVICE_URL = os.environ.get("PUSH_SERVICE_URL", "")
PUSH_SERVICE_TOKEN = os.environ.get("PUSH_SERVICE_TOKEN", "")
SIGNAL_WORKER_TOKEN = os.environ.get("SIGNAL_WORKER_TOKEN", "")


def read_private_report_for_mcp(path, query=None):
    """Fetch the existing internal report without adding a public database port."""
    if path not in ("/product-audit", "/diagnostics", "/simulation-status", "/comparison-status", "/candidate-proofs", "/signal-history", "/push-delivery-history", "/storage-health", "/risk-paper", "/android-read-status", "/android-diagnostic-status"):
        raise ValueError("Unknown report")
    if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
        raise RuntimeError("Private audit unavailable")
    base = PUSH_SERVICE_URL.rstrip("/")
    if not base.startswith(("https://", "http://")):
        base = "https://" + base
    if query is not None:
        if path not in ('/signal-history', '/push-delivery-history'): raise ValueError('Query not supported')
        from urllib.parse import urlencode
        if path == '/signal-history':
            from signal_history import arguments
        else:
            from push_delivery_history import arguments
        path += '?' + urlencode(arguments(query))
    request = Request(base + path, method="GET",
                      headers={"X-Bob-Push-Token": PUSH_SERVICE_TOKEN,
                               "Accept": "application/json"})
    with urlopen(request, timeout=8) as response:
        body = response.read(2 * 1024 * 1024 + 1)
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("Private audit too large")
    result = json.loads(body)
    if not isinstance(result, dict):
        raise ValueError("Private audit unavailable")
    return result


def remote_push_rpc(name, args):
    import remote_push
    remote_push.arguments(name,args)
    if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:raise RuntimeError('Private push unavailable')
    base=PUSH_SERVICE_URL.rstrip('/')
    if not base.startswith(('https://','http://')):base='https://'+base
    request=Request(base+'/remote-push',data=json.dumps({'name':name,'arguments':args}).encode(),
                    headers={'X-Bob-Push-Token':PUSH_SERVICE_TOKEN,'Content-Type':'application/json'},method='POST')
    with urlopen(request,timeout=8) as response:result=json.loads(response.read(65536))
    return result


def android_diagnostic_rpc(payload, remote=False):
    if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:raise RuntimeError('Diagnostics unavailable')
    base=PUSH_SERVICE_URL.rstrip('/')
    if not base.startswith(('https://','http://')):base='https://'+base
    request=Request(base+('/android-remote' if remote else '/android-diagnostics'),data=json.dumps(payload).encode(),method='POST',
        headers={'X-Bob-Push-Token':PUSH_SERVICE_TOKEN,'Content-Type':'application/json'})
    with urlopen(request,timeout=8) as response:return json.loads(response.read(200000))


def read_private_product_audit_for_mcp():
    return read_private_report_for_mcp('/product-audit')


def read_diagnostics_for_mcp():
    # Cached observations only: do not call service_health (it observes/repairs),
    # live_bundle (fetches prices), demos, simulations or notification senders.
    def collection():
        value = auto_collection.status()
        return {**bob_diagnostics.fields(value, ('enabled','running','state','lastCycleAt','updateIntervalSeconds','sessionMode')),
                'feed':bob_diagnostics.fields(value.get('cfdFeed'), ('state','lastCheckedAt','sourceAgeSeconds')),
                'cycleCadence':bob_diagnostics.collection_cycle_snapshot(value.get('cycleCadence'))}
    def research():
        return bob_diagnostics.research_snapshot(gold_research.snapshot())
    def problems():
        value = bob_problems.snapshot()
        return {**bob_diagnostics.fields(value, ('status','count','checkedAt')),
                'items':[bob_diagnostics.fields(item, ('code','number','state','updatedAt','title','reason','message','kiStatus','kiStatusLabel'))
                         for item in value.get('problems', [])[:100]]}
    report = bob_diagnostics.collect({
        'market':lambda:bob_diagnostics.market_snapshot(_live_cache, _live_cache_at),
        'analysis':bob_diagnostics.analysis_snapshot,
        'degiroSync':lambda:bob_diagnostics.broker_sync_snapshot(degiro_sync.status()),
        'products':lambda:bob_diagnostics.product_snapshot(read_private_product_audit_for_mcp()),
        'runtime':lambda:{'build':os.environ.get('RENDER_GIT_COMMIT','unknown'),
            'uptimeSeconds':round(time.monotonic()-PROCESS_STARTED_MONOTONIC),
            'sessionMode':background_push.degiro_session(),
            'snaptradePersonal':snaptrade_bridge.diagnostics(),
            'issuerCatalog':degiro_catalog.diagnostics(),
            'diagnosticDelivery':__import__('diagnostic_history').status(),
            'fibonacci':bob_diagnostics.fields(FIB_MONITOR_HEALTH,('configured','status','lastCheckedAt','lastSuccessAt'))},
        'selfHealing':bob_self_healing.diagnostics_snapshot,
        'collection':collection,
        'background':background_health,
        'sourceReliability':candle_reliability.snapshot,
        'readAccessCoverage':lambda:bob_diagnostics.read_access_coverage(
            json.loads((BASE_DIR / 'Besser_werden/lesezugriff_100_status.json').read_text(
                encoding='utf-8'))),
        'strategyResearch':lambda:bob_diagnostics.fields(strategy_lab_background.status(),
            ('enabled','running','phase','lastSuccessAt','lastAttemptAt','lastRunDay','error')),
        'storage':lambda:read_private_report_for_mcp('/storage-health'),
        'androidTelemetry':lambda:read_private_report_for_mcp('/android-diagnostic-status'),
        'androidReader':lambda:read_private_report_for_mcp('/android-read-status'),
        'simulationAndPush':lambda:read_private_report_for_mcp('/simulation-status'),
        'riskPaper':lambda:bob_diagnostics.risk_paper_snapshot(
            read_private_report_for_mcp('/risk-paper')),
        # Stored comparisons are isolated from the live heartbeat so either
        # report can fail truthfully without erasing the other observation.
        'comparisonEvidence':lambda:read_private_report_for_mcp('/comparison-status'),
        # Small private 24h window; the dedicated reader can paginate prior days.
        'pushDeliveries':lambda:read_private_report_for_mcp('/push-delivery-history'),
        'research':research,
        'problems':problems,
    })
    comparison = report['areas'].get('comparisonEvidence') or {}
    if isinstance(comparison.get('comparisonHealth'), dict):
        report['areas']['comparisonHealth'] = comparison['comparisonHealth']
    if isinstance(comparison.get('entryBlockEvidence'), dict):
        report['areas']['entryBlockEvidence'] = comparison['entryBlockEvidence']
    report['areas']['newFeatures'] = bob_diagnostics.new_feature_snapshot(
        report['areas'], mobile_asset_loaded=bool(BOB_UNIFIED_WORKSPACE_JS))
    report['areas']['simulationEvidence'] = bob_diagnostics.simulation_evidence_snapshot(
        report['areas'].get('simulationAndPush'))
    report['areas']['diagnosticTriage'] = bob_diagnostics.triage_snapshot(report['areas'])
    report['areas']['operationsSummary'] = __import__('bob_operations').snapshot(report)
    report['summary'] = bob_diagnostics.summary(report['areas'])
    return report

FIB_MONITOR_HEALTH = {"configured": bool(PUSH_SERVICE_URL and PUSH_SERVICE_TOKEN), "status": "starting", "lastCheckedAt": None, "lastSuccessAt": None}

PROCESS_STARTED_AT = time.time()
PROCESS_STARTED_MONOTONIC = time.monotonic()
PROCESS_ID = uuid.uuid4().hex[:12]
_FIB_THREAD = None
_FIB_START_LOCK = threading.Lock()

def ensure_fibonacci_monitor():
    """Restart a terminated worker, never duplicate a running monitor."""
    global _FIB_THREAD
    if not FIB_MONITOR_HEALTH['configured']:
        return
    with _FIB_START_LOCK:
        if _FIB_THREAD is None or not _FIB_THREAD.is_alive():
            FIB_MONITOR_HEALTH.update(status='starting', lastCheckedAt=None, lastSuccessAt=None)
            _FIB_THREAD = threading.Thread(target=fibonacci_monitor_loop, name='bob-fibonacci', daemon=True)
            _FIB_THREAD.start()

def service_health():
    """Liveness stays independent of providers; report readiness honestly."""
    collection = auto_collection.health()
    import auxiliary_workers
    auxiliary = auxiliary_workers.health() if collection.get("enabled") else {}
    background = background_health()
    feed = collection.get('cfdFeed') or {}
    reasons = []
    session = background_push.degiro_session()
    normal_feed = feed.get('state') in (('current', 'closed', 'paused') if session == 'weekend' else ('current', 'closed'))
    # Night samples retain original source time; 120-second intraday freshness
    # must not turn the deliberate five-minute night cadence into an outage.
    sampled_at = feed.get('lastCheckedAt')
    nightly_feed = (session == 'night' and feed.get('state') == 'stale'
                    and isinstance(feed.get('sourceAgeSeconds'), (int,float))
                    and 0 <= feed['sourceAgeSeconds'] <= 420
                    and isinstance(sampled_at, (int,float))
                    and 0 <= time.time() - sampled_at <= 650)
    if collection.get('enabled') and (not collection.get('running') or not (normal_feed or nightly_feed)):
        reasons.append('market-feed-not-current')
    if FIB_MONITOR_HEALTH['configured'] and background['status'] != 'ok':
        reasons.append('background-not-current')
    import repair_supervision, product_source_recovery
    supervision = repair_supervision.health(_HEALING_WATCH_THREAD is not None and _HEALING_WATCH_THREAD.is_alive())
    if supervision['state'] in ('stopped', 'stalled'):
        reasons.append('repair-watch-stalled')
    result = {'status': 'degraded' if reasons else 'ok', 'service': 'bob',
            'build': os.environ.get('RENDER_GIT_COMMIT'),
            'runtime': {'processId': PROCESS_ID, 'startedAt': datetime.fromtimestamp(PROCESS_STARTED_AT, timezone.utc).isoformat(),
                        'uptimeSeconds': max(0, int(time.monotonic()-PROCESS_STARTED_MONOTONIC))},
            'ready': not reasons, 'reasons': reasons,
            'fibonacciMonitor': dict(FIB_MONITOR_HEALTH), 'automaticCollection': collection,
            'auxiliaryWorkers': auxiliary, 'repairSupervision': supervision,
            'sourceRecovery': product_source_recovery.health(),
            'marketRecovery': __import__('market_recovery').health(),
            'strategyResearch': strategy_lab_background.status(), 'assistanceCodes': bob_assistance.pending_codes()}
    bob_self_healing.observe(result)
    result["repairPendingCodes"] = bob_self_healing.pending_codes()
    return result


_HEALING_WATCH_THREAD = None
_HEALING_WATCH_LOCK = threading.Lock()


def maintain_known_workers():
    """Safe repairs only: existing idempotent starts, never trade or config changes."""
    import auxiliary_workers
    candle_reliability.start()
    snaptrade_bridge.start()
    auxiliary_workers.maintain(auto_collection.enabled())
    collection_state = auto_collection.health()
    bob_self_healing.restart_worker(
        "market-worker-stopped",
        bool(collection_state.get("enabled") and not collection_state.get("running")),
        auto_collection.start)
    research_state = strategy_lab_background.status()
    bob_self_healing.restart_worker(
        "research-worker-stopped",
        bool(PUSH_SERVICE_URL and PUSH_SERVICE_TOKEN and not research_state.get("running")),
        lambda: strategy_lab_background.start(fetch_technical_history, mark_bar_state))
    bob_self_healing.restart_worker(
        "background-worker-stopped",
        bool(FIB_MONITOR_HEALTH["configured"] and
             (_FIB_THREAD is None or not _FIB_THREAD.is_alive())),
        ensure_fibonacci_monitor)


def _healing_watch_loop():
    # Avoid classifying cold-start warmup as a repair incident.
    time.sleep(90)
    while True:
        try:
            maintain_known_workers()
            import market_recovery
            market_recovery.tick()
            observed_health = service_health()
            import diagnostic_history
            diagnostic_history.health(observed_health)
            import repair_supervision
            repair_supervision.completed()
        except Exception as exc:
            print("BOB_HEALING_WATCH error=" + type(exc).__name__, flush=True)
        time.sleep(30)


def start_healing_watch():
    global _HEALING_WATCH_THREAD
    with _HEALING_WATCH_LOCK:
        if _HEALING_WATCH_THREAD is None or not _HEALING_WATCH_THREAD.is_alive():
            _HEALING_WATCH_THREAD = threading.Thread(
                target=_healing_watch_loop, name="bob-self-healing-watch",
                daemon=True)
            _HEALING_WATCH_THREAD.start()


def background_health():
    """Only a completed cycle proves that background monitoring works."""
    state = dict(FIB_MONITOR_HEALTH)
    last = state.get("lastSuccessAt")
    age = max(0, int(time.time()) - last) if last is not None else None
    paused = bool(state["configured"] and background_push.gold_weekend_seconds_remaining()
                  and state["status"] == "paused" and _FIB_THREAD and _FIB_THREAD.is_alive())
    normal_interval = state.get('expectedCycleSeconds', 30)
    # Five-minute off-hours monitoring is healthy when the documented schedule is met.
    allowed_age = max(120, 2 * normal_interval + 60)
    healthy = paused or bool(state["configured"] and age is not None and age <= allowed_age
                   and state["status"] in ("active", "idle", "checking"))
    return {"status": "ok" if healthy else "unavailable", "service": "bob-background",
            "monitorStatus": state["status"], "lastSuccessAt": last, "ageSeconds": age}


BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "Bob.html"
SW_PATH = BASE_DIR / "sw.js"
MANIFEST_PATH = BASE_DIR / "manifest.json"
ICON_PATH = BASE_DIR / "icon.svg"

# Load static shell assets once at startup. The request handler serves these
# bytes directly; keeping the load explicit prevents runtime NameError failures.
HTML = HTML_PATH.read_bytes() if HTML_PATH.exists() else b""
HTML = HTML.replace(b"</body>", auto_collection.PANEL.encode('utf-8')+b"</body>")
HTML = HTML.replace(b"</body>", candle_shadow.PANEL.encode('utf-8')+b"</body>")
HTML = HTML.replace(b"</body>", b'<script src="/product_evidence_contract.js"></script><script src="/bob_audit_read_pool.js"></script><script src="/degiro_handoff.js"></script><script src="/degiro_portfolio_store.js"></script><script src="/degiro_report_import.js"></script><script src="/degiro_all_products.js"></script><script src="/broker_candidate_pools.js"></script><script src="/degiro_browser_bridge.js"></script><script src="/degiro_android_bridge.js"></script><script src="/degiro_morning_reader.js"></script></body>')
HTML = HTML.replace(b"</body>", degiro_sandbox_panel.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", snaptrade_panel.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", vollautomatisch_panel.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", trade_email_panel.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", trade_review_panel.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", bob_self_healing.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", bob_problems.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", bob_area_checks.PANEL.encode("utf-8")+b"</body>")
HTML = HTML.replace(b"</body>", degiro_product_audit_panel.PANEL.encode("utf-8")+b"</body>")
# Standalone presentation shell (separate from the legacy monolith).
HTML = HTML.replace(b"</body>", b'<script src="/bob_unified_workspace.js"></script></body>')
SW = SW_PATH.read_bytes() if SW_PATH.exists() else None
MANIFEST = MANIFEST_PATH.read_bytes() if MANIFEST_PATH.exists() else None
ICON = ICON_PATH.read_bytes() if ICON_PATH.exists() else None
# Legacy push module fallback. Product import uses its tracked source file below
# so the tested and served implementation cannot diverge after a deployment.
PUSH_MANAGER_JS = (BASE_DIR / "push_manager.js").read_text(encoding="utf-8")
DEGIRO_HANDOFF_JS = (BASE_DIR / "degiro_handoff.js").read_text(encoding="utf-8")
PRODUCT_EVIDENCE_CONTRACT_JS = (BASE_DIR / "product_evidence_contract.js").read_text(encoding="utf-8")
BOB_AUDIT_READ_POOL_JS = (BASE_DIR / "bob_audit_read_pool.js").read_text(encoding="utf-8")
BOB_UNIFIED_WORKSPACE_JS = (BASE_DIR / "bob_unified_workspace.js").read_text(encoding="utf-8")
DEGIRO_PORTFOLIO_STORE_JS = (BASE_DIR / "degiro_portfolio_store.js").read_text(encoding="utf-8")
DEGIRO_BROWSER_BRIDGE_JS = (BASE_DIR / "degiro_browser_bridge.js").read_text(encoding="utf-8")
DEGIRO_MORNING_READER_JS = (BASE_DIR / "degiro_morning_reader.js").read_text(encoding="utf-8")
DEGIRO_ANDROID_BRIDGE_JS = (BASE_DIR / "degiro_android_bridge.js").read_text(encoding="utf-8")
DEGIRO_BROWSER_USERSCRIPT = (BASE_DIR / "bob_degiro_export.user.js").read_text(encoding="utf-8")
DEGIRO_REPORT_IMPORT_JS = (BASE_DIR / "degiro_report_import.js").read_text(encoding="utf-8")
DEGIRO_ALL_PRODUCTS_JS = (BASE_DIR / "degiro_all_products.js").read_text(encoding="utf-8")
BROKER_CANDIDATE_POOLS_JS = (BASE_DIR / "broker_candidate_pools.js").read_text(encoding="utf-8")
DEGIRO_ASSISTANT_JS = (BASE_DIR / "degiro_assistant.js").read_text(encoding="utf-8")
UPSTREAM_TIMEOUT = 4
FRESH_MAX_AGE = 180
LIVE_CACHE_TTL = 20
FX_CACHE_TTL = 30
_live_cache = None
_live_cache_at = 0.0
_fx_cache = {"EUR": None, "CHF": None}
_fx_cache_at = 0.0
_fx_meta = {}
_live_lock = threading.Lock()

def fetch_json(url, retries=2, user_agent="Bob/1.1", timeout=None):
    last_error = None
    for attempt in range(retries + 1):
        req = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=UPSTREAM_TIMEOUT if timeout is None else timeout) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Upstream HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = RuntimeError(f"Upstream HTTP {exc.code} ({url})")
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = RuntimeError(f"Upstream nicht erreichbar oder ungültige JSON-Antwort ({url})")
        if attempt < retries:
            time.sleep(0.6 * (attempt + 1))
    raise last_error or RuntimeError(f"Upstream nicht erreichbar ({url})")

def fetch_json_post(url, payload, retries=1, user_agent="Bob/1.1"):
    last_error = None
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    for attempt in range(retries + 1):
        req = Request(
            url,
            data=body,
            method="POST",
            headers={"User-Agent": user_agent, "Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=UPSTREAM_TIMEOUT) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Upstream HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = RuntimeError(f"Upstream HTTP {exc.code} ({url})")
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = RuntimeError(f"Upstream nicht erreichbar oder ungültige JSON-Antwort ({url})")
        if attempt < retries:
            time.sleep(0.4 * (attempt + 1))
    raise last_error or RuntimeError(f"Upstream nicht erreichbar ({url})")

def enrich_degiro_product(isin):
    return product_quotes.get_quote(isin)

def fetch_goldprice_bars(interval, days):
    """Best-effort genuine XAU/USD spot OHLC; empty means unavailable on current API tier."""
    end = datetime.now(timezone.utc)
    start = datetime.fromtimestamp(end.timestamp() - days * 86400, timezone.utc)
    url = (
        "https://api.goldprice.dev/v1/bars?symbol=XAU-USD-SPOT"
        f"&interval={interval}&from={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&to={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=10000"
    )
    try:
        payload = fetch_json(url, retries=1, user_agent="Bob/1.1")
        out = []
        for b in payload.get("bars", []) if isinstance(payload, dict) else []:
            try:
                ts = datetime.fromisoformat(str(b["bar_start"]).replace("Z", "+00:00")).timestamp()
                o, h, low, close = [float(b[k]) for k in ("open", "high", "low", "close")]
                if not all(v > 0 and v == v for v in (o, h, low, close)): continue
                out.append({"openTime": int(ts*1000), "open": o, "high": h, "low": low, "close": close, "isOpen": not bool(b.get("is_closed", False))})
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        out.sort(key=lambda x: x["openTime"])
        return out
    except Exception:
        return []
def iso_age_seconds(value):
    if not value:
        return None
    try:
        stamp = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(stamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, time.time() - dt.timestamp())
    except (TypeError, ValueError):
        return None

def dated_spot_row(row, now=None):
    """Read a price observation time, never a response-generation timestamp."""
    now = time.time() if now is None else now
    price = row.get('price')
    at = row.get('price_as_of')
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise ValueError('Ungültiger Gold-Spotkurs')
    if not isinstance(at, str):
        raise ValueError('Gold-Quellenzeit fehlt')
    dt = datetime.fromisoformat(at.replace('Z', '+00:00'))
    age = now - dt.timestamp()
    if dt.tzinfo is None or not 0 <= age <= FRESH_MAX_AGE or row.get('is_stale') is not False:
        raise ValueError('Gold-Quellenzeit oder Aktualität nicht bestätigt')
    return float(price), age, at

def normalize_biquote_bars(payload):
    bars = payload.get("bars") if isinstance(payload, dict) else None
    if not isinstance(bars, list):
        return []
    out = []
    for b in bars:
        try:
            ot = b.get("openTime")
            o, h, l, c = map(float, (b.get("open"), b.get("high"), b.get("low"), b.get("close")))
            if not ot or not all(v == v for v in (o, h, l, c)):
                continue
            out.append({
                "openTime": ot,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "isOpen": bool(b.get("isOpen", False))
            })
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["openTime"])
    return out

def normalize_chart_points(points, minutes):
    """Keep source candles, excluding off-grid snapshots without rounding time."""
    step = minutes * 60
    rows, duplicates = {}, set()
    for p in points:
        try:
            ts = p['t']
            if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts <= 0 or ts % step:
                continue
            prices = [p[k] for k in ('o', 'h', 'l', 'c')]
            if any(isinstance(x, bool) for x in prices):continue
            o, h, low, close = map(float, prices)
            if not all(math.isfinite(x) and x > 0 for x in (o, h, low, close)) or low > min(o, close) or h < max(o, close):
                continue
            if ts in rows:
                duplicates.add(ts)
            rows[ts] = dict(openTime=int(ts*1000),open=o,high=h,low=low,close=close,isOpen=False,instrument='XAU/USD')
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return [row for ts,row in sorted(rows.items()) if ts not in duplicates]


def mark_bar_state(bars, minutes):
    """Mark the currently forming bar as open; never feed it into closed-bar analysis."""
    now_ms = int(time.time() * 1000)
    step = minutes * 60 * 1000
    for b in bars:
        try:
            b["isOpen"] = b.get("providerIsOpen", False) or now_ms < int(b["openTime"]) + step
        except (TypeError, ValueError, KeyError):
            b["isOpen"] = True
    return bars

def aggregate_bars(bars, minutes):
    """Only aggregate complete, ordered, same-instrument source candles."""
    base = {5: 1, 15: 5, 30: 5, 240: 60}.get(minutes)
    if base is None:
        raise ValueError('Nicht unterstützte Kerzenaggregation')
    step, source_step = minutes*60000, base*60000
    groups = {}
    for b in bars:
        try:
            ts = b['openTime']
            prices = [b[k] for k in ('open','high','low','close')]
            valid = (not isinstance(ts,bool) and isinstance(ts,(int,float)) and math.isfinite(ts)
                     and ts > 0 and ts % source_step == 0
                     and all(not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in prices))
            if not valid:continue
            o,h,l,c = prices
            if l>min(o,c) or h<max(o,c) or l>h:continue
            groups.setdefault(ts//step*step,[]).append(b)
        except (KeyError,TypeError):continue
    out = []
    now_ms = time.time()*1000
    for ts, items in sorted(groups.items()):
        items.sort(key=lambda b:b['openTime'])
        if ([b['openTime'] for b in items] != [ts+i*source_step for i in range(minutes//base)]
                or len({b.get('instrument','unknown') for b in items}) != 1):
            continue
        out.append(dict(openTime=ts,open=items[0]['open'],high=max(b['high'] for b in items),
                        low=min(b['low'] for b in items),close=items[-1]['close'],
                        instrument=items[0].get('instrument','unknown'),
                        source=items[0].get('source') if len({b.get('source') for b in items}) == 1 else 'aggregate · mixed sources',
                        estimated=any(b.get('estimated',False) for b in items),
                        providerIsOpen=any(b.get('providerIsOpen',False) for b in items),
                        isOpen=now_ms<ts+step or any(b.get('isOpen',False) or b.get('providerIsOpen',False) for b in items)))
    return out


_technical_history = {}
_technical_history_lock = threading.Lock()


def retain_technical_history(interval, rows):
    # Preserve source clocks when secondary work misses the HTTP deadline.
    minutes = technical_candles.MINUTES[interval]
    with _technical_history_lock:
        old = _technical_history.get(interval, [])
        spot_rows = bool(rows) and all(b.get('instrument') == 'XAU/USD' and not b.get('estimated') for b in rows)
        spot_old = bool(old) and all(b.get('instrument') == 'XAU/USD' and not b.get('estimated') for b in old)
        # An unrelated future must never evict genuine spot context. A recovered
        # spot series wins over an earlier cached fallback even if its clock is older.
        if rows and ((spot_rows and not spot_old) or
                     (spot_rows == spot_old and technical_history_latest(rows, minutes) >= technical_history_latest(old, minutes))):
            # Keep only confirmed older candles from the same source. Never
            # splice another provider or fill holes inside its current response.
            sources={b.get('source') for b in rows}
            older=[b for b in old if spot_rows and spot_old and len(sources)==1
                   and b.get('source') in sources and b.get('source')
                   and b['openTime']<rows[0]['openTime'] and not b.get('isOpen')
                   and not b.get('providerIsOpen')]
            _technical_history[interval] = [dict(row) for row in (older+rows)[-2000:]]
        return [dict(row) for row in _technical_history.get(interval, [])]


def technical_history_latest(bars, minutes, now=None):
    now = time.time() if now is None else now
    step = minutes*60*1000
    return max((b['openTime'] for b in bars if not b.get('isOpen') and b['openTime']+step <= now*1000), default=0)


def technical_history_fresh(bars, minutes, now=None):
    now = time.time() if now is None else now
    latest = technical_history_latest(bars, minutes, now)
    return bool(latest and 0 <= now*1000-latest <= minutes*120000)



# EMA200 requires 200 *completed* observations of one XAU/USD timeframe.
# The ordinary independent candle feed may publish fewer than 200 fresh 1h
# bars. Preserve its signal behavior, but try a bounded complete historical
# series from the already configured XAUS alternative.
EMA200_WARMUP_BARS = 200
_EMA_BACKFILL_INTERVAL_SECONDS = 300
_ema_backfill_lock = threading.Lock()
_ema_backfill_attempted = {}
_ema_backfill_series = {}


def _ema_history_sufficient(rows, minutes, now=None, minimum=EMA200_WARMUP_BARS):
    """Validate a single, source-provided XAU/USD series without splicing feeds."""
    now = time.time() if now is None else now
    step = minutes * 60000
    if not isinstance(rows, list):
        return False
    closed = [b for b in rows if not b.get('isOpen') and
              type(b.get('openTime')) in (int, float) and b['openTime'] + step <= now * 1000]
    if len(closed) < minimum or not technical_history_fresh(closed, minutes, now):
        return False
    if any(b.get('instrument') != 'XAU/USD' or b.get('estimated') or
           type(b.get('openTime')) not in (int, float) or b['openTime'] % step != 0 or
           any(type(b.get(k)) not in (int, float) or not math.isfinite(b[k]) or b[k] <= 0
               for k in ('open', 'high', 'low', 'close')) or
           b['low'] > min(b['open'], b['close']) or
           b['high'] < max(b['open'], b['close']) or
           (i > 0 and b['openTime'] <= closed[i - 1]['openTime'])
           for i, b in enumerate(closed)):
        return False
    # Provider session breaks outside current trading are retained; no synthetic
    # candles are inserted. The latest three closed candles must be contiguous.
    return all(b['openTime'] - a['openTime'] == step
               for a, b in zip(closed[-3:], closed[-2:]))


def _ema200_history_backfill(interval, range_value, observed, standby=False):
    """Research-only history warmup; no spot substitution or new order gate.

    One provider attempt per timeframe per five minutes for warmup, or per
    30 seconds when the observed series is stale. Failed attempts leave
    the independent current series in place. A cached longer series is used
    only when it is still source-fresh and not behind the independent source.
    """
    minutes = technical_candles.MINUTES[interval]
    now = time.time()
    fallback_minimum = (EMA200_WARMUP_BARS
                        if technical_history_fresh(observed, minutes, now) else 100)
    with _ema_backfill_lock:
        # Warmup can wait five minutes; recovery of a stale live series cannot.
        # Keep source clocks and freshness gates unchanged.
        retry_seconds = ((30 if interval in ('1m','5m') else 60) if standby else
                         _EMA_BACKFILL_INTERVAL_SECONDS if technical_history_fresh(observed, minutes, now) else 30)
        retry = now - _ema_backfill_attempted.get(interval, -1e12) >= retry_seconds
        if retry:
            _ema_backfill_attempted[interval] = now
    if retry:
        try:
            # Ask for enough real source history for every displayed timeframe.
            fetch_interval = '1h' if interval == '4h' else interval
            history_range = {'1m':'5d','5m':'1mo','15m':'1mo','30m':'1mo','1h':'3mo','4h':'3mo'}[interval]
            payload = fetch_json(
                f"https://xaus.com/api/v1/chart?symbol=xau&range={history_range}&interval={fetch_interval}&fresh={int(now // 60) * 60000}",
                retries=0, user_agent="Bob/1.4", timeout=8)
            points = payload.get('points') if isinstance(payload, dict) else None
            if isinstance(points, list):
                rows = normalize_chart_points(points, 60 if interval == '4h' else minutes)
                for row in rows:
                    row['source'] = 'XAUS · datierte XAU/USD-Historie'
                if interval == '4h':
                    mark_bar_state(rows,60)
                    rows=aggregate_bars(rows,240)
                mark_bar_state(rows, minutes)
                candle_reliability.observe('xaus',interval,rows)
                # Preserve a usable current source even while EMA200 is still
                # warming up. Existing indicator gates decide readiness; an
                # older 200-bar feed must not displace a fresh 100-bar feed.
                if _ema_history_sufficient(rows, minutes, minimum=fallback_minimum):
                    with _ema_backfill_lock:
                        _ema_backfill_series[interval] = [dict(row) for row in rows[-1000:]]
                    print(f"BOB_EMA200_BACKFILL interval={interval} completed={sum(not b['isOpen'] for b in rows)}", flush=True)
            else:
                candle_reliability.observe('xaus',interval,error='incomplete')
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            candle_reliability.observe('xaus',interval,error='unavailable')
            print(f"BOB_EMA200_BACKFILL interval={interval} unavailable", flush=True)
    with _ema_backfill_lock:
        historical = [dict(row) for row in _ema_backfill_series.get(interval, [])]
    mark_bar_state(historical, minutes)
    if (_ema_history_sufficient(historical, minutes, minimum=fallback_minimum)
            and technical_history_latest(historical, minutes) >=
                technical_history_latest(observed, minutes)):
        return retain_technical_history(interval, historical)
    return observed


def fetch_technical_history(interval, range_value):
    primary = []
    minutes = technical_candles.MINUTES[interval]
    independent = technical_candles.fetch(interval, fetch_json)
    if independent:
        independent = retain_technical_history(interval, independent)
        if technical_history_fresh(independent, minutes):
            # EMA200 is context only: a fresh 100-199 bar series remains
            # sufficient for EMA20/50-driven signals, while the older 200-bar
            # reference is fetched independently and never fabricated.
            if not _ema_history_sufficient(independent, minutes):
                return _ema200_history_backfill(interval, range_value, independent)
            return independent
    if interval == '5m':
        # Recover a stalled native 5m feed from complete, confirmed minute
        # candles already collected. Never blend providers or invent OHLC.
        minute_rows = retain_technical_history('1m', [])
        sources = {b.get('source') for b in minute_rows}
        if len(sources) == 1 and None not in sources and '' not in sources:
            aggregated = aggregate_bars(minute_rows, 5)
            if _ema_history_sufficient(aggregated, 5, minimum=100):
                print('BOB_CANDLES recovery=confirmed-1m interval=5m', flush=True)
                return retain_technical_history('5m', aggregated)
    if interval in ("1m", "15m", "30m", "4h"):
        return _ema200_history_backfill(interval, range_value, retain_technical_history(interval, independent))
    # XAUS exposes a documented XAU chart proxy. Use it first so Render
    # does not depend on direct Yahoo connectivity (which currently returns 404).
    xaus_interval = {"5m":"5m", "1h":"1h"}.get(interval, interval)
    try:
        payload = fetch_json(
            f"https://xaus.com/api/v1/chart?symbol=xau&range={range_value}&interval={xaus_interval}&fresh={int(time.time()//60)*60000}",
            retries=1,
            user_agent="Bob/1.4",
        )
        points = payload.get("points") if isinstance(payload, dict) else None
        if isinstance(points, list) and points:
            out = normalize_chart_points(points, minutes)
            rejected = len(points)-len(out)
            if rejected:
                print(f'BOB_HISTORY interval={interval} excluded_non_candles={rejected}',flush=True)
            if out:
                for row in out:row['source']='XAUS · datierte XAU/USD-Historie'
                mark_bar_state(out,minutes)
                candle_reliability.observe('xaus',interval,out)
                out=retain_technical_history(interval,out)
                primary = out
                if technical_history_fresh(out, minutes):
                    return out
    except Exception:
        pass

    retained = retain_technical_history(interval, [])
    if retained and all(b.get('instrument') == 'XAU/USD' and not b.get('estimated') for b in retained):
        return retained  # Stale stays stale; do not replace spot with a futures reference.

    try:
        # Keep direct Yahoo as a secondary fallback.
        payload = fetch_json(
            f"https://query2.finance.yahoo.com/v8/finance/chart/GC%3DF?interval={interval}"
            f"&range={range_value}&includePrePost=true",
            retries=1,
            user_agent="Mozilla/5.0 (Bob/1.5; +https://bob-private-scanner.onrender.com)",
        )
        result = payload.get("chart", {}).get("result", [None])[0] if isinstance(payload, dict) else None
        if not result:
            raise RuntimeError(f"Keine {interval}-Historie verfügbar")
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [None])[0] or {}
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        out = []
        for i, ts in enumerate(timestamps):
            try:
                o, h, low, close = map(float, (opens[i], highs[i], lows[i], closes[i]))
                if not all(v == v and v > 0 for v in (o, h, low, close)):
                    continue
                out.append({"openTime": int(ts)*1000, "open":o, "high":h, "low":low, "close":close, "isOpen":False, "instrument":"GC=F"})
            except (IndexError, TypeError, ValueError, OverflowError):
                continue
        out.sort(key=lambda x:x["openTime"])
        selected = out if technical_history_latest(out, minutes) > technical_history_latest(primary, minutes) else primary
        return retain_technical_history(interval, selected)
    except Exception:
        if primary:
            return primary
        raise


def live_cache_reusable(now=None):
    """Do not add a bundle TTL on top of an already ageing source quote."""
    now = time.time() if now is None else now
    if _live_cache is None or not 0 <= now - _live_cache_at < LIVE_CACHE_TTL:
        return False
    spots = _live_cache.get('spots', {})
    # Preserve the normal error backoff; retrying unavailable providers on every
    # browser request would compete with the background monitor.
    if spots.get('spot_error') or not spots.get('spot_price_as_of'):
        return True
    try:
        stamp = datetime.fromisoformat(spots['spot_price_as_of'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or not 0 <= now - stamp.timestamp() < 30:
            return False
        frames=(_live_cache.get('history') or {}).get('bars_by_tf') or {}
        if isinstance(frames.get('1m'),list):
            # Recovery may already have delivered a newer confirmed minute
            # while this bundle was waiting on other inputs. Do not add the
            # bundle TTL on top of that successfully refreshed candle cache.
            retained=retain_technical_history('1m',[])
            if (technical_history_fresh(retained,1,now)
                    and all(b.get('instrument')=='XAU/USD' and not b.get('estimated') for b in retained)
                    and technical_history_latest(retained,1,now)>
                        technical_history_latest(frames['1m'],1,now)):
                return False
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def recheck_spot_before_bundle(spot_result, now=None):
    """One final shared-source check after secondary I/O, never a new quote clock.

    A legitimately recent Gold-API observation can expire while technical
    histories/FX finish. Reuse the source's own serialized 30-second cache and
    bounded near-expiry retry, but NEVER extend a provider observation's life.
    """
    if not isinstance(spot_result, tuple) or len(spot_result) != 6:
        return spot_result
    price, _age, error, source, is_spot, original_at = spot_result
    if price is None or not is_spot or not isinstance(original_at, str):
        return spot_result
    clock = time.time() if now is None else now
    try:
        old_at = datetime.fromisoformat(original_at.replace('Z', '+00:00'))
        if old_at.tzinfo is None:
            return spot_result
        age = clock - old_at.timestamp()
        if not 0 <= age:
            return spot_result
    except (ValueError, OverflowError, TypeError, AttributeError):
        return spot_result
    # Keep the shared source cadence; a 35s-old quote can already predate
    # the newest closed minute even when the HTTP cache is only seconds old.
    if age >= 30:
        try:
            from spot_data import current
            refreshed = current()
            candidate_at = datetime.fromisoformat(refreshed['at'].replace('Z', '+00:00'))
            newest_age = time.time() - candidate_at.timestamp() if now is None else clock-candidate_at.timestamp()
            if (candidate_at.tzinfo is not None and candidate_at >= old_at
                    and 0 <= newest_age <= 60 and refreshed.get('source') == source):
                price = refreshed['price']
                original_at = refreshed['at']
                error = None
                age = newest_age
        except (OSError, ValueError, KeyError, TypeError, OverflowError, AttributeError):
            # Preserve the original observation and its REAL age. Consumers'
            # unchanged <=60s time gate remains authoritative.
            pass
    age = (time.time() if now is None else clock) - datetime.fromisoformat(
        original_at.replace('Z', '+00:00')).timestamp()
    return price, age, error, source, is_spot, original_at


def build_live_bundle():
    """Build Bob's live bundle without letting slow secondary sources block the spot heartbeat.

    XAU/USD spot, technical history and FX are fetched concurrently. A valid spot
    response is returned even when technical history or FX is temporarily slow.
    """
    global _live_cache, _live_cache_at, _fx_cache, _fx_cache_at
    if live_cache_reusable():
        return _live_cache

    with _live_lock:
        if live_cache_reusable():
            return _live_cache

        now = time.time()

        def fetch_spot():
            from spot_data import current
            try:
                q = current()
                age = time.time() - datetime.fromisoformat(q['at']).timestamp()
                return q['price'], age, None, q['source'], True, q['at']
            except (OSError, ValueError, KeyError, TypeError) as exc:
                return None, None, str(exc), None, False, None


        def fetch_fx():
            global _fx_cache, _fx_cache_at
            if time.time() - _fx_cache_at < FX_CACHE_TTL and any(v is not None for v in _fx_cache.values()):
                return _fx_cache["EUR"], _fx_cache["CHF"], []
            rates = {"EUR": None, "CHF": None}
            errors = []
            for ccy in ("EUR", "CHF"):
                try:
                    fx = fetch_json(
                        f"https://api.goldprice.dev/v1/convert?from=USD&to={ccy}&amount=1",
                        retries=1,
                        user_agent="Bob/1.3",
                    )
                    rate = float(fx.get("rate")) if isinstance(fx, dict) else None
                    if rate and math.isfinite(rate) and rate > 0:
                        rates[ccy] = rate
                        _fx_cache[ccy] = rate
                        _fx_meta[ccy] = {"rate":rate,"fetchedAt":datetime.now(timezone.utc).isoformat(),"sourceAt":None,"source":"GoldPrice.dev conversion API","error":None}
                    else:
                        errors.append(f"Ungültige {ccy}-FX-Rate")
                        _fx_meta.setdefault(ccy,{})["error"]="Ungültige Wechselkursantwort"
                except Exception as exc:
                    errors.append(str(exc))
                    _fx_meta.setdefault(ccy,{})["error"]="Aktualisierung verzögert"
            _fx_cache_at = time.time()
            return rates["EUR"] or _fx_cache["EUR"], rates["CHF"] or _fx_cache["CHF"], errors

        # The spot price is the primary heartbeat. Do NOT wait for every secondary
        # source: ThreadPoolExecutor's context manager would otherwise wait for slow
        # Yahoo/FX requests at shutdown and keep /api/live hanging.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="bob-live")
        futures = {
            pool.submit(fetch_spot): "spot",
            pool.submit(fetch_technical_history, "5m", "5d"): "5m",
            pool.submit(fetch_technical_history, "1h", "3mo"): "1h",
            pool.submit(fetch_technical_history, "15m", "5d"): "15m",
            pool.submit(fetch_technical_history, "4h", "3mo"): "4h",
            pool.submit(fetch_technical_history, "30m", "1mo"): "30m",
            pool.submit(fetch_fx): "fx",
            pool.submit(fetch_technical_history, "1m", "1d"): "1m",
        }
        results = {}
        try:
            # The heartbeat gets a generous but bounded window.
            spot_future = next(f for f, name in futures.items() if name == "spot")
            try:
                results["spot"] = spot_future.result(timeout=12)
            except Exception as exc:
                results["spot"] = exc

            # Secondary data is best-effort. Never let it block the live price.
            secondary_deadline = time.monotonic() + 2.0
            for future, name in futures.items():
                if name == "spot":
                    continue
                remaining = max(0.0, secondary_deadline - time.monotonic())
                if remaining <= 0 and not future.done():
                    results[name] = TimeoutError("Sekundärquelle zu langsam")
                    continue
                try:
                    results[name] = future.result(timeout=remaining)
                except FuturesTimeoutError:
                    results[name] = TimeoutError("Sekundärquelle zu langsam")
                except Exception as exc:
                    results[name] = exc
        finally:
            # Cancel unfinished secondary work and return the HTTP response without
            # waiting for those worker threads to finish.
            for future, name in futures.items():
                if name != "spot" and not future.done():
                    future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)

        spot_result = results.get("spot")
        if isinstance(spot_result, tuple):
            goldprice_price, goldprice_age, spot_error, spot_source, is_spot, spot_price_as_of = spot_result
        else:
            goldprice_price = goldprice_age = None
            spot_error = str(spot_result) if spot_result else "Spotquelle nicht verfügbar"
            spot_source = None
            is_spot = False
            spot_price_as_of = None

        bars_5m = results.get("5m", [])
        if isinstance(bars_5m, Exception):
            technical_5m_error = str(bars_5m)
            bars_5m = retain_technical_history('5m', [])
        else:
            technical_5m_error = None
        bars_1h = results.get("1h", [])
        if isinstance(bars_1h, Exception):
            technical_1h_error = str(bars_1h)
            bars_1h = retain_technical_history('1h', [])
        else:
            technical_1h_error = None

        fx_result = results.get("fx")
        if isinstance(fx_result, tuple):
            usd_eur, usd_chf, fx_errors = fx_result
        else:
            usd_eur, usd_chf, fx_errors = _fx_cache["EUR"], _fx_cache["CHF"], [str(fx_result)] if fx_result else []

        if bars_5m:
            mark_bar_state(bars_5m, 5)
        if bars_1h:
            mark_bar_state(bars_1h, 60)

        technical_errors = []
        if technical_5m_error:
            technical_errors.append(technical_5m_error)
        if technical_1h_error:
            technical_errors.append(technical_1h_error)
        if bars_5m:
            age = max(0, now - bars_5m[-1]["openTime"] / 1000)
            if age > 900:
                technical_errors.append(f"5m-Historie nicht frisch ({age:.0f} s)")
        technical_errors.extend(fx_errors)

        if goldprice_price is not None:
            # Finish the spot observation AFTER the bounded secondary wait.
            # This recovers a newer source tick when the first one was near
            # expiry, without inventing new quotes or weakening the 60s gate.
            (goldprice_price, goldprice_age, spot_error, spot_source,
             is_spot, spot_price_as_of) = recheck_spot_before_bundle(
                 (goldprice_price, goldprice_age, spot_error, spot_source,
                  is_spot, spot_price_as_of))
        if goldprice_price is None:
            # Never promote technical/futures history to the XAU/USD spot field.
            # A GC=F close is a futures reference, not a spot price, and must not
            # masquerade as live XAU/USD data when the genuine spot source fails.
            raise RuntimeError("Kein kostenloser Live-XAU/USD-Spotpreis verfügbar" + (f": {spot_error}" if spot_error else ""))

        bars_15m = aggregate_bars(bars_5m, 15) if bars_5m else []
        bars_30m = aggregate_bars(bars_5m, 30) if bars_5m else []
        bars_4h = aggregate_bars(bars_1h, 240) if bars_1h else []
        # Native longer timeframes retain more history than a short 5m window.
        for tf, minutes in (("15m", 15), ("30m", 30), ("4h", 240)):
            native = results.get(tf)
            if not isinstance(native, list):
                native = retain_technical_history(tf, [])
            if native and technical_history_fresh(native, minutes):
                mark_bar_state(native, minutes)
                if tf == '15m': bars_15m = native
                elif tf == '30m': bars_30m = native
                else: bars_4h = native
        bars_1m = results.get("1m")
        if not isinstance(bars_1m, list):
            bars_1m = retain_technical_history("1m", [])
        mark_bar_state(bars_1m, 1)
        reference = bars_5m[-1]["close"] if bars_5m else goldprice_price
        diff = goldprice_price - reference
        pct = (diff / reference * 100) if reference else 0.0
        points_source = bars_5m if bars_5m else bars_1h
        legacy_points = [
            {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b["openTime"] / 1000)), "p": b["close"]}
            for b in points_source
        ]

        # Bundle diagnostics use the original provider clock at publication,
        # never the older age measured before slow secondary I/O.
        goldprice_age = (time.time() - datetime.fromisoformat(
            spot_price_as_of.replace('Z', '+00:00')).timestamp()
            if spot_price_as_of else None)
        status = "fresh" if goldprice_age is not None and 0 <= goldprice_age <= 60 else "partial"
        bundle = {
            "fetched_at": int(time.time()),
            "spots": {
                "xaus": goldprice_price,
                "goldprice": goldprice_price,
                "yahoo_gc_f": reference if bars_5m and bars_5m[-1].get("instrument") == "GC=F" else None,
                "technical_reference": reference,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": goldprice_age,
                "spot_price_as_of": spot_price_as_of,
                "dailyChange": spot_daily_change.change(goldprice_price, spot_price_as_of),
                "goldprice_age_seconds": goldprice_age,
                "usd_eur": usd_eur,
                "usd_eur_meta": dict(_fx_meta.get("EUR", {})),
                "usd_chf": usd_chf,
                "usd_chf_meta": dict(_fx_meta.get("CHF", {})),
                "yahoo_gc_f_age_seconds": max(0, now - bars_5m[-1]["openTime"] / 1000) if bars_5m else None,
                "yahoo_1h_age_seconds": max(0, now - bars_1h[-1]["openTime"] / 1000) if bars_1h else None,
                "technical_4h_status": "available" if bars_4h else "unavailable",
                "technical_4h_error": "; ".join(technical_errors) if technical_errors else None,
                "goldprice_status": spot_source,
                "xaus_is_spot": is_spot,
                "is_genuine_xauusd_spot": is_spot,
                "spot_source_type": "XAU/USD spot" if is_spot else None,
                "primary": spot_source,
                "reference": bars_5m[-1].get("source", bars_5m[-1].get("instrument")) if bars_5m else None,
                "reference_note": "Technische Kerzenquelle; separat vom gemeinsamen Gold-Spotkurs",
                "spot_error": spot_error,
            },
            "history": {
                "bars_by_tf": {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m, "30m": bars_30m, "1h": bars_1h, "4h": bars_4h},
                "points": legacy_points,
                "data_state": {
                    "status": status,
                    "source": (spot_source or "keine Spotquelle") + " · Historie " + ", ".join(sorted({b.get("source", b.get("instrument", "unknown")) for b in bars_5m+bars_1h})),
                    "technical_4h_status": "available" if bars_4h else "unavailable",
                    "technical_errors": technical_errors,
                },
                "age_seconds": goldprice_age,
            },
        }
        # Transparent input diagnostics: never influence market direction or orders.
        try:
            import market_review
            bundle['marketReview'] = market_review.review(bundle, now=time.time())
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            bundle['marketReview'] = {'version':'market-input-review-v1', 'readOnly':True,
                                      'affectsTradeApproval':False, 'warnings':['Markt-Diagnose vorübergehend nicht verfügbar']}
            print('BOB_MARKET_REVIEW unavailable '+type(exc).__name__, flush=True)
        # Research output only. No selection, score, ranking or push consumes it.
        try:
            bundle['candleShadow'] = candle_shadow.snapshot(
                bundle['history']['bars_by_tf'],
                {tf: _mtf_score(bundle['history']['bars_by_tf'][tf], tf)
                 for tf in candle_shadow.STEPS}, now_ms=now*1000)
        except Exception as exc:
            bundle['candleShadow'] = {'mode': 'shadow', 'affectsSelection': False,
                                      'status': 'unavailable'}
            print('BOB_CANDLE_SHADOW unavailable '+type(exc).__name__, flush=True)
        _live_cache = bundle
        _live_cache_at = now
        return bundle

def _ema(values, period):
    if not values:
        return None
    k = 2.0 / (period + 1.0)
    e = float(values[0])
    for value in values[1:]:
        e = float(value) * k + e * (1.0 - k)
    return e

def _rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    gains /= period
    losses /= period
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        gains = (gains * (period - 1) + max(d, 0.0)) / period
        losses = (losses * (period - 1) + max(-d, 0.0)) / period
    return 50.0 if gains == losses == 0 else 100.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)

def _mtf_score(bars, tf):
    # Futures are a separate reference basis, never confirmed XAU/USD candles.
    # Historical unit-test fixtures without identity retain their old behavior.
    if any(b.get('instrument') not in (None, 'XAU/USD') for b in (bars or []) if isinstance(b, dict) and not b.get('isOpen')):
        return {'dir':'NEUTRAL','available':False,'fresh':False,'reason':'Futures-/Fremdbasis statt XAU/USD-Spotkerzen'}
    step={"1m":60000,"5m":300000,"15m":900000,"30m":1800000,"1h":3600000,"4h":14400000}.get(tf,900000)
    now=int(time.time()*1000)
    if any(not b.get("isOpen") and (not isinstance(b.get("openTime"),(int,float)) or b["openTime"]>now) for b in (bars or [])):
        return {"dir":"NEUTRAL","available":False,"fresh":False,"reason":"Kerzenzeit fehlt oder liegt in der Zukunft"}
    closed = [b for b in (bars or []) if not b.get("isOpen") and isinstance(b.get("openTime"),(int,float)) and b["openTime"]+step<=now][-220:]
    valid=all(b["openTime"]%step==0 and all(isinstance(b.get(k),(int,float)) and not isinstance(b.get(k),bool) and math.isfinite(b[k]) and b[k]>0 for k in ("open","high","low","close")) and b["low"]<=min(b["open"],b["close"]) and b["high"]>=max(b["open"],b["close"]) for b in closed)
    if not valid or any(b["openTime"]<=a["openTime"] for a,b in zip(closed,closed[1:])) or any(b["openTime"]-a["openTime"]!=step for a,b in zip(closed[-3:],closed[-2:])):
        return {"dir":"NEUTRAL","available":False,"fresh":False,"reason":"Ungültige oder lückenhafte Kerzen","bars":len(closed)}
    if len(closed) < 100:
        return {"dir":"NEUTRAL","available":False,"reason":"zu wenig Historie","bars":len(closed)}
    latest = int(closed[-1]["openTime"])
    age = int(time.time() * 1000) - latest
    freshness = step*2
    if age < 0 or age > freshness:
        return {"dir":"NEUTRAL","available":False,"fresh":False,"openTime":latest,"reason":"Kurszeit zukünftig" if age < 0 else "Historie zu alt","bars":len(closed),"ageMs":age}
    values = [float(b["close"]) for b in closed]
    e20, e50, e200 = _ema(values,20), _ema(values,50), _ema(values,200)
    def series(period):
        result=[values[0]]
        for value in values[1:]:result.append(value*2/(period+1)+result[-1]*(1-2/(period+1)))
        return result
    mac_series=[a-b for a,b in zip(series(12),series(26))]
    hist=mac_series[-1]-_ema(mac_series,9)
    rsi = _rsi(values)
    if rsi is None:
        return {"dir":"NEUTRAL","available":False,"reason":"zu wenig Historie für RSI","bars":len(closed),"ageMs":age}
    sign = lambda value: 1 if value > 0 else -1 if value < 0 else 0
    trend,momentum=sign(e20-e50),sign(hist)
    score=trend*(1 if sign(values[-1]-e20)==trend and sign(rsi-50)==trend else .5) if trend and momentum==trend else 0
    direction = "LONG" if score >= 0.5 else "SHORT" if score <= -0.5 else "NEUTRAL"
    return {"dir":direction,"available":True,"reason":"ok","bars":len(closed),"rsi":round(rsi,2),"score":score,"ageMs":age,"fresh":True,"openTime":latest}

def build_mtf_verification(bundle):
    tfbars = bundle.get("history",{}).get("bars_by_tf",{}) if isinstance(bundle,dict) else {}
    results = {tf:_mtf_score(tfbars.get(tf,[]),tf) for tf in ("5m","15m","1h","4h")}
    valid = all(results[tf].get("available") and results[tf].get("fresh") for tf in ("5m","15m"))
    d4,d1,d15,d5 = (results[tf]["dir"] for tf in ("4h","1h","15m","5m"))
    overall,bias = "NEUTRAL",0.0
    if not valid:
        reason = "Intraday-MTF unvollständig oder veraltet"
    elif d15 not in ("LONG","SHORT"):
        reason = "15m-Setup neutral"
    elif d5 != d15:
        reason = "5m bestätigt das 15m-Setup nicht"
    else:
        overall,bias = d15,1.0 if d15 == "LONG" else -1.0
        reason = "Intraday: 15m Setup · 5m Einstieg · 1h/4h Kontext"
    hierarchy = {"regime":d4,"trend":d1,"setup":d15,"timing":d5,"bias":round(bias,3),"reason":reason}
    return {"overall":overall,"valid":valid,"results":results,"hierarchy":hierarchy,"verifiedAt":datetime.now(timezone.utc).isoformat()}

def sanitize_client_diagnostic(payload):
    """Keep browser diagnostics bounded and reclassify known auth expiry."""
    event = str(payload.get("event", "unknown"))[:80]
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    safe = {}
    for key in ("bars5m","bars15m","bars1h","bars4h","available","overall","error","reason","historyStatus","source","direct","server"):
        if key in details:
            value = details[key]
            safe[key] = str(value)[:300] if isinstance(value, str) else value
    # Only market-entry diagnostics, never the full state/products/account data.
    direction = details.get("entryDirection")
    if isinstance(direction, str) and direction in ("LONG", "SHORT", "NEUTRAL"):
        safe["entryDirection"] = direction
    reason = details.get("entryReason")
    if isinstance(reason, str):
        safe["entryReason"] = reason[:800]
    # Tabs opened before the client-side session guard can keep reporting this
    # until their service worker reloads. It is authentication expiry, not a
    # market-data or MTF server failure, so keep old clients honest as well.
    if event == "mtf:server-error" and safe.get("error") == "HTTP 401":
        event = "mtf:verification-skipped"
        safe.pop("error", None)
        safe["reason"] = "Serverprüfung wegen abgelaufener Bob-Anmeldung ausgesetzt"
    return event, safe



class Handler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except bob_passkey.PasskeyRequired:
            self.close_connection = True
            if self.command in ('GET', 'HEAD') and not urlparse(self.path).path.startswith('/api/'):
                bob_auth.send(self, 303, location='/passkey')
            else:
                bob_passkey.respond(self, 403, {'error':'PASSKEY_REQUIRED','url':'/passkey'})
        except bob_auth.AuthenticationUnavailable:
            # A transient store outage is not evidence that a session expired.
            # Deny this request without emitting the 401 that logs the PWA out.
            self.close_connection = True
            try:
                bob_auth.send(self, 503, 'Sitzungsprüfung vorübergehend nicht erreichbar. Bitte erneut versuchen.'.encode())
            except (BrokenPipeError, ConnectionResetError):
                pass
        except (BrokenPipeError, ConnectionResetError):
            # A navigation/refresh can close the client after a successful upstream call.
            # Never retry that completed POST or send a second HTTP response.
            self.close_connection = True

    def authenticated(self):
        return bob_auth.authenticated(self.headers, USER, PASSWORD)

    def do_GET(self):
        if __import__('android_telemetry_http').route(self,'GET',urlparse(self.path).path,android_diagnostic_rpc):return
        if bob_oauth.route(self, USER, PASSWORD):
            return
        if bob_passkey.route(self, USER, PASSWORD):
            return
        if bob_recovery.route(self, USER):
            return
        path = urlparse(self.path).path
        if path == "/.well-known/assetlinks.json":
            # Android must fetch verified public signature metadata with no Bob
            # login, browser redirect or exposed private credentials.
            bob_app_links.send(self, query=urlparse(self.path).query)
            return
        if path.startswith(ocr_assets.PREFIX):
            ocr_assets.serve(self, path)
            return
        if path == "/mcp":
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/login":
            query = parse_qs(urlparse(self.path).query)
            bob_auth.login_page(
                self,
                "Passwort geändert. Bitte mit deinem neuen Passwort anmelden." if query.get("reset") == ["1"] else "",
                view=query.get("view", [""])[0],
            )
            return
        if path.startswith("/handy/"):
            # Normal HTTPS link from ChatGPT. No public personal content:
            # deny unknown paths and require existing Bob web authentication.
            command = bob_handy_landing.route(path, urlparse(self.path).query)
            if command is None:
                bob_auth.send(self, 404)
            elif not self.authenticated():
                view = bob_handy_landing.PAGES[command][1]
                bob_auth.send(self, 303, location="/login?view=" + view)
            else:
                bob_handy_landing.send(self, command)
            return
        if path in ("/", "/index.html", "/bob-live", "/bob-v12") and not self.authenticated():
            # Browser fragments are invisible to servers. The Android companion
            # therefore sends the intended tab as an allowlisted ?view= value.
            requested_view = bob_auth.safe_return_view(
                parse_qs(urlparse(self.path).query).get("view", [""])[0]
            )
            location = "/login?view=" + requested_view if requested_view else "/login"
            bob_auth.send(self, 303, location=location)
            return
        # Sensitive data APIs must be authenticated before any data generation.
        # Keep static PWA resources and /health public, but never expose live,
        # MTF, or DEGIRO enrichment data without the existing Bob credentials.
        protected_api_path = path in ("/api/live", "/api/mtf", "/api/degiro/enrich", "/api/collection-status", "/api/market-cards", "/api/economic-calendar", "/api/gold-research") or path in ("/api/degiro/connection-status", "/api/degiro/sync") or path == "/api/degiro/sandbox" or path == "/api/vollautomatisch/demo" or path == "/api/weekend-archive" or path == "/api/zukunft/research" or path == "/api/degiro/candidates" or path == "/api/degiro/audit" or path == "/api/degiro/candidate-proofs" or path == "/api/self-healing" or path == "/api/problems" or path == "/api/repair-statistics" or path == "/api/source-reliability" or path == "/api/operations-summary"
        if protected_api_path or path == '/api/snaptrade/status':
            auth = self.headers.get("Authorization", "")
            expected = "Basic " + base64.b64encode(
                f"{USER}:{PASSWORD}".encode("utf-8")
            ).decode("ascii")
            if not self.authenticated():
                self.send_response(401)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b"Authentication required.")
                return

        if path == '/api/snaptrade/status':
            snaptrade_bridge.mark_interactive()
            body = json.dumps(snaptrade_bridge.status(), allow_nan=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/api/degiro/connection-status", "/api/degiro/sync"):
            body = json.dumps(degiro_sync.status() if path == "/api/degiro/sync" else degiro_readonly.status()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == '/api/source-reliability':
            body=json.dumps(candle_reliability.snapshot(),allow_nan=False).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/repair-statistics":
            # Independent of GitHub issue availability, including rate limits.
            # Only authenticated users may read private operational statistics.
            body = json.dumps(bob_repair_store.statistics(), ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/operations-summary":
            # Authenticated projection only: no orders, repairs or notification sends.
            import bob_operations
            report = bob_operations.snapshot(read_diagnostics_for_mcp())
            body = json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/problems":
            # Authenticated, read-only index. Public GitHub issues are filtered
            # to the watchdog's fixed diagnostic codes; never emit raw bodies.
            report = bob_problems.snapshot()
            report["selfHealingStatistics"] = bob_repair_store.statistics()
            body = json.dumps(report, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/self-healing":
            body = json.dumps(bob_self_healing.snapshot(service_health()), ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/zukunft/research":
            # Display ONLY the last stored daily background result. Never run
            # research in a browser request; never alter live trade decisions.
            try:
                snapshot = strategy_lab_background.request("read", {})
                if snapshot.get("mode") != "RESEARCH_ONLY":
                    raise ValueError("Forschungsarchiv nicht bestätigt")
                report = snapshot.get("latestReport") or {
                    "status": "pending", "mode": "RESEARCH_ONLY", "approved": False,
                    "orderExecutionEnabled": False, "note": "Erste automatische Auswertung steht aus."
                }
                report = dict(report)
                report["automation"] = snapshot.get("automation") or {}
                report["runtime"] = strategy_lab_background.status()
                report["brokerReadiness"] = broker_bridge.status()
            except Exception as exc:
                print("BOB_STRATEGY_READ error="+type(exc).__name__,flush=True)
                report = {"status": "unavailable", "mode": "RESEARCH_ONLY",
                          "approved": False, "orderExecutionEnabled": False,
                          "reason": "Gespeichertes Forschungsarchiv momentan nicht erreichbar",
                          "automation": {"enabled": False, "history": []},
                          "runtime": strategy_lab_background.status(),
                          "brokerReadiness": broker_bridge.status()}
            body = json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/api/vollautomatisch/demo", "/api/degiro/sandbox"):
            # Authenticated and read-only. Runs fixed synthetic quotes; never
            # dispatches live signals or connects to a brokerage account.
            scenario = parse_qs(urlparse(self.path).query).get("scenario", ["target"])[0]
            if scenario not in ("target", "stop_gap", "stale", "trailing"):
                self.send_response(400)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            result = degiro_sandbox.run(scenario) if path == "/api/degiro/sandbox" else vollautomatisch_engine.demonstration(scenario)
            body = json.dumps(result,
                              ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/gold-research":
            body = json.dumps(gold_research.snapshot(), ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/risk-paper":
            if not self.authenticated():
                bob_auth.send(self,401,body=b'{"error":"Unauthorized"}');return
            try:
                body=json.dumps(read_private_report_for_mcp('/risk-paper')).encode();status=200
            except (OSError, ValueError, RuntimeError, HTTPError, URLError, TimeoutError):
                body=b'{"status":"unavailable"}';status=503
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(body);return

        if path == "/api/collection-status":
            body = json.dumps(auto_collection.status(), ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/degiro/candidate-proofs":
            # Private, read-only user-uploaded DEGIRO detail observations,
            # bounded and stored separately from holdings and trade decisions.
            try:
                report = read_private_report_for_mcp("/candidate-proofs")
                body = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                status = 200
            except (OSError, ValueError, RuntimeError, HTTPError, URLError, TimeoutError):
                status = 503
                body = b'{"status":"unavailable","items":[]}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/degiro/audit":
            # Private proxy; the push service owns the active screenshot list.
            # Never call the issuer or DEGIRO from an interactive status GET.
            try:
                result = read_private_product_audit_for_mcp()
                body = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                status = 200
            except (OSError, ValueError, RuntimeError, HTTPError, URLError, TimeoutError):
                status = 503
                body = json.dumps({"status": "unavailable", "items": [],
                    "reason": "Privater Produktprüfbericht momentan nicht erreichbar"},
                    ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/degiro/candidates":
            # Historical DEGIRO list seeds researched through existing issuer
            # adapters. Never an authenticated DEGIRO account or tradability list.
            degiro_catalog.start()
            body = json.dumps(degiro_catalog.snapshot(),ensure_ascii=False,
                              separators=(",",":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/degiro/enrich":
            try:
                query = parse_qs(urlparse(self.path).query)
                isin = (query.get("isin") or [""])[0].strip().upper()
                if len(isin) != 12:
                    raise ValueError("ISIN fehlt oder ist ungültig")
                if query.get("scope") == ["terms"] and isin in product_quotes.SG_DIRECT_PRODUCTS:
                    from sg_direct import get_quote
                    result = get_quote(isin, terms_only=True)
                else:
                    result = enrich_degiro_product(isin)
                body = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                body = json.dumps({"isin":isin,"found":False,"sourceFailure":True,"source":"Emittentenrecherche","reason":"Zusatzprüfung momentan nicht verfügbar","attemptedAt":datetime.now(timezone.utc).isoformat()}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            return
        if path == "/api/mtf":
            try:
                verification = build_mtf_verification(build_live_bundle())
                body = json.dumps(verification, ensure_ascii=False, separators=(",",":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_response(503)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(json.dumps({"error":str(exc)}).encode("utf-8"))
            return
        if path == "/health/background":
            payload = background_health()
            body = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(200 if payload["status"] == "ok" else 503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/health":
            # Idempotent worker checks; the independent 30-second local watcher
            # provides the same checks while the browser is closed.
            start_healing_watch()
            maintain_known_workers()
            body = json.dumps(service_health(),separators=(",",":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        # Public read-only app resources. No credentials or secrets are returned here.
        # This is required for normal PWA/browser fetch behavior after the initial protected page load.

        if path == "/future_lab.js":
            try:
                body = (BASE_DIR / "future_lab.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/mco_clip.js":
            try:
                body = (BASE_DIR / "mco_clip.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path in ("/risk_workspace.js", "/comparison_diagrams.js", "/mco_comparison.js", "/video_ocr.js", "/video_evidence.js", "/video_brief.js"):
            try:
                body = (BASE_DIR / path.lstrip("/")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/product_trade_curve.js":
            try:
                body = (BASE_DIR / "product_trade_curve.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/bob_stop_assistant.js":
            try:
                body = (BASE_DIR / "bob_stop_assistant.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path in ("/improvement_tracker.js", "/training_help.js"):
            body=(BASE_DIR / path.lstrip("/")).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/real_trade_journal.js":
            try:
                body = (BASE_DIR / "real_trade_journal.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/push_manager.js":
            try:
                body = PUSH_MANAGER_JS.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/late_entry_guard.js":
            try:
                body = (BASE_DIR / "late_entry_guard.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path in ("/product_evidence_contract.js", "/bob_audit_read_pool.js", "/bob_unified_workspace.js", "/degiro_assistant.js", "/degiro_handoff.js", "/degiro_portfolio_store.js", "/degiro_report_import.js", "/degiro_all_products.js", "/broker_candidate_pools.js", "/degiro_browser_bridge.js", "/degiro_android_bridge.js", "/degiro_morning_reader.js", "/bob_degiro_export.user.js"):
            try:
                body = (DEGIRO_MORNING_READER_JS if path == "/degiro_morning_reader.js" else PRODUCT_EVIDENCE_CONTRACT_JS if path == "/product_evidence_contract.js" else BOB_AUDIT_READ_POOL_JS if path == "/bob_audit_read_pool.js" else BOB_UNIFIED_WORKSPACE_JS if path == "/bob_unified_workspace.js" else DEGIRO_BROWSER_BRIDGE_JS if path == "/degiro_browser_bridge.js" else DEGIRO_BROWSER_USERSCRIPT if path == "/bob_degiro_export.user.js" else DEGIRO_HANDOFF_JS if path == "/degiro_handoff.js" else DEGIRO_PORTFOLIO_STORE_JS if path == "/degiro_portfolio_store.js" else DEGIRO_REPORT_IMPORT_JS if path == "/degiro_report_import.js" else DEGIRO_ALL_PRODUCTS_JS if path == "/degiro_all_products.js" else BROKER_CANDIDATE_POOLS_JS if path == "/broker_candidate_pools.js" else DEGIRO_ANDROID_BRIDGE_JS if path == "/degiro_android_bridge.js" else DEGIRO_ASSISTANT_JS).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/sw.js" and SW is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(SW)
            return

        if path == "/icon.svg" and ICON is not None:
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(ICON)
            return

        if path == "/manifest.json" and MANIFEST is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(MANIFEST)
            return

        if path == "/api/economic-calendar":
            body = json.dumps(economic_calendar.snapshot(), ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/cfd-chart":
            tf=parse_qs(urlparse(self.path).query).get('tf',['15m'])[0]
            import investing_card
            payload=investing_card.chart_snapshot(tf)
            body=json.dumps(payload,allow_nan=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/weekend-archive":
            try:
                import weekend_archive
                payload=weekend_archive.request('read',{})
                data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
                status=200
            except Exception as exc:
                print('BOB_WEEKEND_ARCHIVE read_error='+type(exc).__name__,flush=True)
                data=b'{"error":"Wochenendarchiv nicht erreichbar"}'
                status=503
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/market-cards":
            body = json.dumps(market_cards.snapshot(), ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/live":
            try:
                payload = build_live_bundle()
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The client went away after the live response had started.
                # This is not a live-data failure and a second response would
                # only raise another socket error.
                self.close_connection = True
            except Exception as exc:
                print(f"Bob /api/live ERROR: {type(exc).__name__}: {exc}", flush=True)
                body = json.dumps({"error": "Live-Daten momentan nicht verfügbar", "error_type": type(exc).__name__}).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            return

        path = urlparse(self.path).path

        auth = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{USER}:{PASSWORD}".encode("utf-8")
        ).decode("ascii")

        worker_token = self.headers.get("X-Bob-Worker-Token", "")
        worker_ok = bool(SIGNAL_WORKER_TOKEN) and hmac.compare_digest(worker_token, SIGNAL_WORKER_TOKEN)
        public_push_path = path in ("/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences")
        if not public_push_path and not worker_ok and (not self.authenticated()):
            print(
                f'BOB_AUTH_FAIL path={path} auth_present={bool(auth)} '
                f'auth_scheme={auth.split(" ",1)[0] if auth else "-"} '
                f'user_configured={bool(USER)} password_configured={bool(PASSWORD)} '
                f'worker_token_present={bool(worker_token)} worker_token_configured={bool(SIGNAL_WORKER_TOKEN)}',
                flush=True,
            )
            self.send_response(401)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        if path == '/api/trade-reference':
            try:
                import trade_reference
                raw = parse_qs(urlparse(self.path).query).get('at', [''])[0]
                currency=parse_qs(urlparse(self.path).query).get('currency',['EUR'])[0]
                payload = trade_reference.lookup(raw,currency=currency)
                status = 200
            except ValueError as exc:
                payload = {'available': False, 'reason': str(exc)}
                status = 400
            except Exception:
                payload = {'available': False, 'reason': 'Historische Gold-/FX-Quelle momentan nicht erreichbar oder Antwort nicht verwendbar. Referenz bleibt offen.'}
                status = 502
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode('utf-8'))
            return

        # Fresh pathname bypasses stale PWA shells on devices that cached an older root.
        if path == "/bob-v12":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Bob-Version", "bob-v12")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(HTML)
            return

        if path == "/bob-live":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Bob-Version", "live-shell-v8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; img-src 'self' data: blob:; frame-src https://www.youtube-nocookie.com; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(HTML)
            return

        if path in ("/", "/index.html"):
            print(f'BOB_ROOT_SHELL path={path} shell_sha_hint=bc7499bb9f3e0a1676022a3d3c2225a236615adf auth_present={bool(self.headers.get("Authorization", ""))}', flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline'; "
                "connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; "
                "img-src 'self' data: blob:; frame-src https://www.youtube-nocookie.com; "
                "worker-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'"
            )
            self.end_headers()
            self.wfile.write(HTML)
            return

        if path == "/api/push/vapid-public-key":
            try:
                if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
                    raise RuntimeError("Push-Service nicht konfiguriert")
                base = PUSH_SERVICE_URL
                if not base.startswith("http://") and not base.startswith("https://"):
                    base = "http://" + base
                req = Request(base.rstrip("/") + "/vapid-public-key", headers={"Accept":"application/json"})
                with urlopen(req, timeout=8) as response:
                    result = response.read()
                    status = response.status
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(result)
            except HTTPError as exc:
                self.send_response(exc.code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"error":"Push-Service-Fehler"}')
            except (URLError, TimeoutError):
                self.send_response(503)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"error":"Push-Service nicht erreichbar"}')
            return


    def do_HEAD(self):
        # Render and other HTTP probes use HEAD. Mirror the root/health access
        # policy without generating a response body, so probes do not produce
        # false 501 errors and the private root stays private.
        path = urlparse(self.path).path
        if path == "/.well-known/assetlinks.json":
            bob_app_links.send(self, query=urlparse(self.path).query, head=True)
            return
        if path.startswith("/handy/"):
            command = bob_handy_landing.route(path, urlparse(self.path).query)
            if command is None:
                bob_auth.send(self, 404)
            elif not self.authenticated():
                view = bob_handy_landing.PAGES[command][1]
                bob_auth.send(self, 303, location="/login?view=" + view)
            else:
                bob_handy_landing.send(self, command, head=True)
            return
        if path == "/health/background":
            self.send_response(200 if background_health()["status"] == "ok" else 503)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/health":
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/login":
            bob_auth.send(self, 200)
            return
        if path in ("/", "/index.html") and not self.authenticated():
            requested_view = bob_auth.safe_return_view(
                parse_qs(urlparse(self.path).query).get("view", [""])[0]
            )
            location = "/login?view=" + requested_view if requested_view else "/login"
            bob_auth.send(self, 303, location=location)
            return
        if path in ("/", "/index.html"):
            auth = self.headers.get("Authorization", "")
            expected = "Basic " + base64.b64encode(
                f"{USER}:{PASSWORD}".encode("utf-8")
            ).decode("ascii")
            if not self.authenticated():
                self.send_response(401)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; img-src 'self' data: blob:; frame-src https://www.youtube-nocookie.com; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if __import__('android_telemetry_http').route(self,'POST',urlparse(self.path).path,android_diagnostic_rpc):return
        if bob_oauth.route(self, USER, PASSWORD):
            return
        if bob_passkey.route(self, USER, PASSWORD):
            return
        if bob_recovery.route(self, USER):
            return
        path = urlparse(self.path).path
        if path == "/mcp":
            # The legacy machine credential remains product-read-only.
            # Only explicit OAuth consent enables the separate push-test scope.
            # Legacy user-password access remains subject to the daily factor.
            products_allowed = (bob_mcp.service_authenticated(self.headers)
                or bob_oauth.bearer_authenticated(self.headers, USER)
                or (self.headers.get("Authorization", "").startswith("Basic ") and self.authenticated()))
            diagnostics_allowed = bob_oauth.bearer_authenticated(self.headers, USER, bob_oauth.DIAGNOSTICS_SCOPE)
            push_test_allowed = bob_oauth.bearer_authenticated(self.headers, USER, bob_oauth.PUSH_TEST_SCOPE)
            phone_allowed = bob_oauth.bearer_authenticated(self.headers, USER, bob_oauth.PHONE_SCOPE)
            if not products_allowed and not diagnostics_allowed and not push_test_allowed and not phone_allowed:
                self.send_response(401)
                self.send_header("WWW-Authenticate", bob_oauth.challenge_header())
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise ValueError("MCP expects JSON")
                length = self.headers.get("Content-Length", "")
                if not length.isdecimal() or not 0 < int(length) <= 16384:
                    raise ValueError("MCP request size invalid")
                payload = json.loads(self.rfile.read(int(length)).decode("utf-8"))
                status, output = bob_mcp.handle(payload, read_private_product_audit_for_mcp,
                    read_diagnostics_for_mcp if diagnostics_allowed else None, products=products_allowed,
                    remote_phone=True, phone_handler=(lambda name,args:android_diagnostic_rpc({'action':'mcp','name':name,'arguments':args},remote=True)) if phone_allowed else None,
                    remote_push=True, push_reader=remote_push_rpc if diagnostics_allowed else None,
                    push_sender=remote_push_rpc if push_test_allowed else None,
                    signal_history_reader=(lambda args:read_private_report_for_mcp("/signal-history", args)) if diagnostics_allowed else None,
                    push_history_reader=(lambda args:read_private_report_for_mcp("/push-delivery-history", args)) if diagnostics_allowed else None)
            except (ValueError, UnicodeError):
                status, output = 400, bob_mcp.error(None, -32700, "Invalid JSON request")
            except (HTTPError, URLError, OSError, TimeoutError, RuntimeError):
                status, output = 503, bob_mcp.error(None, -32001, "Private audit temporarily unavailable")
            if output is None:
                body = b""
            else:
                body = json.dumps(output, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
            return
        if path == "/login":
            bob_auth.login(self, USER, PASSWORD)
            return
        if path == "/logout":
            bob_auth.logout(self)
            return
        # Signed AgentMail webhook; no browser cookie, no Basic auth and no
        # trading action. Disabled until the mailbox/signing secret is set.
        if path == "/api/trade-email/webhook":
            try:
                import trade_email_import
                secret = os.environ.get("BOB_AGENTMAIL_WEBHOOK_SECRET", "")
                if not secret or not os.environ.get("BOB_EMAIL_ALLOWED_FROM"):
                    raise RuntimeError("E-Mail-Eingang nicht verbunden")
                if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
                    raise RuntimeError("Speicher nicht konfiguriert")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= trade_email_import.MAX_BODY:
                    raise ValueError("Anfragegröße ungültig")
                raw = self.rfile.read(length)
                event, signed_id = trade_email_import.verify_svix(raw, self.headers, secret)
                # Save only a safe structured result, never the original email
                # body, attachment, personal account details or webhook secret.
                record = trade_email_import.import_event(event, os.environ["BOB_EMAIL_ALLOWED_FROM"])
                # Strictly scoped attachment retrieval. If a relevant PDF
                # cannot be fetched, return 503 for AgentMail retry instead
                # of silently acknowledging a discarded trade confirmation.
                import trade_attachment_import
                record = trade_attachment_import.enrich_event(
                    event, record, os.environ["BOB_EMAIL_ALLOWED_FROM"],
                    os.environ.get("BOB_AGENTMAIL_API_KEY", ""))
                message = event.get("message") if isinstance(event.get("message"), dict) else {}
                message_id = message.get("message_id") or signed_id
                if not isinstance(message_id, str) or len(message_id) > 200:
                    raise ValueError("Message-ID ungültig")
                payload = {"messageId":message_id,"record":record}
                base = PUSH_SERVICE_URL if PUSH_SERVICE_URL.startswith(("https://","http://")) else "http://" + PUSH_SERVICE_URL
                req = Request(base.rstrip("/") + "/email-import/receive",
                              method="POST", data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type":"application/json",
                                       "X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
                with urlopen(req, timeout=9) as response:
                    response.read(4096)
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except (ValueError, json.JSONDecodeError):
                self.send_response(401)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except Exception as exc:
                print("BOB_EMAIL_IMPORT unavailable="+type(exc).__name__,flush=True)
                self.send_response(503)
                self.send_header("Cache-Control","no-store")
                self.end_headers()
            return
        if bob_auth.cookie(self.headers, bob_auth.COOKIE) and not bob_auth.same_origin(self.headers):
            bob_auth.send(self, 403)
            return
        auth = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{USER}:{PASSWORD}".encode("utf-8")
        ).decode("ascii")
        worker_token = self.headers.get("X-Bob-Worker-Token", "")
        worker_ok = bool(SIGNAL_WORKER_TOKEN) and hmac.compare_digest(worker_token, SIGNAL_WORKER_TOKEN)

        if path == "/api/assistance":
            if not self.authenticated():
                bob_auth.send(self, 401)
                return
            if not bob_auth.same_origin(self.headers):
                bob_auth.send(self, 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 128:
                    raise ValueError("Invalid size")
                result = bob_assistance.report(json.loads(self.rfile.read(length)))
                code = 200
            except (ValueError, TypeError):
                result, code = {"ok": False, "error": "Invalid assistance code"}, 400
            body = json.dumps(result).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ('/api/snaptrade/configure', '/api/snaptrade/check', '/api/snaptrade/disconnect', '/api/snaptrade/csv-import', '/api/snaptrade/csv-clear', '/api/snaptrade/csv-auto', '/api/snaptrade/catalog-probe'):
            if not self.authenticated():
                bob_auth.send(self, 401); return
            if not bob_auth.same_origin(self.headers):
                bob_auth.send(self, 403); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= (1_000_000 if path in ('/api/snaptrade/csv-import','/api/snaptrade/csv-auto') else 2048):
                    raise ValueError('Ungültige Anfragegröße.')
                result = snaptrade_bridge.handle(path.rsplit('/', 1)[-1], json.loads(self.rfile.read(length)))
                code = 200
            except snaptrade_bridge.ReadError as exc:
                result, code = {'code': exc.code, 'message': 'Einrichtung nicht gespeichert. Geschützten Speicher prüfen.'}, 503
            except Exception as exc:
                # Keep infrastructure failures a structured response, never raw
                # request bodies, keys or exception messages in the response/log.
                if isinstance(exc, (ValueError, TypeError)):
                    result, code = ({'code': 'INVALID_CSV_LINK', 'message': 'CSV-Zuordnung nicht gespeichert.'} if path in ('/api/snaptrade/csv-import','/api/snaptrade/csv-clear','/api/snaptrade/csv-auto') else {'code': 'INVALID_INPUT', 'message': 'Nur kostenlosen Personal-Schlüssel und Bestätigung eintragen.'}), 400
                else:
                    result, code = {'code': 'SETUP_FAILED', 'message': 'Einrichtung nicht gespeichert. Technischen Fehler in Bob prüfen.'}, 503
            body = json.dumps(result, allow_nan=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/api/degiro/connection-test", "/api/degiro/sync/start", "/api/degiro/sync/stop", "/api/degiro/preflight"):
            if not self.authenticated():
                bob_auth.send(self, 401)
                return
            if not bob_auth.same_origin(self.headers):
                bob_auth.send(self, 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= (2048 if path.endswith("/preflight") else 128):
                    raise ValueError("Ungültige Anfragegröße")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or (not path.endswith("/preflight") and set(payload) - {"otp"}):
                    raise ValueError("Ungültige Anfrage")
                result = (degiro_preflight.probe(payload) if path.endswith("/preflight") else
                          degiro_sync.start(payload.get("otp", "")) if path.endswith("/start") else
                          degiro_sync.stop() if path.endswith("/stop") else
                          {"ok": False, "code": "BUSY"} if degiro_sync.status()["running"] else
                          degiro_readonly.probe(payload.get("otp", "")))
                code = 200
            except (ValueError, TypeError):
                result, code = {"ok": False, "code": "INVALID_INPUT"}, 400
            body = json.dumps(result).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/research/youtube":
            if not self.authenticated():
                bob_auth.send(self, 401)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 250000:raise ValueError('Ungültige Anfragegröße')
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(payload, dict):raise ValueError('Ungültige Anfrage')
                import youtube_research
                result = youtube_research.from_screenshot(payload) if 'screenshotText' in payload else {'ok': True, 'item': youtube_research.manual(payload)}
                status = 200
            except ValueError as exc:
                result = {'ok': False, 'error': str(exc)}
                status = 400
            except Exception:
                result = {'ok': False, 'error': 'Untertitel momentan nicht öffentlich abrufbar. Du kannst ein vorhandenes Transkript unten einfügen.'}
                status = 502
            body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/diag":
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0 or length > 8192:
                    raise ValueError("invalid diagnostic payload size")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                event, safe = sanitize_client_diagnostic(payload)
                print(f"BOB_DIAG event={event} seq={payload.get('seq')} details={json.dumps(safe, ensure_ascii=False, separators=(',',':'))}", flush=True)
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except Exception as exc:
                print(f"BOB_DIAG_ERROR {type(exc).__name__}: {exc}", flush=True)
                self.send_response(400)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            return

        if path in ("/api/improvement/read", "/api/research/video-evidence", "/api/ranking-learning/control", "/api/precision-learning/control", "/api/degiro/venue", "/api/degiro/candidate-proof", "/api/degiro/list-correction", "/api/degiro/android-observations", "/api/rule-learning/read", "/api/rule-learning/rollback", "/api/real-trades/read", "/api/real-trades/write", "/api/real-trades/curve", "/api/real-trades/risk", "/api/real-trades/confirm-sale", "/api/audit/read", "/api/audit/write", "/api/trade-email/read", "/api/push/test-background", "/api/push/selection", "/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences") and not worker_ok and (not self.authenticated()):
            self.send_response(401)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        if path in ("/api/degiro/candidate-proof", "/api/degiro/list-correction", "/api/degiro/android-observations"):
            # Only an authenticated user in this site's own UI can submit a
            # candidate image observation. A worker token is insufficient.
            if not self.authenticated():
                bob_auth.send(self, 401)
                return
            if not bob_auth.same_origin(self.headers):
                bob_auth.send(self, 403)
                return
        path = urlparse(self.path).path
        if path not in ("/api/improvement/read", "/api/research/video-evidence", "/api/ranking-learning/control", "/api/precision-learning/control", "/api/degiro/venue", "/api/degiro/candidate-proof", "/api/degiro/list-correction", "/api/degiro/android-observations", "/api/rule-learning/read", "/api/rule-learning/rollback", "/api/real-trades/read", "/api/real-trades/write", "/api/real-trades/curve", "/api/real-trades/risk", "/api/real-trades/confirm-sale", "/api/audit/read", "/api/audit/write", "/api/trade-email/read", "/api/push/test-background", "/api/push/selection", "/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences", "/api/push/device-receipt"):
            self.send_response(404)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Not found.")
            return

        if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"error":"Push-Service nicht konfiguriert"}'.encode("utf-8"))
            return

        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0 or length > (1024 if path == "/api/push/device-receipt" else 800000 if path == "/api/research/video-evidence" else 524288 if path in ("/api/push/selection", "/api/audit/write") else 65536):
                raise ValueError("Ungültige Payload-Größe")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            base = PUSH_SERVICE_URL
            if not base.startswith("http://") and not base.startswith("https://"):
                base = "http://" + base
            relay_path = {
                "/api/research/video-evidence": "/research-video/evidence",
                "/api/degiro/venue": "/broker-venue/write",
                "/api/degiro/candidate-proof": "/candidate-proof/write",
                "/api/degiro/list-correction": "/list-correction",
                "/api/degiro/android-observations": "/android-observations",
                "/api/ranking-learning/control": "/ranking-learning/control",
                "/api/precision-learning/control": "/precision-learning/control",
                "/api/rule-learning/read": "/rule-learning/read",
                "/api/rule-learning/rollback": "/rule-learning/rollback",
                "/api/real-trades/read": "/real-trades/read",
                "/api/real-trades/write": "/real-trades/write",
                "/api/real-trades/curve": "/real-trades/curve",
                "/api/real-trades/risk": "/real-trades/risk",
                "/api/real-trades/confirm-sale": "/real-trades/confirm-sale",
                "/api/improvement/read": "/improvement/read",
                "/api/audit/read": "/decision-audit/read",
                "/api/trade-email/read": "/email-import/read",
                "/api/audit/write": "/decision-audit/write",
                "/api/push/test-background": "/test-background",
                "/api/push/selection": "/selection",
                "/api/push/send": "/send",
                "/api/push/subscribe": "/subscribe",
                "/api/push/unsubscribe": "/unsubscribe",
                "/api/push/preferences": "/preferences",
                "/api/push/device-receipt": "/device-receipt",
            }[path]
            req = Request(
                base.rstrip("/") + relay_path,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Bob-Push-Token": PUSH_SERVICE_TOKEN,
                    "Accept": "application/json",
                },
            )
            # Audit reports may recover from a 10s database cancellation and
            # retry a smaller window; allow the bounded recovery to finish.
            relay_timeout = 45 if path in ("/api/audit/read", "/api/improvement/read") else 12
            with urlopen(req, timeout=relay_timeout) as response:
                result = response.read()
                status = response.status
            if path == "/api/trade-email/read" and status == 200:
                record = json.loads(result)
                record["configured"] = bool(os.environ.get("BOB_AGENTMAIL_WEBHOOK_SECRET") and
                                            os.environ.get("BOB_EMAIL_ALLOWED_FROM"))
                result = json.dumps(record, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(result)
        except HTTPError as exc:
            body = exc.read() or b'{"error":"Push-Service-Fehler"}'
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ValueError, json.JSONDecodeError):
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"error":"Ungültige Push-Payload"}'.encode("utf-8"))
        except (URLError, TimeoutError):
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"error":"Push-Service nicht erreichbar"}'.encode("utf-8"))

    def log_message(self, fmt, *args):
        # Explicit runtime access logging. Render HTTP request logs are not
        # available on every workspace tier, so keep a compact server-side
        # trace for diagnosing browser -> Render connectivity.
        try:
            request_id = self.headers.get("Rndr-Id", "-")
            print(f"BOB_HTTP path={urlparse(self.path).path} method={self.command} status={args[1] if len(args)>1 else '-'} rndr_id={request_id}", flush=True)
        except Exception:
            pass

def fibonacci_monitor_loop():
    """Monitor registered active trades using existing free services."""
    if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
        FIB_MONITOR_HEALTH["status"] = "unconfigured"
        print("BOB_FIB monitor_unconfigured", flush=True)
        return
    base = PUSH_SERVICE_URL.rstrip("/")
    if not base.startswith(("https://", "http://")):
        base = "http://" + base
    while True:
        remaining = background_push.gold_weekend_seconds_remaining()
        if remaining:
            FIB_MONITOR_HEALTH.update(status="paused", lastCheckedAt=int(time.time()))
            print("BOB_FIB weekend_paused", flush=True)
            time.sleep(remaining)
            continue
        cycle_started = time.monotonic()
        poll_seconds = 30  # Connection failure: retry promptly to protect an unknown active trade.
        try:
            request = Request(base+"/monitor-status", headers={"X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
            with urlopen(request, timeout=10) as response:
                monitors = json.loads(response.read(4096))
                active = monitors.get("activeMonitors", 0)
                active_trades = monitors.get("activeTrades", 0)
            poll_seconds = background_push.degiro_poll_seconds(active_trade=bool(active_trades))
            FIB_MONITOR_HEALTH.update(status="checking", lastCheckedAt=int(time.time()),
                                      expectedCycleSeconds=poll_seconds, session=background_push.degiro_session())
            background_ok = True
            print("BOB_FIB monitor_connected active="+str(active), flush=True)
            # A paper-trading forward test must receive market bundles even with
            # the browser closed, no Push subscriber and the old four-day study ended.
            # Only trading hours initiate fresh product analysis.
            if active or intraday_comparison.active() or background_push.degiro_session() == "trading":
                try:
                    bundle = build_live_bundle()
                    bars = bundle.get("history", {}).get("bars_by_tf", {})
                except Exception:
                    bundle = {}
                    bars = {}  # Let the push monitor announce a data outage once.
                import diagnostic_history
                source_trace = diagnostic_history.trace(bundle)
                diagnostic_history.emit('input', source_trace, {**(bundle.get('spots') or {}), 'fetchedAt':bundle.get('fetched_at')})
                background_bundle = {**bundle, "history":{**bundle.get("history",{}),"bars_by_tf":{tf:bars.get(tf,[])[-240:] for tf in ("1m","5m","15m","1h","4h")}}}
                request = Request(base+"/background",data=json.dumps({"bundle":background_bundle}).encode(),method="POST",headers={"Content-Type":"application/json","X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
                try:
                    with urlopen(request,timeout=45) as response:
                        background_result=json.loads(response.read(4096))
                    diagnostic_history.emit('transport', source_trace, {'outcome':'background-accepted'})
                    print("BOB_BACKGROUND checked sent="+str(background_result.get('sent',0)),flush=True)
                except Exception as exc:
                    background_ok = False
                    diagnostic_history.emit('transport', source_trace, {'outcome':'background-failed','errorType':type(exc).__name__})
                    print("BOB_BACKGROUND error="+type(exc).__name__,flush=True)
                if active:
                    payload = {"barsByTf":{tf:bars.get(tf, [])[-12:] for tf in ("5m","15m","1h")}}
                    request = Request(base+"/monitor", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type":"application/json","X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
                    with urlopen(request, timeout=20) as response:
                        result = json.loads(response.read(4096))
                    print("BOB_FIB monitor_checked active="+str(active)+" sent="+str(result.get("sent",0)), flush=True)
            if background_ok:
                FIB_MONITOR_HEALTH.update(status="active" if active else "idle", lastSuccessAt=int(time.time()))
            else:
                FIB_MONITOR_HEALTH.update(status="unavailable")
        except Exception as exc:
            FIB_MONITOR_HEALTH.update(status="unavailable", lastCheckedAt=int(time.time()))
            print("BOB_FIB monitor_error="+type(exc).__name__, flush=True)
        time.sleep(max(1, poll_seconds - (time.monotonic() - cycle_started)))

_AGENTMAIL_RECOVERY_THREAD = None
_AGENTMAIL_RECOVERY_LOCK = threading.Lock()

def _agentmail_recovery_loop():
    """Read-only fallback for missed webhook events and original-DEGIRO receipts."""
    import agentmail_receipt_recovery
    while True:
        phase="agentmail-read"
        try:
            records = agentmail_receipt_recovery.recover(
                os.environ.get("BOB_AGENTMAIL_API_KEY", ""),
                os.environ.get("BOB_EMAIL_ALLOWED_FROM", ""))
            phase="private-import"
            count = agentmail_receipt_recovery.submit(
                records, PUSH_SERVICE_URL, PUSH_SERVICE_TOKEN)
            print("BOB_EMAIL_RECOVERY status=ok checked="+str(len(records))+
                  " transmitted="+str(count),flush=True)
        except Exception as exc:
            # Never log URL, mailbox content, API key or bearer credentials.
            from urllib.error import HTTPError
            http_status=exc.code if isinstance(exc,HTTPError) else "n/a"
            print("BOB_EMAIL_RECOVERY status=error phase="+phase+
                  " kind="+type(exc).__name__+
                  " httpStatus="+str(http_status),flush=True)
        time.sleep(30)

def start_agentmail_recovery():
    global _AGENTMAIL_RECOVERY_THREAD
    if not all((os.environ.get("BOB_AGENTMAIL_API_KEY"),
                os.environ.get("BOB_EMAIL_ALLOWED_FROM"),
                PUSH_SERVICE_URL, PUSH_SERVICE_TOKEN)):
        print("BOB_EMAIL_RECOVERY status=not-configured",flush=True)
        return
    with _AGENTMAIL_RECOVERY_LOCK:
        if _AGENTMAIL_RECOVERY_THREAD is None or not _AGENTMAIL_RECOVERY_THREAD.is_alive():
            _AGENTMAIL_RECOVERY_THREAD=threading.Thread(
                target=_agentmail_recovery_loop,name="bob-agentmail-recovery",daemon=True)
            _AGENTMAIL_RECOVERY_THREAD.start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print(f"BOB_START port={port} host=0.0.0.0 version=runtime-http-trace-v2 process={PROCESS_ID}", flush=True)
    # Attribute scanner/container peaks before starting background fetchers.
    # Counts and sizes only: no request data, credentials or trading payloads.
    import memory_watch
    memory_watch.start(reclaim=True)
    candle_reliability.start()
    ensure_fibonacci_monitor()
    auto_collection.start()
    degiro_catalog.start()
    strategy_lab_background.start(fetch_technical_history, mark_bar_state)
    gold_research.start()
    start_healing_watch()
    start_agentmail_recovery()
    import weekend_archive
    weekend_archive.start(build_live_bundle,market_cards.snapshot)
    BobHTTPServer(("0.0.0.0", port), Handler).serve_forever()

# Bob maintenance marker: 4h MTF upgrade in progress







