"""Standalone bounded OCR HTTP worker for Cloud Run; never stores image data."""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import subprocess
import sys


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log private paths, headers, screenshots or product text.

    def respond(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            return self.respond(200, {"status": "ready"})
        return self.respond(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/ocr":
            return self.respond(404, {"error": "not_found"})
        token = os.environ.get("BOB_REMOTE_OCR_TOKEN", "")
        # Cloud Run IAM already verified the short-lived ID token at the edge.
        # An additional private key remains mandatory at this application layer.
        key = self.headers.get("X-Bob-Ocr-Key", "")
        if (len(token) < 32 or not hmac.compare_digest(key, token)):
            return self.respond(401, {"error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 100 or length > 8_010_000:
                return self.respond(413, {"error": "input_bounds"})
            message = json.loads(self.rfile.read(length))
            if not isinstance(message, dict) or set(message) != {"png", "sha256", "enhanced"}:
                raise ValueError
            png, sha, enhanced = message["png"], message["sha256"], message["enhanced"]
            if (not isinstance(png, str) or len(png) > 8_000_000
                    or not isinstance(sha, str) or len(sha) != 64
                    or type(enhanced) is not bool):
                raise ValueError
            raw = base64.b64decode(png, validate=True)
            if not raw.startswith(b"\x89PNG\r\n\x1a\n") or hashlib.sha256(raw).hexdigest() != sha:
                raise ValueError
            env = {k: v for k, v in os.environ.items() if k in (
                "PATH", "LANG", "LD_LIBRARY_PATH", "PYTHONPATH")}
            env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
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
                    or any(not isinstance(s, str) or len(s) > 30_000 for s in recognized[0])):
                raise ValueError
            return self.respond(200, {"sha256": sha, "passes": recognized[0]})
        except (OSError, ValueError, subprocess.SubprocessError):
            # Never include image, source output, exception, or identities.
            return self.respond(422, {"error": "recognition_failed"})


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
