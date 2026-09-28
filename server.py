import os
import base64
import hmac
import json
import time
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse
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

def fetch_json(url, retries=2):
    last_error = None
    for attempt in range(retries + 1):
        req = Request(url, headers={"User-Agent": "Bob/1.1", "Accept": "application/json"})
        try:
            with urlopen(req, timeout=UPSTREAM_TIMEOUT) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Upstream HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = RuntimeError(f"Upstream HTTP {exc.code}")
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = RuntimeError("Upstream nicht erreichbar oder ungültige JSON-Antwort")
        if attempt < retries:
            time.sleep(0.6 * (attempt + 1))
    raise last_error or RuntimeError("Upstream nicht erreichbar")

def iso_age_seconds(value):
    if not value:
        return None
    try:
        stamp = value.replace("Z", "+00:00")
        from datetime import datetime, timezone
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

        now_ms = int(time.time() * 1000)

        # XAUS remains the independent reference spot source.
        xaus = fetch_json(f"https://xaus.com/api/v1/spot?currency=USD&compact=1&fresh={now_ms}")
        xaus_price = float(xaus.get("spot_usd_oz"))
        xaus_state = xaus.get("data_state", {}).get("status")
        xaus_age = iso_age_seconds(xaus.get("price_as_of") or xaus.get("updated_at"))
        if not (xaus_price > 0):
            raise RuntimeError("XAUS liefert keinen gültigen XAU/USD-Preis")
        if xaus_state != "fresh" or xaus_age is None or xaus_age > FRESH_MAX_AGE:
            raise RuntimeError(f"XAUS Spot nicht frisch (Status {xaus_state}, Alter {xaus_age if xaus_age is not None else 'unbekannt'} s)")

        # Biquote provides broker/MT5-derived live ticks and long OHLC history.
        bq = fetch_json("https://biquote.io/api/XAUUSD?allowStale=false")
        bq_price = float(bq.get("mid"))
        bq_age = float(bq.get("quoteAgeSeconds", 999999))
        if not (bq_price > 0):
            raise RuntimeError("Biquote liefert keinen gültigen XAU/USD-Preis")
        if bq.get("stale") is True or bq_age > FRESH_MAX_AGE:
            raise RuntimeError(f"Biquote XAU/USD nicht frisch (Alter {bq_age:.0f} s)")

        diff = abs(xaus_price - bq_price)
        pct = diff / ((xaus_price + bq_price) / 2) * 100
        if pct > 0.50:
            raise RuntimeError(f"XAUS und Biquote weichen um {pct:.3f}% ab – Analyse angehalten")

        bars_by_tf = {}
        for tf, limit in (("5m", 1000), ("15m", 1000), ("1h", 500), ("4h", 500)):
            payload = fetch_json(f"https://biquote.io/api/XAUUSD/ohlc?interval={tf}&limit={limit}")
            bars = normalize_biquote_bars(payload)
            if not bars:
                raise RuntimeError(f"Biquote liefert keine {tf}-Historie")
            bars_by_tf[tf] = bars

        # Optional secondary source. It never blocks the live feed.
        gp_price = bq_price
        gp_age = bq_age
        gp_status = "Biquote-Kontrollwert"

        # Keep the legacy frontend contract: points are 5m closes.
        # 1000 x 5m bars give the 15m view >300 bars, enough for EMA200.
        legacy_points = [
            {"t": b["openTime"], "p": b["close"]}
            for b in bars_by_tf.get("5m", [])
            if not b.get("isOpen")
        ]

        bundle = {
            "fetched_at": int(time.time()),
            "spots": {
                "xaus": xaus_price,
                "biquote": bq_price,
                "goldprice": gp_price,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": xaus_age,
                "biquote_age_seconds": bq_age,
                "goldprice_age_seconds": gp_age,
                "goldprice_status": gp_status,
                "primary": "Biquote + XAUS"
            },
            "history": {
                "bars_by_tf": bars_by_tf,
                "points": legacy_points,
                "data_state": {"status": "fresh", "source": "Biquote OHLC + XAUS spot"},
                "age_seconds": bq_age
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

port = int(os.environ.get("PORT", "10000"))
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
