"""Opt-in isolated OCR fallback for memory-blocked DEGIRO screenshot imports.

Never transmits data unless explicitly enabled AND configured to an allowlisted
Google Cloud Run HTTPS hostname. No retry, no redirect, no product approval.
"""
import base64
import hashlib
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler


class RemoteOcrError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RemoteOcrError("redirect_not_allowed")


def configured():
    return os.environ.get("BOB_REMOTE_OCR_ENABLED") == "true"


def _fetch_identity_token(audience):
    """Google Cloud Run IAM token using a securely configured service account.

    Never use an unauthenticated public Cloud Run endpoint. Keep JSON keys only
    in provider-managed secrets; do not log or persist credentials.
    """
    value = os.environ.get("BOB_REMOTE_OCR_GCP_SA_JSON", "")
    if len(value) < 100 or len(value) > 12_000:
        raise RemoteOcrError("missing_cloud_identity")
    try:
        info = json.loads(value)
        if info.get("type") != "service_account":
            raise ValueError("service account required")
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as AuthRequest
        credentials = service_account.IDTokenCredentials.from_service_account_info(
            info, target_audience=audience)
        credentials.refresh(AuthRequest())
        if not credentials.token:
            raise ValueError("no ID token")
        return credentials.token
    except Exception:
        raise RemoteOcrError("cloud_identity_unavailable") from None


def recognize(image, enhanced=False, *, opener=None):
    """Return [passes] or None when disabled. The caller revalidates locally."""
    if not configured():
        return None
    target = os.environ.get("BOB_REMOTE_OCR_URL", "")
    token = os.environ.get("BOB_REMOTE_OCR_TOKEN", "")
    parts = urlsplit(target)
    host = parts.hostname or ""
    if (parts.scheme != "https" or not host.endswith(".a.run.app")
            or parts.port is not None or parts.username or parts.password
            or parts.path != "/ocr" or parts.query or parts.fragment
            or len(token) < 32 or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)):
        raise RemoteOcrError("invalid_private_configuration")
    data = image.get("png") if isinstance(image, dict) else None
    if not isinstance(data, str) or len(data) > 8_000_000 or len(data) < 100:
        raise RemoteOcrError("invalid_input_size")
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, base64.binascii.Error):
        raise RemoteOcrError("invalid_base64") from None
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RemoteOcrError("not_png")
    digest = hashlib.sha256(raw).hexdigest()
    body = json.dumps({"png": data, "sha256": digest, "enhanced": enhanced is True},
                      separators=(",", ":")).encode()
    # Cloud Run IAM validates this short-lived Google-signed ID token before
    # allocating the container; the secondary secret restricts app-layer use.
    identity = _fetch_identity_token(parts.scheme + "://" + parts.netloc)
    request = Request(target, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + identity,
        "X-Bob-Ocr-Key": token,
        "Accept": "application/json",
    })
    client = opener or build_opener(HTTPSHandler(), _NoRedirect())
    try:
        with client.open(request, timeout=70) as response:
            if response.status != 200:
                raise RemoteOcrError("provider_unavailable")
            response_body = response.read(90_001)
    except RemoteOcrError:
        raise
    except Exception:
        raise RemoteOcrError("provider_unavailable") from None
    if len(response_body) > 90_000:
        raise RemoteOcrError("response_too_large")
    try:
        message = json.loads(response_body)
    except (ValueError, UnicodeDecodeError):
        raise RemoteOcrError("invalid_response") from None
    if not isinstance(message, dict) or set(message) != {"sha256", "passes"}:
        raise RemoteOcrError("invalid_response")
    passes = message["passes"]
    if (message["sha256"] != digest or not isinstance(passes, list)
            or not 2 <= len(passes) <= 3
            or any(not isinstance(p, str) or len(p) > 30_000 for p in passes)):
        raise RemoteOcrError("invalid_response")
    return [passes]
