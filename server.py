import os
import base64
import hmac
import json
import time
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USER = os.environ.get("BOB_USER", "")
PASSWORD = os.environ.get("BOB_PASSWORD", "")
PUSH_SERVICE_URL = os.environ.get("PUSH_SERVICE_URL", "")
PUSH_SERVICE_TOKEN = os.environ.get("PUSH_SERVICE_TOKEN", "")
SIGNAL_WORKER_TOKEN = os.environ.get("SIGNAL_WORKER_TOKEN", "")

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "Bob.html"
SW_PATH = BASE_DIR / "sw.js"
MANIFEST_PATH = BASE_DIR / "manifest.json"
ICON_PATH = BASE_DIR / "icon.svg"
# Runtime-module fallback: Render must serve these two browser modules even if
# the deployed filesystem snapshot omits an untracked/static file. Keeping the
# source embedded here makes the JS delivery independent of that filesystem edge case.
PUSH_MANAGER_JS = "/* Bob Push Manager: browser notification + optional server Web Push registration. */\n(function(){\n  const KEY=\"bobPushV1\", LEGACY=\"goldScannerPush\";\n  const PUSH_API=\"/api/push\";\n  const defaults={registered:false,serverRegistered:false,general:false,trade:false,activeTrade:false};\n  function read(){\n    try{\n      const raw=localStorage.getItem(KEY);\n      if(raw)return {...defaults,...JSON.parse(raw)};\n      const old=localStorage.getItem(LEGACY);\n      if(old)return {...defaults,...JSON.parse(old)};\n    }catch(_){}\n    return {...defaults};\n  }\n  function save(s){const next={...defaults,...s};try{localStorage.setItem(KEY,JSON.stringify(next));}catch(_){}return next;}\n  function b64ToBytes(value){\n    const pad=\"=\".repeat((4-(value.length%4))%4);\n    const raw=atob(value.replace(/-/g,\"+\").replace(/_/g,\"/\")+pad);\n    return Uint8Array.from(raw,c=>c.charCodeAt(0));\n  }\n  async function registerServerPush(reg){\n    try{\n      const keyRes=await fetch(PUSH_API+\"/vapid-public-key\",{cache:\"no-store\"});\n      if(!keyRes.ok)throw new Error(\"VAPID-Key konnte nicht geladen werden.\");\n      const {publicKey}=await keyRes.json();\n      if(!publicKey)throw new Error(\"VAPID-Key fehlt.\");\n      if(!reg.pushManager)return false;\n      // Recreate the browser subscription with the current VAPID public key.\n      // This repairs subscriptions created with a previous VAPID key after a\n      // server-side key rotation or a recreated push database.\n      let sub=await reg.pushManager.getSubscription();\n      if(sub){\n        try{\n          await fetch(PUSH_API+\"/unsubscribe\",{\n            method:\"POST\",\n            headers:{\"Content-Type\":\"application/json\"},\n            body:JSON.stringify({endpoint:sub.endpoint})\n          });\n        }catch(_){}\n        try{await sub.unsubscribe();}catch(_){}\n        sub=null;\n      }\n      sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(publicKey)});\n      const res=await fetch(PUSH_API+\"/subscribe\",{\n        method:\"POST\",\n        headers:{\"Content-Type\":\"application/json\"},\n        body:JSON.stringify({subscription:sub.toJSON()})\n      });\n      if(!res.ok)throw new Error(\"Push-Subscription konnte nicht gespeichert werden.\");\n      return true;\n    }catch(_){return false;}\n  }\n  async function enable(){\n    if(!(\"Notification\" in window))throw new Error(\"Web-Benachrichtigungen werden von diesem Browser nicht unterstützt.\");\n    const p=await Notification.requestPermission();\n    if(p!==\"granted\")throw new Error(\"Benachrichtigungen wurden nicht freigegeben.\");\n    let serverRegistered=false;\n    if(\"serviceWorker\" in navigator){\n      const reg=await navigator.serviceWorker.register(\"/sw.js\",{updateViaCache:\"none\"});\n      try{await reg.update();}catch(_){}\n      serverRegistered=await registerServerPush(reg);\n    }\n    return save({...read(),registered:true,serverRegistered});\n  }\n  function state(){return read();}\n  function allowed(kind){\n    const s=read();\n    return s.registered&&Notification.permission===\"granted\"&&s[kind]===true&&(kind!==\"trade\"||s.activeTrade===true);\n  }\n  async function emit(kind,title,body,data={}){\n    const testTrade=kind===\"trade\"&&data&&data.test===true;\n    if(testTrade){\n      const s=read();\n      if(!(s.registered&&Notification.permission===\"granted\"&&s.trade===true))return false;\n    }else if(!allowed(kind))return false;\n    const tag=\"bob-\"+kind+\"-\"+(data.signalId||\"current\");\n    const payload={title,body,data:{...data,url:data.url||\"/\",kind,signalId:data.signalId||null},tag};\n    let serverSent=false;\n    if(read().serverRegistered){\n      try{\n        const res=await fetch(\"/api/push/send\",{\n          method:\"POST\",\n          headers:{\"Content-Type\":\"application/json\"},\n          body:JSON.stringify(payload)\n        });\n        if(res.ok){\n          const result=await res.json().catch(()=>null);\n          serverSent=Boolean(result&&result.sent>0);\n          if(result&&result.vapidReset){\n            const reg=await navigator.serviceWorker.ready;\n            serverSent=await registerServerPush(reg);\n            if(serverSent){\n              const retry=await fetch(\"/api/push/send\",{\n                method:\"POST\",\n                headers:{\"Content-Type\":\"application/json\"},\n                body:JSON.stringify(payload)\n              });\n              if(retry.ok){\n                const retryResult=await retry.json().catch(()=>null);\n                serverSent=Boolean(retryResult&&retryResult.sent>0);\n              }\n            }\n          }\n        }\n      }catch(_){}\n    }\n    if(serverSent)return true;\n    const options={body,tag,data:{url:data.url||\"/\",kind,signalId:data.signalId||null},renotify:false};\n    try{\n      if(\"serviceWorker\" in navigator){\n        const reg=await navigator.serviceWorker.ready;\n        await reg.showNotification(title,options);\n        return true;\n      }\n      new Notification(title,options);\n      return true;\n    }catch(_){return false;}\n  }\n  function set(kind,value){return save({...read(),[kind]:Boolean(value)});}\n  function setActiveTrade(value){return set(\"activeTrade\",value);}\n  window.BobPush={state,save,enable,allowed,emit,set,setActiveTrade};\n})();"
DEGIRO_ASSISTANT_JS = "/* Bob DEGIRO assistant: deterministic risk math only. No order execution and no product ranking. */\n(function(){\n  function n(v){const x=Number(v);return Number.isFinite(x)?x:null;}\n  function koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}\n  function riskModel(p){\n    const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);\n    if(spot===null||stop===null||riskEur===null||riskEur<=0)return {ok:false,reason:\"Ungültige Eingabedaten für Risiko.\"};\n    if(fx===null||fx<=0)return {ok:false,reason:\"Keine gültige USD→EUR-FX-Rate.\"};\n    const dist=Math.abs(spot-stop);\n    if(dist<=0)return {ok:false,reason:\"Stop-Distanz ist null.\"};\n    const maxLossUsd=riskEur/fx;\n    const approxNotionalUsd=maxLossUsd/(dist/spot);\n    const approxNotionalEur=approxNotionalUsd*fx;\n    const marginEur=approxNotionalEur/lev;\n    const ko=n(p.ko);\n    const koPct=koDistancePct(spot,ko);\n    const warnings=[];\n    if(ko!==null && ((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push(\"KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.\");\n    if(koPct!==null&&koPct<2)warnings.push(\"KO-Abstand liegt unter 2%.\");\n    return {ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};\n  }\n  window.BobDegiro={riskModel,koDistancePct};\n})();"
with HTML_PATH.open("rb") as f:
    HTML = f.read()
SW = SW_PATH.read_bytes() if SW_PATH.exists() else None
MANIFEST = MANIFEST_PATH.read_bytes() if MANIFEST_PATH.exists() else None
ICON = ICON_PATH.read_bytes() if ICON_PATH.exists() else None

UPSTREAM_TIMEOUT = 4
FRESH_MAX_AGE = 180
LIVE_CACHE_TTL = 65
FX_CACHE_TTL = 900
_live_cache = None
_live_cache_at = 0.0
_fx_cache = {"EUR": None, "CHF": None}
_fx_cache_at = 0.0
_live_lock = threading.Lock()

def fetch_json(url, retries=2, user_agent="Bob/1.1"):
    last_error = None
    for attempt in range(retries + 1):
        req = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
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
            time.sleep(0.6 * (attempt + 1))
    raise last_error or RuntimeError(f"Upstream nicht erreichbar ({url})")

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

def mark_bar_state(bars, minutes):
    """Mark the currently forming bar as open; never feed it into closed-bar analysis."""
    now_ms = int(time.time() * 1000)
    step = minutes * 60 * 1000
    for b in bars:
        try:
            b["isOpen"] = now_ms < int(b["openTime"]) + step
        except (TypeError, ValueError, KeyError):
            b["isOpen"] = True
    return bars

def aggregate_bars(bars, minutes):
    step = minutes * 60 * 1000
    buckets = {}
    now_ms = int(time.time() * 1000)
    for b in bars:
        try:
            ts = int(b["openTime"])
            bucket = (ts // step) * step
            if bucket not in buckets:
                buckets[bucket] = {"openTime": bucket, "open": float(b["open"]), "high": float(b["high"]), "low": float(b["low"]), "close": float(b["close"]), "isOpen": False}
            else:
                x = buckets[bucket]
                x["high"] = max(x["high"], float(b["high"]))
                x["low"] = min(x["low"], float(b["low"]))
                x["close"] = float(b["close"])
        except (TypeError, ValueError, KeyError):
            continue
    out = []
    for x in sorted(buckets.values(), key=lambda v: v["openTime"]):
        x["isOpen"] = now_ms < x["openTime"] + step
        out.append(x)
    return out

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
            last_error = None
            endpoints = [
                "https://xaus.com/api/v1/spot?compact=1",
                "https://api.goldprice.dev/v1/prices?symbol=XAU-USD-SPOT",
                "https://api.goldprice.dev/v1/spot/XAU-USD-SPOT",
            ]
            for endpoint in endpoints:
                try:
                    payload = fetch_json(endpoint, retries=1, user_agent="Bob/1.3")
                    if endpoint.startswith("https://xaus.com/"):
                        row = {
                            "price": payload.get("spot_usd_oz") if isinstance(payload, dict) else None,
                            "computed_at": payload.get("updated_at") if isinstance(payload, dict) else None,
                            "is_stale": (payload.get("data_state", {}).get("status") == "stale") if isinstance(payload, dict) else True,
                        }
                    elif "/v1/spot/" in endpoint:
                        row = payload if isinstance(payload, dict) else None
                    else:
                        symbols = payload.get("symbols") if isinstance(payload, dict) else None
                        row = symbols[0] if isinstance(symbols, list) and symbols else None
                    if not isinstance(row, dict):
                        raise RuntimeError("GoldPrice.dev liefert keine XAU/USD-Daten")
                    price = float(row.get("price"))
                    age = iso_age_seconds(row.get("computed_at"))
                    if price <= 0:
                        raise RuntimeError("GoldPrice.dev liefert keinen gültigen XAU/USD-Preis")
                    if row.get("is_stale") is True or age is None or age > FRESH_MAX_AGE:
                        raise RuntimeError(
                            f"GoldPrice.dev Spot nicht frisch (stale={row.get('is_stale')}, "
                            f"Alter {age if age is not None else 'unbekannt'} s)"
                        )
                    return price, age, None, "GoldPrice.dev · live", True
                except Exception as exc:
                    last_error = exc
            return None, None, str(last_error) if last_error else "Spotquelle nicht verfügbar", None, False

        def fetch_yahoo(interval, range_value):
            # XAUS exposes a documented XAU chart proxy. Use it first so Render
            # does not depend on direct Yahoo connectivity (which currently returns 404).
            xaus_interval = {"5m":"5m", "1h":"1h"}.get(interval, interval)
            try:
                payload = fetch_json(
                    f"https://xaus.com/api/v1/chart?symbol=xau&range={range_value}&interval={xaus_interval}",
                    retries=1,
                    user_agent="Bob/1.4",
                )
                points = payload.get("points") if isinstance(payload, dict) else None
                if isinstance(points, list) and points:
                    out = []
                    for p in points:
                        try:
                            ts = int(p["t"])
                            o, h, low, close = map(float, (p["o"], p["h"], p["l"], p["c"]))
                            if not all(v == v and v > 0 for v in (o, h, low, close)):
                                continue
                            out.append({
                                "openTime": ts * 1000,
                                "open": o,
                                "high": h,
                                "low": low,
                                "close": close,
                                "isOpen": False,
                            })
                        except (KeyError, TypeError, ValueError, OverflowError):
                            continue
                    out.sort(key=lambda x: x["openTime"])
                    if out:
                        return out
            except Exception:
                pass

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
                    out.append({"openTime": int(ts)*1000, "open":o, "high":h, "low":low, "close":close, "isOpen":False})
                except (IndexError, TypeError, ValueError, OverflowError):
                    continue
            out.sort(key=lambda x:x["openTime"])
            return out

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
        pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bob-live")
        futures = {
            pool.submit(fetch_spot): "spot",
            pool.submit(fetch_yahoo, "5m", "5d"): "5m",
            pool.submit(fetch_yahoo, "1h", "3mo"): "1h",
            pool.submit(fetch_fx): "fx",
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
                if remaining <= 0:
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
            goldprice_price, goldprice_age, spot_error, spot_source, is_spot = spot_result
        else:
            goldprice_price = goldprice_age = None
            spot_error = str(spot_result) if spot_result else "Spotquelle nicht verfügbar"
            spot_source = None
            is_spot = False

        bars_5m = results.get("5m", [])
        if isinstance(bars_5m, Exception):
            technical_5m_error = str(bars_5m)
            bars_5m = []
        else:
            technical_5m_error = None
        bars_1h = results.get("1h", [])
        if isinstance(bars_1h, Exception):
            technical_1h_error = str(bars_1h)
            bars_1h = []
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
            if bars_5m:
                goldprice_price = bars_5m[-1]["close"]
                goldprice_age = max(0, now - bars_5m[-1]["openTime"] / 1000)
                spot_source = "Yahoo Finance GC=F · FALLBACK"
                is_spot = False
            else:
                raise RuntimeError("Kein kostenloser Live-Preis verfügbar" + (f": {spot_error}" if spot_error else ""))

        bars_15m = aggregate_bars(bars_5m, 15) if bars_5m else []
        bars_4h = aggregate_bars(bars_1h, 240) if bars_1h else []
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
                "yahoo_gc_f": reference,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": goldprice_age,
                "goldprice_age_seconds": goldprice_age,
                "usd_eur": usd_eur,
                "usd_chf": usd_chf,
                "yahoo_gc_f_age_seconds": max(0, now - bars_5m[-1]["openTime"] / 1000) if bars_5m else None,
                "yahoo_1h_age_seconds": max(0, now - bars_1h[-1]["openTime"] / 1000) if bars_1h else None,
                "technical_4h_status": "available" if bars_4h else "unavailable",
                "technical_4h_error": "; ".join(technical_errors) if technical_errors else None,
                "goldprice_status": spot_source,
                "xaus_is_spot": spot_source == "GoldPrice.dev · live",
                "primary": spot_source,
                "reference": "Yahoo Finance GC=F",
                "reference_note": "GC=F ist Gold-Futures, nicht XAU/USD Spot",
                "spot_error": spot_error,
            },
            "history": {
                "bars_by_tf": {"5m": bars_5m, "15m": bars_15m, "1h": bars_1h, "4h": bars_4h},
                "points": legacy_points,
                "data_state": {
                    "status": status,
                    "source": "GoldPrice.dev XAU/USD Spot + Yahoo Finance GC=F technische Referenz",
                    "technical_4h_status": "available" if bars_4h else "unavailable",
                    "technical_errors": technical_errors,
                },
                "age_seconds": goldprice_age,
            },
        }
        _live_cache = bundle
        _live_cache_at = time.time()
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
    if len(values) < period + 2:
        return 50.0
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
    return 100.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)

def _mtf_score(bars, tf):
    closed = [b for b in (bars or []) if not b.get("isOpen")][-220:]
    if len(closed) < 200:
        return {"dir":"NEUTRAL","available":False,"reason":"zu wenig Historie","bars":len(closed)}
    latest = int(closed[-1]["openTime"])
    age = max(0, int(time.time() * 1000) - latest)
    freshness = {"5m":1200000,"15m":2700000,"1h":10800000,"4h":43200000}.get(tf,10800000)
    if age > freshness:
        return {"dir":"NEUTRAL","available":False,"reason":"Historie zu alt","bars":len(closed),"ageMs":age}
    values = [float(b["close"]) for b in closed]
    e20, e50, e200 = _ema(values,20), _ema(values,50), _ema(values,200)
    e12, e26 = _ema(values,12), _ema(values,26)
    mac = e12 - e26
    prev_values = values[:-1]
    prev_mac = _ema(prev_values,12) - _ema(prev_values,26)
    rsi = _rsi(values)
    score = 0
    score += 1 if values[-1] > e20 else -1
    score += 1 if e20 > e50 else -1
    score += 1 if e50 > e200 else -1
    score += 1 if mac > prev_mac else -1
    score += 1 if 50 <= rsi <= 70 else (-1 if rsi < 35 else 0)
    direction = "LONG" if score >= 2 else "SHORT" if score <= -2 else "NEUTRAL"
    return {"dir":direction,"available":True,"reason":"ok","bars":len(closed),"rsi":round(rsi,2),"score":score,"ageMs":age}

def build_mtf_verification(bundle):
    tfbars = bundle.get("history",{}).get("bars_by_tf",{}) if isinstance(bundle,dict) else {}
    results = {tf:_mtf_score(tfbars.get(tf,[]),tf) for tf in ("5m","15m","1h","4h")}
    valid = all(v.get("available") for v in results.values())
    dirs = [results[tf]["dir"] for tf in ("4h","1h","15m","5m")]
    overall = "LONG" if valid and dirs[0]=="LONG" and dirs[1]=="LONG" and dirs[2]!="SHORT" and dirs[3]!="SHORT" else "SHORT" if valid and dirs[0]=="SHORT" and dirs[1]=="SHORT" and dirs[2]!="LONG" and dirs[3]!="LONG" else "NEUTRAL"
    return {"overall":overall,"valid":valid,"results":results,"verifiedAt":datetime.now(timezone.utc).isoformat()}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
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
        if path == "/health":
            body = b'{"status":"ok","service":"bob"}'
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
        if not public_push_path and not worker_ok and (not USER or not PASSWORD or not hmac.compare_digest(auth, expected)):
            print(
                f'BOB_AUTH_FAIL path={path} auth_present={bool(auth)} '
                f'auth_scheme={auth.split(" ",1)[0] if auth else "-"} '
                f'user_configured={bool(USER)} password_configured={bool(PASSWORD)} '
                f'worker_token_present={bool(worker_token)} worker_token_configured={bool(SIGNAL_WORKER_TOKEN)}',
                flush=True,
            )
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Bob"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
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
            self.send_header("Referrer-Policy", "no-referrer")
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
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; img-src 'self' data:; worker-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
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
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; "
                "img-src 'self' data:; "
                "worker-src 'self'; "
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


    def do_POST(self):
        path = urlparse(self.path).path
        auth = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{USER}:{PASSWORD}".encode("utf-8")
        ).decode("ascii")
        worker_token = self.headers.get("X-Bob-Worker-Token", "")
        worker_ok = bool(SIGNAL_WORKER_TOKEN) and hmac.compare_digest(worker_token, SIGNAL_WORKER_TOKEN)

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

        if path == "/api/push/send" and not worker_ok and (not USER or not PASSWORD or not hmac.compare_digest(auth, expected)):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Bob"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        path = urlparse(self.path).path
        if path not in ("/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences"):
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
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Payload-Größe")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            base = PUSH_SERVICE_URL
            if not base.startswith("http://") and not base.startswith("https://"):
                base = "http://" + base
            relay_path = {
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

port = int(os.environ.get("PORT", "10000"))
print(f"BOB_START port={port} host=0.0.0.0 version=runtime-http-trace-v1", flush=True)
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

# Bob maintenance marker: 4h MTF upgrade in progress
