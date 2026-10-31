"""Independent, read-only Bob Zentrale PWA shell.

The shell is served by the existing scanner without a second Render instance.
Private HTML requires the ordinary Bob session. Static install metadata carries
no private data. No database writes, orders, or archival operations occur here.
"""
from pathlib import Path
from urllib.parse import urlparse
import bob_auth

ROOT = Path(__file__).resolve().parent / "zentrale"
ASSETS = {
    "/zentrale": ("index.html", "text/html; charset=utf-8", True),
    "/zentrale/": ("index.html", "text/html; charset=utf-8", True),
    "/zentrale/index.html": ("index.html", "text/html; charset=utf-8", True),
    "/zentrale/app.js": ("app.js", "application/javascript; charset=utf-8", False),
    "/zentrale/sw.js": ("sw.js", "application/javascript; charset=utf-8", False),
    "/zentrale/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8", False),
    "/zentrale/icon.svg": ("icon.svg", "image/svg+xml", False),
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


def route(handler, user, password, *, head=False):
    """Return True when this exact GET/HEAD URL belongs to Bob Zentrale."""
    parsed = urlparse(handler.path)
    asset = ASSETS.get(parsed.path)
    if asset is None:
        return False
    if parsed.query or parsed.params or parsed.fragment:
        bob_auth.send(handler, 404)
        return True
    filename, content_type, private = asset
    if private and not bob_auth.authenticated(handler.headers, user, password):
        bob_auth.send(handler, 303, location="/login")
        return True
    try:
        content = (ROOT / filename).read_bytes()
    except OSError:
        bob_auth.send(handler, 503)
        return True
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Referrer-Policy", "no-referrer")
    if private:
        handler.send_header("Content-Security-Policy", CSP)
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    if not head:
        handler.wfile.write(content)
    return True
