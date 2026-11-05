"""Bounded encrypted cold tier for completed comparison evidence.

Retain all evaluation fields locally. Never replace open cases, unknown versions,
small payloads, or evidence before a verified remote round trip and exact CAS.
"""
import copy
import gzip
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid
import cold_metrics as codec

TAG = '_bobColdTestV1'
TABLE = 'bob_entry_exit_comparison'
# Reviewed families participate in the regular full, independently restored backup.
# New families must explicitly register before any payload replacement is allowed.
BACKUP_TABLES = frozenset((TABLE, 'bob_quality_campaign', 'bob_quality_cases',
    'bob_quality_legacy', 'bob_shadow_study_control', 'bob_shadow_study_events',
    'bob_shadow_study_cases', 'bob_cold_test_batches', 'bob_cold_test_scan'))
# Remove only original bulky detail fields; every other field stays SQL-readable.
DETAILS = frozenset(('entryQuote', 'exitQuote', 'entryKoEvidence', 'triggerBars', 'stopHistory'))
_THREAD = None
_START_LOCK = threading.Lock()
_LAST = {'status': 'not-run', 'physicalBytesFreed': None}


def projection(payload):
    result = copy.deepcopy(payload)
    for arm in result['arms'].values():
        for field in DETAILS:
            arm.pop(field, None)
    return result


def eligible(payload, now_ms):
    from paper_entry_exit_comparison import VERSION, ARMS
    return (isinstance(payload, dict) and TAG not in payload
        and payload.get('version') == VERSION and payload.get('complete') is True
        and type(payload.get('checkedAt')) in (int, float)
        and 0 <= payload['checkedAt'] <= now_ms - 86400000
        and isinstance(payload.get('arms'), dict) and set(payload['arms']) == set(ARMS)
        and all(isinstance(a, dict) and a.get('status') in ('closed', 'inconclusive', 'no-entry')
                for a in payload['arms'].values()))


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_cold_test_batches (
        batch_key TEXT PRIMARY KEY, file_id TEXT NOT NULL, sha256 TEXT NOT NULL,
        verified_at TIMESTAMPTZ NOT NULL DEFAULT now(), moved_rows INTEGER NOT NULL,
        original_json_bytes BIGINT NOT NULL, reference_json_bytes BIGINT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_cold_test_scan (
        singleton BOOLEAN PRIMARY KEY CHECK(singleton), last_id TEXT NOT NULL)''')


def resolve(conn, row_id, payload, *, drive=None, verified_rows=None):
    if not isinstance(payload, dict) or TAG not in payload:
        return payload
    try:
        ref = payload[TAG]
        if (not isinstance(ref, list) or len(ref) != 2 or type(ref[1]) is not int
                or not 0 <= ref[1] < 8 or not isinstance(ref[0], str)
                or len(ref[0]) != 32 or any(c not in '0123456789abcdef' for c in ref[0])):
            raise ValueError('Invalid reference')
        rows = verified_rows
        if rows is None:
            location = conn.execute('SELECT file_id,sha256 FROM bob_cold_test_batches WHERE batch_key=%s', (ref[0],)).fetchone()
            if not location:
                raise ValueError('Missing index')
            rows = codec.read_chunk(drive, *location, conn=conn, cached=False)
        row = rows[ref[1]]
        if row[:4] != [TABLE, row_id, True, payload.get('checkedAt')]:
            raise ValueError('Identity mismatch')
        if codec.encoded({k:v for k,v in payload.items() if k != TAG}) != codec.encoded(projection(row[4])):
            raise ValueError('Evaluation projection mismatch')
        return copy.deepcopy(row[4])
    except Exception:
        raise codec.ColdArchiveUnavailable('Original test evidence unavailable; replay incomplete') from None


def get(conn, row_id, *, drive=None):
    row = conn.execute('SELECT payload FROM bob_entry_exit_comparison WHERE id=%s', (row_id,)).fetchone()
    return resolve(conn, row_id, row[0], drive=drive) if row else None


def offload_batch(conn, drive, *, now_ms=None):
    if not conn.autocommit:
        raise ValueError('Dedicated autocommit connection required')
    now_ms = time.time()*1000 if now_ms is None else now_ms
    # Fixed identifiers, bounded row count AND per-row bytes. No full history in RAM.
    checkpoint = conn.execute('SELECT last_id FROM bob_cold_test_scan WHERE singleton=TRUE').fetchone()
    lower = checkpoint[0] if checkpoint else ''
    candidates = conn.execute('''SELECT id,payload FROM bob_entry_exit_comparison
        WHERE id>%s AND complete=TRUE AND NOT(payload ? %s)
        AND jsonb_typeof(payload->'checkedAt')='number'
        AND CASE WHEN jsonb_typeof(payload->'checkedAt')='number'
            THEN (payload->>'checkedAt')::numeric ELSE NULL END <= %s
        AND octet_length(payload::text) BETWEEN 2048 AND 131072
        ORDER BY id LIMIT 8''', (lower, TAG, now_ms-86400000)).fetchall()
    def advance_scan():
        conn.execute('''INSERT INTO bob_cold_test_scan VALUES(TRUE,%s)
            ON CONFLICT(singleton) DO UPDATE SET last_id=excluded.last_id''',
            (candidates[-1][0] if candidates else '',))
    rows = []
    key = uuid.uuid4().hex
    for row_id, payload in candidates:
        if not eligible(payload, now_ms):
            continue
        pointer = {**projection(payload), TAG: [key, len(rows)]}
        if len(codec.encoded(payload))-len(codec.encoded(pointer)) >= 1024:
            rows.append([TABLE, row_id, True, payload['checkedAt'], payload])
    if not rows:
        advance_scan()
        return {'status': 'no-eligible-rows', 'movedRows': 0, 'physicalBytesFreed': None}
    raw = codec.encoded({'format': codec.FORMAT, 'rows': rows})
    if len(raw) > codec.MAX_RAW:
        raise ValueError('Test archive raw budget exceeded')
    with tempfile.TemporaryDirectory(prefix='bob-test-cold-') as tmp:
        plain = Path(tmp)/'tests.gz'
        plain.write_bytes(gzip.compress(raw, mtime=0)); os.chmod(plain, 0o600)
        sealed = Path(tmp)/('tests-'+key+'.enc')
        from cold_chunk_encryption import seal_chunk
        checksum = seal_chunk(plain, sealed)
        if sealed.stat().st_size > codec.MAX_FILE:
            raise ValueError('Test archive encrypted budget exceeded')
        file_id = drive.upload(sealed, checksum)
    restored = codec.read_chunk(drive, file_id, checksum, cached=False)
    if codec.encoded(rows) != codec.encoded(restored):
        raise codec.ColdArchiveUnavailable('Original test download differs')
    moved = original = references = 0
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='500ms'")
        conn.execute("SET LOCAL statement_timeout='2s'")
        for index, row in enumerate(rows):
            pointer = {**projection(row[4]), TAG: [key, index]}
            updated = conn.execute('''UPDATE bob_entry_exit_comparison SET payload=%s::jsonb
                WHERE id=%s AND complete=TRUE AND payload=%s::jsonb RETURNING payload''',
                (codec.encoded(pointer).decode(), row[1], codec.encoded(row[4]).decode())).fetchone()
            if updated:
                if codec.encoded(resolve(conn, row[1], updated[0], verified_rows=restored)) != codec.encoded(row[4]):
                    raise codec.ColdArchiveUnavailable('Test read-through differs')
                moved += 1; original += len(codec.encoded(row[4])); references += len(codec.encoded(pointer))
        conn.execute('''INSERT INTO bob_cold_test_batches
            (batch_key,file_id,sha256,moved_rows,original_json_bytes,reference_json_bytes)
            VALUES(%s,%s,%s,%s,%s,%s)''', (key, file_id, checksum, moved, original, references))
        advance_scan()
    return dict(status='verified-offload', movedRows=moved, originalJsonBytes=original,
                referenceJsonBytes=references, readThroughVerified=True, physicalBytesFreed=None)


def run_once(factory=codec.connect):
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError('Dedicated autocommit connection required')
        # The completed-test family needs the same fresh independent recovery
        # AND provider-measured WAL/scratch reserve as all other cold writers.
        guard = __import__('storage_pressure').verified_writer_preflight(conn)
        if guard is not None:
            return guard
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('bob_cold_test_v1'))").fetchone()[0]:
            return {'status': 'busy', 'movedRows': 0}
        init(conn)
        return offload_batch(conn, codec.runtime_drive(conn))


def status(conn):
    result = dict(policy='completed-evidence-v1', hotHours=24, rowsPerCycle=8,
        intervalSeconds=1800, evaluationRetained=True, originalsRecoverable=True,
        unknownFamilies='backup-registration-and-tested-reader-required',
        physicalBytesFreed=None, lastCycle=dict(_LAST))
    try:
        with conn.transaction():
            r = conn.execute('''SELECT coalesce(sum(moved_rows),0),coalesce(sum(original_json_bytes-reference_json_bytes),0),max(verified_at)
                FROM bob_cold_test_batches''').fetchone()
        result.update(status='observed', offloadedRows=int(r[0]), logicalJsonBytesReduced=int(r[1]),
                      lastVerifiedAt=str(r[2]) if r[2] else None)
    except Exception:
        result['status'] = 'not-observed'
    return result


def start():
    global _THREAD
    if not os.environ.get('DATABASE_URL') or os.environ.get('BOB_COLD_TESTS_DISABLED') == '1':
        return
    with _START_LOCK:
        if _THREAD is not None:
            return
        def loop():
            global _LAST
            time.sleep(420)
            while True:
                try:
                    result = ({'status': 'archive-running'} if __import__('archive_worker').status().get('status') == 'running'
                              else run_once())
                except Exception as exc:
                    result = {'status': 'deferred', 'errorType': type(exc).__name__}
                _LAST = result
                print('BOB_COLD_TESTS '+json.dumps(result, sort_keys=True), flush=True)
                time.sleep(1800)
        _THREAD = threading.Thread(target=loop, name='bob-cold-tests', daemon=True)
        _THREAD.start()
