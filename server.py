import intraday_comparison
import os
import base64
import hmac
import json
import math
import time
import threading
import bob_auth
import auto_collection
import ocr_assets
import product_quotes
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

USER = os.environ.get("BOB_USER", "")
PASSWORD = os.environ.get("BOB_PASSWORD", "")
PUSH_SERVICE_URL = os.environ.get("PUSH_SERVICE_URL", "")
PUSH_SERVICE_TOKEN = os.environ.get("PUSH_SERVICE_TOKEN", "")
SIGNAL_WORKER_TOKEN = os.environ.get("SIGNAL_WORKER_TOKEN", "")
FIB_MONITOR_HEALTH = {"configured": bool(PUSH_SERVICE_URL and PUSH_SERVICE_TOKEN), "status": "starting", "lastCheckedAt": None, "lastSuccessAt": None}

def background_health():
    """Only a completed cycle proves that background monitoring works."""
    state = dict(FIB_MONITOR_HEALTH)
    last = state.get("lastSuccessAt")
    age = max(0, int(time.time()) - last) if last is not None else None
    healthy = bool(state["configured"] and age is not None and age <= 120
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
SW = SW_PATH.read_bytes() if SW_PATH.exists() else None
MANIFEST = MANIFEST_PATH.read_bytes() if MANIFEST_PATH.exists() else None
ICON = ICON_PATH.read_bytes() if ICON_PATH.exists() else None
# Legacy push module fallback. Product import uses its tracked source file below
# so the tested and served implementation cannot diverge after a deployment.
PUSH_MANAGER_JS = '/* Bob Push Manager: browser notification + optional server Web Push registration. */\n(function(){\n  const KEY="bobPushV1", LEGACY="goldScannerPush";\n  const PUSH_API="/api/push";\n  const defaults={registered:false,serverRegistered:false,general:false,trade:false,activeTrade:false};\n  function read(){\n    try{\n      const raw=localStorage.getItem(KEY);\n      if(raw)return {...defaults,...JSON.parse(raw)};\n      const old=localStorage.getItem(LEGACY);\n      if(old)return {...defaults,...JSON.parse(old)};\n    }catch(_){}\n    return {...defaults};\n  }\n  function save(s){const next={...defaults,...s};try{localStorage.setItem(KEY,JSON.stringify(next));}catch(_){}return next;}\n  function b64ToBytes(value){\n    const pad="=".repeat((4-(value.length%4))%4);\n    const raw=atob(value.replace(/-/g,"+").replace(/_/g,"/")+pad);\n    return Uint8Array.from(raw,c=>c.charCodeAt(0));\n  }\n  async function registerServerPush(reg){\n    try{\n      const keyRes=await fetch(PUSH_API+"/vapid-public-key",{cache:"no-store"});\n      if(!keyRes.ok)throw new Error("VAPID-Key konnte nicht geladen werden.");\n      const {publicKey}=await keyRes.json();\n      if(!publicKey)throw new Error("VAPID-Key fehlt.");\n      if(!reg.pushManager)return false;\n      // Recreate the browser subscription with the current VAPID public key.\n      // This repairs subscriptions created with a previous VAPID key after a\n      // server-side key rotation or a recreated push database.\n      let sub=await reg.pushManager.getSubscription();\n      if(sub){\n        try{\n          await fetch(PUSH_API+"/unsubscribe",{\n            method:"POST",\n            headers:{"Content-Type":"application/json"},\n            body:JSON.stringify({endpoint:sub.endpoint})\n          });\n        }catch(_){}\n        try{await sub.unsubscribe();}catch(_){}\n        sub=null;\n      }\n      sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(publicKey)});\n      const res=await fetch(PUSH_API+"/subscribe",{\n        method:"POST",\n        headers:{"Content-Type":"application/json"},\n        body:JSON.stringify({subscription:sub.toJSON()})\n      });\n      if(!res.ok)throw new Error("Push-Subscription konnte nicht gespeichert werden.");\n      return true;\n    }catch(_){return false;}\n  }\n  async function enable(){\n    if(!("Notification" in window))throw new Error("Web-Benachrichtigungen werden von diesem Browser nicht unterstützt.");\n    const p=await Notification.requestPermission();\n    if(p!=="granted")throw new Error("Benachrichtigungen wurden nicht freigegeben.");\n    let serverRegistered=false;\n    if("serviceWorker" in navigator){\n      const reg=await navigator.serviceWorker.register("/sw.js",{updateViaCache:"none"});\n      try{await reg.update();}catch(_){}\n      serverRegistered=await registerServerPush(reg);\n    }\n    const next=save({...read(),registered:true,serverRegistered});syncWorkerPreferences();return next;\n  }\n  function state(){return read();}\n  function allowed(kind){\n    const s=read();\n    return s.registered&&Notification.permission==="granted"&&s[kind]===true&&(kind!=="trade"||s.activeTrade===true);\n  }\n  async function emit(kind,title,body,data={}){\n    if(read().backgroundEnabled&&!data.test)return false;\n    // Generic notification calls must never bypass the dedicated server selection check.\n    if(data.isin||/product|best.trade|produktempfehl|bester trade/i.test([kind,data.kind,title].join(\' \')))return false;\n    const testTrade=kind==="trade"&&data&&data.test===true;\n    if(testTrade){\n      const s=read();\n      if(!(s.registered&&Notification.permission==="granted"&&s.trade===true))return false;\n    }else if(!allowed(kind))return false;\n    const tag="bob-"+kind+"-"+(data.signalId||"current");\n    if(!data.test){\n      const at=Number(data.candleClosedAt||data.dataAt);\n      body+=\' · Datenzeit: \'+(at>0?new Date(at).toLocaleString(\'de-CH\',{timeZone:\'Europe/Zurich\'}):\'unbekannt\')+\'.\';\n    }\n    title=(data.test?"TEST · ":kind==="trade"?"TRADE-WARNUNG · ":"MARKTSIGNAL · ")+title;\n    const payload={title,body,data:{...data,url:data.url||"/",kind,signalId:data.signalId||null},tag};\n    let serverSent=false;\n    if(read().serverRegistered){\n      try{\n        const res=await fetch("/api/push/send",{\n          method:"POST",\n          headers:{"Content-Type":"application/json"},\n          body:JSON.stringify(payload)\n        });\n        if(res.ok){\n          const result=await res.json().catch(()=>null);\n          serverSent=Boolean(result&&result.sent>0);\n          if(result&&result.vapidReset){\n            const reg=await navigator.serviceWorker.ready;\n            serverSent=await registerServerPush(reg);\n            if(serverSent){\n              const retry=await fetch("/api/push/send",{\n                method:"POST",\n                headers:{"Content-Type":"application/json"},\n                body:JSON.stringify(payload)\n              });\n              if(retry.ok){\n                const retryResult=await retry.json().catch(()=>null);\n                serverSent=Boolean(retryResult&&retryResult.sent>0);\n              }\n            }\n          }\n        }\n      }catch(_){}\n    }\n    if(serverSent)return true;\n    const options={body,tag,data:{url:data.url||"/",kind,signalId:data.signalId||null},renotify:false};\n    try{\n      if("serviceWorker" in navigator){\n        const reg=await navigator.serviceWorker.ready;\n        await reg.showNotification(title,options);\n        return true;\n      }\n      new Notification(title,options);\n      return true;\n    }catch(_){return false;}\n  }\n  function activeTradeId(){try{const t=JSON.parse(localStorage.getItem(\'goldScannerTradeMgmt\')||\'{}\');return t.tradeId||t.fibonacciMonitor?.tradeId||null;}catch(_){return null;}}\n  function syncWorkerPreferences(){\n    if(!(\'serviceWorker\' in navigator))return;\n    navigator.serviceWorker.ready.then(reg=>reg.active?.postMessage({type:\'BOB_PUSH_PREFERENCES\',general:read().general===true,trade:read().trade===true,activeTrade:read().activeTrade===true,tradeId:activeTradeId()})).catch(()=>{});\n  }\n  let selectionBusy=false,selectionLastAt=0,selectionLastKey=\'\',selectionGeneration=0;\n  function productStatus(text){const el=typeof document!==\'undefined\'?document.getElementById(\'productPushStatus\'):null;if(el)el.textContent=text;}\n  async function updateSelection(evidence,flow){\n    const s=read();\n    if(!s.general){productStatus(\'Produktpush: aus – Marktsignale sind deaktiviert.\');return false;}\n    if(!s.serverRegistered||!allowed(\'general\')){productStatus(\'Produktpush: Gerät für Server-Push registrieren.\');return false;}\n    const key=JSON.stringify([flow.direction,flow.groups.map(g=>[g.scope,g.candidates.map(p=>p.isin)]),flow.gateReasons]);\n    if(selectionBusy||(key===selectionLastKey&&Date.now()-selectionLastAt<10000))return false;\n    selectionBusy=true;const generation=selectionGeneration;\n    try{\n      const reg=await navigator.serviceWorker.ready,sub=await reg.pushManager.getSubscription();\n      if(!sub||!read().general||generation!==selectionGeneration)return false;\n      const payload={...evidence,capturedAt:Date.now(),endpoint:sub.endpoint};\n      const res=await fetch(\'/api/push/selection\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(payload)});\n      const result=res.ok?await res.json():null;\n      if(generation!==selectionGeneration||!read().general)return false;\n      selectionLastAt=Date.now();selectionLastKey=key;\n      productStatus(!result?\'Produktpush: Serverprüfung derzeit nicht erreichbar; keine neue Empfehlung.\':result.disabled?\'Produktpush: Marktsignale serverseitig aus – Einstellung erneut synchronisieren.\':result.approvedCount?\'Produktpush: \'+result.approvedCount+\' Produkt(e) serverseitig geprüft. \'+(result.sent?\'Benachrichtigung versandt.\':\'Unveränderte Auswahl / Wiederholung unterdrückt.\'):\'Produktpush: Abwarten – keine freigegebene Auswahl.\');\n      return Boolean(result?.sent);\n    }catch(_){selectionLastAt=Date.now();selectionLastKey=key;productStatus(\'Produktpush: Serverprüfung nicht erreichbar; keine neue Empfehlung.\');return false;}\n    finally{selectionBusy=false;}\n  }\n  function set(kind,value){\n    const next=save({...read(),[kind]:Boolean(value)});\n    if(kind===\'trade\'||kind===\'activeTrade\')syncWorkerPreferences();\n    if(kind===\'general\'){selectionGeneration++;selectionLastAt=0;selectionLastKey=\'\';syncWorkerPreferences();}\n    return next;\n  }\n  function setActiveTrade(value){return set("activeTrade",value);}\n  window.BobPush={state,save,enable,allowed,emit,set,setActiveTrade,updateSelection,syncWorkerPreferences};\n  syncWorkerPreferences();\n\n  // Active-trade push monitor. This intentionally stays in the push layer:\n  // it does not place orders or alter market/DEGIRO logic. It only triggers\n  // the existing stop-management suggestion and a close recommendation when\n  // the stored active-trade stop is actually breached.\n  function activeTradePushMonitor(){\n    try{\n      const s=read();\n      if(s.backgroundEnabled||!s.registered||!s.trade||!s.activeTrade)return;\n      const raw=localStorage.getItem("goldScannerTradeMgmt");\n      if(!raw)return;\n      const t=JSON.parse(raw);\n      if(!t?.active||!t?.dir||!Number.isFinite(Number(t.stop)))return;\n\n      const priceEl=document.getElementById("tradePrice");\n      const liveEl=document.getElementById("price");\n      const p=Number(priceEl?.value)||Number.parseFloat(String(liveEl?.textContent||"").replace(",","."));\n      if(!Number.isFinite(p))return;\n\n      // Stop proximity/breach transitions are owned by maybePushAnalysisAlerts.\n      // Keep a single alert producer; the second monitor only updates stops.\n      // Let Bob\'s existing, tested stop model decide whether the stop can be\n      // improved. The function itself emits "Stop-Loss anpassen" only when the\n      // new stop is genuinely better, so normal price noise stays silent.\n      const stopBtn=document.querySelector(\'button[onclick="suggestStopUpdate()"]\');\n      if(stopBtn && typeof window.suggestStopUpdate==="function"){\n        stopBtn.click();\n      }\n    }catch(e){\n      // Push monitoring must never interfere with the rest of Bob.\n      console.warn("Bob active-trade push monitor",e);\n    }\n  }\n\n  window.addEventListener("load",()=>{\n    setTimeout(activeTradePushMonitor,1500);\n    setInterval(activeTradePushMonitor,60000);\n  });\n})()'
DEGIRO_ASSISTANT_JS = (BASE_DIR / "degiro_assistant.js").read_text(encoding="utf-8")
UPSTREAM_TIMEOUT = 4
FRESH_MAX_AGE = 180
LIVE_CACHE_TTL = 20
FX_CACHE_TTL = 900
_live_cache = None
_live_cache_at = 0.0
_fx_cache = {"EUR": None, "CHF": None}
_fx_cache_at = 0.0
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
    base = {15: 5, 240: 60}.get(minutes)
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
                        isOpen=now_ms<ts+step or any(b.get('isOpen',False) for b in items)))
    return out


_technical_history = {}
_technical_history_lock = threading.Lock()


def retain_technical_history(interval, rows):
    # Preserve source clocks when secondary work misses the HTTP deadline.
    minutes = technical_candles.MINUTES[interval]
    with _technical_history_lock:
        old = _technical_history.get(interval, [])
        if rows and technical_history_latest(rows, minutes) >= technical_history_latest(old, minutes):
            _technical_history[interval] = [dict(row) for row in rows]
        return [dict(row) for row in _technical_history.get(interval, [])]


def technical_history_latest(bars, minutes, now=None):
    now = time.time() if now is None else now
    step = minutes*60*1000
    return max((b['openTime'] for b in bars if not b.get('isOpen') and b['openTime']+step <= now*1000), default=0)


def technical_history_fresh(bars, minutes, now=None):
    now = time.time() if now is None else now
    latest = technical_history_latest(bars, minutes, now)
    return bool(latest and 0 <= now*1000-latest <= minutes*120000)


def fetch_technical_history(interval, range_value):
    primary = []
    minutes = technical_candles.MINUTES[interval]
    independent = technical_candles.fetch(interval, fetch_json)
    if independent:
        retain_technical_history(interval, independent)
        if technical_history_fresh(independent, minutes):
            return independent
    if interval in ("1m", "15m", "4h"):
        return retain_technical_history(interval, independent)
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
            out = normalize_chart_points(points, 5 if interval == '5m' else 60)
            rejected = len(points)-len(out)
            if rejected:
                print(f'BOB_HISTORY interval={interval} excluded_non_candles={rejected}',flush=True)
            if out:
                primary = out
                retain_technical_history(interval, out)
                if technical_history_fresh(out, minutes):
                    return out
    except Exception:
        pass

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


def build_live_bundle():
    """Build Bob's live bundle without letting slow secondary sources block the spot heartbeat.

    XAU/USD spot, technical history and FX are fetched concurrently. A valid spot
    response is returned even when technical history or FX is temporarily slow.
    """
    global _live_cache, _live_cache_at, _fx_cache, _fx_cache_at
    if _live_cache is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
        return _live_cache

    with _live_lock:
        if _live_cache is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
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
                    if rate and rate > 0:
                        rates[ccy] = rate
                        _fx_cache[ccy] = rate
                    else:
                        errors.append(f"Ungültige {ccy}-FX-Rate")
                except Exception as exc:
                    errors.append(str(exc))
            _fx_cache_at = time.time()
            return rates["EUR"] or _fx_cache["EUR"], rates["CHF"] or _fx_cache["CHF"], errors

        # The spot price is the primary heartbeat. Do NOT wait for every secondary
        # source: ThreadPoolExecutor's context manager would otherwise wait for slow
        # Yahoo/FX requests at shutdown and keep /api/live hanging.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        pool = ThreadPoolExecutor(max_workers=7, thread_name_prefix="bob-live")
        futures = {
            pool.submit(fetch_spot): "spot",
            pool.submit(fetch_technical_history, "5m", "5d"): "5m",
            pool.submit(fetch_technical_history, "1h", "3mo"): "1h",
            pool.submit(fetch_technical_history, "15m", "5d"): "15m",
            pool.submit(fetch_technical_history, "4h", "3mo"): "4h",
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

        if goldprice_price is None:
            # Never promote technical/futures history to the XAU/USD spot field.
            # A GC=F close is a futures reference, not a spot price, and must not
            # masquerade as live XAU/USD data when the genuine spot source fails.
            raise RuntimeError("Kein kostenloser Live-XAU/USD-Spotpreis verfügbar" + (f": {spot_error}" if spot_error else ""))

        bars_15m = aggregate_bars(bars_5m, 15) if bars_5m else []
        bars_4h = aggregate_bars(bars_1h, 240) if bars_1h else []
        # Native longer timeframes retain more history than a short 5m window.
        for tf, minutes in (("15m", 15), ("4h", 240)):
            native = results.get(tf)
            if not isinstance(native, list):
                native = retain_technical_history(tf, [])
            if native and technical_history_fresh(native, minutes):
                mark_bar_state(native, minutes)
                if tf == '15m': bars_15m = native
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

        status = "fresh" if goldprice_age is not None and goldprice_age <= FRESH_MAX_AGE else "partial"
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
                "usd_chf": usd_chf,
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
                "bars_by_tf": {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m, "1h": bars_1h, "4h": bars_4h},
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
    step={"5m":300000,"15m":900000,"1h":3600000,"4h":14400000}.get(tf,900000)
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

class Handler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            # A navigation/refresh can close the client after a successful upstream call.
            # Never retry that completed POST or send a second HTTP response.
            self.close_connection = True

    def authenticated(self):
        return bob_auth.authenticated(self.headers, USER, PASSWORD)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith(ocr_assets.PREFIX):
            ocr_assets.serve(self, path)
            return
        if path == "/login":
            bob_auth.login_page(self)
            return
        if path in ("/", "/index.html", "/bob-live", "/bob-v12") and not self.authenticated():
            bob_auth.send(self, 303, location="/login")
            return
        # Sensitive data APIs must be authenticated before any data generation.
        # Keep static PWA resources and /health public, but never expose live,
        # MTF, or DEGIRO enrichment data without the existing Bob credentials.
        protected_api_path = path in ("/api/live", "/api/mtf", "/api/degiro/enrich", "/api/collection-status", "/api/market-cards", "/api/economic-calendar", "/api/gold-research")
        if protected_api_path:
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

        if path == "/api/gold-research":
            body = json.dumps(gold_research.snapshot(), ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/collection-status":
            body = json.dumps(auto_collection.status(), ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/degiro/enrich":
            try:
                query = parse_qs(urlparse(self.path).query)
                isin = (query.get("isin") or [""])[0].strip().upper()
                if len(isin) != 12:
                    raise ValueError("ISIN fehlt oder ist ungültig")
                result = enrich_degiro_product(isin)
                body = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                body = json.dumps({"found":False,"source":"Emittentenrecherche","reason":"Zusatzprüfung momentan nicht verfügbar","checkedAt":datetime.now(timezone.utc).isoformat()}, ensure_ascii=False).encode("utf-8")
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
            auto_collection.start()
            body = json.dumps({"status":"ok","service":"bob","fibonacciMonitor":dict(FIB_MONITOR_HEALTH),"automaticCollection":auto_collection.health()},separators=(",",":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        # Public read-only app resources. No credentials or secrets are returned here.
        # This is required for normal PWA/browser fetch behavior after the initial protected page load.
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

        if path == "/degiro_assistant.js":
            try:
                body = DEGIRO_ASSISTANT_JS.encode("utf-8")
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
                payload = trade_reference.lookup(raw)
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
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; img-src 'self' data:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
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
                "img-src 'self' data:; "
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
            bob_auth.send(self, 303, location="/login")
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
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; img-src 'self' data:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            bob_auth.login(self, USER, PASSWORD)
            return
        if path == "/logout":
            bob_auth.logout(self)
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
                result = {'ok': True, 'item': youtube_research.manual(payload)}
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
                event = str(payload.get("event", "unknown"))[:80]
                details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
                safe = {}
                for key in ("bars5m","bars15m","bars1h","bars4h","available","overall","error","reason","historyStatus","source","direct","server"):
                    if key in details:
                        value = details[key]
                        safe[key] = str(value)[:300] if isinstance(value, str) else value
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

        if path in ("/api/audit/read", "/api/audit/write", "/api/push/test-background", "/api/push/selection", "/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences") and not worker_ok and (not self.authenticated()):
            self.send_response(401)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        path = urlparse(self.path).path
        if path not in ("/api/audit/read", "/api/audit/write", "/api/push/test-background", "/api/push/selection", "/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences"):
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
            if length <= 0 or length > (524288 if path == "/api/push/selection" else 65536):
                raise ValueError("Ungültige Payload-Größe")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            base = PUSH_SERVICE_URL
            if not base.startswith("http://") and not base.startswith("https://"):
                base = "http://" + base
            relay_path = {
                "/api/audit/read": "/decision-audit/read",
                "/api/audit/write": "/decision-audit/write",
                "/api/push/test-background": "/test-background",
                "/api/push/selection": "/selection",
                "/api/push/send": "/send",
                "/api/push/subscribe": "/subscribe",
                "/api/push/unsubscribe": "/unsubscribe",
                "/api/push/preferences": "/preferences",
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
            with urlopen(req, timeout=12) as response:
                result = response.read()
                status = response.status
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
            print(f"BOB_HTTP path={self.path} method={self.command} status={args[1] if len(args)>1 else '-'} rndr_id={request_id}", flush=True)
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
        cycle_started = time.monotonic()
        try:
            request = Request(base+"/monitor-status", headers={"X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
            with urlopen(request, timeout=10) as response:
                active = json.loads(response.read(4096)).get("activeMonitors", 0)
            FIB_MONITOR_HEALTH.update(status="checking", lastCheckedAt=int(time.time()))
            background_ok = True
            print("BOB_FIB monitor_connected active="+str(active), flush=True)
            if active or intraday_comparison.active():
                try:
                    bundle = build_live_bundle()
                    bars = bundle.get("history", {}).get("bars_by_tf", {})
                except Exception:
                    bundle = {}
                    bars = {}  # Let the push monitor announce a data outage once.
                background_bundle = {**bundle, "history":{**bundle.get("history",{}),"bars_by_tf":{tf:bars.get(tf,[])[-240:] for tf in ("5m","15m","1h","4h")}}}
                request = Request(base+"/background",data=json.dumps({"bundle":background_bundle}).encode(),method="POST",headers={"Content-Type":"application/json","X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
                try:
                    with urlopen(request,timeout=45) as response:
                        background_result=json.loads(response.read(4096))
                    print("BOB_BACKGROUND checked sent="+str(background_result.get('sent',0)),flush=True)
                except Exception as exc:
                    background_ok = False
                    print("BOB_BACKGROUND error="+type(exc).__name__,flush=True)
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
        time.sleep(max(1, 30 - (time.monotonic() - cycle_started)))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print(f"BOB_START port={port} host=0.0.0.0 version=runtime-http-trace-v1", flush=True)
    threading.Thread(target=fibonacci_monitor_loop, name="bob-fibonacci", daemon=True).start()
    auto_collection.start()
    gold_research.start()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

# Bob maintenance marker: 4h MTF upgrade in progress




