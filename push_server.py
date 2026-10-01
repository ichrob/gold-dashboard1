import base64
import json
import os
import secrets
import fibonacci_monitor
import bob_session_store
import bob_market_store
import bob_validation_store
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
        bob_session_store.init(conn)
        bob_market_store.init(conn)
        bob_validation_store.init(conn)
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
        conn.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS trade_monitor JSONB")
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
            if path == "/monitor-status":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                with db() as conn:
                    count = conn.execute("SELECT count(*) FROM subscriptions WHERE trade_enabled=TRUE AND active_trade=TRUE AND trade_monitor IS NOT NULL").fetchone()[0]
                send_json(self, 200, {"activeMonitors": count})
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
            if path in ('/market-validations/read','/market-validations/write'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if not isinstance(payload,dict):raise ValueError('Ungültige Messdaten')
                with db() as conn:
                    result=bob_validation_store.handle(conn,path.rsplit('/',1)[-1],payload)
                    conn.commit()
                send_json(self,200,result)
                return
            if path in ('/market-spots/read','/market-spots/write'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if not isinstance(payload,dict):raise ValueError('Ungültige Spot-Speicherdaten')
                with db() as conn:
                    result=bob_market_store.handle(conn,path.rsplit('/',1)[-1],payload)
                    conn.commit()
                send_json(self,200,result)
                return
            if path in ('/auth-session/create', '/auth-session/check', '/auth-session/revoke'):
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error': 'Unauthorized'})
                    return
                payload = json_body(self)
                if not isinstance(payload, dict):
                    raise ValueError('Ungültige Sitzungsdaten')
                with db() as conn:
                    result = bob_session_store.handle(conn, path.rsplit('/', 1)[-1], payload)
                    conn.commit()
                send_json(self, 200, result)
                return
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
                monitor = fibonacci_monitor.validate_monitor(payload.get("fibonacciMonitor")) if active and trade else None
                with db() as conn:
                    old = conn.execute("SELECT trade_monitor FROM subscriptions WHERE endpoint=%s FOR UPDATE", (endpoint,)).fetchone()
                    if not old:
                        raise ValueError("Push-Abonnement nicht registriert")
                    if monitor and old[0] and old[0].get("tradeId") == monitor["tradeId"]:
                        monitor = old[0]
                    conn.execute("""
                      UPDATE subscriptions
                      SET general_enabled=%s, trade_enabled=%s, active_trade=%s, trade_monitor=%s::jsonb, updated_at=now()
                      WHERE endpoint=%s
                    """, (general, trade, active, json.dumps(monitor) if monitor else None, endpoint))
                    conn.commit()
                send_json(self, 200, {"ok": True, "fibonacciMonitor": "active" if monitor else "inactive"})
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

            if path == "/monitor":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                bars_by_tf = payload.get("barsByTf", {})
                if not isinstance(bars_by_tf, dict):
                    raise ValueError("Kerzendaten fehlen")
                sent = 0
                with db() as conn:
                    rows = conn.execute("SELECT id, subscription, trade_monitor FROM subscriptions WHERE trade_enabled=TRUE AND active_trade=TRUE AND trade_monitor IS NOT NULL FOR UPDATE").fetchall()
                    key = vapid() if rows else None
                    for sid, sub, monitor in rows:
                        checkpoint, alerts, status = fibonacci_monitor.advance_monitor(monitor, bars_by_tf.get(monitor['timeframe'], []))
                        delivered = True
                        # Coalesce simultaneous level breaks into one notification.
                        if alerts:
                            event = alerts[-1]
                            latest_alerts = [a for a in alerts if a['candleClosedAt']==event['candleClosedAt'] and a['crossed']==event['crossed']]
                            label = ", ".join(a['levelLabel'] + " bei " + format(a['levelPrice'], '.2f') for a in latest_alerts)
                            body = (f"{event['instrument']} · {event['direction']}-Trade · {event['timeframe']}-Kerzenschluss {event['price']:.2f} USD. "
                                    f"Fibonacci {label} USD nach {'oben' if event['crossed']=='up' else 'unten'} durchbrochen · "
                                    f"{'für' if event['favorable'] else 'gegen'} deine Position. Kein automatischer Trade.")
                            try:
                                webpush(subscription_info=sub, data=json.dumps({'title':'Bob – Fibonacci-Level durchbrochen','body':body,'data':{**event,'events':latest_alerts,'url':'/','kind':'trade'}},separators=(',',':')), vapid_private_key=key,vapid_claims={'sub':VAPID_SUBJECT},ttl=300)
                                sent += 1
                            except WebPushException as exc:
                                delivered = False
                                code = getattr(getattr(exc, 'response', None), 'status_code', None)
                                if code in (404, 410):
                                    conn.execute("DELETE FROM subscriptions WHERE id=%s", (sid,))
                                print("BOB_FIB delivery_failed status="+str(code), flush=True)
                        if delivered:
                            if status == 'expired':
                                conn.execute("UPDATE subscriptions SET trade_monitor=NULL WHERE id=%s", (sid,))
                            else:
                                conn.execute("UPDATE subscriptions SET trade_monitor=%s::jsonb WHERE id=%s", (json.dumps(checkpoint),sid))
                    conn.commit()
                send_json(self, 200, {'ok':True,'sent':sent})
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

if __name__ == "__main__":
    init_db()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
