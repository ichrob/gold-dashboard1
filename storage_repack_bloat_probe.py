"""One-shot transient pgstattuple bloat probe on a single fixed table.

Only an explicit opt-in after Push is healthy may run this. CREATE EXTENSION
is strictly inside a rollback-only transaction; no DDL or images persist.
Never runs pg_repack, VACUUM, DELETE or a table rewrite.
"""
import json
import os
import threading
import time

_TARGET = "public.bob_improvement_observations"
# Only these exact tables may be probed. No caller-provided SQL identifiers.
_TARGETS = {"improvement": _TARGET, "metric": "public.bob_metric_checks",
            "diagnostic": "public.bob_diagnostic_history",
            "repairs": "public.bob_test_repairs",
            "outcomes": "public.bob_decision_outcomes"}


def selected_target():
    name = os.environ.get("BOB_BLOAT_PROBE_TARGET", "improvement")
    if name not in _TARGETS:
        raise ValueError("Unapproved bloat target")
    return _TARGETS[name]

_LIMIT_BYTES = 100_000_000
_DIAGNOSTIC_LIMIT_BYTES = 200_000_000  # Only for the fixed journal
_LOCK = threading.Lock()


def _connect():
    import psycopg
    return psycopg.connect(
        os.environ["DATABASE_URL"],autocommit=False,connect_timeout=6,
        application_name="bob_transient_pgstattuple_probe",
        options="-c statement_timeout=4000 -c lock_timeout=250 "
                "-c idle_in_transaction_session_timeout=11000")


def _volume_gate():
    import render_disk_metrics
    v=render_disk_metrics.report()
    stamp=v.get("observedAt")
    return (v.get("status")=="observed" and
            v.get("resource")=="dpg-datjno1srm7s738vv500-a" and
            v.get("unit")=="bytes" and
            type(v.get("diskUsage")) is int and
            v["diskUsage"]<750_000_000 and
            type(stamp) in (int,float) and 0<=time.time()-stamp<=300)


def _bloat_stats(conn, oid):
    # oid is obtained only from the fixed public table or its TOAST relation.
    row=conn.execute("""SELECT table_len::bigint,dead_tuple_len::bigint,
        approx_free_space::bigint,scanned_percent::float8
        FROM public.pgstattuple_approx(%s::oid::regclass)""",(oid,)).fetchone()
    if (not row or len(row)!=4 or
            any(type(v) not in (int,float) or v<0 for v in row)):
        raise ValueError("Invalid approximate tuple stats")
    total,dead,free,scanned=row
    if (type(total) is not int or type(dead) is not int or
            type(free) is not int or not 0<=scanned<=100 or
            dead+free>total):
        raise ValueError("Unexpected tuple statistics")
    return {"relationBytes":total,"deadTupleBytes":dead,
            "approxFreeBytes":free,"scannedPercent":round(scanned,2)}


def inspect_once():
    """Bounded scan with guaranteed rollback, even if CREATE EXTENSION worked."""
    if __import__("archive_worker").status().get("status")=="running":
        raise ValueError("Archive worker active")
    if not _volume_gate():
        raise ValueError("Provider volume gate unavailable")
    target=selected_target()
    limit = (_DIAGNOSTIC_LIMIT_BYTES if target ==
             _TARGETS["diagnostic"] else _LIMIT_BYTES)
    conn=_connect()
    initial_installed=None
    try:
        conn.execute("SET LOCAL statement_timeout='4s'")
        conn.execute("SET LOCAL lock_timeout='250ms'")
        original=conn.execute("""SELECT installed_version FROM
            pg_available_extensions WHERE name='pgstattuple'""").fetchone()
        if not original:
            raise ValueError("pgstattuple unavailable")
        initial_installed=original[0] is not None
        row=conn.execute("""SELECT c.oid::oid,c.reltoastrelid::oid,
            pg_total_relation_size(c.oid)::bigint
            FROM pg_class c
            WHERE c.oid=%s::regclass""",(target,)).fetchone()
        if (not row or len(row)!=3 or type(row[2]) is not int or
                not 0<row[2]<limit or not row[1]):
            raise ValueError("Target beyond safe scan size")
        # PostgreSQL supports transactional CREATE EXTENSION. We MUST roll
        # this transaction back, including after a successful probe.
        if not initial_installed:
            conn.execute("CREATE EXTENSION pgstattuple WITH SCHEMA public")
        heap=_bloat_stats(conn,row[0])
        toast=_bloat_stats(conn,row[1])
    finally:
        # This is intentionally not a context-managed commit transaction.
        conn.rollback()
        conn.close()

    # On a separate read-only connection, independently verify that our
    # transaction did not leave an extension behind if it was absent.
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"],autocommit=True,
        connect_timeout=6,application_name="bob_pgstattuple_rollback_verify",
        options="-c default_transaction_read_only=on -c statement_timeout=1500") as check:
        after=check.execute("""SELECT installed_version FROM
            pg_available_extensions WHERE name='pgstattuple'""").fetchone()
    if (not after or (after[0] is not None)!=initial_installed):
        raise ValueError("Extension rollback cannot be independently confirmed")
    return {
        "status":"rolled-back-approximate-bloat-measurement",
        "table":target,
        "mainHeap":heap,
        "toast":toast,
        "combinedDeadAndApproxFreeBytes":heap["deadTupleBytes"]+
            heap["approxFreeBytes"]+toast["deadTupleBytes"]+toast["approxFreeBytes"],
        "measurementScope":"heap-and-toast-only-not-index-bloat",
        "extensionLeftInstalled":initial_installed,
        "rollbackVerified":True,
        "databaseRowsModified":False,
        "maintenanceAuthorized":False,
        "readyToRepack":False,
        "diskBytesFreed":None,
    }


def start_if_enabled():
    """One isolated background execution on this instance, never a schedule."""
    if os.environ.get("BOB_BLOAT_PROBE_ONCE")!="1":
        return
    def run():
        if not _LOCK.acquire(False):
            return
        try:
            try:
                result=inspect_once()
            except Exception as exc:
                kind=type(exc).__name__
                result={"status":"probe-unavailable",
                        "errorType":kind if kind in (
                            "ValueError","InsufficientPrivilege","QueryCanceled",
                            "OperationalError","ProgrammingError","DatabaseError"
                        ) else "Error",
                        "rollbackVerified":False,
                        "databaseRowsModified":False,
                        "maintenanceAuthorized":False,
                        "readyToRepack":False,
                        "diskBytesFreed":None}
            print("BOB_REPACK_BLOAT "+
                  json.dumps(result,sort_keys=True,separators=(",",":")),
                  flush=True)
        finally:
            _LOCK.release()
    threading.Thread(target=run,name="bob-pgstattuple-rollback-probe",
                     daemon=True).start()
