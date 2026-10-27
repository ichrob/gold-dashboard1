import candle_reliability
import bob_passkey_store
import snaptrade_settings
import bob_oauth_store
import base64
import atexit
import json
import os
import secrets
import threading
import time
import product_push
import fibonacci_monitor
import background_push
import bob_session_store
import bob_recovery
import diagnostic_history
import push_receipt
import bob_repair_store
import research_transcript_provider
import research_enhancements
import bob_market_store
import weekend_archive
import youtube_feed_archive
import bob_validation_store
import real_trade_journal
import trade_email_import
import decision_audit
import decision_evidence
import improvement_tracker
import report_admission
import hashlib
import ranking_learning
import adaptive_learning as rule_learning
import strategy_lab_store
import stop_target_audit
import paper_simulation
import degiro_product_audit
import paper_health
import manual_paper_watch
import evaluator_runtime
import intraday_comparison
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from bob_http import BobHTTPServer
from urllib.parse import urlparse

import psycopg
from psycopg_pool import ConnectionPool, TooManyRequests
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import webpush as _webpush, WebPushException
from requests.exceptions import RequestException

PORT = int(os.environ.get("PORT", "10000"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:bob@localhost")
PUSH_SERVICE_TOKEN = os.environ.get("PUSH_SERVICE_TOKEN", "")
BOB_ORIGIN = os.environ.get("BOB_ORIGIN", "")
TRANSIENT_DB_ERRORS = (psycopg.errors.LockNotAvailable,
                       psycopg.errors.DeadlockDetected,
                       psycopg.errors.SerializationFailure)
_db_pool = None
_db_pool_lock = threading.Lock()

_auth_db_pool = None

def db(auth=False):
    global _db_pool, _auth_db_pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL fehlt")
    # Reuse a bounded set of connections across HTTP and background workers.
    # The context commits/rolls back and returns the connection to the pool.
    with _db_pool_lock:
        pool = _auth_db_pool if auth else _db_pool
        if pool is None:
            # Reserve two of the existing eight connections for authentication.
            # Slow archive/quote transactions cannot consume this reserve.
            pool = ConnectionPool(
                DATABASE_URL, min_size=0 if auth else 1, max_size=2 if auth else 6, timeout=5,
                max_waiting=16, max_idle=60, open=True,
                check=ConnectionPool.check_connection,
                kwargs=dict(connect_timeout=5,
                    options="-c lock_timeout=3000 -c statement_timeout=10000"))
            if auth:_auth_db_pool = pool
            else:_db_pool = pool
            atexit.register(pool.close)
    return pool.connection()

def read_improvement_report():
    def load():
        with db() as conn:
            result=improvement_tracker.report(conn)
            try:
                import product_data_quality
                with conn.transaction():result['dataQuality']=product_data_quality.read(conn)
            except Exception:
                result['dataQuality']={'status':'unavailable','note':'Produktqualität derzeit nicht abrufbar; kein bestätigter aktueller Stand.'}
            try:
                import improvement_status
                with conn.transaction():result['operatingStatus']=improvement_status.read(conn,result)
            except Exception:
                result['operatingStatus']={'available':False}
        return result
    return report_admission.read("improvement",load)


def read_audit_report(payload):
    key="audit:"+hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    def load():
        with db() as conn:
            result=decision_audit.handle(conn,"read",payload)
            conn.commit()
        return result
    return report_admission.read(key,load)


def read_db_report(key, reader):
    """Admit a read-only report before it borrows a pooled connection."""
    def load():
        with db() as conn:
            return reader(conn)
    return report_admission.read(key, load)


def read_video_evidence(payload):
    # The dashboard starts one reader per retained video. Bound those readers
    # with the other reports before video_evidence borrows from the DB pool.
    identity = payload.get('videoId') if isinstance(payload, dict) else None
    key = 'video-evidence:' + hashlib.sha256(
        json.dumps({'videoId': identity}, sort_keys=True).encode()
    ).hexdigest()
    import video_evidence
    return report_admission.read(key, lambda: video_evidence.handle(db, payload))


def webpush(**kwargs):
    """Send Web Push and asynchronously retain a redacted attempt record.

    Each provider request is a separate attempt. A 2xx response is NOT a
    browser/service-worker/device-display acknowledgement.
    """
    kwargs['timeout'] = 8
    message, data = {}, {}
    try:
        parsed = json.loads(kwargs.get('data') or '{}')
        if isinstance(parsed, dict):
            message = parsed
            data = parsed.get('data') if isinstance(parsed.get('data'), dict) else {}
    except (ValueError, TypeError, AttributeError):
        pass
    # One random proof per provider attempt, confined to its encrypted payload.
    proof = push_receipt.issue(PUSH_SERVICE_TOKEN)
    if proof:
        data = {**data, **proof}
        message = {**message, 'data': data}
        kwargs['data'] = json.dumps(message, separators=(',', ':'))
    raw_kinds = data.get('events')
    if not isinstance(raw_kinds, list) or not raw_kinds:
        raw_kinds = [data.get('eventKind') or data.get('kind') or 'unknown']
    # Never persist the notification body, endpoint, token, user or trade data.
    event_kinds = []
    for item in raw_kinds[:16]:
        if isinstance(item, str) and 0 < len(item) <= 64 and all(
            ch in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for ch in item):
            event_kinds.append(item)
    if not event_kinds:
        event_kinds = ['unknown']
    direction = data.get('direction') if data.get('direction') in ('LONG', 'SHORT') else None
    is_test = (data.get('test') is True or data.get('synthetic') is True
               or any(kind.endswith('-test') for kind in event_kinds))
    is_synthetic = data.get('synthetic') is True or any(
        kind.endswith('-test') for kind in event_kinds)

    def safe_clock(field):
        stamp = data.get(field)
        return stamp if type(stamp) in (int, float) and 0 < stamp < 4102444800000 else None

    def log(outcome, status=None):
        print('BOB_PUSH_DELIVERY '+json.dumps({'events': event_kinds, 'outcome': outcome,
              'status': status, 'at': int(time.time()*1000)}), flush=True)
        # The existing 7-day diagnostic queue is best effort and never holds
        # the provider request or a subscription/database row lock.
        trace = data.get('traceId')
        decision = data.get('decisionId')
        if not isinstance(trace, str) or len(trace) != 32 or any(
                c not in '0123456789abcdef' for c in trace):
            trace = secrets.token_hex(16)
        if not isinstance(decision, str) or len(decision) != 32 or any(
                c not in '0123456789abcdef' for c in decision):
            decision = None
        diagnostic_history.emit('push-delivery', trace, {
            'outcome': 'provider-rejected' if outcome == 'failed' else outcome,
            'httpStatus': status if type(status) is int else None,
            'eventKinds': event_kinds,
            'direction': direction,
            'test': is_test,
            'synthetic': is_synthetic,
            'signalBarAt': safe_clock('signalBarAt'),
            'dataAt': safe_clock('dataAt'),
            'receiptId': proof['receiptId'] if proof else None}, decision)

    try:
        result = _webpush(**kwargs)
        log('provider-accepted', getattr(result, 'status_code', None))
        return result
    except WebPushException as exc:
        log('failed', getattr(getattr(exc, 'response', None), 'status_code', None))
        raise
    except RequestException as exc:
        log('network-failed')
        raise WebPushException('Push provider connection failed') from exc


def init_db():
    for attempt in range(3):
        try:
            _init_db_once()
            return
        except (psycopg.OperationalError, TooManyRequests):
            if attempt == 2:
                raise
            print(f'BOB_PUSH startup=database_retry attempt={attempt + 1}', flush=True)
            time.sleep(attempt + 1)


def _init_db_once():
    with db() as conn:
        bob_session_store.init(conn)
        bob_recovery.init(conn)
        bob_passkey_store.init(conn)
        bob_oauth_store.init(conn)
        bob_repair_store.init(conn)
        diagnostic_history.init(conn)
        bob_market_store.init(conn)
        candle_reliability.init(conn)
        strategy_lab_store.init(conn)
        weekend_archive.init(conn)
        youtube_feed_archive.init(conn)
        research_transcript_provider.init(conn)
        research_enhancements.init(conn)
        bob_validation_store.init(conn)
        decision_audit.init(conn)
        improvement_tracker.init(conn)
        real_trade_journal.init(conn)
        trade_email_import.init(conn)
        degiro_product_audit.init(conn)
        import broker_candidate_evidence
        broker_candidate_evidence.init(conn)
        # Operational receipt-only audit. Never log message contents, sender,
        # ISIN, order ID, security tokens or any identifying values.
        states = conn.execute("""
            SELECT payload->'result'->>'status',
                   payload->'result'->>'sourceKind',
                   (payload->'result'->>'attachmentCount')::integer
            FROM bob_trade_email_import
            ORDER BY imported_at DESC LIMIT 4
        """).fetchall()
        print("BOB_EMAIL_IMPORT_AUDIT " + json.dumps([
            {"status": row[0] if len(row) > 0 else None,
             "source": row[1] if len(row) > 1 else None,
             "pdfCount": row[2] if len(row) > 2 else None}
            for row in states], ensure_ascii=True), flush=True)
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
    if length <= 0 or length > (1048576 if urlparse(handler.path).path in ("/market-candles/write", "/selection", "/background", "/research-enhancement/read", "/research-video/evidence", "/decision-audit/write", "/weekend-archive/write", "/strategy-lab/write", "/snaptrade-settings/state-save") else 65536):
        raise ValueError("Ungültige Payload-Größe")
    return json.loads(handler.rfile.read(length).decode("utf-8"))

def send_json(handler, status, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    cors(handler)
    handler.send_header("Content-Length", str(len(body)))
    try:
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        # The request may already have committed. Never retry it or write a
        # second error response to a disconnected caller.
        handler.close_connection = True
        print('BOB_PUSH_HTTP client_disconnected', flush=True)

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


def handle_auth_session(action, payload, attempts=3):
    """Run a session-store action with bounded auth-pool checkout retries."""
    for attempt in range(attempts):
        try:
            with db(auth=True) as conn:
                result = bob_session_store.handle(conn, action, payload)
                conn.commit()
            return result
        except TooManyRequests:
            if attempt + 1 >= attempts:
                raise
            print(f'BOB_PUSH database_retry route=auth-session attempt={attempt + 1}',
                  flush=True)
            time.sleep(0.25 * (attempt + 1))


def write_market_spots(payload, attempts=3):
    """Persist a market observation, retrying bounded transient lock races."""
    for attempt in range(attempts):
        try:
            with db() as conn:
                result = bob_market_store.handle(conn, 'write', payload)
                conn.commit()
            return result
        except TRANSIENT_DB_ERRORS:
            if attempt + 1 >= attempts:
                raise
            print(f'BOB_PUSH database_retry route=market-spots attempt={attempt + 1}',
                  flush=True)
            time.sleep(0.25 * (attempt + 1))


def store_product_selection(endpoint, payload, checked, attempts=2):
    """Persist/deliver a selection, retrying only a transient row-lock race."""
    evidence = {k: payload[k] for k in ('products', 'references', 'fixedBarriers')
                if k in payload}
    for attempt in range(attempts):
        try:
            with db() as conn:
                row = conn.execute(
                    "SELECT id, subscription, product_selection FROM subscriptions "
                    "WHERE endpoint=%s AND general_enabled=TRUE FOR UPDATE",
                    (endpoint,),
                ).fetchone()
                if row:
                    conn.execute(
                        'UPDATE subscriptions SET selection_evidence=%s::jsonb WHERE id=%s',
                        (json.dumps(evidence), row[0]),
                    )
                sent = deliver_product_selection(conn, row, checked) if row else 0
                conn.commit()
            return row, sent
        except TRANSIENT_DB_ERRORS:
            if attempt + 1 >= attempts:
                raise
            print(f'BOB_PUSH database_retry route=selection attempt={attempt + 1}',
                  flush=True)
            time.sleep(0.25 * (attempt + 1))


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
            if background_push.degiro_entry_allowed():
                expire_product_selections()
            # Explicit tests are always permitted, including at night.
            deliver_background_tests()
        except Exception as exc:
            print('BOB_PRODUCT expiry_error='+type(exc).__name__, flush=True)
        time.sleep(15)


def trigger_test_message(stage, now):
    """Exercise real trigger rules with isolated synthetic data, never a user trade."""
    settings=background_push.config({'trade':{'active':True,'tradeId':'synthetic-push-test',
        'instrument':'XAU/USD','dir':'LONG','entry':100,'stop':90,'initialRisk':10,'target':120}})
    market={'ready':True,'priceFresh':True,'price':120 if stage==0 else 89,'dataAt':now,
        'direction':'LONG','mtf':'LONG','score':80,'atr':4}
    _,events=background_push.advance({},settings,market,False,True,now=now)
    kind='target' if stage==0 else 'stop-hit'
    event=next(e for e in events if e['data']['eventKind']==kind)
    return {'title':'TEST · '+('Ziel erreicht' if stage==0 else 'Stop erreicht'),
        'body':'Künstlicher Kurs hat die '+('Zielregel' if stage==0 else 'Stopregel')+' auf dem Server ausgelöst. Kein echter Trade, keine Order.',
        'tag':'bob-trigger-test-'+kind,'data':{**event['data'],'test':True,'url':'/','expiresAt':now+180000}}


def early_warning_test_message(side, now):
    """Fixed, synthetic early-warning *delivery* example, not market evaluation."""
    if side not in ('LONG', 'SHORT'):
        raise ValueError('Unknown early-warning test direction')
    return {
        'title': 'TEST · ' + side + '-Frühwarnung',
        'body': 'Künstliche ' + side + '-Frühwarnung zum Prüfen der Handy-Zustellung. '
                'Keine echte Goldbewegung, kein Einstiegssignal, keine '
                'Produktempfehlung und keine Order.',
        'tag': 'bob-early-warning-test-' + side.lower(),
        'data': {
            'kind': 'general', 'eventKind': 'early-warning-test',
            'direction': side, 'test': True, 'synthetic': True,
            'comparisonOnly': True, 'affectsApproval': False,
            'url': '/', 'expiresAt': now + 180000,
        },
    }


def deliver_background_tests():
    now=int(time.time()*1000)
    with db() as conn:
        rows=conn.execute("SELECT id, subscription, pending_test, general_enabled, trade_enabled FROM subscriptions WHERE pending_test IS NOT NULL AND (pending_test->>'dueAt')::bigint<=%s FOR UPDATE",(now,)).fetchall()
        for sid, sub, pending, general, trade in rows:
            scenario=pending.get('scenario','delivery')
            allowed=(general or trade) if scenario=='stop-target' else (general if scenario in ('early-long','early-short') else (general if pending.get('kind')=='general' else trade))
            if allowed and now < pending['dueAt']+300000:
                message={'title':'TEST · Push bei geschlossener App','body':'Diese Testnachricht wurde zeitversetzt auf dem Server ausgelöst. Kein Handelssignal.','tag':'bob-background-test','data':{'kind':pending['kind'],'test':True,'url':'/','expiresAt':now+180000}}
                if scenario=='stop-target':
                    message=trigger_test_message(pending.get('stage',0),now)
                elif scenario in ('early-long','early-short'):
                    message=early_warning_test_message('LONG' if scenario=='early-long' else 'SHORT',now)
                try:
                    webpush(subscription_info=sub,data=json.dumps(message),vapid_private_key=vapid(),vapid_claims={'sub':VAPID_SUBJECT},ttl=180)
                    # A provider acceptance is never a proof of on-device display.
                    print('BOB_PUSH_TEST outcome=provider-accepted scenario='+scenario,flush=True)
                except WebPushException as exc:
                    code=getattr(getattr(exc,'response',None),'status_code',None)
                    print('BOB_PUSH_TEST outcome=provider-rejected scenario='+scenario+
                          ' status='+str(code if type(code) is int else 'unknown'),flush=True)
                    continue
            if allowed and now < pending['dueAt']+300000 and pending.get('scenario')=='stop-target' and pending.get('stage',0)==0:
                pending.update(stage=1,dueAt=now+30000)
                conn.execute('UPDATE subscriptions SET pending_test=%s::jsonb WHERE id=%s',(json.dumps(pending),sid))
            else:
                conn.execute('UPDATE subscriptions SET pending_test=NULL WHERE id=%s',(sid,))
        conn.commit()


def record_market_observation(conn, market, bundle=None):
    """Persist the frozen read-only observation; no order, Push or product release."""
    if bundle is not None:
        import metric_quality
        try:
            with conn.transaction():metric_quality.capture(conn,bundle,market)
        except Exception as exc:print('BOB_METRIC_CAPTURE error='+type(exc).__name__,flush=True)
    if not market.get('analysisBarAt'):
        return False
    # Invalid captures remain visible in metric coverage, but must not start
    # forward signal tests that can never acquire a valid original entry.
    source_at = decision_audit.milliseconds(market.get('dataAt'))
    now = time.time()*1000
    if (market.get('priceFresh') is not True or not decision_audit.positive(market.get('price'))
            or source_at is None or not 0 <= now-source_at <= 60000):
        print('BOB_SIGNAL_CAPTURE skipped=invalid-start', flush=True)
        return False
    decision_audit.write(conn,{'ruleVersion':market.get('ruleVersion'),'origin':'background','direction':market.get('direction','NEUTRAL'),'baseDirection':market.get('baseDirection'),'learningPolicy':market.get('learningPolicy'),
        'trendContext':market.get('trendContext'),'earlyImpulse':market.get('earlyImpulse'),'earlyWarning':market.get('earlyWarning'),'plan':market.get('plan'),'minuteEntry':market.get('minuteEntry'),'entryQuality':market.get('entryQuality'),'shadowDirection':market.get('shadowDirection'),'intraday':market.get('intraday'),'barAt':market['analysisBarAt'],
        'price':market.get('price'),'priceAt':market.get('dataAt'),'reason':market.get('decisionReason'),
        'score':market.get('score'),'indicators':market.get('context'),
        'decisionContext':decision_evidence.capture(market), 'products':[],
        'selection':[], 'gateReasons':[] if market.get('ready') else ['Marktdaten nicht freigegeben']})
    return True


def run_audit_harvest_once(database):
    """Backfill real forward prices without blocking trade/Push request transactions."""
    import product_precision
    failures=[]
    stages=(('decision',decision_audit.harvest),
            ('product-precision',product_precision.harvest),
            ('ranking',ranking_learning.harvest))
    for name,harvest in stages:
        try:
            # A timeout in one archive must roll back only that stage. Later
            # bounded harvesters still make forward progress on their evidence.
            with database() as conn:
                harvest(conn)
                conn.commit()
        except Exception as exc:
            failures.append(name)
            print('BOB_AUDIT_HARVEST stage='+name+' error='+type(exc).__name__,flush=True)
    return {'completed':[name for name,_ in stages if name not in failures],
            'failed':failures}


def run_test_repair_once(database):
    import evidence_repair
    print('BOB_TEST_REPAIR phase=start',flush=True)
    with database() as conn:
        result=evidence_repair.tick(conn)
        conn.commit()
    try:
        import training_handoff
        with database() as conn:
            handoff=training_handoff.summary(conn)
            training_handoff.sync_groups(conn,handoff)
            conn.commit()
        training_handoff.publish(handoff)
    except Exception as exc:
        print('BOB_TRAINING_HELP error='+type(exc).__name__,flush=True)
    print('BOB_TEST_REPAIR checked='+str(result['processed']),flush=True)


def run_improvement_review_once(database):
    with database() as conn:
        status=improvement_tracker.archive_review(conn)
        conn.commit()
    if status:
        print('BOB_IMPROVEMENT_STATUS '+json.dumps(status,allow_nan=False),flush=True)
    return status


def audit_outcome_loop():
    while True:
        try:
            import improvement_resilience
            improvement_resilience.run_drills(db)
        except Exception as exc:
            print("BOB_RESILIENCE error="+type(exc).__name__,flush=True)
        try:
            run_audit_harvest_once(db)
        except Exception as exc:
            # Bulk backfill timeouts must not block targeted repair attempts.
            print('BOB_AUDIT_HARVEST error='+type(exc).__name__, flush=True)
        try:
            run_test_repair_once(db)
        except Exception as exc:
            print('BOB_TEST_REPAIR error='+type(exc).__name__,flush=True)
        try:
            if int(time.time()*1000)>=improvement_tracker.START:
                run_improvement_review_once(db)
        except Exception as exc:
            print('BOB_IMPROVEMENT review_error='+type(exc).__name__,flush=True)
        time.sleep(120)


def run_background(bundle):
    sent = 0
    with db() as conn:
        # Evaluate frozen plans even if no device currently has a trade or Push
        # enabled. Isolate failures from alert delivery and interactive reports.
        try:
            with conn.transaction():
                stop_target_audit.harvest(conn)
        except Exception as exc:
            print('BOB_STOP_TARGET error='+type(exc).__name__,flush=True)
        try:
            with conn.transaction():rule_learning.tick(conn,bundle,background_push.analyze)
        except Exception as exc:
            print('BOB_RULE_LEARNING error='+type(exc).__name__,flush=True)
        try:
            with conn.transaction():ranking_learning.tick(conn)
        except Exception as exc:print('BOB_RANKING error='+type(exc).__name__,flush=True)
        learning_policy=rule_learning.policy(conn)
        bundle={**bundle,'learningPolicy':learning_policy}
        try:
            with conn.transaction():
                real_trade_journal.reconcile_sales(conn)
                real_trade_journal.recover_closed_settlements(conn)
                real_trade_journal.sync_devices(conn)
        except Exception as exc:
            print('BOB_REAL_TRADE device_sync_failed='+type(exc).__name__,flush=True)
        # Release completed maintenance and device-sync locks before evaluation or I/O.
        conn.commit()
        # One canonical observation per bundle, independent of devices or open browser.
        capture_improvement = improvement_tracker.eligible(int(time.time()*1000))
        if capture_improvement or background_push.degiro_session() == 'trading':
            try:
                canonical = background_push.analyze(bundle, {'timeframe':'15m','learningPolicy':learning_policy}, priority=2)
            except Exception:
                canonical = {}
            try:
                with conn.transaction():
                    record_market_observation(conn, canonical, bundle)
                    if capture_improvement: improvement_tracker.capture(conn, canonical)
            except Exception as exc:
                print('BOB_IMPROVEMENT capture_error='+type(exc).__name__,flush=True)
        conn.commit()  # Research writes must not hold locks through alert delivery.
        rows = conn.execute("SELECT id, subscription, general_enabled, trade_enabled, active_trade, background_config, background_state, selection_evidence, product_selection FROM subscriptions WHERE (general_enabled=TRUE OR (trade_enabled=TRUE AND active_trade=TRUE)) AND background_config IS NOT NULL FOR UPDATE SKIP LOCKED").fetchall()
        for sid, sub, general, trade, active, settings, previous, evidence, selection in rows:
            try:
                market = background_push.analyze(bundle, {**settings,'learningPolicy':learning_policy})
            except Exception as exc:
                print('BOB_BACKGROUND analysis_failed='+type(exc).__name__, flush=True)
                market = background_push.failed_analysis_market(bundle)
            # Subscriber-specific monitoring continues independently of audit failures.
            try:
                with conn.transaction(): record_market_observation(conn, market, bundle)
            except Exception as exc:
                print('BOB_AUDIT write_failed='+type(exc).__name__,flush=True)
            state, events = background_push.advance(previous, settings, market, general, trade and active)
            linked=settings.get('journalTradeId')
            if trade and active and linked and (previous or {}).get('journalConnected')!=linked+':v2':
                events.append({'title':'BOB · Trade-Push verbunden',
                    'body':'Der gespeicherte Trade ist jetzt mit diesem Gerät verbunden. Stopp, Ziel und KO werden auf dem Server überwacht. Keine automatische DEGIRO-Order.',
                    'tag':'bob-trade-connected-'+linked,
                    'data':{'kind':'trade','eventKind':'trade-connected','test':True,'tradeId':linked,'url':'/#trade','expiresAt':int(time.time()*1000)+180000}})
                state['journalConnected']=linked+':v2'
            delivered = True
            if events:
                # One delivery/checkpoint per device, so a failure cannot consume an alert.
                message = background_push.compose_events(events)
                if linked:message['data']['journalManaged']=True
                # Correlate the original decision, not a reconstructed market tick.
                message['data']['traceId'] = market.get('traceId')
                message['data']['decisionId'] = market.get('decisionId')
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
                    history = state.setdefault('pushHistory', [])
                    history.append({'at': int(time.time()*1000), 'kind': 'delivery',
                                    'outcome': 'provider-accepted',
                                    'events': [e['data']['eventKind'] for e in events]})
                    del history[:-50]
                except WebPushException as exc:
                    delivered=False
                    if getattr(getattr(exc,'response',None),'status_code',None) in (404,410):
                        conn.execute('DELETE FROM subscriptions WHERE id=%s',(sid,))
            diagnostic_history.emit('push', market.get('traceId') or diagnostic_history.trace(bundle),
                {'outcome':('provider-accepted' if delivered else 'delivery-failed') if events else 'no-alert',
                 'eventsCount':len(events),
                 'events':[e for e in state.get('pushHistory',[]) if e.get('at',0)>=(previous or {}).get('diagnosticAt',0)][-20:]},
                market.get('decisionId'))
            state['diagnosticAt']=int(time.time()*1000)
            if events:
                try:
                    import improvement_resilience
                    with conn.transaction():improvement_resilience.capture(conn,sid,events,delivered,int(time.time()*1000))
                except Exception as exc:
                    print('BOB_HINT_AUDIT error='+type(exc).__name__,flush=True)
            if events and (settings.get('trade') or {}).get('tradeId'):
                try:
                    with conn.transaction():
                        real_trade_journal.event(conn,settings['trade']['tradeId'],'push-delivery',
                            {'at':int(time.time()*1000),'events':events,'message':message,
                             'outcome':'provider-accepted' if delivered else 'delivery-failed',
                             'note':'Annahme durch Push-Dienst bestätigt keinen Empfang am Handy'},
                            str(sid)+':'+str(time.time_ns()))
                except Exception as exc:
                    print('BOB_REAL_TRADE push_log_failed='+type(exc).__name__,flush=True)
            if delivered:
                state['checkedAt']=int(time.time()*1000)
                conn.execute('UPDATE subscriptions SET background_state=%s::jsonb WHERE id=%s',(json.dumps(state),sid))
            if general and evidence and background_push.degiro_entry_allowed():
                try:
                    checked=product_push.evaluate({**evidence,'capturedAt':int(time.time()*1000),'bundle':bundle,'context':market.get('context',{'direction':'NEUTRAL'})},
                        quotes=paper_simulation.observed_quotes(evidence.get('products', [])),ranking_policy=ranking_learning.policy(conn))
                    sent += deliver_product_selection(conn,(sid,sub,selection),checked)
                except Exception as exc:
                    print('BOB_BACKGROUND selection_failed='+type(exc).__name__,flush=True)
        try:
            with conn.transaction():real_trade_journal.observe(conn,bundle)
        except Exception as exc:
            print('BOB_REAL_TRADE error='+type(exc).__name__,flush=True)
        # A single independent campaign, even with no devices subscribed to Push.
        now=int(time.time()*1000)
        if intraday_comparison.active(now):
            try:
                with conn.transaction():
                    slot=intraday_comparison.slot_at(now)
                    if intraday_comparison.needs_capture(conn,now):
                        try: trial=background_push.analyze(bundle,{'timeframe':'15m'},priority=2)
                        except Exception: trial={'ready':False,'decisionReason':'Hintergrundanalyse fehlgeschlagen'}
                        captured=intraday_comparison.capture(conn,trial,now)
                        print('BOB_COMPARISON captured valid='+str(bool(captured and captured['valid']))+' slot='+str(slot),flush=True)
                    else: intraday_comparison.harvest(conn,now)
            except Exception as exc:
                print('BOB_COMPARISON error='+type(exc).__name__,flush=True)
        conn.commit()
    return sent


class Handler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_OPTIONS(self):
        self.send_response(204)
        cors(self)
        self.end_headers()

    def do_HEAD(self):
        # Render probes the root path with HEAD while bringing up a deploy.
        # Treat it as a readiness check for the dependencies required by the
        # push service, but never expose a response body or private state.
        path = urlparse(self.path).path
        if path not in ("/", "/health"):
            status = 404
        else:
            try:
                vapid()
                with db() as conn:
                    conn.execute("SELECT 1").fetchone()
                status = 200
            except Exception as exc:
                print("BOB_PUSH_HEAD readiness_error=" + type(exc).__name__, flush=True)
                status = 503
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        cors(self)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/health":
                vapid()
                with db() as conn:
                    conn.execute("SELECT 1").fetchone()
                    try:
                        paper_heartbeat = paper_health.snapshot(conn)
                    except Exception as paper_exc:
                        print("BOB_PAPER_HEALTH error=" + type(paper_exc).__name__, flush=True)
                        paper_heartbeat = {"state":"unavailable", "accountsTotal":5,
                                           "accountsChecked":0,"realOrders":False,
                                           "scope":"paper-account-heartbeat-not-quote-quality"}
                    improvement_protocol=conn.execute('SELECT payload FROM bob_improvement_protocol WHERE id=%s',(improvement_tracker.VERSION,)).fetchone()
                    improvement_schedule={'configured':bool(improvement_protocol and improvement_protocol[0]==improvement_tracker.PROTOCOL),'startAt':improvement_tracker.START,'mode':'research-only'}
                    # The public endpoint reveals ONLY allowlisted diagnostic
                    # categories. No private instrument names, quantities,
                    # prices, timestamps or screenshot-list metadata.
                    try:
                        product_codes = degiro_product_audit.public_help_codes(
                            degiro_product_audit.read(conn))
                    except Exception as audit_exc:
                        print("BOB_PRODUCT_AUDIT health_error="+type(audit_exc).__name__, flush=True)
                        product_codes = None  # Unknown is NOT a confirmed repair.
                send_json(self, 200, {"ok": True, "productSelectionVerifier": "shared-js-v1", "build": os.environ.get("RENDER_GIT_COMMIT", "unknown"), "pushPresentation": "action-first-v2", "evaluator": evaluator_runtime.status(), "paperObservation":paper_heartbeat, "productAuditCodes":product_codes,"improvementSchedule":improvement_schedule,"runtimeWatchdog":__import__('runtime_watchdog').snapshot()})
                return
            if path == "/push-delivery-history":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                from urllib.parse import parse_qs
                import push_delivery_history
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                if any(len(v) != 1 for v in query.values()):
                    raise ValueError("Duplicate argument")
                args = {k: v[0] for k, v in query.items()}
                if "offset" in args:
                    args["offset"] = int(args["offset"])
                args = push_delivery_history.arguments(args)
                with db() as conn:
                    conn.execute("SET TRANSACTION READ ONLY")
                    result = push_delivery_history.report(conn, args)
                send_json(self, 200, result)
                return
            if path == "/signal-history":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error":"Unauthorized"})
                    return
                from urllib.parse import parse_qs
                import signal_history
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                if any(len(v)!=1 for v in query.values()): raise ValueError('Duplicate argument')
                args = {k:v[0] for k,v in query.items()}
                if 'offset' in args: args['offset']=int(args['offset'])
                args=signal_history.arguments(args)
                with db() as conn:
                    conn.execute("SET TRANSACTION READ ONLY")
                    result=signal_history.report(conn,args)
                send_json(self,200,result)
                return
            if path == "/storage-health":
                supplied=self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{"error":"Unauthorized"});return
                with db() as conn:
                    conn.execute("SET TRANSACTION READ ONLY")
                    conn.execute("SET LOCAL statement_timeout='3s'")
                    result=__import__('storage_budget').report(conn)
                send_json(self,200,result);return
            if path == "/diagnostics":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error":"Unauthorized"})
                    return
                import bob_diagnostics, paper_portfolios
                with db() as conn:
                    # Enforce the read boundary at the database as well.
                    conn.execute("SET TRANSACTION READ ONLY")
                    result = bob_diagnostics.push_snapshot(conn, evaluator_runtime, paper_health, paper_portfolios, extended=True)
                result['runtimeWatchdog'] = __import__('runtime_watchdog').snapshot()
                send_json(self, 200, result)
                return
            if path == "/product-audit":
                # Private product universe; never publish it in /health or
                # public GitHub issues. Browser access goes through Bob auth.
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                result = read_db_report("product-audit", degiro_product_audit.read)
                send_json(self, 200, result)
                return
            if path == "/candidate-proofs":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                import broker_candidate_evidence
                def candidate_report(conn):
                    conn.execute("SET TRANSACTION READ ONLY")
                    return broker_candidate_evidence.report(conn)
                result = read_db_report("candidate-proofs", candidate_report)
                send_json(self, 200, result)
                return
            if path == "/monitor-status":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                with db() as conn:
                    count = conn.execute("SELECT count(*) FROM subscriptions WHERE general_enabled=TRUE OR (trade_enabled=TRUE AND active_trade=TRUE)").fetchone()[0]
                    trades = conn.execute("SELECT count(*) FROM subscriptions WHERE trade_enabled=TRUE AND active_trade=TRUE").fetchone()[0]
                send_json(self, 200, {"activeMonitors": count, "activeTrades": trades})
                return
            if path == "/vapid-public-key":
                send_json(self, 200, {"publicKey": vapid_public_key()})
                return
            send_json(self, 404, {"error": "Not found"})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as exc:
            print("push-service error:", type(exc).__name__, flush=True)
            send_json(self, 503, {"error": "Push-Service nicht bereit"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == '/device-receipt':
                # The browser need not have a live login cookie. Its scoped
                # HMAC is checked before any asynchronous diagnostic write.
                payload = json_body(self)
                try:
                    receipt_id, receipt_state = push_receipt.verify(payload, PUSH_SERVICE_TOKEN)
                except ValueError:
                    send_json(self, 400, {'error': 'Invalid or expired receipt'})
                    return
                diagnostic_history.emit('push-delivery', receipt_id,
                    {'outcome': 'browser-receipt', 'receiptId': receipt_id,
                     'receiptState': receipt_state},
                    event_id=push_receipt.event_id(receipt_id, receipt_state))
                send_json(self, 202, {'queued': True, 'androidDisplayVerified': False})
                return
            if path == '/diagnostic-history':
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                payload=json_body(self)
                with db() as conn:
                    conn.execute("SET LOCAL statement_timeout='1500ms'")
                    diagnostic_history.write(conn,payload)
                send_json(self,200,{'ok':True});return
            if path in ("/self-heal-events/read", "/self-heal-events/write"):
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                payload = json_body(self)
                with db() as conn:
                    result = bob_repair_store.handle(conn, path.rsplit("/", 1)[-1], payload)
                    conn.commit()
                send_json(self, 200, result)
                return
            if path == '/ranking-learning/control':
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                payload=json_body(self)
                with db() as conn:
                    result=ranking_learning.control(conn,payload.get('enabled'),int(time.time()*1000));conn.commit()
                with decision_audit._report_lock: decision_audit._report_cache=None
                send_json(self,200,result);return
            if path == '/precision-learning/control':
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                payload=json_body(self)
                import precision_learning
                with db() as conn:
                    result=precision_learning.control(conn,payload.get('enabled'),int(time.time()*1000))
                    conn.commit()
                with decision_audit._report_lock: decision_audit._report_cache=None
                send_json(self,200,result);return
            if path in ('/rule-learning/read','/rule-learning/rollback'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                json_body(self)
                with db() as conn:
                    result=rule_learning.rollback(conn) if path.endswith('/rollback') else rule_learning.policy(conn)
                    result['rankingPolicy']=ranking_learning.policy(conn)
                    conn.commit()
                if path.endswith('/rollback'):
                    with decision_audit._report_lock: decision_audit._report_cache=None
                send_json(self,200,result);return
            if path in ("/email-import/receive", "/email-import/read"):
                supplied=self.headers.get("X-Bob-Push-Token","")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{"error":"Unauthorized"});return
                payload=json_body(self)
                if not isinstance(payload,dict):
                    raise ValueError("Ungültige E-Mail-Daten")
                if path.endswith("/read"):
                    result=read_db_report("email-import", trade_email_import.report)
                else:
                    with db() as conn:
                        message_id=payload.get("messageId")
                        record=payload.get("record")
                        if not isinstance(message_id,str) or not 1<=len(message_id)<=200 or not isinstance(record,dict):
                            raise ValueError("Ungültige Mail-ID oder Nachricht")
                        # This endpoint trusts ONLY the private Bob->push token.
                        # Sender/Svix verification happens on Bob's public front.
                        safe={k:record.get(k) for k in (
                            "status","reason","isin","side","quantity","priceEur","executedAt",
                            "executedLocal","timezoneConfirmed","sourceKind",
                            "orderIdDigest","costsChf","grossChf","totalChf",
                            "fxEurPerChf","senderKind","attachmentCount")
                              if k in record}
                        if len(json.dumps(safe))>4096:
                            raise ValueError("Zu viele Importdaten")
                        old_row=conn.execute("SELECT payload->'result' FROM bob_trade_email_import WHERE message_id=%s FOR UPDATE",(message_id,)).fetchone()
                        old_record=old_row[0] if old_row else None
                        enrich=trade_email_import.receipt_enrichment(old_record,safe)
                        inserted=conn.execute("""INSERT INTO bob_trade_email_import(message_id,payload)
                            VALUES(%s,%s::jsonb) ON CONFLICT(message_id)
                            DO UPDATE SET payload=EXCLUDED.payload
                            WHERE (bob_trade_email_import.payload->'result'->>'status'
                                IN ('sender-unconfirmed','incomplete')
                              AND EXCLUDED.payload->'result'->>'status'='pending-review')
                              OR (%s AND bob_trade_email_import.payload->'result'=%s::jsonb)
                            RETURNING message_id""",
                            (message_id,json.dumps({"messageId":message_id,"version":trade_email_import.VERSION,
                                "result":safe,"receivedAt":int(time.time()*1000)}),enrich,json.dumps(old_record))).fetchone()
                        result={"ok":True,"new":bool(inserted)}
                        real_trade_journal.reconcile_sales(conn)
                        conn.commit()
                send_json(self,200,result);return
            if path == '/list-correction':
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                import list_corrections
                payload=json_body(self)
                if payload.get('action')=='read':
                    result=read_db_report("list-correction",lambda conn:list_corrections.handle(conn,payload))
                else:
                    with db() as conn:
                        result=list_corrections.handle(conn,payload)
                        conn.commit()
                send_json(self,200,result);return
            if path == '/broker-venue/write':
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error': 'Unauthorized'}); return
                import broker_venue_evidence
                payload = json_body(self)
                with db() as conn:
                    result = broker_venue_evidence.save(conn, payload)
                    conn.commit()
                send_json(self, 200, result)
                return
            if path == '/candidate-proof/write':
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error': 'Unauthorized'}); return
                import broker_candidate_evidence
                payload = json_body(self)
                with db() as conn:
                    result = broker_candidate_evidence.save(conn, payload)
                    conn.commit()
                send_json(self, 200, result)
                return
            if path == '/improvement/read':
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                result=read_improvement_report()
                send_json(self,200,result);return
            if path in ('/real-trades/read','/real-trades/write','/real-trades/curve','/real-trades/risk','/real-trades/confirm-sale'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                payload=json_body(self)
                with db() as conn:
                    result=real_trade_journal.handle(conn,path.rsplit('/',1)[-1],payload)
                    conn.commit()
                send_json(self,200,result);return
            if path in ('/decision-audit/read','/decision-audit/write'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if not isinstance(payload, dict):
                    raise ValueError('Prüfprotokoll muss ein Objekt sein')
                # Simulation sync carries screenshot provenance, not audit-writer identity.
                if path.endswith('/write') and payload.get('mode') not in (
                    'simulation-sync', 'manual-paper-watch-sync', 'manual-paper-watch-levels'
                ):
                    payload['origin']='browser'
                if path.endswith('/read'):
                    result=read_audit_report(payload)
                else:
                    with db() as conn:
                        result=decision_audit.handle(conn,'write',payload)
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
            if path in ('/research-enhancement/read','/research-video/evidence'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if not isinstance(payload,dict):raise ValueError('Ungültige Recherche-Anfrage')
                if path=='/research-video/evidence':
                    if payload.get('action','read')=='read':
                        send_json(self,200,read_video_evidence(payload))
                    else:
                        import video_evidence
                        send_json(self,200,video_evidence.handle(db,payload))
                else:send_json(self,200,research_enhancements.handle(db,payload))
                return
            if path=='/research-transcript/read':
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if not isinstance(payload,dict):raise ValueError('Ungültige Recherche-Anfrage')
                send_json(self,200,research_transcript_provider.handle(db,payload))
                return
            if path in ('/youtube-feed/read','/youtube-feed/write'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if not isinstance(payload,dict):
                    raise ValueError('Ungültige Videoarchivanfrage')
                with db() as conn:
                    result=youtube_feed_archive.handle(conn,path.rsplit('/',1)[-1],payload)
                    conn.commit()
                send_json(self,200,result)
                return
            if path in ('/weekend-archive/read','/weekend-archive/write'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'})
                    return
                payload=json_body(self)
                if not isinstance(payload,dict):
                    raise ValueError('Ungültige Archivdaten')
                with db() as conn:
                    result=weekend_archive.handle(conn,path.rsplit('/',1)[-1],payload)
                    conn.commit()
                send_json(self,200,result)
                return
            if path in ("/strategy-lab/read", "/strategy-lab/write"):
                supplied=self.headers.get("X-Bob-Push-Token","")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{"error":"Unauthorized"});return
                payload=json_body(self)
                if not isinstance(payload,dict):
                    raise ValueError("Ungültige Forschungsarchivdaten")
                with db() as conn:
                    result=strategy_lab_store.handle(conn,path.rsplit("/",1)[-1],payload)
                    conn.commit()
                send_json(self,200,result)
                return
            if path in ('/market-candles/read','/market-candles/write'):
                supplied=self.headers.get('X-Bob-Push-Token','')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied,PUSH_SERVICE_TOKEN):
                    send_json(self,401,{'error':'Unauthorized'});return
                payload=json_body(self)
                if not isinstance(payload,dict):raise ValueError('Invalid candle payload')
                with db() as conn:
                    conn.execute("SET LOCAL statement_timeout='1500ms'")
                    result=candle_reliability.handle(conn,path.rsplit('/',1)[-1],payload)
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
                action=path.rsplit('/',1)[-1]
                if action == 'write':
                    result=write_market_spots(payload)
                else:
                    with db() as conn:
                        result=bob_market_store.handle(conn,action,payload)
                        conn.commit()
                send_json(self,200,result)
                return
            if path in ('/snaptrade-settings/read', '/snaptrade-settings/save', '/snaptrade-settings/delete', '/snaptrade-settings/state-read', '/snaptrade-settings/state-save'):
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error': 'Unauthorized'}); return
                payload = json_body(self)
                with db() as conn:
                    result = snaptrade_settings.handle(conn, path.rsplit('/', 1)[-1], payload)
                    conn.commit()
                send_json(self, 200, result); return
            if path.startswith('/auth-oauth/'):
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error':'Unauthorized'}); return
                payload = json_body(self)
                if not isinstance(payload, dict): raise ValueError('Invalid OAuth payload')
                with db(auth=True) as conn:
                    result = bob_oauth_store.handle(conn, path.rsplit('/',1)[-1], payload)
                    conn.commit()
                send_json(self, 200, result); return
            if path.startswith('/auth-passkey/'):
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error':'Unauthorized'}); return
                payload = json_body(self)
                if not isinstance(payload, dict): raise ValueError('Invalid passkey payload')
                with db(auth=True) as conn:
                    result = bob_passkey_store.handle(conn, path.rsplit('/',1)[-1], payload)
                    conn.commit()
                send_json(self, 200, result); return
            if path in ('/auth-recovery/state', '/auth-recovery/issue', '/auth-recovery/reset', '/auth-recovery/cancel'):
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error': 'Unauthorized'})
                    return
                payload = json_body(self)
                if not isinstance(payload, dict):
                    raise ValueError('Ungültige Wiederherstellungsdaten')
                with db(auth=True) as conn:
                    result = bob_recovery.handle(conn, path.rsplit('/', 1)[-1], payload)
                    conn.commit()
                send_json(self, 200, result)
                return
            if path in ('/auth-session/create', '/auth-session/check', '/auth-session/revoke'):
                supplied = self.headers.get('X-Bob-Push-Token', '')
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {'error': 'Unauthorized'})
                    return
                payload = json_body(self)
                if not isinstance(payload, dict):
                    raise ValueError('Ungültige Sitzungsdaten')
                result = handle_auth_session(path.rsplit('/', 1)[-1], payload)
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
                    real_trade_journal.sync_devices(conn)
                    conn.commit()
                send_json(self, 200, {"ok": True, "fibonacciMonitor": "active" if monitor else "inactive", "backgroundEnabled": settings is not None, "backgroundTrade": (background_state or {}).get("trade"), "continuedCalculation": (background_state or {}).get("continuedCalculation")})
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
                scenario=payload.get('scenario','delivery')
                if scenario not in ('delivery','stop-target','early-long','early-short'):
                    raise ValueError('Unbekannter Push-Test')
                with db() as conn:
                    row=conn.execute('SELECT general_enabled, trade_enabled, pending_test FROM subscriptions WHERE endpoint=%s FOR UPDATE',(endpoint,)).fetchone()
                    if not row or not any(row):
                        raise ValueError('Zuerst Gerät anmelden und mindestens einen Push-Schalter aktivieren')
                    if scenario in ('early-long','early-short') and row[0] is not True:
                        raise ValueError('Marktbeobachtung muss für Frühwarn-Tests aktiv sein')
                    now_ms=int(time.time()*1000)
                    existing=row[2] if len(row)>2 else None
                    if (isinstance(existing,dict) and type(existing.get('dueAt')) in (int,float)
                            and now_ms < existing['dueAt']+90000):
                        # One pending test per subscriber. Never silently replace
                        # LONG with SHORT or cancel an earlier stop/target test.
                        send_json(self,409,{'error':'Test bereits vorgemerkt','retryable':True})
                        return
                    pending={'kind':'general' if row[0] else 'trade','dueAt':now_ms+30000}
                    if scenario=='stop-target':pending.update(scenario='stop-target',stage=0)
                    elif scenario in ('early-long','early-short'):pending['scenario']=scenario
                    conn.execute('UPDATE subscriptions SET pending_test=%s::jsonb WHERE endpoint=%s',(json.dumps(pending),endpoint))
                    conn.commit()
                print('BOB_PUSH_TEST outcome=scheduled scenario='+scenario,flush=True)
                send_json(self,200,{'ok':True,'dueAt':pending['dueAt']})
                return

            if path == "/background":
                supplied = self.headers.get("X-Bob-Push-Token", "")
                if not PUSH_SERVICE_TOKEN or not secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN):
                    send_json(self, 401, {"error": "Unauthorized"})
                    return
                bundle=payload.get('bundle') or {}
                import trade_auto_monitor
                trade_auto_monitor.enqueue(db,bundle)
                import product_comparison_worker
                product_comparison_worker.enqueue(db,bundle)
                paper_simulation.enqueue(bundle,db)
                manual_paper_watch.enqueue(db)
                sent = run_background(bundle)
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
                        monitor_bars = bars_by_tf.get(monitor['timeframe'], [])
                        checkpoint, alerts, status = fibonacci_monitor.advance_monitor(monitor, monitor_bars)
                        # Weekend candle gaps are not failures when a genuine
                        # final Friday candle is present. Do not silence older outages.
                        clock_ms = int(time.time() * 1000)
                        if status == 'unavailable' and monitor.get('dataHealth') != 'unavailable' and background_push.gold_weekend_close(clock_ms) is not None:
                            step = fibonacci_monitor.STEPS[monitor['timeframe']]
                            last_close = max((bar['openTime'] + step for bar in monitor_bars
                                              if isinstance(bar, dict) and type(bar.get('openTime')) in (int, float)
                                              and bar.get('instrument') == monitor['instrument']
                                              and bar.get('isOpen') is False), default=None)
                            if background_push.weekend_quote_at_close(clock_ms, last_close):
                                status = 'closed'
                        checkpoint, alerts = fibonacci_monitor.notification_alerts(checkpoint, alerts)
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
                with db() as conn:ranking_policy=ranking_learning.policy(conn)
                checked = product_push.evaluate(payload,ranking_policy=ranking_policy)
                row, sent = store_product_selection(endpoint, payload, checked)
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
        except research_transcript_provider.TranscriptError as exc:
            print('BOB_RESEARCH error_code='+exc.code, flush=True)
            send_json(self, 400, {'error': str(exc), 'errorCode': exc.code})
        except (ValueError, json.JSONDecodeError) as exc:
            if path == '/decision-audit/write':
                # Previous browser writes returned HTTP 400 without any
                # actionable trace. Log category only, never client contents.
                print('BOB_AUDIT rejected code='+decision_audit.rejection_code(exc), flush=True)
            send_json(self, 400, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except (psycopg.OperationalError, TooManyRequests) as exc:
            print(f"BOB_PUSH database_busy path={path} error={type(exc).__name__}", flush=True)
            send_json(self, 503, {"error": "Push-Service kurzzeitig belegt", "retryable": True})
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
    diagnostic_history.configure(db)
    print("BOB_PUSH startup=ready", flush=True)
    # Process/child memory telemetry is read-only and never blocks Push.
    import memory_watch
    memory_watch.start()
    import runtime_watchdog
    runtime_watchdog.start()
    paper_simulation.start_preflight(db)
    threading.Thread(target=product_expiry_loop, name="bob-product-expiry", daemon=True).start()
    threading.Thread(target=audit_outcome_loop, name="bob-audit-outcomes", daemon=True).start()
    import browserless_profile
    threading.Thread(target=browserless_profile.probe,name="bob-browserless-profile-check",daemon=True).start()
    import browserless_trial
    threading.Thread(target=browserless_trial.run_once,args=(db,),name="bob-browserless-trial",daemon=True).start()
    import video_ocr
    threading.Thread(target=video_ocr.loop,args=(db,),name="bob-video-ocr",daemon=True).start()
    BobHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()





