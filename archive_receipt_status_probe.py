"""One-shot read-only, redacted status of real private Drive archive attempts.

The provider status is read from Bob's durable PostgreSQL attempt ledger,
not guessed from Drive file names or the presence of a successful upload.
No original payloads, Drive IDs, hostnames, credentials or SQL arguments appear
in returned reports or logs.
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

_ENABLED="BOB_ARCHIVE_STATUS_PROBE_ONCE"
_STATES={"verified","failed","running","already-attempted-today",
         "blocked","ready","disabled"}
_PHASES={"drive-preflight","restore-isolation-check","export",
         "local-restore","encrypt-before-upload","encrypted-upload",
         "encrypted-download","authenticated-decrypt",
         "verify-independent-recovery-key","upload",
         "download","remote-restore","receipt-upload"}
_THREAD=None
_LOCK=threading.Lock()


def _connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"],autocommit=True,
        connect_timeout=7,application_name="bob_archive_receipt_probe",
        options="-c default_transaction_read_only=on "
                "-c statement_timeout=2000 -c lock_timeout=250")


def _redacted(row):
    if not row:
        return {"status":"not-recorded"}
    state, updated, stored = row
    item=stored if type(stored) is dict else {}
    details=item.get("receipt") if type(item.get("receipt")) is dict else {}
    age=None
    if isinstance(updated,datetime) and updated.tzinfo is not None:
        elapsed=(datetime.now(timezone.utc)-updated).total_seconds()
        if 0<=elapsed<=7*86400:
            age=round(elapsed/60,1)
    phase=item.get("phase")
    kind=item.get("errorType")
    return {
        "status":state if state in _STATES else "unknown",
        "ageMinutes":age,
        "phase":phase if phase in _PHASES else None,
        "errorType":kind if type(kind) is str and
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}",kind) else None,
        "restoreVerified":details.get("restoreVerified") is True,
        "remoteDownloadVerified":details.get("remoteDownloadVerified") is True,
        "encryptionVerified":details.get("encryptionVerified") is True,
        "encryptionVersion":(details.get("encryptionVersion") if
            details.get("encryptionVersion") in
            ("none","aes-256-gcm-stream-v1") else None),
        "deletionPermitted":False,
    }


def inspect_once(factory=_connect):
    with factory() as conn:
        latest=conn.execute("""SELECT status,updated_at,receipt
            FROM bob_archive_attempts
            ORDER BY updated_at DESC LIMIT 1""").fetchone()
        verified=conn.execute("""SELECT status,updated_at,receipt
            FROM bob_archive_attempts WHERE status='verified'
            ORDER BY updated_at DESC LIMIT 1""").fetchone()
    return {"status":"checked","readOnly":True,
            "latestAttempt":_redacted(latest),
            "latestVerified":_redacted(verified),
            "diskBytesFreed":None}


def start_if_enabled():
    global _THREAD
    if os.environ.get(_ENABLED)!="1" or not os.environ.get("DATABASE_URL"):
        return
    with _LOCK:
        if _THREAD is not None:
            return
        def work():
            time.sleep(8)
            try:
                result=inspect_once()
            except Exception as exc:
                # Never print an exception's potentially sensitive message.
                result={"status":"probe-unavailable",
                        "errorType":type(exc).__name__,
                        "diskBytesFreed":None,"readOnly":True}
            print("BOB_ARCHIVE_RECEIPT_STATUS "+json.dumps(result,
                sort_keys=True,separators=(",",":")),flush=True)
        _THREAD=threading.Thread(target=work,
            name="bob-archive-receipt-status-once",daemon=True)
        _THREAD.start()
