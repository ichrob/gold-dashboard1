import base64, json, os, secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import psycopg
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import webpush, WebPushException

PORT=int(os.environ.get("PORT","10000"))
DATABASE_URL=os.environ.get("DATABASE_URL","")
VAPID_PRIVATE_KEY=os.environ.get("VAPID_PRIVATE_KEY","")
VAPID_SUBJECT=os.environ.get("VAPID_SUBJECT","mailto:bob@localhost")
PUSH_SERVICE_TOKEN=os.environ.get("PUSH_SERVICE_TOKEN","")
BOB_ORIGIN=os.environ.get("BOB_ORIGIN","")

def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL fehlt")
    return psycopg.connect(DATABASE_URL)

def vapid():
    if not VAPID_PRIVATE_KEY:
        raise RuntimeError("VAPID_PRIVATE_KEY fehlt")
    raw=VAPID_PRIVATE_KEY.strip().encode().replace(b"+",b"-").replace(b"/",b"_").rstrip(b"=")
    return Vapid.from_string(raw.decode())

def vapid_public_key():
    key=vapid().public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(key).rstrip(b"=").decode()

def init_db():
    with db() as conn:
        conn.execute("""
          CREATE TABLE IF NOT EXISTS subscriptions (
            id BIGSERIAL PRIMARY KEY,
            endpoint TEXT UNIQUE NOT NULL,
            subscription JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
          )
        """)
        conn.commit()

def cors(handler):
    origin=handler.headers.get("Origin","")
    if origin and BOB_ORIGIN and origin != BOB_ORIGIN:
        return False
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary","Origin")
    handler.send_header("Access-Control-Allow-Headers","Content-Type, X-Bob-Push-Token")
    handler.send_header("Access-Control-Allow-Methods","POST, OPTIONS")
    return True

def json_body(handler):
    length=int(handler.headers.get("Content-Length","0") or 0)
    if length<=0 or length>65536:
        raise ValueError("Ungültige Payload-Größe")
    return json.loads(handler.rfile.read(length).decode("utf-8"))

def send_json(handler,status,payload):
    body=json.dumps(payload,separators=(",",":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type","application/json; charset=utf-8")
    handler.send_header("Cache-Control","no-store")
    handler.send_header("X-Content-Type-Options","nosniff")
    cors(handler)
    handler.end_headers()
    handler.wfile.write(body)

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        cors(self)
        self.end_headers()

    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/vapid-public-key":
            send_json(self,200,{"publicKey":vapid_public_key()})
            return
        if path=="/health":
            send_json(self,200,{"ok":True})
            return
        send_json(self,404,{"error":"Not found"})

    def do_POST(self):
        path=urlparse(self.path).path
        try:
            payload=json_body(self)
            if path=="/subscribe":
                sub=payload.get("subscription")
                endpoint=sub.get("endpoint") if isinstance(sub,dict) else None
                if not endpoint or not isinstance(sub,dict):
                    raise ValueError("subscription fehlt")
                with db() as conn:
                    conn.execute("""
                      INSERT INTO subscriptions(endpoint,subscription)
                      VALUES(%s,%s::jsonb)
                      ON CONFLICT(endpoint) DO UPDATE
                      SET subscription=EXCLUDED.subscription, updated_at=now()
                    """,(endpoint,json.dumps(sub)))
                    conn.commit()
                send_json(self,200,{"ok":True})
                return

            if path=="/unsubscribe":
                endpoint=payload.get("endpoint")
                if not endpoint:
                    raise ValueError("endpoint fehlt")
                with db() as conn:
                    conn.execute("DELETE FROM subscriptions WHERE endpoint=%s",(endpoint,))
                    conn.commit()
                send_json(self,200,{"ok":True})
                return

            if path=="/send":
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(
                    self.headers.get("X-Bob-Push-Token",""),PUSH_SERVICE_TOKEN):
                    send_json(self,401,{"error":"Unauthorized"})
                    return
                title=str(payload.get("title","Bob"))[:120]
                body=str(payload.get("body",""))[:1000]
                data=payload.get("data") if isinstance(payload.get("data"),dict) else {}
                message=json.dumps({"title":title,"body":body,"data":data},separators=(",",":"))
                with db() as conn:
                    rows=conn.execute("SELECT id,endpoint,subscription FROM subscriptions").fetchall()
                sent=0; removed=0
                for sid,endpoint,sub in rows:
                    try:
                        webpush(
                            subscription_info=sub,
                            data=message,
                            vapid_private_key=VAPID_PRIVATE_KEY,
                            vapid_claims={"sub":VAPID_SUBJECT}
                        )
                        sent+=1
                    except WebPushException as exc:
                        code=getattr(getattr(exc,"response",None),"status_code",None)
                        if code in (404,410):
                            with db() as conn:
                                conn.execute("DELETE FROM subscriptions WHERE id=%s",(sid,))
                                conn.commit()
                            removed+=1
                send_json(self,200,{"ok":True,"sent":sent,"removed":removed})
                return
            send_json(self,404,{"error":"Not found"})
        except (ValueError, json.JSONDecodeError) as exc:
            send_json(self,400,{"error":str(exc)})
        except Exception as exc:
            print("push-service error:",type(exc).__name__,flush=True)
            send_json(self,500,{"error":"Interner Push-Service-Fehler"})

    def log_message(self,fmt,*args):
        pass

init_db()
ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
