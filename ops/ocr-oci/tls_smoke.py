"""CI-only TLS handshake test: no images, only the fake missing-key response."""
import ssl
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

context = ssl.create_default_context(cafile=sys.argv[1])
request = Request("https://127.0.0.1:8443/ocr", data=b"{}", method="POST",
                  headers={"Content-Type": "application/json"})
try:
    with urlopen(request, context=context, timeout=10):
        raise AssertionError("unauthenticated OCR must never succeed")
except HTTPError as error:
    if error.code != 401:
        raise AssertionError("expected fail-closed unauthorized response") from error

print("oracle_ocr_tls_ip_and_private_key_gate=verified")
