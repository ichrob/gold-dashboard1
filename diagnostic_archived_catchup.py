"""Drive-verified catch-up of the EXISTING 7-day/60k diagnostic retention.

This does not alter the retention period, erase source candle/quote archives,
or run any physical table rewrite. A successful *remote-download and separate-
database restore* of the full reviewed-evidence export is required first.
It runs on its own limited DB connection, never during live push delivery.
"""
import json
import os
import threading
import time
from datetime import datetime, time as day_time, timedelta, timezone

_ENABLED = "BOB_DRIVE_VERIFIED_DIAGNOSTIC_CATCHUP"
_INTERVAL_SECONDS = 600
_MAX_PROOF_AGE_SECONDS = 6 * 3600
_LOCK = threading.Lock()
_THREAD = None


def connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True,
        connect_timeout=8, application_name="bob_drive_verified_diag_catchup",
        options="-c statement_timeout=6000 -c lock_timeout=500")


def backup_cutoff(conn, now=None):
    """Oldest-safe cutoff, not a claimed upload time.

    The archive day is assigned before a read-only repeatable-read export.
    Anything before the PREVIOUS UTC midnight predates its source snapshot.
    Requiring the exact reviewed table export scope and a verified *remote*
    restore rules out incidental screenshots / separate partial backups.
    """
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    row = conn.execute("""SELECT day,status,updated_at,receipt
        FROM bob_archive_attempts
        WHERE status='verified'
        ORDER BY updated_at DESC LIMIT 1""").fetchone()
    if not row or len(row)!=4:
        return None
    day, state, updated, outer = row
    if (state!="verified" or not isinstance(updated,datetime)
            or updated.tzinfo is None or not 0<=
            (now-updated).total_seconds()<=_MAX_PROOF_AGE_SECONDS
            or type(outer) is not dict):
        return None
    proof=outer.get("receipt")
    if (type(proof) is not dict
            or proof.get("version")!="bob-evidence-archive-v3"
            or proof.get("scope")!="reviewed-evidence-tables-not-full-database-backup"
            or proof.get("restoreVerified") is not True
            or proof.get("remoteDownloadVerified") is not True
            or proof.get("restoreIsolation")!="separate-database-instance"
            or proof.get("deletionPermitted") is not False
            or proof.get("evidenceDeleted") is True
            or not isinstance(proof.get("archiveSha256"),str)
            or len(proof["archiveSha256"])!=64
            or not isinstance(proof.get("driveFileId"),str)
            or not proof["driveFileId"]):
        return None
    # Must be the archive's UTC day, never user-configured local midnight.
    if not hasattr(day,"year") or not hasattr(day,"month") or not hasattr(day,"day"):
        return None
    start=datetime.combine(day,day_time.min,tzinfo=timezone.utc)
    if start>now:
        return None
    return start-timedelta(days=1)


def run_once(*,factory=connect,now=None,volume=None):
    """At most 500 events per cycle and none without source restore proof."""
    if os.environ.get(_ENABLED)!="1":
        return {"status":"disabled","removed":0,"diskBytesFreed":None}
    now = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(now,datetime) or now.tzinfo is None
            or __import__("archive_worker").status().get("status")=="running"):
        return {"status":"archive-running-or-clock-unavailable","removed":0,
                "diskBytesFreed":None}
    # Independent provider metric with an actual physical timestamp; never
    # mistake pg_database_size for available WAL/scratch disk space.
    if volume is None:
        volume=__import__("render_disk_metrics").report()
    observed=volume.get("observedAt")
    if (volume.get("status")!="observed"
            or volume.get("resource")!="dpg-datjno1srm7s738vv500-a"
            or volume.get("unit")!="bytes"
            or type(volume.get("diskUsage")) is not int
            or volume["diskUsage"]>725_000_000
            or type(observed) not in (int,float)
            or not 0<=now.timestamp()-observed<=300):
        return {"status":"physical-reserve-unavailable","removed":0,
                "diskBytesFreed":None}
    import diagnostic_history
    with factory() as conn:
        if not conn.autocommit:
            return {"status":"autocommit-required","removed":0,
                    "diskBytesFreed":None}
        with conn.transaction():
            cutoff=backup_cutoff(conn,now)
        if cutoff is None:
            return {"status":"fresh-separate-Drive-restore-required",
                    "removed":0,"diskBytesFreed":None}
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='5s'")
                removed=diagnostic_history.prune(conn,archive_cutoff=cutoff)
        except Exception as exc:
            return {"status":"deferred","errorType":type(exc).__name__,
                    "removed":0,"diskBytesFreed":None}
        if type(removed) is not int or not 0<=removed<=1000:
            raise ValueError("Unbounded cleanup result")
    return {"status":"checked","removed":removed,"diskBytesFreed":None,
            "evidenceDeleted":False,
            "scope":"existing-journal-retention-only-before-proved-cutoff"}


def start():
    """Only one opt-in background thread on Push, non-blocking to trading."""
    global _THREAD
    if (os.environ.get(_ENABLED)!="1" or
            not os.environ.get("DATABASE_URL")):
        return
    with _LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(300)
            while True:
                try:
                    result=run_once()
                except Exception as exc:
                    result={"status":"deferred","errorType":type(exc).__name__,
                            "removed":0,"diskBytesFreed":None}
                # No original row identifiers, SQL payloads, timestamps,
                # authentication state, file IDs or prices in the log.
                print("BOB_DRIVE_DIAG_CATCHUP "+json.dumps(result,sort_keys=True),
                      flush=True)
                time.sleep(_INTERVAL_SECONDS)
        _THREAD=threading.Thread(target=loop,name="bob-drive-diag-catchup",
                                 daemon=True)
        _THREAD.start()
