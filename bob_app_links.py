"""Public Android Digital Asset Links for Bob's *signed* stable companion only.

This association grants Android OS intent resolution for harmless, individually
approved display proposals. It is NOT an authenticated remote command channel.
No response may be published until the fingerprint has been copied from the
known GitHub signed-release certificate and verified separately.
"""
import json
import re
from pathlib import Path

PACKAGE = "ch.bob.degirocompanion.stable"
ORIGIN = "https://bob-private-scanner.onrender.com"
PUBLIC_PIN_PATH = Path(__file__).resolve().parent / "android_companion" / "app_link_certificate.sha256"


def read_public_pin(path=PUBLIC_PIN_PATH):
    try:
        raw = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    normalized = raw.replace(":", "").replace(" ", "").upper()
    if not re.fullmatch(r"[0-9A-F]{64}", normalized):
        return None
    return ":".join(normalized[i:i + 2] for i in range(0, 64, 2))


def association(pin):
    if not isinstance(pin, str) or not re.fullmatch(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}", pin):
        raise ValueError("Invalid signed Android certificate fingerprint")
    return [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": PACKAGE,
            "sha256_cert_fingerprints": [pin],
        },
    }]


def send(handler, *, query="", head=False):
    # This well-known metadata must be HTTPS-public and never redirected to
    # Bob login. Reject query payloads; no device secrets appear in this file.
    pin = read_public_pin() if not query else None
    if pin is None:
        handler.send_response(503 if not query else 404)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    body = json.dumps(association(pin), separators=(",", ":")).encode("ascii")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "public, max-age=300")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if not head:
        handler.wfile.write(body)
