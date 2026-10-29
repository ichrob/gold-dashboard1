"""Short, separately paired Android read sessions; no arbitrary UI or order actions."""
import hashlib
import json
import re
import time

SCOPE = 'bob:handy:control'
ACTIONS = ('READ_PAGE', 'SEARCH_GOLD', 'STOP')
TOOLS = ('bob_handy_sessions', 'bob_handy_action')
ACKS = ('STARTED', 'STOPPED', 'BUSY', 'LOCKED', 'WRONG_APP', 'REJECTED', 'EXPIRED')

def definitions():
    common={'sessionId':{'type':'string','pattern':'^[a-f0-9]{24}$'}}
    return [
        dict(name='bob_handy_sessions',description='Read explicitly paired 15-minute Bob Handy sessions and fixed reader diagnostics. No live screen image or arbitrary UI tree. An accepted command is not a completed product read.',inputSchema={'type':'object','properties':{},'additionalProperties':False},annotations={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}),
        dict(name='bob_handy_action',description='Request one bounded READ_PAGE, SEARCH_GOLD or STOP in an explicitly paired active Bob Handy session. Requires separate bob:handy:control consent and local phone session. READ_PAGE and SEARCH_GOLD require DEGIRO already foreground and unlocked. No login, orders, arbitrary clicks or text. Reuse requestId on retry. Confirm results separately with bob_handy_sessions.',inputSchema={'type':'object','properties':{**common,'action':{'type':'string','enum':list(ACTIONS)},'requestId':{'type':'string','pattern':'^[a-f0-9]{32}$'}},'required':['sessionId','action','requestId'],'additionalProperties':False},annotations={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':True})]

def arguments(name, args):
    if name not in TOOLS or not isinstance(args,dict):raise ValueError('Invalid tool')
    required=set() if name=='bob_handy_sessions' else {'sessionId','action','requestId'}
    if set(args)!=required:raise ValueError('Invalid fields')
    if required:
        if args['action'] not in ACTIONS:raise ValueError('Invalid action')
        for key,size in [('sessionId',24),('requestId',32)]:
            if not isinstance(args[key],str) or not re.fullmatch('[a-f0-9]{%d}'%size,args[key]):raise ValueError('Invalid ID')
    return args

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_android_remote_sessions (
        session_id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
        expires_at BIGINT NOT NULL, revoked BOOLEAN NOT NULL DEFAULT false,
        received_at BIGINT, snapshot JSONB)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_android_remote_commands (
        request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, action TEXT NOT NULL,
        created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
        outcome TEXT NOT NULL DEFAULT 'QUEUED', delivered_at BIGINT)''')

def snapshot(value):
    expected={'version','running','serviceConnected','report','ackId','ackCode'}
    if not isinstance(value,dict) or set(value)!=expected:raise ValueError('Invalid snapshot')
    if type(value['version']) is not int or not 1<=value['version']<=2100000000:raise ValueError('Invalid version')
    if any(type(value[k]) is not bool for k in ('running','serviceConnected')):raise ValueError('Invalid state')
    # Only fixed diagnostic names/counters, not screen/account/credential text.
    from android_remote_codes import REPORT_KEYS
    report=value['report']
    if not isinstance(report,dict) or any(k not in REPORT_KEYS or type(v) is not int or not 0<=v<=999 for k,v in report.items()):raise ValueError('Invalid report')
    if value['ackId'] is not None and (not isinstance(value['ackId'],str) or not re.fullmatch('[a-f0-9]{32}',value['ackId'])):raise ValueError('Invalid acknowledgement')
    if value['ackCode'] not in (None,*ACKS) or (value['ackId'] is None)!=(value['ackCode'] is None):raise ValueError('Invalid acknowledgement')
    return value

def handle(conn, payload, now=None):
    now=int(time.time()*1000) if now is None else now
    if not isinstance(payload,dict):raise ValueError('Invalid request')
    op=payload.get('op')
    if op=='pair':
        if set(payload)!={'op','tokenHash'} or not isinstance(payload['tokenHash'],str) or not re.fullmatch('[a-f0-9]{64}',payload['tokenHash']):raise ValueError('Invalid pairing')
        conn.execute('SELECT pg_advisory_xact_lock(72610430)')
        conn.execute('DELETE FROM bob_android_remote_commands WHERE expires_at<%s',(now-86400000,))
        conn.execute('DELETE FROM bob_android_remote_sessions WHERE expires_at<%s',(now-86400000,))
        digest=payload['tokenHash'];sid=digest[:24]
        existing=conn.execute('SELECT expires_at,revoked FROM bob_android_remote_sessions WHERE token_hash=%s',(digest,)).fetchone()
        if existing:
            if existing[1] or existing[0]<=now:raise PermissionError('Expired session')
            return {'ok':True,'sessionId':sid,'expiresAt':existing[0]}
        if conn.execute('SELECT count(*) FROM bob_android_remote_sessions WHERE expires_at>%s AND NOT revoked',(now,)).fetchone()[0]>=5:raise ValueError('Session limit')
        conn.execute('INSERT INTO bob_android_remote_sessions(session_id,token_hash,expires_at) VALUES(%s,%s,%s)',(sid,digest,now+900000))
        return {'ok':True,'sessionId':sid,'expiresAt':now+900000}
    if op=='sessions':
        if set(payload)!={'op'}:raise ValueError('Invalid request')
        rows=conn.execute('SELECT session_id,expires_at,revoked,received_at,snapshot FROM bob_android_remote_sessions WHERE expires_at>%s ORDER BY expires_at DESC LIMIT 5',(now,)).fetchall()
        return {'realOrders':False,'sessions':[dict(sessionId=s,expiresAt=e,revoked=r,receivedAt=at,fresh=bool(at and 0<=now-at<30000),snapshot=v) for s,e,r,at,v in rows]}
    if op=='command':
        if set(payload)!={'op','arguments'}:raise ValueError('Invalid request')
        a=arguments('bob_handy_action',payload['arguments'])
        row=conn.execute('SELECT received_at,snapshot FROM bob_android_remote_sessions WHERE session_id=%s AND expires_at>%s AND NOT revoked FOR UPDATE',(a['sessionId'],now)).fetchone()
        if not row:raise PermissionError('Inactive session')
        prior=conn.execute('SELECT session_id,action,outcome FROM bob_android_remote_commands WHERE request_id=%s',(a['requestId'],)).fetchone()
        if prior:
            if prior[:2]!=(a['sessionId'],a['action']):raise ValueError('Conflicting request ID')
            return {'ok':True,'status':prior[2],'requestId':a['requestId'],'reused':True}
        if not row[0] or not 0<=now-row[0]<30000:raise ValueError('Phone not recently connected')
        pending=conn.execute("SELECT count(*) FROM bob_android_remote_commands WHERE session_id=%s AND outcome='QUEUED' AND expires_at>%s",(a['sessionId'],now)).fetchone()[0]
        recent=conn.execute('SELECT count(*) FROM bob_android_remote_commands WHERE session_id=%s AND created_at>%s',(a['sessionId'],now-60000)).fetchone()[0]
        if recent>=12 or (pending and a['action']!='STOP'):raise ValueError('Command limit')
        if a['action']=='STOP':conn.execute("UPDATE bob_android_remote_commands SET outcome='EXPIRED' WHERE session_id=%s AND outcome='QUEUED'",(a['sessionId'],))
        conn.execute('INSERT INTO bob_android_remote_commands(request_id,session_id,action,created_at,expires_at) VALUES(%s,%s,%s,%s,%s)',(a['requestId'],a['sessionId'],a['action'],now,now+20000))
        return {'ok':True,'status':'QUEUED','requestId':a['requestId'],'completed':False}
    if op not in ('poll','revoke') or set(payload)!=({'op','token','snapshot'} if op=='poll' else {'op','token'}):raise ValueError('Invalid operation')
    token=payload['token']
    if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{64}',token):raise PermissionError('Invalid token')
    digest=hashlib.sha256(token.encode()).hexdigest()
    row=conn.execute('SELECT session_id FROM bob_android_remote_sessions WHERE token_hash=%s AND expires_at>%s AND NOT revoked FOR UPDATE',(digest,now)).fetchone()
    if not row:raise PermissionError('Inactive session')
    sid=row[0]
    if op=='revoke':
        conn.execute('UPDATE bob_android_remote_sessions SET revoked=true,snapshot=NULL WHERE session_id=%s',(sid,))
        conn.execute("UPDATE bob_android_remote_commands SET outcome='EXPIRED' WHERE session_id=%s AND outcome='QUEUED'",(sid,))
        return {'ok':True}
    value=snapshot(payload['snapshot'])
    if value['ackId']:
        conn.execute("UPDATE bob_android_remote_commands SET outcome=%s WHERE request_id=%s AND session_id=%s AND outcome='DELIVERED'",(value['ackCode'],value['ackId'],sid))
    conn.execute('UPDATE bob_android_remote_sessions SET received_at=%s,snapshot=%s::jsonb WHERE session_id=%s',(now,json.dumps(value),sid))
    command=conn.execute("SELECT request_id,action,expires_at FROM bob_android_remote_commands WHERE session_id=%s AND outcome='QUEUED' AND expires_at>%s ORDER BY created_at LIMIT 1 FOR UPDATE",(sid,now)).fetchone()
    if command:conn.execute("UPDATE bob_android_remote_commands SET outcome='DELIVERED',delivered_at=%s WHERE request_id=%s",(now,command[0]))
    # At-most-once delivery: an uncertain network response never replays a command.
    return {'ok':True,'command':dict(requestId=command[0],action=command[1],expiresAt=command[2]) if command else None}
