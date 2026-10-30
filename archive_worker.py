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
             'BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON', 'BOB_ARCHIVE_RESTORE_DATABASE_URL')


def readiness():
    if os.environ.get('BOB_ARCHIVE_ENABLED') != '1':
        return dict(status='disabled', evidenceDeleted=False)
    required = ('DATABASE_URL', 'BOB_ARCHIVE_PARENT_FOLDER_ID', 'BOB_ARCHIVE_RESTORE_DATABASE_URL') if os.environ.get('BOB_ARCHIVE_CREDENTIAL_SOURCE') == 'encrypted-store' else _REQUIRED
    missing = [key for key in required if not os.environ.get(key)]
    return dict(status='blocked' if missing else 'ready', missingConfiguration=missing,
                evidenceDeleted=False, restoreIsolation='separate-database-instance',
                additionalPaidServices=False)


def status():
    return {**readiness(), **_STATE} if _THREAD else readiness()


def init(conn):
    # Keep v1 failures/receipts intact; v2 permits one new-format attempt per day.
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_archive_runs_v2 (
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
            claimed = conn.execute('''INSERT INTO bob_archive_runs_v2(day,status)
                VALUES(%s,'running') ON CONFLICT DO NOTHING RETURNING day''', (day,)).fetchone()
        if not claimed:
            _STATE = dict(status='already-attempted-today', evidenceDeleted=False)
            return _STATE
        try:
            if runner is None:
                from drive_evidence_archive import run, GoogleDrive
                def runner():
                    # Source is read-only; restoration requires a different server.
                    dsn = os.environ['DATABASE_URL']
                    if os.environ.get('BOB_ARCHIVE_CREDENTIAL_SOURCE') == 'encrypted-store':
                        from archive_runtime import drive_client
                        drive = drive_client(db)
                    else:
                        drive = GoogleDrive()
                    return run(dsn, os.environ['BOB_ARCHIVE_RESTORE_DATABASE_URL'], os.environ.get('BOB_ARCHIVE_WORK_DIRECTORY', '/tmp/bob-archive'),
                               drive, progress=lambda phase: _STATE.update(status='running', phase=phase))
            result = runner()
            if not (result.get('restoreVerified') is True and
                    result.get('remoteDownloadVerified') is True and
                    result.get('deletionPermitted') is False and result.get('receiptFileId')):
                raise ValueError('Verified remote receipt required')
            _STATE = dict(status='verified', receipt=result, evidenceDeleted=False)
        except Exception as error:
            # Never persist/print OAuth responses, DSNs or signed upload URLs.
            _STATE = dict(status='failed', errorType=type(error).__name__, phase=_STATE.get('phase'), evidenceDeleted=False)
        with db() as conn:
            conn.execute('''UPDATE bob_archive_runs_v2 SET status=%s,updated_at=now(),receipt=%s::jsonb
                WHERE day=%s''', (_STATE['status'], json.dumps(_STATE), day))
        return _STATE
    finally:
        _LOCK.release()


def start(db):
    global _THREAD, _STATE
    if _THREAD or (readiness()['status'] != 'ready' and os.environ.get('BOB_ARCHIVE_PREPARE') != '1'):
        return
    _STATE = readiness()
    def loop():
        # Let push/simulation startup finish. Failures never stop live workers.
        time.sleep(60)
        while True:
            try:
                if os.environ.get('BOB_ARCHIVE_PREPARE') == '1':
                    from archive_runtime import prepare
                    prepared = prepare(db)
                    _STATE.update(prepared)
                    if readiness()['status'] == 'ready' and prepared['status'] == 'prepared':
                        cycle(db)
                else:
                    cycle(db)
            except Exception as error:
                _STATE.update(status='failed', errorType=type(error).__name__, evidenceDeleted=False)
            time.sleep(60 if _STATE.get('status') == 'awaiting-folder-placement' else 3600)
    _THREAD = threading.Thread(target=loop, name='bob-private-archive', daemon=True)
    _THREAD.start()
