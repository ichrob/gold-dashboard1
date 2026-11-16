"""Bounded user-opened handset sessions; no arbitrary taps, text or order commands."""
import json
import re
import time
import uuid
from android_telemetry import token_hash

SCOPE='bob:phone:control'
TOOLS=('bob_phone_status','bob_phone_command')
ACTIONS=('inspect','search_gold','search_isin','read_page','read_account_settings','termux_check','stop')
# The handset runs in the background when DEGIRO is in the foreground. Android
# may delay remote polls for longer than 20s. Keep the *undelivered* request
# bounded but separate its deadline from the short device execution lease.
QUEUE_TTL=90
DELIVERY_LEASE=20
# Only short-lived, minimised account enums survive a new handset session.
# This is not account identity matching and never proves broker fees.
ACCOUNT_EVIDENCE_MAX_AGE=7*86400
ACCOUNT_EVIDENCE_SOURCES=('degiro-app-local-accessibility','degiro-app-owner-confirmed')

def verified_settings(state,now):
    result={}
    if not isinstance(state,dict):return result
    prior=state.get('verifiedSettings')
    if isinstance(prior,dict):
        for key,allowed in [('feeProfile',('BASIC','ACTIVE','TRADER')),
                            ('autoFx',('ON','OFF'))]:
            item=prior.get(key)
            if (isinstance(item,dict) and set(item)=={'value','capturedAt','source'} and
                    item['value'] in allowed and type(item['capturedAt']) is int and
                    0<=now-item['capturedAt']<=ACCOUNT_EVIDENCE_MAX_AGE and
                    item['source'] in ACCOUNT_EVIDENCE_SOURCES):
                result[key]=dict(item)
    # Compatible upgrade from the previously validated single-session
    # receipt, without re-scanning any credential or raw screen content.
    previous=state.get('accountSettings')
    if isinstance(previous,dict) and previous.get('source') in ACCOUNT_EVIDENCE_SOURCES:
        when=previous.get('capturedAt')
        if type(when) is int and 0<=now-when<=ACCOUNT_EVIDENCE_MAX_AGE:
            for key,allowed in [('feeProfile',('BASIC','ACTIVE','TRADER')),
                                ('autoFx',('ON','OFF'))]:
                if key not in result and previous.get(key) in allowed:
                    result[key]=dict(value=previous[key],capturedAt=when,
                                     source=previous['source'])
    return result

def definitions():
    common={'deviceId':{'type':'string','pattern':'^[a-f0-9]{12}$'}}
    return [dict(name='bob_phone_status',description='Read the latest user-opened Bob Handy session, product-only observation, bounded redacted settings evidence and command acknowledgement. Cached timestamps are not a live screen; never an order or full-phone access.',inputSchema={'type':'object','properties':common,'additionalProperties':False},annotations={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}),
      dict(name='bob_phone_command',description='Request one bounded DEGIRO product-reading action or read_account_settings on a user-opened settings page, in an explicitly opened handset session. search actions perform ONE semantic navigation step; inspect again before continuing. Account settings never confirm actual fees or executable quotes. termux_check may request only a fixed on-device help check during a user-opened session: no shell input, secrets, or orders. Queued/delivered does not mean performed. Reuse requestId on retry.',inputSchema={'type':'object','properties':{**common,'sessionId':{'type':'string'},'requestId':{'type':'string'},'action':{'type':'string','enum':list(ACTIONS)},'isin':{'type':'string'}},'required':['deviceId','sessionId','requestId','action'],'additionalProperties':False},annotations={'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True,'openWorldHint':True})]

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
    required_exchange={'sessionId','expiresAt','active','observation','ack'}
    if not isinstance(value,dict) or not required_exchange<=set(value) or set(value)-required_exchange-{'purpose'}:
        raise ValueError('Invalid exchange')
    purpose=value.get('purpose','product_read')
    if purpose not in ('product_read','owner_account_settings'):
        raise ValueError('Invalid handset session purpose')
    if state.get('sessionId')==value['sessionId'] and state.get('purpose','product_read')!=purpose:
        raise ValueError('Session purpose cannot change')
    if not identifier(value['sessionId'],32) or type(value['active']) is not bool or type(value['expiresAt']) is not int:raise ValueError('Invalid session')
    if value['active'] and not now<value['expiresAt']<=now+905:raise ValueError('Expired session')
    obs=value['observation']
    required={'at','code','nodeCount','isins','draft','diagnostics'}
    if not isinstance(obs,dict) or not required<=set(obs) or set(obs)-required-{'accountSettings'}:raise ValueError('Invalid observation')
    if type(obs['at']) is not int or not now-60<=obs['at']<=now+60:raise ValueError('Stale observation')
    if not isinstance(obs['code'],str) or not re.fullmatch('[A-Z_]{1,64}',obs['code']):raise ValueError('Invalid code')
    if type(obs['nodeCount']) is not int or not 0<=obs['nodeCount']<=500:raise ValueError('Invalid count')
    if not isinstance(obs['isins'],list) or len(obs['isins'])>12 or not all(valid_isin(s) for s in obs['isins']):raise ValueError('Invalid identities')
    if not isinstance(obs['draft'],str) or len(obs['draft'])>8000:raise ValueError('Invalid product draft')
    if not isinstance(obs['diagnostics'],str) or len(obs['diagnostics'])>8000:raise ValueError('Invalid diagnostics')
    if 'accountSettings' in obs:
        if obs['draft'] or obs['isins']:
            raise ValueError('Settings cannot accompany product or account text')
        # Only a read request in THIS active, user-opened session can
        # introduce a redacted setting observation; never accept raw UI text.
        evidence=obs['accountSettings']
        if not isinstance(evidence,dict) or set(evidence)!={'source','capturedAt','status','feeProfile','autoFx'}:
            raise ValueError('Invalid account settings evidence')
        if evidence['source'] not in ACCOUNT_EVIDENCE_SOURCES or type(evidence['capturedAt']) is not int or not now-60<=evidence['capturedAt']<=now+60:
            raise ValueError('Invalid account evidence source/time')
        if evidence['status'] not in ('COMPLETE','PARTIAL') or evidence['feeProfile'] not in (None,'BASIC','ACTIVE','TRADER') or evidence['autoFx'] not in (None,'ON','OFF'):
            raise ValueError('Invalid account evidence values')
        complete=evidence['feeProfile'] is not None and evidence['autoFx'] is not None
        if (evidence['status']=='COMPLETE')!=complete or (evidence['feeProfile'] is None and evidence['autoFx'] is None):
            raise ValueError('Unsubstantiated account evidence')
        ack=value['ack']
        remote_read=(isinstance(ack,dict) and ack.get('code')==obs['code']
                     and identifier(ack.get('requestId'),32)
                     and state.get('sessionId')==value['sessionId']
                     and any(c.get('requestId')==ack['requestId']
                             and c.get('action')=='read_account_settings'
                             and c.get('status') in ('delivered','acknowledged')
                             for c in state.get('commands',[])))
        # The owner starts this exact mode with its separate local button.
        # No server-side free navigation or remote command is necessary.
        # Only a redacted enum can be submitted, exactly once per session.
        owner_read=(purpose=='owner_account_settings' and value['active'] and
                    ack is None and (state.get('sessionId')!=value['sessionId']
                         or state.get('purpose')=='owner_account_settings'))
        prior=state.get('accountSettings') if state.get('sessionId')==value['sessionId'] else None
        if owner_read and prior is not None:
            owner_read=all(prior.get(k)==evidence[k] for k in
                           ('source','capturedAt','status','feeProfile','autoFx'))
        if evidence['source']=='degiro-app-owner-confirmed':
            # An explicit device-owner assertion can only concern the
            # displayed profile, never automatically assert FX or fees.
            if not owner_read or evidence['feeProfile'] is None or evidence['autoFx'] is not None:
                raise ValueError('Owner assertion must be profile-only with physical consent')
        if obs['code'] not in ('ACCOUNT_SETTINGS_COMPLETE','ACCOUNT_SETTINGS_PARTIAL') or not (remote_read or owner_read):
            raise ValueError('Account evidence requires owner settings consent or delivered read request')
    if state.get('sessionId')!=value['sessionId']:
        retained=verified_settings(state,now)
        state={'sessionId':value['sessionId'],'expiresAt':value['expiresAt'],
               'purpose':purpose,'commands':[],'verifiedSettings':retained}
    else:
        # A heartbeat cannot silently extend a previously consented session
        # or re-label a product session as account settings.
        value=dict(value,expiresAt=min(state['expiresAt'],value['expiresAt']))
    state.update({k:value[k] for k in ('active','expiresAt','observation')})
    # Preserve the last small, already-validated enum receipt within this
    # consented session. Normal 2-second product heartbeat must not erase it.
    # Never promote it into fee configuration or executed-quote fields.
    if 'accountSettings' in obs:
        state['accountSettings']=dict(obs['accountSettings'],accountFeeConfirmed=False,
                                      brokerExecutionConfirmed=False)
        validated=verified_settings(state,now)
        for name,allowed in [('feeProfile',('BASIC','ACTIVE','TRADER')),
                             ('autoFx',('ON','OFF'))]:
            if obs['accountSettings'].get(name) in allowed:
                validated[name]=dict(value=obs['accountSettings'][name],
                   capturedAt=obs['accountSettings']['capturedAt'],
                   source=obs['accountSettings']['source'])
        # Do not treat independent sessions as a verified account identity,
        # a confirmed fee schedule or an executable order.
        state['verifiedSettings']=validated
        state['sameAccountAcrossSessionsConfirmed']=False
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
                c.update(status='delivered',deliveredAt=now)
                # PhoneCommandPolicy independently rejects commands whose
                # execution deadline is >30s away. Delayed queue delivery
                # must not broaden that on-device protection window.
                command=dict(c,expiresAt=min(now+DELIVERY_LEASE,c['expiresAt']))
                break
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
    c.update(status='queued',createdAt=now,expiresAt=min(now+QUEUE_TTL,state['expiresAt']))
    state['commands'].append(c)
    return dict(c)

def init(conn):
    __import__("android_list").init(conn)
    __import__("termux_maintenance").init(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS bob_android_remote (token_hash TEXT PRIMARY KEY REFERENCES bob_android_diagnostic_devices(token_hash) ON DELETE CASCADE,state JSONB NOT NULL)")

def handle(conn,payload):
    now=int(time.time());op=payload.get('action')
    if op in ('termux-exchange','termux-mcp'):return __import__('termux_maintenance').handle(conn,payload)
    if op in ('list-upload','list-get','list-receipt','list-status','list-details'):return __import__('android_list').handle(conn,payload,now)
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
