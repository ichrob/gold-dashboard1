"""Bounded user-opened handset sessions; no arbitrary taps, text or order commands."""
import json
import re
import time
import uuid
from android_telemetry import token_hash

SCOPE='bob:phone:control'
TOOLS=('bob_phone_status','bob_phone_command')
ACTIONS=('inspect','search_gold','search_isin','read_page','stop')

def definitions():
    common={'deviceId':{'type':'string','pattern':'^[a-f0-9]{12}$'}}
    return [dict(name='bob_phone_status',description='Read the latest user-opened Bob Handy session, product-only observation and command acknowledgement. Cached timestamps are not a live screen; never an order or full-phone access.',inputSchema={'type':'object','properties':common,'additionalProperties':False},annotations={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}),
      dict(name='bob_phone_command',description='Request one bounded DEGIRO product-reading action in an explicitly opened handset session. search actions perform ONE semantic navigation step; inspect again before continuing. No coordinates, passwords or orders. Queued/delivered does not mean performed. Reuse requestId on retry.',inputSchema={'type':'object','properties':{**common,'sessionId':{'type':'string'},'requestId':{'type':'string'},'action':{'type':'string','enum':list(ACTIONS)},'isin':{'type':'string'}},'required':['deviceId','sessionId','requestId','action'],'additionalProperties':False},annotations={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':True})]

def identifier(v,n):
    return isinstance(v,str) and re.fullmatch('[a-f0-9]{%d}'%n,v) is not None

def valid_isin(s):
    if not isinstance(s,str) or not re.fullmatch('[A-Z]{2}[A-Z0-9]{9}[0-9]',s):return False
    digits=''.join(str(ord(c)-55) if c.isalpha() else c for c in s)
    return sum(sum(divmod(int(c)*(2 if i%2 else 1),10)) for i,c in enumerate(digits[::-1]))%10==0

def arguments(name,a):
    if not isinstance(a,dict):raise ValueError('Invalid arguments')
    if name=='bob_phone_status':
        if set(a)-{'deviceId'} or ('deviceId' in a and not identifier(a['deviceId'],12)):raise ValueError('Invalid device')
    elif name=='bob_phone_command':
        if set(a)-{'deviceId','sessionId','requestId','action','isin'} or not all(identifier(a.get(k),n) for k,n in [('deviceId',12),('sessionId',32),('requestId',32)]):raise ValueError('Invalid command identity')
        if a.get('action') not in ACTIONS:raise ValueError('Invalid action')
        if a['action']=='search_isin':
            if not valid_isin(a.get('isin')):raise ValueError('Invalid ISIN')
        elif 'isin' in a:raise ValueError('Unexpected ISIN')
    else:raise ValueError('Invalid operation')
    return dict(a)

def exchange(state,value,now):
    if not isinstance(value,dict) or set(value)!={'sessionId','expiresAt','active','observation','ack'}:raise ValueError('Invalid exchange')
    if not identifier(value['sessionId'],32) or type(value['active']) is not bool or type(value['expiresAt']) is not int:raise ValueError('Invalid session')
    if value['active'] and not now<value['expiresAt']<=now+905:raise ValueError('Expired session')
    obs=value['observation']
    if not isinstance(obs,dict) or set(obs)!={'at','code','nodeCount','isins','draft','diagnostics'}:raise ValueError('Invalid observation')
    if type(obs['at']) is not int or not now-60<=obs['at']<=now+60:raise ValueError('Stale observation')
    if not isinstance(obs['code'],str) or not re.fullmatch('[A-Z_]{1,64}',obs['code']):raise ValueError('Invalid code')
    if type(obs['nodeCount']) is not int or not 0<=obs['nodeCount']<=500:raise ValueError('Invalid count')
    if not isinstance(obs['isins'],list) or len(obs['isins'])>12 or not all(valid_isin(s) for s in obs['isins']):raise ValueError('Invalid identities')
    if not isinstance(obs['draft'],str) or len(obs['draft'])>8000:raise ValueError('Invalid product draft')
    if not isinstance(obs['diagnostics'],str) or len(obs['diagnostics'])>8000:raise ValueError('Invalid diagnostics')
    if state.get('sessionId')!=value['sessionId']:
        state={'sessionId':value['sessionId'],'expiresAt':value['expiresAt'],'commands':[]}
    else:
        # A heartbeat cannot silently extend a previously consented session.
        value=dict(value,expiresAt=min(state['expiresAt'],value['expiresAt']))
    state.update({k:value[k] for k in ('active','expiresAt','observation')})
    state['seenAt']=now
    ack=value['ack']
    if ack is not None:
        if not isinstance(ack,dict) or set(ack)!={'requestId','code'} or not identifier(ack['requestId'],32) or not re.fullmatch('[A-Z_]{1,64}',str(ack['code'])):raise ValueError('Invalid acknowledgement')
        for c in state['commands']:
            if c['requestId']==ack['requestId'] and c['status']=='delivered':c.update(status='acknowledged',result=ack['code'],ackAt=now)
    for c in state['commands']:
        if c['status']=='queued' and (c['expiresAt']<=now or not state['active']):c['status']='expired'
    command=None
    if state['active'] and state['expiresAt']>now:
        for c in state['commands']:
            if c['status']=='queued':
                c.update(status='delivered',deliveredAt=now);command=dict(c);break
    return state,{'ok':True,'sessionId':state['sessionId'],'command':command}

def enqueue(state,a,now):
    if not state or state.get('sessionId')!=a['sessionId']:return {'status':'session-missing'}
    for c in state['commands']:
        if c['requestId']==a['requestId']:
            if c['action']!=a['action'] or c.get('isin')!=a.get('isin'):raise ValueError('Request ID reused')
            return dict(c)
    if not state.get('active') or state['expiresAt']<=now or now-state.get('seenAt',0)>30:return {'status':'session-offline'}
    pending=[c for c in state['commands'] if c['status'] in ('queued','delivered') and c['expiresAt']>now]
    if pending and a['action']!='stop':return {'status':'busy'}
    if a['action']=='stop':
        for c in pending:c['status']='cancelled'
    if len(state['commands'])>120 or (len(state['commands'])>=120 and a['action']!='stop'):return {'status':'session-command-limit'}
    c={k:v for k,v in a.items() if k!='deviceId'}
    c.update(status='queued',createdAt=now,expiresAt=min(now+20,state['expiresAt']))
    state['commands'].append(c)
    return dict(c)

def init(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS bob_android_remote (token_hash TEXT PRIMARY KEY REFERENCES bob_android_diagnostic_devices(token_hash) ON DELETE CASCADE,state JSONB NOT NULL)")

def handle(conn,payload):
    now=int(time.time());op=payload.get('action')
    if op=='exchange':
        digest=token_hash(payload.get('token'))
        device=conn.execute('SELECT token_hash FROM bob_android_diagnostic_devices WHERE token_hash=%s AND NOT revoked AND expires_at>now() FOR UPDATE',(digest,)).fetchone()
        if not device:raise PermissionError('Device not paired')
        row=conn.execute('SELECT state FROM bob_android_remote WHERE token_hash=%s FOR UPDATE',(digest,)).fetchone()
        state,answer=exchange(row[0] if row else {},payload.get('value'),now)
        conn.execute('INSERT INTO bob_android_remote VALUES(%s,%s::jsonb) ON CONFLICT(token_hash) DO UPDATE SET state=EXCLUDED.state',(digest,json.dumps(state)))
        return answer
    if op!='mcp':raise ValueError('Invalid operation')
    name=payload.get('name');a=arguments(name,payload.get('arguments'))
    # Only authenticated server-side MCP dispatch can reach this branch.
    rows=conn.execute("SELECT d.token_hash,r.state FROM bob_android_diagnostic_devices d JOIN bob_android_remote r USING(token_hash) WHERE NOT d.revoked AND d.expires_at>now() ORDER BY d.created_at DESC LIMIT 5 FOR UPDATE OF d,r").fetchall()
    rows=[r for r in rows if not a.get('deviceId') or r[0].startswith(a['deviceId'])]
    if name=='bob_phone_status':
        return {'devices':[{'deviceId':d[:12],**dict(s,commands=s.get('commands',[])[-12:]),'fresh':now-s.get('seenAt',0)<=30,'online':s.get('active',False) and s.get('expiresAt',0)>now and now-s.get('seenAt',0)<=30} for d,s in rows], 'serverAt':now,'ordersAllowed':False}
    if len(rows)!=1:return {'status':'device-missing-or-ambiguous'}
    digest,state=rows[0];answer=enqueue(state,a,now)
    conn.execute('UPDATE bob_android_remote SET state=%s::jsonb WHERE token_hash=%s',(json.dumps(state),digest))
    return answer
