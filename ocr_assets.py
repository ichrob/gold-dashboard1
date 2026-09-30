"""Serve fixed, integrity-checked OCR dependencies from Bob's own origin.

Only the bundled manifest is accepted; this is not a user-controlled proxy.
No browser headers, credentials or screenshots are forwarded to the CDN.
"""
import hashlib
import json
import threading
from pathlib import Path
from urllib.request import urlopen

PREFIX = "/ocr-assets/v5/"
ASSETS = json.loads(Path(__file__).with_name("ocr_assets.json").read_text())
MAX_BYTES = 8 * 1024 * 1024
_cache = {}
_locks = {name: threading.Lock() for name in ASSETS}


def load(name):
    if name not in ASSETS:
        raise KeyError(name)
    with _locks[name]:
        if name in _cache:
            return _cache[name]
        url, expected = ASSETS[name]
        with urlopen(url, timeout=20) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("OCR dependency failed integrity validation")
        _cache[name] = data
        return data


def serve(handler, path):
    name = path[len(PREFIX):]
    if name not in ASSETS:
        handler.send_error(404)
        return
    try:
        data = load(name)
    except Exception as error:
        print(f"BOB_OCR_ASSET name={name} error={type(error).__name__}", flush=True)
        handler.send_response(503)
        handler.send_header("Retry-After", "5")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "application/javascript" if name.endswith(".js") else "application/octet-stream")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "public, max-age=31536000, immutable")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
    if name == "worker.min.js":
        # A normal same-origin worker has its own policy. Only its WASM engine
        # needs compile permission; no JavaScript eval or external connections.
        handler.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; object-src 'none'")
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(data)
