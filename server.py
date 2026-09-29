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
with HTML_PATH.open("rb") as f:
    HTML = f.read()
SW = SW_PATH.read_bytes() if SW_PATH.exists() else None
MANIFEST = MANIFEST_PATH.read_bytes() if MANIFEST_PATH.exists() else None
ICON = ICON_PATH.read_bytes() if ICON_PATH.exists() else None

UPSTREAM_TIMEOUT = 10
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
    """Build Bob's free-tier live bundle.
    Live XAU/USD comes from the anonymous GoldPrice.dev spot endpoint.
    Technical history uses Yahoo GC=F only; paid GoldPrice intraday bars are never requested.
    A history failure must not hide an otherwise valid live spot price.
    """
    global _live_cache, _live_cache_at
    if _live_cache is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
        return _live_cache

    with _live_lock:
        if _live_cache is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
            return _live_cache

        now = time.time()
        goldprice_price = None
        goldprice_age = None
        spot_error = None

        try:
            goldprice = fetch_json(
                "https://api.goldprice.dev/v1/prices?symbol=XAU-USD-SPOT",
                retries=1,
                user_agent="Bob/1.1",
            )
            symbols = goldprice.get("symbols") if isinstance(goldprice, dict) else None
            row = symbols[0] if isinstance(symbols, list) and symbols else None
            if not isinstance(row, dict):
                raise RuntimeError("GoldPrice.dev liefert keine XAU/USD-Daten")
            goldprice_price = float(row.get("price"))
            goldprice_age = iso_age_seconds(row.get("computed_at"))
            if not goldprice_price > 0:
                raise RuntimeError("GoldPrice.dev liefert keinen gültigen XAU/USD-Preis")
            if row.get("is_stale") is True or goldprice_age is None or goldprice_age > FRESH_MAX_AGE:
                raise RuntimeError(
                    f"GoldPrice.dev Spot nicht frisch (stale={row.get('is_stale')}, "
                    f"Alter {goldprice_age if goldprice_age is not None else 'unbekannt'} s)"
                )
        except Exception as exc:
            spot_error = str(exc)

        bars_5m, bars_1h = [], []
        technical_errors = []

        def yahoo_bars(interval, range_value):
            payload = fetch_json(
                f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval={interval}"
                f"&range={range_value}&includePrePost=true",
                retries=1,
                user_agent="Bob/1.1",
            )
            result = payload.get("chart", {}).get("result", [None])[0] if isinstance(payload, dict) else None
            if not result:
                raise RuntimeError(f"Yahoo Finance liefert keine {interval}-Historie")
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
                    out.append({
                        "openTime": int(ts) * 1000,
                        "open": o,
                        "high": h,
                        "low": low,
                        "close": close,
                        "isOpen": False,
                    })
                except (IndexError, TypeError, ValueError, OverflowError):
                    continue
            out.sort(key=lambda x: x["openTime"])
            return out

        try:
            bars_5m = yahoo_bars("5m", "5d")
            mark_bar_state(bars_5m, 5)
            if bars_5m:
                age = max(0, now - bars_5m[-1]["openTime"] / 1000)
                if age > 900:
                    technical_errors.append(f"5m-Historie nicht frisch ({age:.0f} s)")
        except Exception as exc:
            technical_errors.append(str(exc))

        try:
            bars_1h = yahoo_bars("1h", "3mo")
            mark_bar_state(bars_1h, 60)
        except Exception as exc:
            technical_errors.append(str(exc))

        bars_15m = aggregate_bars(bars_5m, 15) if bars_5m else []
        bars_4h = aggregate_bars(bars_1h, 240) if bars_1h else []

        if goldprice_price is None:
            if bars_5m:
                goldprice_price = bars_5m[-1]["close"]
                goldprice_age = max(0, now - bars_5m[-1]["openTime"] / 1000)
                spot_source = "Yahoo Finance GC=F · FALLBACK"
            else:
                raise RuntimeError(
                    "Kein kostenloser Live-Preis verfügbar"
                    + (f": {spot_error}" if spot_error else "")
                )
        else:
            spot_source = "GoldPrice.dev · live"

        reference = bars_5m[-1]["close"] if bars_5m else goldprice_price
        diff = goldprice_price - reference
        pct = (diff / reference * 100) if reference else 0.0
        points_source = bars_5m if bars_5m else bars_1h
        legacy_points = [
            {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b["openTime"] / 1000)), "p": b["close"]}
            for b in points_source
        ]

        global _fx_cache, _fx_cache_at
        if time.time() - _fx_cache_at < FX_CACHE_TTL and any(v is not None for v in _fx_cache.values()):
            usd_eur = _fx_cache["EUR"]
            usd_chf = _fx_cache["CHF"]
        else:
            usd_eur = None
            usd_chf = None
            for ccy in ("EUR", "CHF"):
                try:
                    fx = fetch_json(
                        f"https://api.goldprice.dev/v1/convert?from=USD&to={ccy}&amount=1",
                        retries=1,
                        user_agent="Bob/1.1",
                    )
                    rate = float(fx.get("rate")) if isinstance(fx, dict) else None
                    if rate and rate > 0:
                        _fx_cache[ccy] = rate
                        if ccy == "EUR":
                            usd_eur = rate
                        else:
                            usd_chf = rate
                except Exception:
                    pass
            _fx_cache_at = time.time()
            if usd_eur is None:
                usd_eur = _fx_cache["EUR"]
            if usd_chf is None:
                usd_chf = _fx_cache["CHF"]

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
                "yahoo_gc_f_age_seconds": (
                    max(0, now - bars_5m[-1]["openTime"] / 1000) if bars_5m else None
                ),
                "yahoo_1h_age_seconds": (
                    max(0, now - bars_1h[-1]["openTime"] / 1000) if bars_1h else None
                ),
                "technical_4h_status": "available" if bars_4h else "unavailable",
                "technical_4h_error": "; ".join(technical_errors) if technical_errors else None,
                "goldprice_status": spot_source,
                "primary": spot_source,
                "reference": "Yahoo Finance GC=F",
                "reference_note": "GC=F ist Gold-Futures, nicht XAU/USD Spot",
                "spot_error": spot_error,
            },
            "history": {
                "bars_by_tf": {
                    "5m": bars_5m,
                    "15m": bars_15m,
                    "1h": bars_1h,
                    "4h": bars_4h,
                },
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

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
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

        auth = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{USER}:{PASSWORD}".encode("utf-8")
        ).decode("ascii")

        worker_token = self.headers.get("X-Bob-Worker-Token", "")
        worker_ok = bool(SIGNAL_WORKER_TOKEN) and hmac.compare_digest(worker_token, SIGNAL_WORKER_TOKEN)
        if not worker_ok and (not USER or not PASSWORD or not hmac.compare_digest(auth, expected)):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Bob"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
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
                body = json.dumps({"error": str(exc), "error_type": type(exc).__name__}).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            return

        if path == "/manifest.json" and MANIFEST is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(MANIFEST)
            return


        if not worker_ok and (not USER or not PASSWORD or not hmac.compare_digest(auth, expected)):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Bob"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        path = urlparse(self.path).path
        if path not in ("/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe"):
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
        pass

port = int(os.environ.get("PORT", "10000"))
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

# Bob maintenance marker: 4h MTF upgrade in progress
