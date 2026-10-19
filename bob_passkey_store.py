"""Durable WebAuthn state. Called only by authenticated internal service RPC."""
import base64
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlsplit

ORIGIN = 'https://bob-private-scanner.onrender.com'
RP_ID = urlsplit(ORIGIN).hostname
TTL = 24 * 60 * 60

def encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()

def decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_passkeys (
        account TEXT PRIMARY KEY, state JSONB NOT NULL DEFAULT '{}'::jsonb)''')

def proof_valid(state, binding, now):
    return state.get('proofs', {}).get(binding, 0) > now

def transition(state, action, payload, now=None):
    """Pure state transition; caller serializes and commits even rejected ceremonies."""
    now = time.time() if now is None else now
    state.setdefault('credentials', {})
    state.setdefault('proofs', {})
    state.setdefault('challenges', {})
    state['proofs'] = {k:v for k,v in state['proofs'].items() if v > now}
    state['challenges'] = {k:v for k,v in state['challenges'].items() if v['expires'] > now}
    binding = payload.get('binding', '')
    if not isinstance(binding,str) or not re.fullmatch('[a-f0-9]{64}',binding):
        raise ValueError('Invalid session binding')
    state.setdefault('proofKeys', {})
    state.setdefault('recent', {})
    active = bool(state['credentials'])
    if action == 'status':
        return {'enabled':active, 'verified':proof_valid(state,binding,now), 'validUntil':state['proofs'].get(binding),
                'recoverySaved':state.get('recoverySaved',False),
                'credentials':[{'id':cid,'name':key.get('name','Passkey'),'current':state['proofKeys'].get(binding)==cid} for cid,key in state['credentials'].items()] if proof_valid(state,binding,now) else [],
                'recoveryRemaining':len(state.get('recovery',[])) if proof_valid(state,binding,now) else None}
    failures = [stamp for stamp in state.get('failures',[]) if stamp > now-300]
    state['failures'] = failures
    if len(failures) >= 5:
        return {'ok':False,'error':'TOO_MANY_ATTEMPTS'}
    from webauthn import (generate_registration_options, generate_authentication_options,
                          verify_registration_response, verify_authentication_response, options_to_json)
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, UserVerificationRequirement,
                                         ResidentKeyRequirement, PublicKeyCredentialDescriptor)
    if action in ('revoke-credential','rotate-recovery','confirm-recovery','machine-authorize'):
        if not proof_valid(state,binding,now) and (active or action!='machine-authorize'):
            return {'ok':False,'error':'PASSKEY_REQUIRED'}
        if active and state['recent'].get(binding,0)<=now:
            return {'ok':False,'error':'FRESH_PASSKEY_REQUIRED'}
        if action=='machine-authorize':return {'ok':True}
        if action=='revoke-credential':
            cid=payload.get('credentialId','')
            if cid not in state['credentials']:return {'ok':False,'error':'UNKNOWN_CREDENTIAL'}
            if len(state['credentials'])<=1:return {'ok':False,'error':'LAST_CREDENTIAL'}
            del state['credentials'][cid]
            # Revoke every other daily grant and all pending ceremonies. A stolen
            # phone cannot continue on yesterday's proof after its key is removed.
            keep=state['proofKeys'].get(binding)!=cid
            state['proofs']={binding:state['proofs'][binding]} if keep else {}
            state['proofKeys']={binding:state['proofKeys'].get(binding)} if keep else {}
            state['recent']={binding:state['recent'][binding]} if keep else {}
            state['challenges']={}
            return {'ok':True}
        if action=='rotate-recovery':
            codes=[secrets.token_hex(16) for _ in range(8)]
            state['pendingRecovery']={'hashes':[hashlib.sha256(c.encode()).hexdigest() for c in codes],'binding':binding,'expires':now+600}
            return {'ok':True,'recoveryCodes':codes}
        pending=state.get('pendingRecovery',{})
        digest=hashlib.sha256(str(payload.get('code','')).strip().encode()).hexdigest()
        hashes=(pending.get('hashes',[]) if pending.get('binding')==binding and pending.get('expires',0)>now else [])
        if hashes and digest in hashes:
            state['recovery']=hashes
            state.pop('pendingRecovery',None)
        elif not state.get('recoverySaved') and digest in state.get('recovery',[]):
            pass
        else:
            failures.append(now)
            return {'ok':False,'error':'INVALID_RECOVERY_CODE'}
        state['recoverySaved']=True
        return {'ok':True}
    if action in ('register-options','authenticate-options'):
        if action == 'register-options' and active and not proof_valid(state,binding,now):
            return {'ok':False,'error':'PASSKEY_REQUIRED'}
        if action == 'register-options' and len(state['credentials']) >= 5:
            return {'ok':False,'error':'KEY_LIMIT'}
        if action == 'authenticate-options' and not active:
            return {'ok':False,'error':'NOT_ENROLLED'}
        challenge = secrets.token_bytes(32)
        descriptors = [PublicKeyCredentialDescriptor(id=decode(cid)) for cid in state['credentials']]
        if action == 'register-options':
            options = generate_registration_options(rp_id=RP_ID,rp_name='Bob',
                user_id=bytes.fromhex(payload['account']),user_name='Bob',challenge=challenge,
                exclude_credentials=descriptors,authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.PREFERRED,user_verification=UserVerificationRequirement.REQUIRED))
        else:
            options = generate_authentication_options(rp_id=RP_ID,challenge=challenge,
                allow_credentials=descriptors,user_verification=UserVerificationRequirement.REQUIRED)
        if len(state['challenges']) >= 20:
            state['challenges'].pop(next(iter(state['challenges'])))
        state['challenges'][binding]={'value':encode(challenge),'expires':now+300,'kind':action.split('-')[0]}
        return {'ok':True,'options':json.loads(options_to_json(options))}
    if action == 'recover':
        code=payload.get('code','')
        digest=hashlib.sha256(str(code).strip().encode()).hexdigest()
        codes=state.get('recovery',[])
        if not active or digest not in codes:
            failures.append(now)
            return {'ok':False,'error':'INVALID_RECOVERY_CODE'}
        codes.remove(digest)
        state['proofs'][binding]=now+TTL
        state['recent'][binding]=now+300
        state['proofKeys'][binding]='recovery'
        return {'ok':True,'validUntil':now+TTL,'recovered':True}
    if action not in ('register-verify','authenticate-verify'):
        raise ValueError('Unknown action')
    pending=state['challenges'].pop(binding,None)
    if not pending or pending['kind'] != action.split('-')[0]:
        failures.append(now)
        return {'ok':False,'error':'CHALLENGE_EXPIRED'}
    try:
        common={'credential':payload['credential'],'expected_challenge':decode(pending['value']),
                'expected_origin':ORIGIN,'expected_rp_id':RP_ID,'require_user_verification':True}
        codes=[]
        if action == 'register-verify':
            if active and not proof_valid(state,binding,now):
                raise ValueError('Second factor required')
            verified=verify_registration_response(**common)
            cid=encode(verified.credential_id)
            if cid in state['credentials']:
                raise ValueError('Duplicate credential')
            state['credentials'][cid]={'key':encode(verified.credential_public_key),'count':verified.sign_count,'name':str(payload.get('name','Passkey'))[:60]}
            if not active:
                codes=[secrets.token_hex(16) for _ in range(8)]
                state['recovery']=[hashlib.sha256(c.encode()).hexdigest() for c in codes]
                state['proofs']={}
                state['recoverySaved']=False
        else:
            cid=payload['credential']['id']
            saved=state['credentials'][cid]
            verified=verify_authentication_response(**common,credential_public_key=decode(saved['key']),
                                                   credential_current_sign_count=saved['count'])
            saved['count']=verified.new_sign_count
        state['proofs'][binding]=now+TTL
        state['recent'][binding]=now+300
        state['proofKeys'][binding]=cid
        return {'ok':True,'validUntil':now+TTL, 'recoveryCodes':codes}
    except Exception:
        failures.append(now)
        return {'ok':False,'error':'VERIFICATION_FAILED'}

def handle(conn, action, payload):
    account=payload.get('account','')
    if not isinstance(account,str) or not re.fullmatch('[a-f0-9]{64}',account):
        raise ValueError('Invalid account')
    # A missing row is the default opt-out state. Status reads never create it.
    if action == 'status':
        row=conn.execute('SELECT state FROM bob_passkeys WHERE account=%s',(account,)).fetchone()
        return transition(dict(row[0]) if row else {},action,payload)
    conn.execute('INSERT INTO bob_passkeys(account) VALUES(%s) ON CONFLICT DO NOTHING',(account,))
    row=conn.execute('SELECT state FROM bob_passkeys WHERE account=%s FOR UPDATE',(account,)).fetchone()
    state=dict(row[0])
    result=transition(state,action,payload)
    conn.execute('UPDATE bob_passkeys SET state=%s::jsonb WHERE account=%s',(json.dumps(state),account))
    return result
