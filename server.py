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
LIVE_CACHE_TTL = 20
_live_cache = None
_live_cache_at = 0.0
_live_lock = threading.Lock()

def fetch_json(url):
    req = Request(url, headers={"User-Agent": "Bob/1.0", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=UPSTREAM_TIMEOUT) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Upstream HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Upstream HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Upstream nicht erreichbar oder ungültige JSON-Antwort") from exc

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

def build_live_bundle():
    global _live_cache, _live_cache_at
    cached = _live_cache
    if cached is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
        return cached

    with _live_lock:
        cached = _live_cache
        if cached is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
            return cached

        now = int(time.time() * 1000)
        xaus = fetch_json(f"https://xaus.com/api/v1/spot?currency=USD&fresh={now}")
        intraday = fetch_json("https://xaus.com/api/v1/intraday?symbol=xau&hours=48")
        goldprice = fetch_json("https://api.goldprice.dev/v1/prices?symbol=XAU-USD-SPOT")

        xaus_price = float(xaus.get("spot_usd_oz"))
        gp_row = (goldprice.get("symbols") or [None])[0]
        gp_price = float(gp_row.get("price")) if gp_row else float("nan")
        if not (xaus_price > 0 and gp_price > 0):
            raise RuntimeError("Ungültige Live-Goldwerte")

        if xaus.get("data_state", {}).get("status") != "fresh":
            raise RuntimeError("XAUS Spot-Daten nicht frisch")
        if intraday.get("data_state", {}).get("status") != "fresh":
            raise RuntimeError("XAUS Intraday-Daten nicht frisch")
        if gp_row.get("is_stale") is True:
            raise RuntimeError("GoldPrice.dev-Daten nicht frisch")

        spot_age = iso_age_seconds(xaus.get("price_as_of") or xaus.get("updated_at"))
        intraday_age = iso_age_seconds(intraday.get("data_state", {}).get("as_of"))
        gp_age = iso_age_seconds(gp_row.get("computed_at"))
        if any(age is None or age > FRESH_MAX_AGE for age in (spot_age, intraday_age, gp_age)):
            raise RuntimeError("Mindestens eine Live-Quelle ist älter als 180 Sekunden")

        points = intraday.get("points") or []
        if not points:
            raise RuntimeError("XAUS Intraday-Serie ist leer")

        diff = abs(xaus_price - gp_price)
        pct = diff / ((xaus_price + gp_price) / 2) * 100
        if pct > 0.50:
            raise RuntimeError(f"Live-Quellen weichen um {pct:.3f}% ab – Analyse angehalten")

        bundle = {
            "fetched_at": int(time.time()),
            "spots": {
                "xaus": xaus_price,
                "goldprice": gp_price,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": spot_age,
                "goldprice_age_seconds": gp_age
            },
            "history": {
                "points": points,
                "data_state": intraday.get("data_state", {}),
                "age_seconds": intraday_age
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
                "connect-src 'self' https://ntfy.sh; "
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
                body = json.dumps({"error": str(exc)}).encode("utf-8")
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
