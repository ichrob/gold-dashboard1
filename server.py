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

        # Yahoo Finance provides recent XAU/USD 5-minute bars for the technical history.
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
        if len(bars_5m) < 200:
            raise RuntimeError(f"Yahoo Finance liefert zu wenig Gold-Futures-5m-Historie ({len(bars_5m)} Kerzen)")

        latest_bar_age = max(0, now - bars_5m[-1]["openTime"] / 1000)
        if latest_bar_age > 900:
            raise RuntimeError(f"Yahoo Gold-Futures-Historie nicht frisch (Alter {latest_bar_age:.0f} s)")

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
                "biquote": yahoo_price,
                "goldprice": goldprice_price,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": goldprice_age,
                "biquote_age_seconds": latest_bar_age,
                "goldprice_age_seconds": goldprice_age,
                "goldprice_status": "GoldPrice.dev · live",
                "primary": "GoldPrice.dev"
            },
            "history": {
                "bars_by_tf": {"5m": bars_5m},
                "points": legacy_points,
                "data_state": {"status": "fresh", "source": "GoldPrice.dev spot + Yahoo Finance GC=F 5m"},
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

def startup_live_self_test():
    try:
        bundle = build_live_bundle()
        print(f"Bob startup live self-test OK: XAUS={bundle['spots']['xaus']:.2f}, 5m_bars={len(bundle['history']['bars_by_tf']['5m'])}", flush=True)
    except Exception as exc:
        print(f"Bob startup live self-test ERROR: {type(exc).__name__}: {exc}", flush=True)

threading.Thread(target=startup_live_self_test, daemon=True).start()

port = int(os.environ.get("PORT", "10000"))
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
