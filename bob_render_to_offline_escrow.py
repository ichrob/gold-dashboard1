"""Local-only Render -> offline AES root escrow.

NO remote command endpoint, service deployment, log upload or GitHub credential.
This CLI is run deliberately in Termux on a device controlled by the operator.
The Render API key is requested with getpass; the original PUSH_SERVICE_TOKEN
exists only transiently in local process memory and goes straight into the
already reviewed authenticated offline escrow format. Nothing prints either key.
"""
import getpass
import hmac
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bob_offline_key_escrow import create_escrow, unlock_escrow

API_HOST = "https://api.render.com"
TARGET_SERVICE = "bob-push-service"
TARGET_ENV_KEY = "PUSH_SERVICE_TOKEN"
OUTPUT = Path.home() / "bob-sicher" / "bob-archive-root.vault"
_SERVICE_ID = re.compile(r"srv-[a-z0-9]{8,64}\\Z")
MAX_REPLY = 262144


class TransportBlocked(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_json(token, path, *, opener=None):
    """Pinned HTTPS Render API only, with redirects disabled and byte cap."""
    if (type(token) is not str or not 20 <= len(token) <= 4096 or
            "\n" in token or "\r" in token):
        raise TransportBlocked("Invalid authentication")
    if (not path.startswith("/v1/") or "//" in path or
            "?" in path and path.count("?") > 1 or
            any(c in path for c in ("#", "\r", "\n", "\\", "@"))):
        raise TransportBlocked("Invalid Render API path")
    # The only permitted endpoints are service discovery and the single
    # exact named environment variable on a verified service identity.
    allowed = path == "/v1/services?limit=100"
    if not allowed and path.startswith("/v1/services?limit=100&cursor="):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        allowed = (set(query) == {"limit", "cursor"} and
                   query.get("limit") == ["100"] and
                   len(query.get("cursor", [])) == 1 and
                   0 < len(query["cursor"][0]) <= 1024)
    if not allowed:
        m = re.fullmatch(r"/v1/services/(srv-[a-z0-9]{8,64})/env-vars/PUSH_SERVICE_TOKEN", path)
        allowed = m is not None
    if not allowed:
        raise TransportBlocked("Unapproved Render API request")

    request = urllib.request.Request(
        API_HOST + path, method="GET",
        headers={"Accept": "application/json",
                 "Authorization": "Bearer " + token,
                 "User-Agent": "bob-offline-escrow/1"})
    opener = opener or urllib.request.build_opener(
        NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=12) as resp:
            if resp.status != 200:
                raise TransportBlocked("Render API response rejected")
            data = resp.read(MAX_REPLY + 1)
            if len(data) > MAX_REPLY:
                raise TransportBlocked("Oversized Render API response")
            return json.loads(data.decode("utf-8"))
    except (urllib.error.URLError, OSError, UnicodeError, ValueError) as error:
        raise TransportBlocked("Render API read unavailable") from None


def discover_service(token, fetch=read_json):
    """The exact service name must be unique. No free-form target allowed."""
    found = set()
    cursor = None
    seen = set()
    for _ in range(5):
        path = "/v1/services?limit=100"
        if cursor:
            path += "&cursor=" + urllib.parse.quote(cursor, safe="")
        data = fetch(token, path)
        if type(data) is not list or len(data) > 100:
            raise TransportBlocked("Unexpected service list")
        for row in data:
            if not isinstance(row, dict):
                raise TransportBlocked("Unexpected service entry")
            service = row.get("service")
            if not isinstance(service, dict):
                raise TransportBlocked("Unexpected service metadata")
            if service.get("name") == TARGET_SERVICE:
                sid = service.get("id")
                if type(sid) is not str or not _SERVICE_ID.fullmatch(sid):
                    raise TransportBlocked("Invalid service identifier")
                found.add(sid)
        if len(found) > 1:
            raise TransportBlocked("Ambiguous push service")
        if len(data) < 100:
            break
        cursor = data[-1].get("cursor")
        if (type(cursor) is not str or not cursor or
                len(cursor) > 1024 or cursor in seen):
            raise TransportBlocked("Unknown pagination boundary")
        seen.add(cursor)
    else:
        raise TransportBlocked("Service list limit reached")
    if len(found) != 1:
        raise TransportBlocked("Target service missing")
    return next(iter(found))


def original_root(token, fetch=read_json):
    sid = discover_service(token, fetch)
    data = fetch(token, f"/v1/services/{sid}/env-vars/{TARGET_ENV_KEY}")
    env = data.get("envVar") if isinstance(data, dict) else None
    if (not isinstance(env, dict) or
            env.get("key") != TARGET_ENV_KEY or
            type(env.get("value")) is not str):
        # This includes linked environment-group values, which are NOT
        # implicitly accessible through the service endpoint.
        raise TransportBlocked("Original root not directly available")
    root = env["value"].encode("utf-8")
    if not 32 <= len(root) <= 4096 or b"\x00" in root:
        raise TransportBlocked("Invalid original root")
    return root


def run_once(*, input_secret=getpass.getpass, fetch=read_json, output=OUTPUT):
    """Private interactive procedure, never called by an Android remote action."""
    if Path(output).exists():
        raise TransportBlocked("Escrow file already exists; do not overwrite")
    api_token = input_secret("Temporary Render API key (hidden): ")
    if not api_token:
        raise TransportBlocked("Missing API credential")
    try:
        root = original_root(api_token, fetch)
    finally:
        # The network credential is never written to disk or environment.
        api_token = None
    password = input_secret("New independent offline passphrase (hidden): ")
    repeat = input_secret("Repeat passphrase (hidden): ")
    if not hmac.compare_digest(password, repeat):
        raise TransportBlocked("Passphrase confirmation mismatch")
    Path(output).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = create_escrow(root, password, output)
    reopened = unlock_escrow(output, password)
    if not hmac.compare_digest(root, reopened):
        Path(output).unlink(missing_ok=True)
        raise TransportBlocked("Local escrow roundtrip failed")
    return {"status": result["status"],
            "localRoundtripVerified": True,
            "renderEnvSource": TARGET_SERVICE + ":" + TARGET_ENV_KEY,
            "offlineMediaVerified": False,
            "archiveCiphertextVerified": False,
            "independentPostgresRestoreVerified": False,
            "productionDataChanged": False,
            "secretTransmittedToChat": False}


def main():
    # No input is accepted from command line, network, ChatGPT or clipboard.
    if len(sys.argv) != 1:
        print(json.dumps({"status": "blocked", "reason": "no-arguments-accepted"}))
        return 2
    try:
        result = run_once()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        # Never print URLs, exception messages, API secrets or the root.
        print(json.dumps({"status": "blocked", "errorType": type(error).__name__,
                          "productionDataChanged": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
