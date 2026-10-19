"""Isolated test state; no real account, database or production requests."""
import json
import sys
import bob_passkey_store as store
state = {}
now = 2000000000
for line in sys.stdin:
    try:
        request = json.loads(line)
        if request['action'] == '_advance':
            now += request['seconds']
            result = {'ok': True}
        else:
            result = store.transition(state, request['action'], {
                'account': 'a' * 64,
                'binding': request['binding'],
                **request.get('payload', {})}, now)
        print(json.dumps(result), flush=True)
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': type(exc).__name__}), flush=True)
