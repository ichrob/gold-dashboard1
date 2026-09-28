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
_live_cache = None
_live_cache_at = 0.0
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
    global _live_cache, _live_cache_at
    cached = _live_cache
    if cached is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
        return cached

    with _live_lock:
        cached = _live_cache
        if cached is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
            return cached

        now = time.time()

        # Primary live spot: goldprice.dev, anonymous endpoint.
        goldprice = fetch_json(
            "https://api.goldprice.dev/v1/prices?symbol=XAU-USD-SPOT",
            retries=2,
            user_agent="Bob/1.1"
        )
        symbols = goldprice.get("symbols") if isinstance(goldprice, dict) else None
        if not isinstance(symbols, list) or not symbols:
            raise RuntimeError("GoldPrice.dev liefert keine XAU/USD-Daten")
        row = symbols[0]
        goldprice_price = float(row.get("price"))
        goldprice_age = iso_age_seconds(row.get("computed_at"))
        if not (goldprice_price > 0):
            raise RuntimeError("GoldPrice.dev liefert keinen gültigen XAU/USD-Preis")
        if row.get("is_stale") is True or goldprice_age is None or goldprice_age > FRESH_MAX_AGE:
            raise RuntimeError(
                f"GoldPrice.dev Spot nicht frisch (stale={row.get('is_stale')}, "
                f"Alter {goldprice_age if goldprice_age is not None else 'unbekannt'} s)"
            )

        # Yahoo Finance provides recent GC=F gold-futures 5-minute bars for technical history.
        yahoo = fetch_json(
            "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=5m&range=5d&includePrePost=true",
            retries=2,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
        )
        result = yahoo.get("chart", {}).get("result", [None])[0] if isinstance(yahoo, dict) else None
        if not result:
            raise RuntimeError("Yahoo Finance liefert keine Gold-Futures-Historie")
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [None])[0] or {}
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        bars_5m = []
        for i, ts in enumerate(timestamps):
            try:
                o, h, l, close = map(float, (opens[i], highs[i], lows[i], closes[i]))
                if not all(v == v and v > 0 for v in (o, h, l, close)):
                    continue
                bars_5m.append({
                    "openTime": int(ts) * 1000,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": close,
                    "isOpen": False
                })
            except (IndexError, TypeError, ValueError, OverflowError):
                continue
        bars_5m.sort(key=lambda x: x["openTime"])
        mark_bar_state(bars_5m, 5)
        if len(bars_5m) < 200:
            raise RuntimeError(f"Yahoo Finance liefert zu wenig Gold-Futures-5m-Historie ({len(bars_5m)} Kerzen)")

        latest_bar_age = max(0, now - bars_5m[-1]["openTime"] / 1000)
        if latest_bar_age > 900:
            raise RuntimeError(f"Yahoo Gold-Futures-Historie nicht frisch (Alter {latest_bar_age:.0f} s)")

        # Longer 1h history is optional: live spot/5m data must remain available
        # even if Yahoo's longer history endpoint is temporarily unavailable.
        bars_1h, bars_15m, bars_4h, latest_1h_age = [], [], [], None
        history_4h_error = None
        try:
            yahoo_1h = fetch_json(
                "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1h&range=3mo&includePrePost=true",
                retries=2,
                user_agent="Mozilla/5.0"
            )
            result_1h = yahoo_1h.get("chart", {}).get("result", [None])[0] if isinstance(yahoo_1h, dict) else None
            if not result_1h:
                raise RuntimeError("Yahoo Finance liefert keine 1h-Historie")
            ts_1h = result_1h.get("timestamp") or []
            q_1h = (result_1h.get("indicators", {}).get("quote") or [None])[0] or {}
            o_1h, h_1h, l_1h, c_1h = q_1h.get("open") or [], q_1h.get("high") or [], q_1h.get("low") or [], q_1h.get("close") or []
            for i, ts in enumerate(ts_1h):
                try:
                    o, h, low, close = map(float, (o_1h[i], h_1h[i], l_1h[i], c_1h[i]))
                    if not all(v == v and v > 0 for v in (o, h, low, close)):
                        continue
                    bars_1h.append({"openTime": int(ts) * 1000, "open": o, "high": h, "low": low, "close": close, "isOpen": False})
                except (IndexError, TypeError, ValueError, OverflowError):
                    continue
            bars_1h.sort(key=lambda x: x["openTime"])
            mark_bar_state(bars_1h, 60)
            if len(bars_1h) < 800:
                raise RuntimeError(f"Zu wenig 1h-Historie für 4h/EMA200 ({len(bars_1h)} Kerzen)")
            latest_1h_age = max(0, now - bars_1h[-1]["openTime"] / 1000)
            if latest_1h_age > 7200:
                raise RuntimeError(f"Yahoo 1h-Historie nicht frisch (Alter {latest_1h_age:.0f} s)")

            # 15m must come from genuine 15-minute OHLC data.
            # Aggregating 1h candles down to 15m would invent invalid intrabar OHLC.
            yahoo_15m = fetch_json(
                "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=15m&range=60d&includePrePost=true",
                retries=2,
                user_agent="Mozilla/5.0"
            )
            result_15m = yahoo_15m.get("chart", {}).get("result", [None])[0] if isinstance(yahoo_15m, dict) else None
            if not result_15m:
                raise RuntimeError("Yahoo Finance liefert keine 15m-Historie")
            ts_15m = result_15m.get("timestamp") or []
            q_15m = (result_15m.get("indicators", {}).get("quote") or [None])[0] or {}
            o_15m, h_15m, l_15m, c_15m = q_15m.get("open") or [], q_15m.get("high") or [], q_15m.get("low") or [], q_15m.get("close") or []
            for i, ts in enumerate(ts_15m):
                try:
                    o, h, low, close = map(float, (o_15m[i], h_15m[i], l_15m[i], c_15m[i]))
                    if not all(v == v and v > 0 for v in (o, h, low, close)):
                        continue
                    bars_15m.append({"openTime": int(ts) * 1000, "open": o, "high": h, "low": low, "close": close, "isOpen": False})
                except (IndexError, TypeError, ValueError, OverflowError):
                    continue
            bars_15m.sort(key=lambda x: x["openTime"])
            mark_bar_state(bars_15m, 15)
            if len(bars_15m) < 200:
                raise RuntimeError(f"Zu wenig echte 15m-Historie ({len(bars_15m)} Kerzen)")
            bars_4h = aggregate_bars(bars_1h, 240)
            if len([b for b in bars_4h if not b["isOpen"]]) < 200:
                raise RuntimeError("Zu wenig geschlossene 4h-Historie für EMA200")
        except Exception as exc:
            history_4h_error = str(exc)
            bars_1h, bars_4h, latest_1h_age = [], [], None


        # Prefer genuine XAU/USD spot OHLC when the GoldPrice.dev tier exposes intraday bars.
        # Each timeframe is independent; a plan-gated interval falls back to the existing Yahoo futures history.
        spot_5m = fetch_goldprice_bars("5m", 30)
        if len([b for b in spot_5m if not b["isOpen"]]) >= 200:
            latest_spot_age = max(0, now - spot_5m[-1]["openTime"] / 1000)
            if latest_spot_age <= 900:
                bars_5m = spot_5m
        spot_15m = fetch_goldprice_bars("15m", 30)
        spot_1h = fetch_goldprice_bars("1h", 30)
        spot_4h = fetch_goldprice_bars("4h", 30)
        spot_1h_closed = [b for b in spot_1h if not b["isOpen"]]
        if len(spot_1h_closed) >= 200:
            bars_1h = spot_1h
            latest_1h_age = max(0, now - bars_1h[-1]["openTime"] / 1000)
        if len([b for b in spot_15m if not b["isOpen"]]) >= 200:
            bars_15m = spot_15m
        if len([b for b in spot_4h if not b["isOpen"]]) >= 200:
            bars_4h = spot_4h
            history_4h_error = None

        usd_eur = None
        usd_chf = None
        for ccy in ("EUR", "CHF"):
            try:
                fx = fetch_json(f"https://api.goldprice.dev/v1/convert?from=USD&to={ccy}&amount=1", retries=1, user_agent="Bob/1.1")
                rate = float(fx.get("rate")) if isinstance(fx, dict) else None
                if rate and rate > 0:
                    if ccy == "EUR":
                        usd_eur = rate
                    else:
                        usd_chf = rate
            except Exception:
                pass

        yahoo_price = bars_5m[-1]["close"]
        diff = goldprice_price - yahoo_price
        pct = (diff / yahoo_price * 100) if yahoo_price else 0.0

        legacy_points = [
            {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b["openTime"] / 1000)), "p": b["close"]}
            for b in bars_5m
        ]

        bundle = {
            "fetched_at": int(time.time()),
            "spots": {
                "xaus": goldprice_price,
                "yahoo_gc_f": yahoo_price,
                "goldprice": goldprice_price,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": goldprice_age,
                "usd_eur": usd_eur,
                "usd_chf": usd_chf,
                "yahoo_gc_f_age_seconds": latest_bar_age,
                "yahoo_1h_age_seconds": latest_1h_age,
                "technical_4h_status": "available" if bars_4h else "unavailable",
                "technical_4h_error": history_4h_error,
                "goldprice_age_seconds": goldprice_age,
                "goldprice_status": "GoldPrice.dev · live",
                "primary": "GoldPrice.dev",
                "reference": "Yahoo Finance GC=F",
                "reference_note": "GC=F ist Gold-Futures, nicht XAU/USD Spot"
            },
            "history": {
                "bars_by_tf": {"5m": bars_5m, "15m": bars_15m, "1h": bars_1h, "4h": bars_4h},
                "points": legacy_points,
                "data_state": {"status": "fresh", "source": "GoldPrice.dev XAU/USD Spot OHLC where available; Yahoo Finance GC=F fallback", "technical_4h_status": "available" if bars_4h else "unavailable"},
                "age_seconds": goldprice_age
            }
        }
        _live_cache = bundle
        _live_cache_at = time.time()
        return bundle

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{USER}:{PASSWORD}".encode("utf-8")
        ).decode("ascii")

        if not USER or not PASSWORD or not hmac.compare_digest(auth, expected):
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

        if path == "/api/degiro-products":
            raw_products = os.environ.get("BOB_DEGIRO_PRODUCTS_JSON", "")
            try:
                products = json.loads(raw_products) if raw_products else []
                if not isinstance(products, list):
                    raise ValueError("BOB_DEGIRO_PRODUCTS_JSON muss eine Liste sein")
                safe = []
                for p in products:
                    if not isinstance(p, dict):
                        continue
                    item = {
                        "name": str(p.get("name", ""))[:120],
                        "isin": str(p.get("isin", ""))[:20],
                        "direction": str(p.get("direction", "")).upper()[:10],
                        "leverage": p.get("leverage"),
                        "ko": p.get("ko"),
                        "bid": p.get("bid"),
                        "ask": p.get("ask"),
                        "expiry": p.get("expiry"),
                        "bidOnly": bool(p.get("bidOnly", False)),
                        "tradable": p.get("tradable", True),
                    }
                    safe.append(item)
                body = json.dumps({
                    "products": safe,
                    "source": "BOB_DEGIRO_PRODUCTS_JSON" if raw_products else "not configured"
                }, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                body = json.dumps({"error": str(exc), "products": []}).encode("utf-8")
                self.send_response(400)
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

        if path == "/icon.svg" and ICON is not None:
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(ICON)
            return

        if path == "/sw.js" and SW is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(SW)
            return

        self.send_response(404)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"Not found.")

    def log_message(self, fmt, *args):
        pass

port = int(os.environ.get("PORT", "10000"))
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

# Bob maintenance marker: 4h MTF upgrade in progress
