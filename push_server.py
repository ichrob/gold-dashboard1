import base64
import json
import os
import secrets
import threading
import time
import product_push
import fibonacci_monitor
import background_push
import bob_session_store
import bob_market_store
import bob_validation_store
import decision_audit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import psycopg
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import webpush as _webpush, WebPushException
from requests.exceptions import RequestException

PORT = int(os.environ.get("PORT", "10000"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:bob@localhost")
PUSH_SERVICE_TOKEN = os.environ.get("PUSH_SERVICE_TOKEN", "")
BOB_ORIGIN = os.environ.get("BOB_ORIGIN", "")

def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL fehlt")
    return psycopg.connect(DATABASE_URL, connect_timeout=5,
                           options="-c lock_timeout=3000 -c statement_timeout=10000")

def webpush(**kwargs):
    # Never hold subscription locks indefinitely on an unreachable push provider.
    kwargs['timeout'] = 8
    try:
        return _webpush(**kwargs)
    except RequestException as exc:
        raise WebPushException('Push provider connection failed') from exc


def init_db():
    for attempt in range(3):
        try:
            _init_db_once()
            return
        except (psycopg.errors.LockNotAvailable, psycopg.errors.DeadlockDetected,
                psycopg.errors.SerializationFailure):
            if attempt == 2:
                raise
            print(f'BOB_PUSH startup=database_retry attempt={attempt + 1}', flush=True)
            time.sleep(attempt + 1)


def _init_db_once():
    with db() as conn:
        bob_session_store.init(conn)
        bob_market_store.init(conn)
        bob_validation_store.init(conn)
        decision_audit.init(conn)
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
        # Even a no-op ALTER requests an exclusive table lock. Existing
        # subscriptions are in use by the old instance during rolling deploys.
        existing = {row[0] for row in conn.execute("""
            SELECT attname FROM pg_attribute
            WHERE attrelid = 'subscriptions'::regclass
              AND attnum > 0 AND NOT attisdropped
        """).fetchall()}
        columns = {
            **{name: 'BOOLEAN NOT NULL DEFAULT FALSE' for name in
               ('general_enabled', 'trade_enabled', 'active_trade')},
            **{name: 'JSONB' for name in ('trade_monitor', 'product_selection',
               'background_config', 'background_state', 'selection_evidence', 'pending_test')},
        }
        for column, definition in columns.items():
            if column not in existing:
                conn.execute('ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS '
                             + column + ' ' + definition)
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
    if length <= 0 or length > (1048576 if urlparse(handler.path).path in ("/selection", "/background") else 65536):
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

def deliver_product_selection(conn, row, checked):
    sid, sub, previous = row
    state, message = product_push.transition(previous, checked)
    if message:
        ttl = max(1, min(300, int((message['data']['expiresAt']-time.time()*1000)/1000)))
        try:
            webpush(subscription_info=sub, data=json.dumps(message, separators=(',', ':')),
                    vapid_private_key=vapid(), vapid_claims={'sub': VAPID_SUBJECT}, ttl=ttl)
        except WebPushException as exc:
            code = getattr(getattr(exc, 'response', None), 'status_code', None)
            if code in (404, 410):
                conn.execute("DELETE FROM subscriptions WHERE id=%s", (sid,))
            return 0  # Failed delivery must not consume a notification transition.
    conn.execute("UPDATE subscriptions SET product_selection=%s::jsonb WHERE id=%s", (json.dumps(state), sid))
    return int(message is not None)


def expire_product_selections():
    now = int(time.time()*1000)
    with db() as conn:
        rows = conn.execute("SELECT id, subscription, product_selection FROM subscriptions WHERE general_enabled=TRUE AND product_selection IS NOT NULL AND (product_selection->>'notified')::boolean=TRUE AND (product_selection->>'expiresAt')::bigint<=%s FOR UPDATE", (now,)).fetchall()
        for row in rows:
            deliver_product_selection(conn, row, {'products': [], 'expiresAt': now, 'reasons': ['Aktuelle Bestätigung abgelaufen; Bob öffnen und erneut prüfen']})
        conn.commit()


def product_expiry_loop():
    while True:
        try:
            expire_product_selections()
            deliver_background_tests()
        except Exception as exc:
            print('BOB_PRODUCT expiry_error='+type(exc).__name__, flush=True)
        time.sleep(15)


def deliver_background_tests():
    now=int(time.time()*1000)
    with db() as conn:
        rows=conn.execute("SELECT id, subscription, pending_test, general_enabled, trade_enabled FROM subscriptions WHERE pending_test IS NOT NULL AND (pending_test->>'dueAt')::bigint<=%s FOR UPDATE",(now,)).fetchall()
        for sid, sub, pending, general, trade in rows:
            allowed=general if pending['kind']=='general' else trade
            if allowed and now < pending['dueAt']+300000:
                message={'title':'TEST · Push bei geschlossener App','body':'Diese Testnachricht wurde zeitversetzt auf dem Server ausgelöst. Kein Handelssignal.','tag':'bob-background-test','data':{'kind':pending['kind'],'test':True,'url':'/','expiresAt':now+180000}}
                try:
                    webpush(subscription_info=sub,data=json.dumps(message),vapid_private_key=vapid(),vapid_claims={'sub':VAPID_SUBJECT},ttl=180)
                except WebPushException:
                    continue
            conn.execute('UPDATE subscriptions SET pending_test=NULL WHERE id=%s',(sid,))
        conn.commit()


def run_background(bundle):
    sent = 0
    with db() as conn:
        rows = conn.execute("SELECT id, subscription, general_enabled, trade_enabled, active_trade, background_config, background_state, selection_evidence, product_selection FROM subscriptions WHERE (general_enabled=TRUE OR (trade_enabled=TRUE AND active_trade=TRUE)) AND background_config IS NOT NULL FOR UPDATE").fetchall()
        for sid, sub, general, trade, active, settings, previous, evidence, selection in rows:
            try:
                market = background_push.analyze(bundle, settings)
            except Exception as exc:
                print('BOB_BACKGROUND analysis_failed='+type(exc).__name__, flush=True)
                market = {'ready':False,'priceFresh':False}
            # Audit failures must not interrupt stop/target monitoring or its transaction.
            try:
                with conn.transaction():
                    if market.get('analysisBarAt'):
                        decision_audit.write(conn,{'origin':'background','direction':market.get('direction','NEUTRAL'),
                            'shadowDirection':market.get('shadowDirection'),'intraday':market.get('intraday'),'barAt':market['analysisBarAt'],
                            'price':market.get('price'),'priceAt':market.get('dataAt'),'reason':market.get('decisionReason'),
                            'score':market.get('score'),'indicators':market.get('context'), 'products':[],
                            'selection':[], 'gateReasons':[] if market.get('ready') else ['Marktdaten nicht freigegeben']})
                        decision_audit.harvest(conn)
            except Exception as exc:
                print('BOB_AUDIT write_failed='+type(exc).__name__,flush=True)
            state, events = background_push.advance(previous, settings, market, general, trade and active)
            delivered = True
            if events:
                # One delivery/checkpoint per device, so a failure cannot consume an alert.
                priority = {'stop-hit':0,'reversal':1,'target':2}
                events.sort(key=lambda e:priority.get(e['data']['eventKind'],3))
                message = dict(events[0])
                message['body'] = ' | '.join(e['body'] for e in events)
                message['data'] = dict(message['data'], events=[e['data']['eventKind'] for e in events])
                if any(e['data']['kind']=='trade' for e in events):
                    message['data']['kind']='trade'
                at=market.get('dataAt')
                if at:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo
                    message['body'] += ' · Kurszeit '+datetime.fromtimestamp(at/1000,ZoneInfo('Europe/Zurich')).strftime('%d.%m. %H:%M:%S')+' (Zürich).'
                else:
                    message['body'] += ' · Kurszeit unbekannt.'
                try:
                    webpush(subscription_info=sub,data=json.dumps(message,separators=(',',':')),vapid_private_key=vapid(),vapid_claims={'sub':VAPID_SUBJECT},ttl=180)
                    sent += 1
                except WebPushException as exc:
                    delivered=False
                    if getattr(getattr(exc,'response',None),'status_code',None) in (404,410):
                        conn.execute('DELETE FROM subscriptions WHERE id=%s',(sid,))
            if delivered:
                state['checkedAt']=int(time.time()*1000)
                conn.execute('UPDATE subscriptions SET background_state=%s::jsonb WHERE id=%s',(json.dumps(state),sid))
            if general and evidence:
                try:
                    checked=product_push.evaluate({**evidence,'capturedAt':int(time.time()*1000),'bundle':bundle,'context':market.get('context',{'direction':'NEUTRAL'})})
                    sent += deliver_product_selection(conn,(sid,sub,selection),checked)
                except Exception as exc:
                    print('BOB_BACKGROUND selection_failed='+type(exc).__name__,flush=True)
        conn.commit()
    return sent


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
                send_json(self, 200, {"ok": True, "productSelectionVerifier": "shared-js-v1"})
                return
            if path == "/monitor-status":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                with db() as conn:
                    count = conn.execute("SELECT count(*) FROM subscriptions WHERE general_enabled=TRUE OR (trade_enabled=TRUE AND active_trade=TRUE)").fetchone()[0]
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
            if path in ('/decision-audit/read','/decision-audit/write'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if path.endswith('/write'):payload['origin']='browser'
                with db() as conn:
                    result=decision_audit.handle(conn,path.rsplit('/',1)[-1],payload)
                    conn.commit()
                send_json(self,200,result)
                return
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
                general = payload.get("general") is True
                trade = bool(payload.get("trade"))
                active = bool(payload.get("activeTrade"))
                monitor = fibonacci_monitor.validate_monitor(payload.get("fibonacciMonitor")) if active and trade else None
                raw_settings = dict(payload.get('background') or {})
                if not (trade and active):
                    raw_settings['trade'] = None
                settings = background_push.config(raw_settings) if 'background' in payload else None
                if settings and not (trade and active):
                    settings['trade'] = None
                with db() as conn:
                    old = conn.execute("SELECT trade_monitor FROM subscriptions WHERE endpoint=%s FOR UPDATE", (endpoint,)).fetchone()
                    if not old:
                        raise ValueError("Push-Abonnement nicht registriert")
                    if monitor and old[0] and old[0].get("tradeId") == monitor["tradeId"]:
                        monitor = old[0]
                    if monitor and settings is not None:
                        monitor = {**monitor, "backgroundManaged": True}
                    background_state = None
                    if settings is not None:
                        row = conn.execute('SELECT background_state FROM subscriptions WHERE endpoint=%s', (endpoint,)).fetchone()
                        background_state = row[0] if row and isinstance(row[0], dict) else {}
                        if not settings.get('trade'):
                            background_state.pop('trade', None)
                        conn.execute('UPDATE subscriptions SET background_config=%s::jsonb, background_state=%s::jsonb WHERE endpoint=%s', (json.dumps(settings),json.dumps(background_state),endpoint))
                    conn.execute("""
                      UPDATE subscriptions
                      SET general_enabled=%s, trade_enabled=%s, active_trade=%s, trade_monitor=%s::jsonb,
                          product_selection=CASE WHEN %s THEN product_selection ELSE NULL END, updated_at=now()
                      WHERE endpoint=%s
                    """, (general, trade, active, json.dumps(monitor) if monitor else None, general, endpoint))
                    conn.commit()
                send_json(self, 200, {"ok": True, "fibonacciMonitor": "active" if monitor else "inactive", "backgroundEnabled": settings is not None, "backgroundTrade": (background_state or {}).get("trade")})
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

            if path == "/test-background":
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                endpoint=payload.get('endpoint')
                with db() as conn:
                    row=conn.execute('SELECT general_enabled, trade_enabled FROM subscriptions WHERE endpoint=%s FOR UPDATE',(endpoint,)).fetchone()
                    if not row or not any(row):
                        raise ValueError('Zuerst Gerät anmelden und mindestens einen Push-Schalter aktivieren')
                    pending={'kind':'general' if row[0] else 'trade','dueAt':int(time.time()*1000)+30000}
                    conn.execute('UPDATE subscriptions SET pending_test=%s::jsonb WHERE endpoint=%s',(json.dumps(pending),endpoint))
                    conn.commit()
                send_json(self,200,{'ok':True,'dueAt':pending['dueAt']})
                return

            if path == "/background":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                sent = run_background(payload.get('bundle') or {})
                send_json(self, 200, {'ok': True, 'sent': sent})
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
                        old_health = monitor.get('dataHealth')
                        checkpoint['dataHealth'] = status
                        if not monitor.get('backgroundManaged') and ((status == 'unavailable' and old_health != 'unavailable') or (status == 'active' and old_health == 'unavailable')):
                            body = ('Aktuelle Kerzendaten fehlen oder sind veraltet. Analyse mit vorhandenen Werten läuft weiter; aktuelle Trade-Überwachung eingeschränkt.' if status == 'unavailable' else 'Aktuelle Kerzendaten wieder vorhanden. Trade-Überwachung fortgesetzt; dies ist keine Entwarnung für den Trade.')
                            try:
                                webpush(subscription_info=sub, data=json.dumps({'title':'DATENSTATUS · Bob', 'body':monitor['instrument']+' · '+monitor['direction']+' · '+body, 'tag':'bob-monitor-health', 'data':{'kind':'trade','url':'/','tradeId':monitor['tradeId']}},separators=(',',':')), vapid_private_key=key,vapid_claims={'sub':VAPID_SUBJECT},ttl=300)
                                sent += 1
                            except WebPushException:
                                delivered = False
                        # Coalesce simultaneous level breaks into one notification.
                        if alerts:
                            event = alerts[-1]
                            latest_alerts = [a for a in alerts if a['candleClosedAt']==event['candleClosedAt'] and a['crossed']==event['crossed']]
                            label = ", ".join(a['levelLabel'] + " bei " + format(a['levelPrice'], '.2f') for a in latest_alerts)
                            body = (f"{event['instrument']} · {event['direction']}-Trade · {event['timeframe']}-Kerzenschluss {event['price']:.2f} USD. "
                                    f"Fibonacci {label} USD nach {'oben' if event['crossed']=='up' else 'unten'} durchbrochen · "
                                    f"{'für' if event['favorable'] else 'gegen'} deine Position. Kein automatischer Trade.")
                            try:
                                webpush(subscription_info=sub, data=json.dumps({'title':'TRADE-WARNUNG · Fibonacci-Level durchbrochen','body':body,'data':{**event,'tradeId':monitor['tradeId'],'events':latest_alerts,'url':'/','kind':'trade'}},separators=(',',':')), vapid_private_key=key,vapid_claims={'sub':VAPID_SUBJECT},ttl=300)
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

            if path == "/selection":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                endpoint = payload.get("endpoint")
                if not isinstance(endpoint, str) or not endpoint:
                    raise ValueError("Push-Abonnement fehlt")
                # Check the persisted switch before running the evaluator, then
                # recheck under a row lock immediately before delivery.
                with db() as conn:
                    row = conn.execute("SELECT general_enabled FROM subscriptions WHERE endpoint=%s", (endpoint,)).fetchone()
                if not row or row[0] is not True:
                    send_json(self, 200, {"ok": True, "sent": 0, "disabled": True})
                    return
                checked = product_push.evaluate(payload)
                with db() as conn:
                    row = conn.execute("SELECT id, subscription, product_selection FROM subscriptions WHERE endpoint=%s AND general_enabled=TRUE FOR UPDATE", (endpoint,)).fetchone()
                    if row:
                        evidence = {k: payload[k] for k in ('products','references','fixedBarriers') if k in payload}
                        conn.execute('UPDATE subscriptions SET selection_evidence=%s::jsonb WHERE id=%s',(json.dumps(evidence),row[0]))
                    sent = deliver_product_selection(conn, row, checked) if row else 0
                    conn.commit()
                send_json(self, 200, {"ok": True, "sent": sent, "disabled": not bool(row), "approvedCount": len(checked['products']) if row else 0})
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
                # No server-side evidence exists for a released product selection.
                if data.get("isin") or any(word in (str(data.get("kind", "")) + " " + str(payload.get("kind", "")) + " " + title).lower() for word in ("product", "best-trade", "best_trade", "bester trade", "produktempfehl")):
                    send_json(self, 200, {"ok": True, "sent": 0, "reason": "Product selection is not verified by the push service"})
                    return
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
                                "SELECT id, endpoint, subscription FROM subscriptions WHERE trade_enabled=TRUE AND active_trade=TRUE AND background_config IS NULL"
                            ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT id, endpoint, subscription FROM subscriptions WHERE general_enabled=TRUE" + ("" if is_test else " AND background_config IS NULL")
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
        # Route and status only: never log device endpoints or authentication data.
        print(f"BOB_PUSH_HTTP method={self.command} path={urlparse(self.path).path} status={args[1] if len(args)>1 else '-'}", flush=True)

if __name__ == "__main__":
    product_push.evaluate({'products': [], 'capturedAt': int(time.time()*1000)})
    print("BOB_PUSH startup=database", flush=True)
    init_db()
    print("BOB_PUSH startup=ready", flush=True)
    threading.Thread(target=product_expiry_loop, name="bob-product-expiry", daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
