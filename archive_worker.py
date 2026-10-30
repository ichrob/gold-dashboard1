"""Opt-in internal archive runner. No public endpoint, extra service or deletion."""
import json
import os
import threading
import time
from datetime import datetime, timezone

_LOCK = threading.Lock()
_THREAD = None
_STATE = {'status': 'disabled', 'evidenceDeleted': False}
_REQUIRED = ('DATABASE_URL', 'BOB_ARCHIVE_DRIVE_FOLDER_ID',
             'BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON')


def readiness():
    if os.environ.get('BOB_ARCHIVE_ENABLED') != '1':
        return dict(status='disabled', evidenceDeleted=False)
    missing = [key for key in _REQUIRED if not os.environ.get(key)]
    return dict(status='blocked' if missing else 'ready', missingConfiguration=missing,
                evidenceDeleted=False, restoreIsolation='session-temporary-tables',
                additionalPaidServices=False)


def status():
    return {**readiness(), **_STATE} if _THREAD else readiness()


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_archive_runs (
        day DATE PRIMARY KEY, status TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        receipt JSONB NOT NULL DEFAULT '{}'::jsonb)''')


def cycle(db, runner=None):
    """One claim per UTC day, across processes/restarts. No ambiguous retries.

    Failed/interrupted attempts remain visible and are not automatically repeated
    that day. Claim and final receipt are tiny operational metadata, never evidence.
    """
    global _STATE
    _STATE = readiness()
    if _STATE['status'] != 'ready' or not _LOCK.acquire(blocking=False):
        return _STATE
    try:
        day = datetime.now(timezone.utc).date()
        with db() as conn:
            claimed = conn.execute('''INSERT INTO bob_archive_runs(day,status)
                VALUES(%s,'running') ON CONFLICT DO NOTHING RETURNING day''', (day,)).fetchone()
        if not claimed:
            _STATE = dict(status='already-attempted-today', evidenceDeleted=False)
            return _STATE
        try:
            if runner is None:
                from drive_evidence_archive import run, GoogleDrive
                def runner():
                    # Existing internal DATABASE_URL; restore only in pg_temp.
                    dsn = os.environ['DATABASE_URL']
                    return run(dsn, dsn, os.environ.get('BOB_ARCHIVE_WORK_DIRECTORY', '/tmp/bob-archive'),
                               GoogleDrive(), temporary_session=True)
            result = runner()
            if not (result.get('restoreVerified') is True and
                    result.get('remoteDownloadVerified') is True and
                    result.get('deletionPermitted') is False and result.get('receiptFileId')):
                raise ValueError('Verified remote receipt required')
            _STATE = dict(status='verified', receipt=result, evidenceDeleted=False)
        except Exception as error:
            # Never persist/print OAuth responses, DSNs or signed upload URLs.
            _STATE = dict(status='failed', errorType=type(error).__name__, evidenceDeleted=False)
        with db() as conn:
            conn.execute('''UPDATE bob_archive_runs SET status=%s,updated_at=now(),receipt=%s::jsonb
                WHERE day=%s''', (_STATE['status'], json.dumps(_STATE), day))
        return _STATE
    finally:
        _LOCK.release()


def start(db):
    global _THREAD, _STATE
    if _THREAD or readiness()['status'] != 'ready':
        return
    _STATE = readiness()
    def loop():
        # Let push/simulation startup finish. Failures never stop live workers.
        time.sleep(300)
        while True:
            try:
                cycle(db)
            except Exception as error:
                _STATE.update(status='failed', errorType=type(error).__name__, evidenceDeleted=False)
            time.sleep(3600)
    _THREAD = threading.Thread(target=loop, name='bob-private-archive', daemon=True)
    _THREAD.start()
