"""Explicitly paired, write-only phone diagnostics. No screen or account content."""
import hashlib
import json
import re
from datetime import datetime, timezone
from android_observations import CODES, timestamp

PIN_RESULTS = {'NO_WINDOW', 'NO_INPUT', 'INPUT_PRESENT', 'NUMERIC_PASSWORD_INPUT',
               'SET_TEXT_OFFERED', 'SENSITIVE_INPUT', 'INCOMPLETE',
               'KEYPAD_VISIBLE', 'KEYPAD_CLICK_OFFERED', 'KEYPAD_AMBIGUOUS',
               'LOGIN_SETUP_VISIBLE', 'LOGIN_DELETE_OFFERED', 'LOGIN_RESET_UNCONFIRMED',
               'LOGIN_DELETE_AMBIGUOUS', 'LOGIN_DELETE_SHARED_TARGET', 'LOGIN_DELETE_NO_ACTION',
               'LOGIN_DELETE_DISABLED', 'LOGIN_DELETE_LABEL_UNRECOGNIZED',
               'SYMBOL_LAYOUT_UNCONFIRMED', 'SYMBOL_NODE_UNAVAILABLE', 'SYMBOL_NODES_MULTIPLE', 'SYMBOL_NO_ACTION', 'SYMBOL_LABELLED_ACTION', 'SYMBOL_UNLABELLED_ACTION',
               'SYMBOL_DISABLED', 'SYMBOL_PARENT_ACTION_OBSERVED', 'SYMBOL_CLICK_FLAG_ONLY', 'SYMBOL_ACTION_ONLY', 'SYMBOL_LABELLED_PASSIVE', 'SYMBOL_UNLABELLED_PASSIVE'}

PIN_RESULTS.update({'KEYPAD_TEST_DELETE_REJECTED', 'KEYPAD_TEST_WAITING', 'KEYPAD_TEST_NO_STATE_CHANGE', 'KEYPAD_TEST_STATE_CYCLE_OBSERVED', 'KEYPAD_TEST_INTERRUPTED', 'KEYPAD_TEST_DIGIT_SENT', 'KEYPAD_TEST_DELETE_SENT', 'KEYPAD_TEST_DIGIT_REJECTED', 'KEYPAD_TEST_TIMEOUT'})

PIN_SYMBOL_FLAGS = {'enabled', 'labelled', 'clickableFlag', 'clickAction', 'nearbyParentAction'}

def validate_pin_symbol_flags(value, result):
    if not isinstance(value, dict) or set(value) != PIN_SYMBOL_FLAGS or any(type(v) is not bool for v in value.values()):
        raise ValueError('Invalid PIN symbol flags')
    if not value['enabled']:
        expected = 'SYMBOL_DISABLED'
    elif value['clickableFlag'] and value['clickAction']:
        expected = 'SYMBOL_LABELLED_ACTION' if value['labelled'] else 'SYMBOL_UNLABELLED_ACTION'
    elif value['nearbyParentAction']:
        expected = 'SYMBOL_PARENT_ACTION_OBSERVED'
    elif value['clickableFlag']:
        expected = 'SYMBOL_CLICK_FLAG_ONLY'
    elif value['clickAction']:
        expected = 'SYMBOL_ACTION_ONLY'
    else:
        expected = 'SYMBOL_LABELLED_PASSIVE' if value['labelled'] else 'SYMBOL_UNLABELLED_PASSIVE'
    if result != expected:
        raise ValueError('Inconsistent PIN symbol result')

PIN_EXERCISE_STAGES = ['DELETE_ACCEPTED', 'DELETE_REQUESTED', 'DIGIT_ACCEPTED', 'DIGIT_REQUESTED', 'WAITING']
PIN_EXERCISE_REASONS = ['ACCESS_DISABLED', 'DELETE_REJECTED', 'DELETE_TOUCH_CANCELLED', 'DIGIT_REJECTED', 'DIGIT_TOUCH_CANCELLED', 'EXCEPTION', 'NONE', 'ROOT_HIDDEN', 'ROOT_MISSING', 'ROOT_PACKAGE', 'ROOT_PROTECTED', 'ROOT_WINDOW', 'SCREEN_LOCKED', 'SERVICE_STOPPED', 'STATE_CYCLE', 'STATE_TIMEOUT', 'STOPPED', 'TARGET_ACTION_UNAVAILABLE', 'TARGET_BOUNDS_CHANGED', 'TARGET_CLASS_CHANGED', 'TARGET_HIDDEN', 'TARGET_ID_CHANGED', 'TARGET_MISSING', 'TARGET_PACKAGE', 'TARGET_PROTECTED', 'TARGET_REFRESH_FAILED', 'TARGET_WINDOW', 'TIMEOUT', 'USER_TOUCH', 'WINDOW_EVENT']

def validate_pin_exercise_trace(value, result):
    if not isinstance(value, dict) or set(value) != {'stage', 'reason'}:
        raise ValueError('Invalid exercise trace fields')
    stage, reason = value['stage'], value['reason']
    if not isinstance(stage, str) or stage not in PIN_EXERCISE_STAGES or not isinstance(reason, str) or reason not in PIN_EXERCISE_REASONS:
        raise ValueError('Invalid exercise trace values')
    if reason == 'DIGIT_TOUCH_CANCELLED' and (result != 'KEYPAD_TEST_INTERRUPTED' or stage != 'DIGIT_ACCEPTED'):
        raise ValueError('Inconsistent touch cancellation')
    if reason == 'DELETE_TOUCH_CANCELLED' and (result != 'KEYPAD_TEST_INTERRUPTED' or stage != 'DELETE_ACCEPTED'):
        raise ValueError('Inconsistent delete touch cancellation')
    if not result.startswith('KEYPAD_TEST_'):
        raise ValueError('Exercise trace on unrelated result')
    expected = {
        'KEYPAD_TEST_STATE_CYCLE_OBSERVED': ('DELETE_ACCEPTED', 'STATE_CYCLE'),
        'KEYPAD_TEST_DIGIT_REJECTED': ('DIGIT_REQUESTED', 'DIGIT_REJECTED'),
        'KEYPAD_TEST_DELETE_REJECTED': ('DELETE_REQUESTED', 'DELETE_REJECTED'),
    }
    if result in expected and (stage, reason) != expected[result]:
        raise ValueError('Inconsistent exercise result')
    terminal = {'STATE_CYCLE': 'KEYPAD_TEST_STATE_CYCLE_OBSERVED', 'DIGIT_REJECTED': 'KEYPAD_TEST_DIGIT_REJECTED',
                'DELETE_REJECTED': 'KEYPAD_TEST_DELETE_REJECTED', 'TIMEOUT': 'KEYPAD_TEST_TIMEOUT',
                'STATE_TIMEOUT': 'KEYPAD_TEST_NO_STATE_CHANGE'}
    if reason in terminal and result != terminal[reason]:
        raise ValueError('Inconsistent exercise reason')

def validate_pin_probe(value, now):
    required = {'runId', 'endedAt', 'result', 'completed'}
    if not isinstance(value, dict) or set(value) not in (required, required | {'symbolFlags'}, required | {'exerciseTrace'}):
        raise ValueError('Invalid PIN probe fields')
    if not isinstance(value['runId'], str) or not re.fullmatch('[a-f0-9]{32}', value['runId']):
        raise ValueError('Invalid PIN probe ID')
    if not isinstance(value['result'], str) or value['result'] not in PIN_RESULTS:
        raise ValueError('Invalid PIN probe result')
    if type(value['completed']) is not bool:
        raise ValueError('Invalid PIN probe state')
    at = timestamp(value['endedAt'])
    if not -60 <= (now-at).total_seconds() <= 86400:
        raise ValueError('Expired PIN probe')
    if 'symbolFlags' in value:
        validate_pin_symbol_flags(value['symbolFlags'], value['result'])
    if 'exerciseTrace' in value:
        validate_pin_exercise_trace(value['exerciseTrace'], value['result'])
    return dict(value)

BOOLS=('serviceEnabled','serviceConnectedInProcess','textAccess','windowAccess','running','pendingRun')

def validate_report(value, now=None):
    now=now or datetime.now(timezone.utc)
    expected={'reportId','observedAt','appVersionCode','lastCode','lastEventAt',*BOOLS}
    if not isinstance(value,dict) or set(value) not in (expected, expected | {'pinProbe'}): raise ValueError('Invalid diagnostic fields')
    if not isinstance(value['reportId'],str) or not re.fullmatch('[a-f0-9]{32}',value['reportId']):raise ValueError('Invalid report ID')
    version=value['appVersionCode']
    if type(version) is not int or not 1<=version<=2100000000:raise ValueError('Invalid version')
    if any(type(value[k]) is not bool for k in BOOLS):raise ValueError('Invalid state')
    at=timestamp(value['observedAt'])
    if not -60<=(now-at).total_seconds()<=86400:raise ValueError('Expired diagnostic')
    if not isinstance(value['lastCode'],str) or value['lastCode'] not in CODES|{'NONE','OTHER'}:raise ValueError('Invalid code')
    if value['lastEventAt'] is not None:
        event=timestamp(value['lastEventAt'])
        if event.year<2020 or (now-event).total_seconds() < -60:raise ValueError('Invalid event time')
    if 'pinProbe' in value:
        validate_pin_probe(value['pinProbe'], now)
    return dict(value)

def token_hash(token):
    if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{64}',token):raise PermissionError('Invalid device credential')
    return hashlib.sha256(token.encode()).hexdigest()

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_android_diagnostic_devices (
        token_hash TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '90 days',
        revoked BOOLEAN NOT NULL DEFAULT false, received_at TIMESTAMPTZ, payload JSONB)''')

def handle(conn, payload):
    if not isinstance(payload,dict):raise ValueError('Invalid request')
    action=payload.get('action')
    if action=='register':
        digest=payload.get('tokenHash')
        if set(payload)!={'action','tokenHash'} or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid pairing')
        # Bounded registrations; explicit re-registration never un-revokes a key.
        conn.execute('LOCK TABLE bob_android_diagnostic_devices IN EXCLUSIVE MODE')
        conn.execute("DELETE FROM bob_android_diagnostic_devices WHERE revoked OR expires_at<now()")
        prior=conn.execute('SELECT revoked FROM bob_android_diagnostic_devices WHERE token_hash=%s',(digest,)).fetchone()
        if prior:
            if prior[0]:raise PermissionError('Revoked pairing')
        else:
            if conn.execute('SELECT count(*) FROM bob_android_diagnostic_devices').fetchone()[0]>=20:raise ValueError('Pairing limit')
            conn.execute('INSERT INTO bob_android_diagnostic_devices(token_hash) VALUES(%s)',(digest,))
        return {'ok':True,'paired':True,'expiresDays':90}
    if action=='revokeAll':
        if set(payload)!={'action'}:raise ValueError('Invalid revoke')
        conn.execute('UPDATE bob_android_diagnostic_devices SET revoked=true,payload=NULL')
        return {'ok':True,'revoked':True}
    if action!='report' or set(payload)!={'action','token','report'}:raise ValueError('Invalid operation')
    digest=token_hash(payload['token'])
    # Validate authentication before parsing any report. Device tokens cannot register/read.
    device=conn.execute('SELECT token_hash FROM bob_android_diagnostic_devices WHERE token_hash=%s AND NOT revoked AND expires_at>now() FOR UPDATE', (digest,)).fetchone()
    if not device:raise PermissionError('Device not paired or revoked')
    report=validate_report(payload['report'])
    # Keep the latest observation; delayed retries cannot replace newer snapshots.
    conn.execute('''UPDATE bob_android_diagnostic_devices SET payload=%s::jsonb,received_at=now()
        WHERE token_hash=%s AND NOT revoked AND expires_at>now()
        AND (payload IS NULL OR (payload->>'observedAt')::timestamptz<=%s::timestamptz)''',
        (json.dumps(report),digest,report['observedAt']))
    return {'ok':True,'saved':True,'reportId':report['reportId']}

def status(conn):
    rows=conn.execute('''SELECT token_hash,revoked,expires_at,received_at,payload
        FROM bob_android_diagnostic_devices ORDER BY created_at DESC LIMIT 20''').fetchall()
    now=datetime.now(timezone.utc)
    return {'status':'observed' if rows else 'not-paired','readOnly':True,'remoteControl':False,
        'listImports':__import__('android_list').status(conn),
        'devices':[{'deviceId':r[0][:12],'revoked':r[1],'expiresAt':r[2].isoformat(),
          'receivedAt':r[3].isoformat() if r[3] else None,
          'fresh':bool(not r[1] and r[2]>now and r[3] and (now-r[3]).total_seconds()<1800 and r[4] and -60<=(now-timestamp(r[4]['observedAt'])).total_seconds()<1800),
          'report':r[4]} for r in rows]}


