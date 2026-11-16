"""One read-only signal-triggered request per owner-opened handset session."""
import json
import uuid
from handset_entry_check import clock

FIELDS = ['Geld', 'Brief', 'Anzeigezeit', 'Hebel']


def candidate(planning, now):
    if planning.get('resultFresh') is not True:
        return None
    result = planning.get('result') or {}
    if result.get('configRevision') != planning.get('revision'):
        return None
    for item in result.get('items', [])[:12]:
        at = clock(item.get('modelReferenceAt'))
        if (item.get('available') is True and item.get('entrySuitable') is True
                and not item.get('reasons') and at is not None
                and 0 <= now*1000-at <= 90000):
            return item
    return None


def prepare(conn, digest, state, now):
    existing = state.get('entryRead')
    if existing:
        if existing.get('status') == 'queued':
            command = next((c for c in state.get('commands', [])
                            if c.get('requestId') == existing['requestId']), {})
            status = ('expired' if now > existing['expiresAt'] or command.get('status') == 'expired' else
                      'device-rejected' if command.get('status') == 'acknowledged' and command.get('result') != 'ENTRY_READ_STARTED' else
                      'awaiting-read-receipt' if command.get('status') == 'acknowledged' else 'queued')
            if status != 'queued':
                existing['status'] = status
                state['entryReadStatus'] = status
        elif existing.get('status') == 'awaiting-read-receipt' and now > existing['expiresAt']:
            existing['status'] = state['entryReadStatus'] = 'expired'
        return
    # Signal monitoring continues server-side while Android is locked.
    # Do not send a DEGIRO command that cannot be safely executed until the
    # owner has unlocked the same, still-valid device session.
    if (state.get('observation') or {}).get('code') == 'WAITING_FOR_UNLOCK':
        state['entryReadStatus'] = 'WAITING_FOR_UNLOCK'
        return
    # Ordinary reader/settings sessions cannot opt in remotely.
    if (state.get('purpose') != 'entry_read' or not state.get('active')
            or state.get('expiresAt', 0)-now < 60 or state.get('entryRead')
            or now-state.get('entryCheckAt', 0) < 30):
        return
    state['entryCheckAt'] = now
    from handset_planning import read
    from android_remote import enqueue, valid_isin
    planning = read(conn)
    item = candidate(planning, now)
    if item is None or not valid_isin(item.get('isin')):
        state['entryReadStatus'] = 'WAITING_FOR_SIGNAL'
        return
    result = planning['result']
    row = conn.execute("""SELECT batch_id, parsed_items, payload->'images'->-1->>'at'
        FROM bob_android_list_images WHERE token_hash=%s
        AND import_receipt->>'stage'='synced' AND created_at<=now()
        AND created_at>now()-interval '14 hours'
        ORDER BY created_at DESC LIMIT 1""", (digest,)).fetchone()
    if (not row or row[2] != result.get('listUploadedAt')
            or not any(p.get('isin') == item['isin'] and
                       not p.get('listRow', {}).get('excluded') for p in (row[1] or []))):
        state['entryReadStatus'] = 'OWNED_CURRENT_LIST_REQUIRED'
        return
    request = dict(action='entry_read', sessionId=state['sessionId'],
                   requestId=uuid.uuid4().hex, isin=item['isin'],
                   listBatchId=row[0], listUploadedAt=row[2])
    queued = enqueue(state, request, now)
    if queued.get('status') != 'queued':
        state['entryReadStatus'] = 'READER_BUSY'
        return
    state['entryRead'] = dict(requestId=request['requestId'], isin=item['isin'],
        listBatchId=row[0], createdAt=now, expiresAt=min(now+180, state['expiresAt']),
        configRevision=planning['revision'], contextFingerprint=planning.get('contextFingerprint'),
        modelReferenceAt=item['modelReferenceAt'], status='queued',
        entryApproved=False, brokerExecutionVerified=False)
    state['entryReadStatus'] = 'REQUEST_QUEUED'


def receipt(conn, digest, batch, run, now):
    row = conn.execute('SELECT state FROM bob_android_remote WHERE token_hash=%s FOR UPDATE',
                       (digest,)).fetchone()
    state = (row[0] or {}) if row else {}
    request = state.get('entryRead') or {}
    if run.get('batchId') != request.get('requestId'):
        return
    if (batch != request['listBatchId'] or run.get('isins') != [request['isin']]
            or run.get('requestedFields') != {request['isin']: FIELDS}):
        raise ValueError('Entry read response identity mismatch')
    # Original observations are stored by the normal importer first. A partial
    # receipt can later become complete, but old/future captures never confirm it.
    rows = conn.execute('SELECT payload FROM bob_android_read_runs WHERE batch_id=%s',
                        (request['requestId']+':'+str(run.get('revision')),)).fetchone()
    saved = rows[0] if rows else {}
    observations = saved.get('results', [])
    observed = observations[0] if len(observations) == 1 else {}
    at = clock((observed.get('observation') or {}).get('observedAt'))
    current = __import__('handset_planning').read(conn)
    current_item = candidate(current, now)
    same = (current.get('revision') == request['configRevision']
            and current.get('contextFingerprint') == request['contextFingerprint']
            and current_item is not None and current_item.get('isin') == request['isin']
            and current_item.get('modelReferenceAt') == request['modelReferenceAt'])
    status = ('expired' if now > request['expiresAt'] else
              'signal-or-settings-changed' if not same else
              'capture-time-invalid' if at is None or not request['createdAt']*1000 <= at <= now*1000 else
              'read-received-source-time-unverified' if observed.get('code') == 'COMPLETE' else
              'read-incomplete')
    request.update(status=status, receivedAt=now, entryApproved=False,
                   brokerExecutionVerified=False)
    state['entryReadStatus'] = status
    conn.execute('UPDATE bob_android_remote SET state=%s::jsonb WHERE token_hash=%s',
                 (json.dumps(state), digest))
