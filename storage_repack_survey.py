"""One-shot, read-only WAL / TOAST / repack feasibility survey.

Disabled by default. There is NO maintenance operation, pg_repack invocation,
extension installation, source payload read, scheduled repeat, or DB writer.
Only safe aggregates about one fixed public table leave this module.
"""
import json
import os
import threading
import time

TARGET = "public.bob_improvement_observations"
_RESOURCE = "dpg-datjno1srm7s738vv500-a"
_LOCK = threading.Lock()
_STATE = {"status":"not-requested","readOnly":True,"diskBytesFreed":None}

_RELATION_SQL = """SELECT
  pg_total_relation_size(c.oid)::bigint,
  pg_relation_size(c.oid)::bigint,
  pg_indexes_size(c.oid)::bigint,
  CASE WHEN c.reltoastrelid=0 THEN 0
       ELSE pg_total_relation_size(c.reltoastrelid)::bigint END,
  coalesce(s.n_live_tup,0)::bigint,coalesce(s.n_dead_tup,0)::bigint,
  c.reltoastrelid::oid,
  coalesce(ts.n_live_tup,0)::bigint,coalesce(ts.n_dead_tup,0)::bigint
FROM pg_class c
LEFT JOIN pg_stat_all_tables s ON s.relid=c.oid
LEFT JOIN pg_stat_all_tables ts ON ts.relid=c.reltoastrelid
WHERE c.oid='public.bob_improvement_observations'::regclass"""

_EXT_SQL = """SELECT name,default_version,installed_version
FROM pg_available_extensions
WHERE name IN ('pg_repack','pgstattuple') ORDER BY name"""
_WAL_SQL = "SELECT wal_bytes::numeric,stats_reset FROM pg_stat_wal"


def _connect():
    import psycopg
    return psycopg.connect(
        os.environ["DATABASE_URL"],autocommit=True,connect_timeout=6,
        application_name="bob_repack_readonly_wal_survey",
        options="-c default_transaction_read_only=on "
                "-c statement_timeout=1500 -c lock_timeout=250")


def _snapshot():
    """Fresh read-only connection; no long transaction across observations."""
    with _connect() as conn:
        row=conn.execute(_RELATION_SQL).fetchone()
        if not row or len(row)!=9 or any(type(v) is not int or v<0 for v in row):
            raise ValueError("Table footprint unavailable")
        ext=conn.execute(_EXT_SQL).fetchall()
        extensions={name: {"available":True,
                           "installed":installed is not None,
                           "version":installed if installed is not None else default}
                    for name,default,installed in ext
                    if name in ("pg_repack","pgstattuple") and
                    isinstance(default,str) and len(default)<32 and
                    (installed is None or isinstance(installed,str) and len(installed)<32)}
        try:
            wal=conn.execute(_WAL_SQL).fetchone()
            if not wal or wal[0] is None or wal[1] is None:
                wal=None
            else:
                wal=(int(wal[0]),str(wal[1]))
        except Exception:
            # autocommit=True: one rejected read does not affect others
            wal=None
        # pgstattuple_approx may still scan pages; never auto-run it in an
        # operational HTTP report or against a live unbounded table.
    return row,extensions,wal


def _safe_volume():
    try:
        import render_disk_metrics
        v=render_disk_metrics.report()
        t=time.time()
        if (v.get("status")=="observed" and v.get("resource")==_RESOURCE
                and v.get("unit")=="bytes"
                and type(v.get("diskUsage")) is int
                and type(v.get("observedAt")) in (int,float)
                and 0 <= t-v["observedAt"] <= 300):
            return v["diskUsage"]
    except Exception:
        pass
    return None


def evaluate(first,second,elapsed,volume,client_present):
    """Interpret aggregate catalog and cumulative WAL counters; never infer bloat."""
    row,ext,wal=first
    _,_,later_wal=second
    if (type(elapsed) not in (int,float) or not 10<=elapsed<=90
            or type(row) not in (tuple,list) or len(row)!=9):
        raise ValueError("Invalid bounded survey")
    wal_bytes=None
    if wal is not None and later_wal is not None:
        start,reset=wal
        finish,later_reset=later_wal
        if type(start) is int and type(finish) is int and (finish>=start>=0
                and reset==later_reset):
            wal_bytes=finish-start
    repack=ext.get("pg_repack",{})
    stat=ext.get("pgstattuple",{})
    return {
        "status":"bounded-readonly-survey",
        "table":TARGET,
        "totalRelationBytes":row[0],
        "heapBytes":row[1],
        "indexBytes":row[2],
        "toastBytes":row[3],
        "liveRowEstimate":row[4],
        "deadRowEstimate":row[5],
        "toastLiveRowEstimate":row[7],
        "toastDeadRowEstimate":row[8],
        "pgRepackExtensionAvailable":repack.get("available",False),
        "pgRepackExtensionInstalled":repack.get("installed",False),
        "pgStattupleExtensionAvailable":stat.get("available",False),
        "pgStattupleExtensionInstalled":stat.get("installed",False),
        "pgRepackClientPresent":client_present is True,
        "walObservationSeconds":round(elapsed,1),
        "walGeneratedBytesInWindow":wal_bytes,
        "walCounterStatus":"observed" if wal_bytes is not None else "not-observed",
        "physicalRenderVolumeBytes":volume,
        "actualTableBloatBytes":None,
        "walFreeHeadroomBytes":None,
        "scratchPeakBytes":None,
        "readOnly":True,
        "maintenanceAuthorized":False,
        "readyToRepack":False,
        "productionRowsModified":False,
        "deletionAuthorized":False,
        "diskBytesFreed":None,
    }


def inspect_once(*, sleep=time.sleep, clock=time.monotonic):
    first=_snapshot()
    start=clock()
    sleep(15)
    second=_snapshot()
    elapsed=clock()-start
    import repack_client_installer
    return evaluate(first,second,elapsed,_safe_volume(),
                    repack_client_installer.client_available())


def start_if_enabled():
    """At most once per service instance; never blocks Push startup."""
    if os.environ.get("BOB_REPACK_SURVEY_ONCE")!="1":
        return
    def run():
        global _STATE
        if not _LOCK.acquire(False):
            return
        try:
            try:
                _STATE=inspect_once()
            except Exception as error:
                name=type(error).__name__
                _STATE={"status":"survey-unavailable",
                        "errorType":name if name in
                          ("ValueError","OperationalError","DatabaseError",
                           "ProgrammingError","KeyError","TimeoutError")
                          else "Error",
                        "readOnly":True,"maintenanceAuthorized":False,
                        "readyToRepack":False,"diskBytesFreed":None}
            print("BOB_REPACK_SURVEY "+
                  json.dumps(_STATE,sort_keys=True,separators=(",",":")),
                  flush=True)
        finally:
            _LOCK.release()
    threading.Thread(target=run,name="bob-repack-survey-readonly",
                     daemon=True).start()


def status():
    return dict(_STATE)
