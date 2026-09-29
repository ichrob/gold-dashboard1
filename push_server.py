import base64
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import psycopg
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import webpush, WebPushException

PORT = int(os.environ.get("PORT", "10000"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:bob@localhost")
PUSH_SERVICE_TOKEN = os.environ.get("PUSH_SERVICE_TOKEN", "")
BOB_ORIGIN = os.environ.get("BOB_ORIGIN", "")

def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL fehlt")
    return psycopg.connect(DATABASE_URL)

def init_db():
    with db() as conn:
        conn.execute("""
          CREATE TABLE IF NOT EXISTS subscriptions (
            id BIGSERIAL PRIMARY KEY,
            endpoint TEXT UNIQUE NOT NULL,
            subscription JSONB NOT NULL,
            general_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            trade_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            active_trade BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
          )
        """)
        conn.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS general_enabled BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS trade_enabled BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS active_trade BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("""
          CREATE TABLE IF NOT EXISTS bob_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
          )
        """)
        row = conn.execute(
            "SELECT value FROM bob_settings WHERE key = 'vapid_private_pem'"
        ).fetchone()
        if not row:
            vapid_key = Vapid()
            vapid_key.generate_keys()
            pem = vapid_key.private_pem().decode("utf-8")
            conn.execute(
                "INSERT INTO bob_settings(key, value) VALUES(%s, %s)",
                ("vapid_private_pem", pem),
            )
        conn.commit()

def vapid():
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM bob_settings WHERE key = 'vapid_private_pem'"
        ).fetchone()
    if not row:
        raise RuntimeError("VAPID-Key fehlt")
    return Vapid.from_pem(row[0].encode("utf-8"))

def vapid_public_key():
    key = vapid().public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(key).rstrip(b"=").decode()

def cors(handler):
    origin = handler.headers.get("Origin", "")
    if origin and BOB_ORIGIN and origin != BOB_ORIGIN:
        return False
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
    handler.send_header(
        "Access-Control-Allow-Headers", "Content-Type, X-Bob-Push-Token"
    )
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    return True

def json_body(handler):
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0 or length > 65536:
        raise ValueError("Ungültige Payload-Größe")
    return json.loads(handler.rfile.read(length).decode("utf-8"))

def send_json(handler, status, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    cors(handler)
    handler.end_headers()
    handler.wfile.write(body)

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        cors(self)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/health":
                vapid()
                with db() as conn:
                    conn.execute("SELECT 1").fetchone()
                send_json(self, 200, {"ok": True})
                return
            if path == "/vapid-public-key":
                send_json(self, 200, {"publicKey": vapid_public_key()})
                return
            send_json(self, 404, {"error": "Not found"})
        except Exception as exc:
            print("push-service error:", type(exc).__name__, flush=True)
            send_json(self, 503, {"error": "Push-Service nicht bereit"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = json_body(self)
            if path == "/subscribe":
                sub = payload.get("subscription")
                endpoint = sub.get("endpoint") if isinstance(sub, dict) else None
                if not endpoint or not isinstance(sub, dict):
                    raise ValueError("subscription fehlt")
                with db() as conn:
                    conn.execute("""
                      INSERT INTO subscriptions(endpoint, subscription)
                      VALUES(%s, %s::jsonb)
                      ON CONFLICT(endpoint) DO UPDATE
                      SET subscription=EXCLUDED.subscription, updated_at=now()
                    """, (endpoint, json.dumps(sub)))
                    conn.commit()
                send_json(self, 200, {"ok": True})
                return

            if path == "/preferences":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                endpoint = payload.get("endpoint")
                if not endpoint:
                    raise ValueError("endpoint fehlt")
                general = bool(payload.get("general"))
                trade = bool(payload.get("trade"))
                active = bool(payload.get("activeTrade"))
                with db() as conn:
                    conn.execute("""
                      UPDATE subscriptions
                      SET general_enabled=%s, trade_enabled=%s, active_trade=%s, updated_at=now()
                      WHERE endpoint=%s
                    """, (general, trade, active, endpoint))
                    conn.commit()
                send_json(self, 200, {"ok": True})
                return

            if path == "/unsubscribe":
                endpoint = payload.get("endpoint")
                if not endpoint:
                    raise ValueError("endpoint fehlt")
                with db() as conn:
                    conn.execute(
                        "DELETE FROM subscriptions WHERE endpoint=%s", (endpoint,)
                    )
                    conn.commit()
                send_json(self, 200, {"ok": True})
                return

            if path == "/send":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(
                    supplied, PUSH_SERVICE_TOKEN
                ):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return

                title = str(payload.get("title", "Bob"))[:120]
                body = str(payload.get("body", ""))[:1000]
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                message = json.dumps(
                    {"title": title, "body": body, "data": data},
                    separators=(",", ":"),
                )
                vapid_key = vapid()
                kind = str(payload.get("kind") or payload.get("data", {}).get("kind") or "general").lower()
                if kind == "signal":
                    kind = "general"
                if kind not in ("general", "trade"):
                    kind = "general"
                is_test = bool(data.get("test")) if isinstance(data, dict) else False
                with db() as conn:
                    if kind == "trade":
                        if is_test:
                            rows = conn.execute(
                                "SELECT id, endpoint, subscription FROM subscriptions WHERE trade_enabled=TRUE"
                            ).fetchall()
                        else:
                            rows = conn.execute(
                                "SELECT id, endpoint, subscription FROM subscriptions WHERE trade_enabled=TRUE AND active_trade=TRUE"
                            ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT id, endpoint, subscription FROM subscriptions WHERE general_enabled=TRUE"
                        ).fetchall()

                sent = 0
                removed = 0
                vapid_reset = False
                for sid, endpoint, sub in rows:
                    try:
                        webpush(
                            subscription_info=sub,
                            data=message,
                            vapid_private_key=vapid_key,
                            vapid_claims={"sub": VAPID_SUBJECT},
                            ttl=3600,
                        )
                        sent += 1
                    except WebPushException as exc:
                        code = getattr(getattr(exc, "response", None), "status_code", None)
                        if code in (404, 410):
                            with db() as conn:
                                conn.execute(
                                    "DELETE FROM subscriptions WHERE id=%s", (sid,)
                                )
                                conn.commit()
                            removed += 1
                        elif code == 403:
                            # A 403 from the push provider can mean that the
                            # subscription was created with a previous VAPID key.
                            # Remove it so the browser can recreate it cleanly.
                            with db() as conn:
                                conn.execute(
                                    "DELETE FROM subscriptions WHERE id=%s", (sid,)
                                )
                                conn.commit()
                            removed += 1
                            vapid_reset = True
                        else:
                            response = getattr(exc, "response", None)
                            status = getattr(response, "status_code", None)
                            detail = str(getattr(response, "text", "") or "")[:300]
                            print(
                                f"push delivery failed ({type(exc).__name__}) status={status} detail={detail}",
                                flush=True,
                            )
                send_json(self, 200, {"ok": True, "sent": sent, "removed": removed, "vapidReset": vapid_reset})
                return

            send_json(self, 404, {"error": "Not found"})
        except (ValueError, json.JSONDecodeError) as exc:
            send_json(self, 400, {"error": str(exc)})
        except Exception as exc:
            print("push-service error:", type(exc).__name__, flush=True)
            send_json(self, 500, {"error": "Interner Push-Service-Fehler"})

    def log_message(self, fmt, *args):
        pass

init_db()
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
