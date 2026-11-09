"""Oracle A1 Always Free: bounded HTTPS OCR for one private screenshot.

TLS terminates in this process using a private certificate with IP SAN; no
public HTTP endpoint, file upload storage, database or external OCR API.
"""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import ssl
import subprocess
import sys


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log IPs, image text, bearer keys, headers or request paths.

    def respond(self, status, data):
        body = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        return self.respond(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/ocr":
            return self.respond(404, {"error": "not_found"})
        token = os.environ.get("BOB_REMOTE_OCR_TOKEN", "")
        received = self.headers.get("X-Bob-Ocr-Key", "")
        if not (32 <= len(token) <= 256 and hmac.compare_digest(received, token)):
            return self.respond(401, {"error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 100 <= length <= 8_010_000:
                return self.respond(413, {"error": "input_bounds"})
            message = json.loads(self.rfile.read(length))
            if not isinstance(message, dict) or set(message) != {"png", "sha256", "enhanced"}:
                raise ValueError
            png, digest, enhanced = message["png"], message["sha256"], message["enhanced"]
            if (not isinstance(png, str) or len(png) > 8_000_000 or
                    not isinstance(digest, str) or len(digest) != 64 or
                    type(enhanced) is not bool):
                raise ValueError
            raw = base64.b64decode(png, validate=True)
            if (not raw.startswith(b"\x89PNG\r\n\x1a\n") or
                    hashlib.sha256(raw).hexdigest() != digest):
                raise ValueError
            env = {k: v for k, v in os.environ.items()
                   if k in ("PATH", "LANG", "LD_LIBRARY_PATH", "PYTHONPATH")}
            env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                       MKL_NUM_THREADS="1")
            result = subprocess.run(
                [sys.executable, "handset_list_worker.py", "--ocr"] +
                (["--enhanced"] if enhanced else []),
                input=json.dumps([{"png": png}]), text=True, capture_output=True,
                timeout=55, check=True, env=env)
            if len(result.stdout) > 90_000:
                raise ValueError
            recognized = json.loads(result.stdout)
            if (not isinstance(recognized, list) or len(recognized) != 1
                    or not isinstance(recognized[0], list)
                    or not 2 <= len(recognized[0]) <= 3
                    or any(not isinstance(s, str) or len(s) > 30_000
                           for s in recognized[0])):
                raise ValueError
            return self.respond(200, {"sha256": digest, "passes": recognized[0]})
        except (ValueError, OSError, subprocess.SubprocessError):
            return self.respond(422, {"error": "recognition_failed"})


class TLSServer(HTTPServer):
    """A bare TCP scanner must not kill the HTTPS worker process."""
    def __init__(self, address, handler, context):
        self.tls_context = context
        super().__init__(address, handler)

    def get_request(self):
        while True:
            raw, peer = super().get_request()
            raw.settimeout(15)
            try:
                return self.tls_context.wrap_socket(raw, server_side=True), peer
            except (ssl.SSLError, TimeoutError, ConnectionError):
                raw.close()


def serve():
    cert = os.environ.get("BOB_ORACLE_OCR_TLS_CERT", "/run/secrets/tls.crt")
    key = os.environ.get("BOB_ORACLE_OCR_TLS_KEY", "/run/secrets/tls.key")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert, keyfile=key)
    server = TLSServer(("0.0.0.0", 8443), Handler, context)
    server.serve_forever()


if __name__ == "__main__":
    serve()
