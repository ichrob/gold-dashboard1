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

        now_ms = int(time.time() * 1000)

        # XAUS remains the independent reference source. Prefer the spot endpoint,
        # but fall back to XAUS's own 2-minute intraday series if the spot upstream
        # temporarily returns 503. This keeps the feed live without inventing prices.
        xaus = None
        spot_error = None
        try:
            xaus = fetch_json(f"https://xaus.com/api/v1/spot?currency=USD&compact=1&fresh={now_ms}")
        except Exception as exc:
            spot_error = exc

        # XAUS's public intraday endpoint records XAU every 2 minutes and supports up to 48h.
        intraday = fetch_json("https://xaus.com/api/v1/intraday?symbol=xau&hours=48")
        intraday_state = intraday.get("data_state", {}) if isinstance(intraday, dict) else {}
        intraday_points = intraday.get("points") if isinstance(intraday, dict) else None
        if not isinstance(intraday_points, list) or not intraday_points:
            raise RuntimeError("XAUS liefert keine Intraday-Historie")
        if intraday_state.get("status") != "fresh":
            raise RuntimeError(f"XAUS Intraday nicht frisch (Status {intraday_state.get('status')})")

        # Determine the freshest valid intraday point for a spot fallback.
        latest_point = None
        for point in intraday_points:
            try:
                stamp = str(point["t"]).replace("Z", "+00:00")
                dt = datetime.fromisoformat(stamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
                price = float(point["p"])
                if price > 0 and (latest_point is None or ts > latest_point[0]):
                    latest_point = (ts, price)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if latest_point is None:
            raise RuntimeError("XAUS liefert keinen gültigen Intraday-Preis")

        if xaus is not None:
            xaus_price = float(xaus.get("spot_usd_oz"))
            xaus_state = xaus.get("data_state", {}).get("status")
            xaus_age = iso_age_seconds(xaus.get("price_as_of") or xaus.get("updated_at"))
            if not (xaus_price > 0):
                raise RuntimeError("XAUS liefert keinen gültigen XAU/USD-Preis")
            if xaus_state != "fresh" or xaus_age is None or xaus_age > FRESH_MAX_AGE:
                raise RuntimeError(f"XAUS Spot nicht frisch (Status {xaus_state}, Alter {xaus_age if xaus_age is not None else 'unbekannt'} s)")
        else:
            xaus_price = latest_point[1]
            xaus_age = max(0, time.time() - latest_point[0])
            if xaus_age > FRESH_MAX_AGE:
                raise RuntimeError(f"XAUS Spot-Fallback nicht frisch (Alter {xaus_age:.0f} s; Spot-Fehler: {spot_error})")

        # Convert the 2-minute XAUS series into the legacy OHLC contract.
        bars_5m = []
        step_ms = 5 * 60 * 1000
        buckets = {}
        for point in intraday_points:
            try:
                stamp = str(point["t"]).replace("Z", "+00:00")
                dt = datetime.fromisoformat(stamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = int(dt.timestamp() * 1000)
                price = float(point["p"])
                bucket = (ts // step_ms) * step_ms
                b = buckets.get(bucket)
                if b is None:
                    buckets[bucket] = {"openTime": bucket, "open": price, "high": price, "low": price, "close": price, "isOpen": False}
                else:
                    b["high"] = max(b["high"], price)
                    b["low"] = min(b["low"], price)
                    b["close"] = price
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        bars_5m = sorted(buckets.values(), key=lambda x: x["openTime"])
        if len(bars_5m) < 200:
            raise RuntimeError(f"XAUS liefert zu wenig 5m-Historie ({len(bars_5m)} Kerzen)")

        bq_price = xaus_price
        bq_age = xaus_age
        diff = 0.0
        pct = 0.0
        gp_price = xaus_price
        gp_age = xaus_age
        gp_status = "XAUS Intraday"

        legacy_points = [
            {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b["openTime"] / 1000)), "p": b["close"]}
            for b in bars_5m
        ]

        bundle = {
            "fetched_at": int(time.time()),
            "spots": {
                "xaus": xaus_price,
                "biquote": xaus_price,
                "goldprice": gp_price,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": xaus_age,
                "biquote_age_seconds": xaus_age,
                "goldprice_age_seconds": gp_age,
                "goldprice_status": gp_status,
                "primary": "XAUS"
            },
            "history": {
                "bars_by_tf": {"5m": bars_5m},
                "points": legacy_points,
                "data_state": {"status": "fresh", "source": "XAUS spot + 2m intraday"},
                "age_seconds": xaus_age
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
