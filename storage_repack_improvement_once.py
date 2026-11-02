"""Operator-opted, one-table pg_repack with independent restore and capacity gates.

Only public.bob_improvement_observations; neither data deletion nor trade logic.
Never kill blocking backends, print connection details, or execute by default.
"""
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_RESOURCE = "dpg-datjno1srm7s738vv500-a"
_TABLE = "public.bob_improvement_observations"
_LOCK_KEYS = ("bob_storage_maintenance_v1", "bob_cold_observations_v1",
              "bob_cold_metrics_v1", "bob_cold_analysis_v1",
              "bob_improvement_repack_once_v1")
_ARCHIVE_SCOPE = "reviewed-evidence-tables-not-full-database-backup"
_CONFIG = "BOB_IMPROVEMENT_REPACK_ONCE"
_IDENT = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_THREAD = None
_START_LOCK = threading.Lock()


def configuration():
    try:
        obj=json.loads(os.environ.get(_CONFIG,""))
    except (ValueError,TypeError):
        return None
    if (type(obj) is not dict or set(obj)!={"id","target","confirmed"} or
            type(obj.get("id")) is not str or not _IDENT.fullmatch(obj["id"]) or
            obj.get("target")!="bob_improvement_observations" or
            obj.get("confirmed") is not True):
        return None
    return obj


def quiet_period(now):
    clock=datetime.fromtimestamp(now,ZoneInfo("Europe/Zurich"))
    return clock.hour>=22 or clock.hour<7


def _connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"],autocommit=True,
        connect_timeout=8,application_name="bob_improvement_repack_once",
        options="-c statement_timeout=7000 -c lock_timeout=800")


def _backup(conn,seconds):
    """Actual independently restored receipt, no caller-supplied claim."""
    row=conn.execute("""SELECT receipt,extract(epoch from updated_at)
        FROM bob_archive_attempts WHERE status='verified'
        ORDER BY updated_at DESC LIMIT 1""").fetchone()
    if not row or type(row[0]) is not dict or row[1] is None:
        return False
    envelope=row[0]
    proof=envelope.get("receipt")
    if not isinstance(proof,dict):
        return False
    return (proof.get("restoreVerified") is True and
        proof.get("remoteDownloadVerified") is True and
        proof.get("deletionPermitted") is False and
        proof.get("scope")==_ARCHIVE_SCOPE and
        0<=seconds-float(row[1])<=24*3600)


def _volume():
    import render_disk_metrics
    v=render_disk_metrics.report()
    stamp=v.get("observedAt")
    if (v.get("status")!="observed" or v.get("resource")!=_RESOURCE or
        v.get("unit")!="bytes" or type(v.get("diskUsage")) is not int or
        type(stamp) not in (int,float) or
        not 0<=time.time()-stamp<=300):
        return None
    return v["diskUsage"],stamp


def _wal(conn):
    """Bounded read-only WAL physical footprint and short write-rate sample."""
    try:
        first=conn.execute("""SELECT coalesce(sum(size),0)::bigint
            FROM pg_ls_waldir()""").fetchone()
        a=conn.execute("SELECT wal_bytes::numeric,stats_reset FROM pg_stat_wal").fetchone()
        time.sleep(2)
        b=conn.execute("SELECT wal_bytes::numeric,stats_reset FROM pg_stat_wal").fetchone()
        if (not first or type(first[0]) is not int or not 0<=first[0]<=96_000_000 or
                not a or not b or a[1]!=b[1] or a[0] is None or b[0] is None):
            return None
        delta=int(b[0]-a[0])
        if not 0<=delta<=4_000_000:
            return None
        return {"directoryBytes":first[0],"twoSecondWrittenBytes":delta}
    except Exception:
        return None


def _proof_rows(conn):
    """Bounded independent SQL read; no original fields leave memory."""
    first=conn.execute("""SELECT campaign,slot,md5(payload::text)
        FROM public.bob_improvement_observations
        ORDER BY campaign,slot LIMIT 16""").fetchall()
    last=conn.execute("""SELECT campaign,slot,md5(payload::text)
        FROM public.bob_improvement_observations
        ORDER BY campaign DESC,slot DESC LIMIT 16""").fetchall()
    return set(first+last)


def _client_environment():
    import psycopg
    opts=psycopg.conninfo.conninfo_to_dict(os.environ["DATABASE_URL"])
    names={"host":"PGHOST","hostaddr":"PGHOSTADDR","port":"PGPORT",
           "user":"PGUSER","password":"PGPASSWORD","dbname":"PGDATABASE",
           "sslmode":"PGSSLMODE","sslrootcert":"PGSSLROOTCERT"}
    env=dict(os.environ)
    for key,name in names.items():
        if key in opts:
            env[name]=str(opts[key])
    db=opts.get("dbname")
    if not db or not re.fullmatch(r"[A-Za-z0-9_]{1,64}",db):
        raise ValueError("Database identifier unavailable")
    return env,db


def _init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_improvement_repack_attempts(
        id TEXT PRIMARY KEY,status TEXT NOT NULL,
        relation_before BIGINT,relation_after BIGINT,
        observed_volume_before BIGINT,observed_volume_after BIGINT,
        error_type TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def run_once(*,now=None,connect=_connect,runner=None):
    """One physical table, once. Every missing proof fails before the claim."""
    cfg=configuration()
    if cfg is None:
        return {"status":"disabled","diskBytesFreed":None}
    seconds=time.time() if now is None else now
    if not quiet_period(seconds):
        return {"status":"market-hours-deferred","diskBytesFreed":None}
    if __import__("archive_worker").status().get("status")=="running":
        return {"status":"archive-running","diskBytesFreed":None}
    v=_volume()
    if not v or v[0]>730_000_000:
        return {"status":"fresh-volume-proof-unavailable","diskBytesFreed":None}
    try:
        probe=__import__("storage_repack_bloat_probe").inspect_once()
    except Exception:
        return {"status":"bloat-proof-unavailable","diskBytesFreed":None}
    if (probe.get("rollbackVerified") is not True or
        probe.get("databaseRowsModified") is not False or
        probe.get("table")!=_TABLE or
        type(probe.get("combinedDeadAndApproxFreeBytes")) is not int or
        probe["combinedDeadAndApproxFreeBytes"]<30_000_000):
        return {"status":"insufficient-verified-bloat","diskBytesFreed":None}
    with connect() as conn:
        if not conn.autocommit:
            return {"status":"non-autocommit-connection","diskBytesFreed":None}
        for key in _LOCK_KEYS:
            if not conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))",
                                (key,)).fetchone()[0]:
                return {"status":"busy","diskBytesFreed":None}
        if not _backup(conn,seconds):
            return {"status":"independent-backup-proof-not-fresh","diskBytesFreed":None}
        relation=conn.execute("""SELECT pg_total_relation_size(c.oid)::bigint,
            EXISTS(SELECT 1 FROM pg_index i WHERE i.indrelid=c.oid
                    AND i.indisprimary AND i.indisvalid)
            FROM pg_class c
            WHERE c.oid=%s::regclass""",(_TABLE,)).fetchone()
        if (not relation or type(relation[0]) is not int or
                not 0<relation[0]<=80_000_000 or relation[1] is not True):
            return {"status":"table-size-or-key-proof-failed","diskBytesFreed":None}
        # Render recommends > 2 x table-and-index footprint. Retain another
        # 120 MB for WAL/scratch growth; already allocated WAL is in volume.
        if 1_000_000_000-v[0]-2*relation[0]<=120_000_000:
            return {"status":"insufficient-wal-and-copy-reserve","diskBytesFreed":None}
        wal=_wal(conn)
        if wal is None:
            return {"status":"wal-directory-or-rate-proof-unavailable","diskBytesFreed":None}
        if not shutil.which("pg_repack"):
            return {"status":"repack-client-unavailable","diskBytesFreed":None}
        ext=conn.execute("""SELECT default_version FROM pg_available_extensions
            WHERE name='pg_repack'""").fetchone()
        if not ext:
            return {"status":"repack-extension-unavailable","diskBytesFreed":None}
        original_count=conn.execute(
            "SELECT count(*) FROM public.bob_improvement_observations").fetchone()[0]
        sample=_proof_rows(conn)
        # Retry cannot run concurrently or after a process restart.
        _init(conn)
        claimed=conn.execute("""INSERT INTO bob_improvement_repack_attempts
            (id,status,relation_before,observed_volume_before)
            VALUES(%s,'running',%s,%s)
            ON CONFLICT(id) DO NOTHING RETURNING id""",
            (cfg["id"],relation[0],v[0])).fetchone()
        if not claimed:
            return {"status":"already-claimed","diskBytesFreed":None}
        state="failed";error_type=None;after=None;volume_after=None
        try:
            # This DDL is limited to pg_repack's required trusted extension.
            # No login/secret or CLI stderr is printed.
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_repack")
            env,db=_client_environment()
            args=["pg_repack","--no-superuser-check","--no-kill-backend",
                  "--wait-timeout=3","--no-order",
                  "--table="+_TABLE,"--dbname="+db]
            if runner is None:
                completed=subprocess.run(args,env=env,capture_output=True,
                                         text=True,timeout=180,check=False)
                exit_code=completed.returncode
            else:
                exit_code=runner(args,env)
            if exit_code!=0:
                raise ValueError("Repack client returned unsuccessful status")
            after=conn.execute("SELECT pg_total_relation_size(%s::regclass)",
                               (_TABLE,)).fetchone()[0]
            final_count=conn.execute(
                "SELECT count(*) FROM public.bob_improvement_observations").fetchone()[0]
            if final_count<original_count or _proof_rows(conn)!=sample:
                state="source-verification-mismatch"
            elif after>relation[0]:
                state="no-reduction-observed"
            else:
                state="verified-relation-reduction"
            updated=_volume()
            if updated is not None and updated[1]>v[1]:
                volume_after=updated[0]
        except Exception as exc:
            error_type=type(exc).__name__
            state="deferred"
        conn.execute("""UPDATE bob_improvement_repack_attempts SET
            status=%s,relation_after=%s,observed_volume_after=%s,
            error_type=%s,updated_at=now() WHERE id=%s""",
            (state,after,volume_after,error_type,cfg["id"]))
        return {"status":state,
                "target":"bob_improvement_observations",
                "relationBytesBefore":relation[0],
                "relationBytesAfter":after,
                "observedRelationBytesDecrease":max(0,relation[0]-after)
                    if type(after) is int else None,
                "observedVolumeBytesBefore":v[0],
                "observedVolumeBytesAfter":volume_after,
                "diskBytesFreed":max(0,v[0]-volume_after)
                    if (type(volume_after) is int and volume_after<v[0])
                    else None,
                "sourceRowsPreserved":state=="verified-relation-reduction",
                "errorType":error_type,"evidenceDeleted":False,
                "realOrders":False}


def start_if_enabled():
    """Only with explicit config; bounded off-hours one-shot on push host."""
    global _THREAD
    if configuration() is None or _THREAD is not None:
        return
    with _START_LOCK:
        if _THREAD is not None:
            return
        def work():
            # Avoid running while intraday sessions are active. The flag is
            # one-shot; after one eligible result there is no repeated attempt.
            for _ in range(90):
                if quiet_period(time.time()):
                    try:
                        answer=run_once()
                    except Exception as exc:
                        answer={"status":"deferred","errorType":type(exc).__name__,
                                "diskBytesFreed":None}
                    print("BOB_IMPROVEMENT_REPACK "+json.dumps(answer,sort_keys=True),
                          flush=True)
                    return
                time.sleep(60)
            print("BOB_IMPROVEMENT_REPACK "+json.dumps(
                {"status":"quiet-window-not-reached","diskBytesFreed":None}),
                flush=True)
        _THREAD=threading.Thread(target=work,name="bob-improvement-repack-once",
                                 daemon=True)
        _THREAD.start()
