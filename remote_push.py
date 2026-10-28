"""Explicitly scoped, bounded synthetic push tests; no registration or trading."""
import json
import re
import time

SCOPE = 'bob:push:test'
READ_TOOLS = ('bob_push_devices', 'bob_push_test_status')
TOOLS = (*READ_TOOLS, 'bob_push_test')


def definitions():
    shapes={
      'bob_push_devices':({},[],'List registered Bob push devices by opaque ID and channel state. No endpoints, keys or handset identity claims. Read only.'),
      'bob_push_test':({'deviceId':{'type':'string'},'requestId':{'type':'string','pattern':'^[0-9a-f]{32}$'}},['deviceId','requestId'],
        'Schedule one fixed synthetic TEST notification for an explicitly selected existing Bob device. Requires separate bob:push:test consent. Reuse requestId on retries. Does not enable permissions, register devices, change channels, send arbitrary text, or trade. If several devices exist, resolve the intended device with the user.'),
      'bob_push_test_status':({'requestId':{'type':'string','pattern':'^[0-9a-f]{32}$'}},['requestId'],
        'Read one remote TEST request and its correlated signed browser receipts. Provider acceptance is not visible Android delivery. Read only.')}
    return [dict(name=name,description=desc,inputSchema={'type':'object','properties':props,'required':required,'additionalProperties':False},
                 annotations={'readOnlyHint':name!='bob_push_test','destructiveHint':False,'idempotentHint':True,'openWorldHint':name=='bob_push_test'})
            for name,(props,required,desc) in shapes.items()]


def arguments(name,args):
    required={'bob_push_devices':set(),'bob_push_test':{'deviceId','requestId'},'bob_push_test_status':{'requestId'}}
    if name not in required or not isinstance(args,dict) or set(args)!=required[name]:raise ValueError('Invalid remote push arguments')
    if 'requestId' in args and (not isinstance(args['requestId'],str) or not re.fullmatch('[0-9a-f]{32}',args['requestId'])):raise ValueError('Invalid requestId')
    if 'deviceId' in args and (not isinstance(args['deviceId'],str) or not re.fullmatch('device-[1-9][0-9]{0,17}',args['deviceId'])):raise ValueError('Invalid deviceId')
    return args


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_remote_push_tests (
        request_id TEXT PRIMARY KEY, device_id BIGINT NOT NULL, created_at BIGINT NOT NULL,
        due_at BIGINT NOT NULL, outcome TEXT NOT NULL DEFAULT 'scheduled', last_attempt_at BIGINT)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_remote_push_tests_device ON bob_remote_push_tests(device_id,created_at)')


def devices(conn):
    rows=conn.execute('''SELECT id,general_enabled,trade_enabled,updated_at,pending_test IS NOT NULL
                         FROM subscriptions ORDER BY updated_at DESC LIMIT 20''').fetchall()
    return {'readOnly':True,'realOrders':False,'devices':[
        {'deviceId':'device-'+str(i),'marketEnabled':g,'tradeEnabled':t,'lastSettingsAt':at.isoformat(),
         'pendingTest':pending,'canTest':bool(g or t),'deviceIdentity':'browser-registration-not-verified-handset'} for i,g,t,at,pending in rows],
        'note':'No device means registration must first be performed on the handset. Never guess between multiple devices.'}


def schedule(conn,args,now=None):
    arguments('bob_push_test',args);now=int(time.time()*1000) if now is None else now
    sid=int(args['deviceId'][7:]);rid=args['requestId']
    # Global transaction lock bounds all remote requests and handles duplicate IDs atomically.
    conn.execute('SELECT pg_advisory_xact_lock(72610429)')
    existing=conn.execute('SELECT device_id,due_at,outcome FROM bob_remote_push_tests WHERE request_id=%s',(rid,)).fetchone()
    if existing:
        if existing[0]!=sid:raise ValueError('requestId already belongs to another device')
        return {'requestId':rid,'deviceId':args['deviceId'],'dueAt':existing[1],'status':existing[2],'reused':True,'realOrders':False}
    row=conn.execute('SELECT general_enabled,trade_enabled,pending_test FROM subscriptions WHERE id=%s FOR UPDATE',(sid,)).fetchone()
    if not row:return {'status':'device-not-found','registrationRequired':True,'realOrders':False}
    if not (row[0] or row[1]):return {'status':'channels-disabled','realOrders':False}
    if row[2]:return {'status':'test-already-pending','realOrders':False}
    counts=conn.execute('SELECT count(*),count(*) FILTER (WHERE created_at>%s) FROM bob_remote_push_tests WHERE device_id=%s AND created_at>%s',(now-300000,sid,now-86400000)).fetchone()
    if counts[0]>=10 or counts[1]:return {'status':'rate-limited','realOrders':False}
    due=now+30000
    pending={'kind':'general' if row[0] else 'trade','dueAt':due,'remoteRequestId':rid}
    conn.execute('INSERT INTO bob_remote_push_tests(request_id,device_id,created_at,due_at) VALUES(%s,%s,%s,%s)',(rid,sid,now,due))
    conn.execute('UPDATE subscriptions SET pending_test=%s::jsonb WHERE id=%s',(json.dumps(pending),sid))
    return {'status':'scheduled','requestId':rid,'deviceId':args['deviceId'],'dueAt':due,'test':True,'realOrders':False}


def record(conn,pending,outcome,now):
    rid=pending.get('remoteRequestId')
    if isinstance(rid,str) and re.fullmatch('[0-9a-f]{32}',rid):
        conn.execute('UPDATE bob_remote_push_tests SET outcome=%s,last_attempt_at=%s WHERE request_id=%s',(outcome,now,rid))


def status(conn,args):
    arguments('bob_push_test_status',args);rid=args['requestId']
    row=conn.execute('SELECT device_id,created_at,due_at,outcome,last_attempt_at FROM bob_remote_push_tests WHERE request_id=%s',(rid,)).fetchone()
    if not row:return {'status':'not-found','readOnly':True}
    receipts=conn.execute('''SELECT DISTINCT r.payload->>'receiptState' FROM bob_diagnostic_history a
        JOIN bob_diagnostic_history r ON r.payload->>'receiptId'=a.payload->>'receiptId'
        WHERE a.trace_id=%s AND a.stage='push-delivery' AND r.stage='push-delivery'
        AND r.payload->>'outcome'='browser-receipt' ''',(rid,)).fetchall()
    states={r[0] for r in receipts}
    return dict(requestId=rid,deviceId='device-'+str(row[0]),createdAt=row[1],dueAt=row[2],status=row[3],lastAttemptAt=row[4],
                browserApiAccepted='show-resolved' in states,notificationClicked='clicked' in states,
                visibleAndroidDeliveryVerified=False,readOnly=True,realOrders=False,
                note='Signed browser API acknowledgement or click is not independent Android display telemetry.')
