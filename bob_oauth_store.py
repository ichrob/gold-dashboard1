"""Single-account OAuth authorization-code/PKCE state, behind internal RPC only.

Opaque credentials are stored as SHA-256 digests. The transaction lock makes
code consumption and refresh rotation atomic across processes and deployments.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time

ORIGIN = 'https://bob-private-scanner.onrender.com'
RESOURCE = ORIGIN + '/mcp'
SCOPE = 'bob:products:read'
DIAGNOSTICS_SCOPE = 'bob:diagnostics:read'
PUSH_TEST_SCOPE = 'bob:push:test'
HANDY_SCOPE = 'bob:handy:control'

def valid_scope(value):
    return isinstance(value, str) and bool(value.split()) and set(value.split()) <= {SCOPE, DIAGNOSTICS_SCOPE, PUSH_TEST_SCOPE, HANDY_SCOPE}

REDIRECT = 'https://chatgpt.com/connector_platform_oauth_redirect'
ACCESS_TTL = 3600
GRANT_TTL = 28 * 86400


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def secret(prefix=''):
    return prefix + secrets.token_urlsafe(32)


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


def init(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS bob_oauth (account TEXT PRIMARY KEY, state JSONB NOT NULL DEFAULT '{}'::jsonb)")


def transition(state, action, p, now=None):
    now = time.time() if now is None else now
    for kind in ('clients', 'pending', 'codes', 'grants', 'access', 'refresh'):
        state.setdefault(kind, {})
    for kind in ('pending', 'codes', 'grants', 'access', 'refresh'):
        state[kind] = {k:v for k,v in state[kind].items() if v['expires'] > now}
    clients, pending, codes, grants, access, refresh = (state[k] for k in ('clients','pending','codes','grants','access','refresh'))

    def error(code='invalid_request'):
        return {'error':code}

    def mint(gid):
        grant = grants[gid]
        # Keep storage bounded even if a malicious client refreshes continuously.
        if len(refresh) >= 2048:
            return error('temporarily_unavailable')
        at, rt = secret('boa_'), secret('bor_')
        expires = min(now + ACCESS_TTL, grant['expires'])
        access[digest(at)] = {'grant':gid, 'expires':expires}
        refresh[digest(rt)] = {'grant':gid, 'expires':grant['expires'], 'used':False}
        return {'access_token':at, 'refresh_token':rt, 'token_type':'Bearer',
                'expires_in':int(expires-now), 'scope':grant.get('scope', SCOPE)}

    if action == 'register':
        if (p.get('redirect_uris') != [REDIRECT] or p.get('token_endpoint_auth_method','none') != 'none'
                or set(p.get('grant_types',['authorization_code','refresh_token'])) != {'authorization_code','refresh_token'}
                or p.get('response_types',['code']) != ['code'] or not valid_scope(p.get('scope',SCOPE))):
            return error('invalid_client_metadata')
        # This private, single-user server permits exactly one public client
        # configuration. Reuse its public ID; registration cannot exhaust state.
        cid = next(iter(clients), None) or secret('bob_')
        clients[cid] = {'redirect_uri':REDIRECT}
        return {'client_id':cid, 'client_id_issued_at':int(now), 'redirect_uris':[REDIRECT],
                'grant_types':['authorization_code','refresh_token'], 'response_types':['code'],
                'token_endpoint_auth_method':'none', 'scope':p.get('scope', SCOPE), 'client_name':'Bob Lesezugang'}
    if action == 'begin':
        cid = p.get('client_id','')
        if cid not in clients or p.get('redirect_uri') != clients[cid]['redirect_uri']:
            return error('invalid_client')
        if (p.get('response_type') != 'code' or not valid_scope(p.get('scope', SCOPE))
                or p.get('resource') != RESOURCE or p.get('code_challenge_method') != 'S256'
                or not re.fullmatch('[A-Za-z0-9_-]{43}', p.get('code_challenge',''))
                or not 1 <= len(p.get('state','')) <= 1024):
            return error()
        if len(pending) >= 128:
            return error('temporarily_unavailable')
        nonce = secret()
        pending[digest(nonce)] = {k:p[k] for k in ('client_id','redirect_uri','state','code_challenge')}
        pending[digest(nonce)]['expires'] = now + 900
        pending[digest(nonce)]['scope'] = p.get('scope', SCOPE)
        return {'request':nonce}
    if action in ('pending', 'approve', 'deny'):
        key = digest(p.get('request',''))
        req = pending.get(key)
        if not req:
            return error('invalid_request')
        if action == 'pending':
            return {'ok':True, 'scope':req.get('scope', SCOPE)}
        pending.pop(key)
        response = {'redirect_uri':req['redirect_uri'], 'state':req['state'], 'iss':ORIGIN}
        if action == 'deny':
            return {**response, 'error':'access_denied'}
        until = min(float(p.get('until',0)), now + GRANT_TTL)
        if until <= now or len(grants) >= 32:
            return {**response, 'error':'access_denied'}
        gid, code = secret(), secret('boc_')
        grants[gid] = {'client_id':req['client_id'], 'expires':until, 'created':now, 'scope':req.get('scope', SCOPE)}
        codes[digest(code)] = {**req, 'grant':gid, 'used':False, 'expires':now+120}
        return {**response, 'code':code}
    if action == 'token':
        cid = p.get('client_id','')
        if cid not in clients:
            return error('invalid_client')
        if p.get('resource') != RESOURCE or not valid_scope(p.get('scope',SCOPE)):
            return error('invalid_target')
        if p.get('grant_type') == 'authorization_code':
            record = codes.get(digest(p.get('code','')))
            verifier = p.get('code_verifier','')
            if (not record or record['client_id'] != cid or p.get('redirect_uri') != record['redirect_uri']
                    or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier)
                    or not hmac.compare_digest(challenge(verifier),record['code_challenge'])):
                return error('invalid_grant')
            if 'scope' in p and set(p['scope'].split()) != set(grants.get(record['grant'], {}).get('scope', SCOPE).split()):
                return error('invalid_scope')
            if record['used']:
                grants.pop(record['grant'],None)
                return error('invalid_grant')
            record['used'] = True
        elif p.get('grant_type') == 'refresh_token':
            record = refresh.get(digest(p.get('refresh_token','')))
            grant = grants.get(record['grant']) if record else None
            if not grant or grant['client_id'] != cid:
                return error('invalid_grant')
            if 'scope' in p and set(p['scope'].split()) != set(grants.get(record['grant'], {}).get('scope', SCOPE).split()):
                return error('invalid_scope')
            if record['used']:
                grants.pop(record['grant'],None)
                return error('invalid_grant')
            record['used'] = True
        else:
            return error('unsupported_grant_type')
        if record['grant'] not in grants:
            return error('invalid_grant')
        return mint(record['grant'])
    if action == 'check':
        record = access.get(digest(p.get('token','')))
        grant = grants.get(record['grant']) if record else None
        return {'valid':bool(grant), 'scope':grant.get('scope', SCOPE) if grant else None, 'resource':RESOURCE if grant else None}
    if action == 'revoke':
        record = access.get(digest(p.get('token',''))) or refresh.get(digest(p.get('token','')))
        grant = grants.get(record['grant']) if record else None
        if grant and grant['client_id'] == p.get('client_id'):
            grants.pop(record['grant'],None)
        return {}
    if action == 'list':
        return {'grants':[{'id':k,'created':v['created'],'expires':v['expires']} for k,v in grants.items()]}
    if action == 'revoke-all':
        for kind in ('grants','access','refresh','codes','pending'):
            state[kind] = {}
        return {'ok':True}
    raise ValueError('Unknown OAuth operation')


def handle(conn, action, payload):
    account = payload.get('account','')
    if not isinstance(account,str) or not re.fullmatch('[a-f0-9]{64}',account):
        raise ValueError('Invalid account')
    if action in ('check','pending','list'):
        row = conn.execute('SELECT state FROM bob_oauth WHERE account=%s',(account,)).fetchone()
        return transition(dict(row[0]) if row else {}, action, payload)
    conn.execute('INSERT INTO bob_oauth(account) VALUES(%s) ON CONFLICT DO NOTHING',(account,))
    row = conn.execute('SELECT state FROM bob_oauth WHERE account=%s FOR UPDATE',(account,)).fetchone()
    state = dict(row[0])
    result = transition(state, action, payload)
    conn.execute('UPDATE bob_oauth SET state=%s::jsonb WHERE account=%s',(json.dumps(state),account))
    return result
