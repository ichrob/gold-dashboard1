"""Optional Oracle Always Free OCR fallback. Default: no external requests.

Only a verified OCI Always Free VM with dedicated TLS trust and a second
application key may receive an original screenshot. No redirects or retries.
"""
import base64
import hashlib
import ipaddress
import json
import os
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler


class RemoteOcrError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RemoteOcrError("redirect_not_allowed")


def configured():
    return (os.environ.get("BOB_REMOTE_OCR_ENABLED") == "true" and
            os.environ.get("BOB_REMOTE_OCR_COST_POLICY") ==
            "oci_always_free_verified")


def _target():
    raw = os.environ.get("BOB_REMOTE_OCR_URL", "")
    approved = os.environ.get("BOB_REMOTE_OCR_ALLOWED_IP", "")
    cert = os.environ.get("BOB_REMOTE_OCR_TLS_CA_PEM", "")
    key = os.environ.get("BOB_REMOTE_OCR_TOKEN", "")
    try:
        parts = urlsplit(raw)
        host = parts.hostname or ""
        address = ipaddress.IPv4Address(host)
        approved_ip = ipaddress.IPv4Address(approved)
        valid = (parts.scheme == "https" and parts.port == 8443
                 and parts.path == "/ocr" and not parts.query and not parts.fragment
                 and parts.username is None and parts.password is None
                 and address == approved_ip and address.is_global
                 and len(cert) <= 10000 and cert.strip().startswith("-----BEGIN CERTIFICATE-----")
                 and len(key) >= 32 and len(key) <= 256
                 and all(33 <= ord(char) <= 126 for char in key))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise RemoteOcrError("invalid_private_configuration")
    try:
        context = ssl.create_default_context(cadata=cert)
    except (ValueError, ssl.SSLError):
        raise RemoteOcrError("invalid_tls_trust") from None
    # urllib's HTTPSHandler verifies the peer certificate, including its IP SAN.
    return raw, key, context


def recognize(image, enhanced=False, *, opener=None):
    """Return [two_or_three_passes] or None. Existing local parser verifies all."""
    if not configured():
        return None
    target, key, context = _target()
    png = image.get("png") if isinstance(image, dict) else None
    if not isinstance(png, str) or len(png) < 100 or len(png) > 8_000_000:
        raise RemoteOcrError("invalid_input_size")
    try:
        data = base64.b64decode(png, validate=True)
    except (ValueError, base64.binascii.Error):
        raise RemoteOcrError("invalid_base64") from None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RemoteOcrError("not_png")
    digest = hashlib.sha256(data).hexdigest()
    payload = json.dumps({"png": png, "sha256": digest, "enhanced": enhanced is True},
                         separators=(",", ":")).encode()
    request = Request(target, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "X-Bob-Ocr-Key": key,
        "Accept": "application/json",
    })
    client = opener or build_opener(HTTPSHandler(context=context), _NoRedirect())
    try:
        with client.open(request, timeout=70) as response:
            if response.status != 200:
                raise RemoteOcrError("provider_unavailable")
            body = response.read(90_001)
    except RemoteOcrError:
        raise
    except Exception:
        raise RemoteOcrError("provider_unavailable") from None
    if len(body) > 90_000:
        raise RemoteOcrError("response_too_large")
    try:
        message = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise RemoteOcrError("invalid_response") from None
    if not isinstance(message, dict) or set(message) != {"sha256", "passes"}:
        raise RemoteOcrError("invalid_response")
    passes = message["passes"]
    if (message["sha256"] != digest or not isinstance(passes, list) or
        not 2 <= len(passes) <= 3 or
        any(not isinstance(p, str) or len(p) > 30_000 for p in passes)):
        raise RemoteOcrError("invalid_response")
    return [passes]
