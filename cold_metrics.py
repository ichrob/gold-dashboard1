"""Lossless, verified Drive payload tier for immutable metric checks.

Primary keys and clocks stay in PostgreSQL. Readers resolve exact JSON values;
an unavailable/corrupt archive is an error, never an empty historical result.
"""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid
from collections import OrderedDict

TAG = '_bobColdMetricV1'
FORMAT = 'bob-cold-metrics-v1'
MAX_RAW = 2 * 1024 * 1024
MAX_FILE = MAX_RAW + 65536
MAX_ROWS = 500
MIN_AGE_MS = 86400000  # Keep the latest full day hot; clocks/keys always remain.
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_THREAD = None
_START_LOCK = threading.Lock()


class ColdArchiveUnavailable(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_cold_metric_batches (
        file_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
        verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        moved_rows INTEGER NOT NULL, original_json_bytes BIGINT NOT NULL,
        reference_json_bytes BIGINT NOT NULL)''')


def runtime_drive(conn):
    import archive_runtime
    from drive_evidence_archive import GoogleDrive
    state = archive_runtime.load(conn)
    return GoogleDrive(info=archive_runtime.credentials(conn), folder_id=state.get('folderId', ''),
                       parent_id=os.environ.get('BOB_ARCHIVE_PARENT_FOLDER_ID', ''))


def read_chunk(drive, file_id, checksum, *, cached=True, conn=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', file_id) or not re.fullmatch(r'[a-f0-9]{64}', checksum):
        raise ColdArchiveUnavailable('Invalid archive reference')
    key = (file_id, checksum)
    if cached:
        with _CACHE_LOCK:
            if key in _CACHE:
                _CACHE.move_to_end(key)
                return _CACHE[key]
    try:
        if drive is None:
            drive = runtime_drive(conn)
        with tempfile.TemporaryDirectory(prefix='bob-cold-read-') as tmp:
            path = Path(tmp) / 'chunk.gz'
            drive.download(file_id, path, max_bytes=MAX_FILE)
            blob = path.read_bytes()
            if len(blob) > MAX_FILE or digest(blob) != checksum:
                raise ValueError('Archive checksum mismatch')
            with gzip.open(path, 'rb') as stream:
                raw = stream.read(MAX_RAW + 1)
            if len(raw) > MAX_RAW:
                raise ValueError('Archive expansion limit')
            result = json.loads(raw)
            rows = result.get('rows')
            if result.get('format') != FORMAT or not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
                raise ValueError('Archive shape mismatch')
            if any(not isinstance(row, list) or len(row) != 5 or not isinstance(row[4], dict)
                   or TAG in row[4] for row in rows):
                raise ValueError('Archive row mismatch')
    except Exception:
        raise ColdArchiveUnavailable('Historical metric archive could not be verified') from None
    if cached:
        with _CACHE_LOCK:
            _CACHE[key] = rows
            # At most four bounded chunks per process, including report reads.
            while len(_CACHE) > 4:
                _CACHE.popitem(last=False)
    return rows


def resolve(conn, payload, scope=None, *, drive=None, verified_rows=None):
    if not isinstance(payload, dict) or TAG not in payload:
        return payload
    try:
        if set(payload) != {TAG}:
            raise ValueError('Mixed payload')
        ref = payload[TAG]
        if not isinstance(ref, dict) or type(ref.get('index')) is not int or not 0 <= ref['index'] < MAX_ROWS:
            raise ValueError('Invalid row index')
        rows = verified_rows if verified_rows is not None else read_chunk(drive, ref['file'], ref['sha256'], conn=conn)
        row = rows[ref['index']]
        if (digest(encoded(row)) != ref['rowSha256'] or
                (scope is not None and row[1] != scope)):
            raise ValueError('Original row mismatch')
        return copy.deepcopy(row[4])
    except Exception:
        raise ColdArchiveUnavailable('Historical metric payload unavailable; report is incomplete') from None


def get(conn, version, scope, bar_at):
    """Exact historical lookup, including checks outside the 30-day report."""
    row = conn.execute('''SELECT payload FROM bob_metric_checks
        WHERE version=%s AND scope=%s AND bar_at=%s''', (version, scope, bar_at)).fetchone()
    return resolve(conn, row[0], scope) if row else None


def offload_batch(conn, drive, now=None):
    """Upload/read back first, then atomically replace unchanged payloads only.

    Caller holds a session advisory lock on a dedicated autocommit connection.
    No SQL transaction stays open during Drive I/O. Failure leaves originals.
    """
    if not conn.autocommit:
        raise ValueError('Dedicated autocommit connection required')
    now = int(time.time() * 1000) if now is None else now
    candidates = conn.execute('''SELECT version,scope,bar_at,checked_at,payload
        FROM bob_metric_checks WHERE checked_at<%s AND NOT (payload ? %s)
        AND pg_column_size(payload)>512
        AND octet_length(payload::text)<65536
        ORDER BY checked_at,version,scope,bar_at LIMIT %s''', (now-MIN_AGE_MS, TAG, MAX_ROWS)).fetchall()
    rows = []
    for candidate in candidates:
        trial = rows + [list(candidate)]
        if len(encoded({'format': FORMAT, 'rows': trial})) > MAX_RAW:
            break
        rows = trial
    if not rows:
        return {'status': 'no-eligible-rows', 'movedRows': 0}
    raw = encoded({'format': FORMAT, 'rows': rows})
    with tempfile.TemporaryDirectory(prefix='bob-cold-write-') as tmp:
        path = Path(tmp) / ('bob-cold-metrics-' + uuid.uuid4().hex + '.json.gz')
        blob = gzip.compress(raw, mtime=0)
        if len(blob) > MAX_FILE:
            raise ValueError('Compressed archive limit')
        path.write_bytes(blob)
        os.chmod(path, 0o600)
        checksum = digest(blob)
        file_id = drive.upload(path, checksum)
    restored = read_chunk(drive, file_id, checksum, cached=False)
    if encoded(restored) != encoded(rows):
        raise ColdArchiveUnavailable('Remote original values differ')
    moved = original_bytes = reference_bytes = 0
    with conn.transaction():
        for index, row in enumerate(rows):
            pointer = {TAG: {'file': file_id, 'sha256': checksum, 'index': index,
                             'rowSha256': digest(encoded(row))}}
            # Keep keys/clocks and duplicate-suppression semantics. Concurrent
            # edits cannot be lost: the original JSON value is part of the CAS.
            updated = conn.execute('''UPDATE bob_metric_checks SET payload=%s::jsonb
                WHERE version=%s AND scope=%s AND bar_at=%s AND checked_at=%s
                AND payload=%s::jsonb RETURNING payload''',
                (encoded(pointer).decode(), *row[:4], encoded(row[4]).decode())).fetchone()
            if updated:
                # Resolve through the same path used by reports, before commit.
                if encoded(resolve(conn, updated[0], row[1], verified_rows=restored)) != encoded(row[4]):
                    raise ColdArchiveUnavailable('Read-through comparison failed')
                moved += 1
                original_bytes += len(encoded(row[4]))
                reference_bytes += len(encoded(pointer))
        conn.execute('''INSERT INTO bob_cold_metric_batches
            (file_id,sha256,moved_rows,original_json_bytes,reference_json_bytes)
            VALUES(%s,%s,%s,%s,%s)''', (file_id, checksum, moved, original_bytes, reference_bytes))
    return {'status': 'verified-offload', 'movedRows': moved,
            'originalJsonBytes': original_bytes, 'referenceJsonBytes': reference_bytes,
            'diskBytesFreed': None, 'readThroughVerified': True}


def connect():
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, connect_timeout=10,
        application_name='bob_cold_metrics', options='-c statement_timeout=10000 -c lock_timeout=1000')


def run_once(factory=connect):
    with factory() as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('bob_cold_metrics_v1'))").fetchone()[0]:
            return {'status': 'busy'}
        init(conn)
        drive = runtime_drive(conn)
        results = []
        for _ in range(8):
            result = offload_batch(conn, drive)
            results.append(result)
            if not result.get('movedRows'):
                break
        return {'status': 'checked', 'batches': results}


def status(conn):
    try:
        with conn.transaction():
            row = conn.execute('''SELECT count(*),coalesce(sum(moved_rows),0),
                coalesce(sum(original_json_bytes),0),coalesce(sum(reference_json_bytes),0),
                max(verified_at) FROM bob_cold_metric_batches''').fetchone()
        return {'status': 'observed', 'verifiedBatches': int(row[0]), 'offloadedRows': int(row[1]),
                'originalJsonBytes': int(row[2]), 'referenceJsonBytes': int(row[3]),
                'lastVerifiedAt': str(row[4]) if row[4] else None,
                'diskBytesFreed': None, 'historicalKeysRetained': True}
    except Exception:
        return {'status': 'not-observed', 'diskBytesFreed': None}


def start():
    global _THREAD
    if os.environ.get('BOB_COLD_METRIC_ENABLED') != '1':
        return
    with _START_LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(240)
            while True:
                try:
                    if __import__('archive_worker').status().get('status') == 'running':
                        result = {'status': 'archive-running'}
                    else:
                        result = run_once()
                        if any(batch.get('movedRows', 0) for batch in result.get('batches', [])):
                            # The offload connection has closed/committed before
                            # normal maintenance makes old tuple space reusable.
                            result['maintenance'] = __import__('storage_maintenance').run_once()
                except Exception as exc:
                    result = {'status': 'deferred', 'errorType': type(exc).__name__}
                print('BOB_COLD_METRICS ' + json.dumps(result, sort_keys=True), flush=True)
                time.sleep(60 if result.get('status') == 'archive-running' else 3600)
        _THREAD = threading.Thread(target=loop, name='bob-cold-metrics', daemon=True)
        _THREAD.start()
