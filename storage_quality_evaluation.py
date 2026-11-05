"""Bounded, resumable quality-metric evaluation without original deletion.

The metric source's 30-day retention and cold-metric reader are unchanged.
This saved overview does NOT replace the original, replayable metric evidence,
prove that individual formulas passed, or authorize source compaction.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import threading
import time

_PAGE = 256
_THREAD = None
_THREAD_LOCK = threading.Lock()
_FAMILIES = frozenset(("display", "dmi", "product", "trade", "other"))
_STATES = frozenset(("matched", "mismatch", "unavailable", "observed",
                     "individual-metrics-no-overall-status",
                     "archived-original-not-inline", "unclassified"))
_SQL = """SELECT version,scope,bar_at,checked_at,
    CASE
      WHEN payload ? '_bobColdMetricV1' OR payload ? '_bobColdMetricV2'
        THEN 'archived-original-not-inline'
      WHEN jsonb_typeof(payload->'metrics')='object'
        AND NOT (payload ? 'status')
        THEN 'individual-metrics-no-overall-status'
      ELSE coalesce(payload->>'status','unclassified') END
    FROM bob_metric_checks
    WHERE (checked_at,version,scope,bar_at) >
          (%s::bigint,%s::text,%s::text,%s::bigint)
      AND checked_at<%s::bigint
    ORDER BY checked_at,version,scope,bar_at LIMIT %s"""


def family(scope):
    if type(scope) is not str or not scope:
        raise ValueError("Unusable quality scope")
    return next((x for x in ("display","dmi","product","trade")
                 if scope.startswith(x+":")), "other")


def validate(row, now_ms):
    """Return only safe labels and a digest of original source identity."""
    if type(row) not in (list,tuple) or len(row)!=5:
        raise ValueError("Bad metric evaluation row")
    version,scope,bar_at,checked_at,state=row
    if (type(version) is not str or not 1<=len(version)<=128 or
            type(scope) is not str or not 1<=len(scope)<=256 or
            type(bar_at) is not int or type(checked_at) is not int or
            not 0<=checked_at<=now_ms or
            not -(2**63)<=bar_at<2**63):
        raise ValueError("Unverifiable metric source")
    label = state if type(state) is str and state in _STATES else "unclassified"
    day=datetime.fromtimestamp(checked_at/1000,timezone.utc).date().isoformat()
    digest=hashlib.sha256(json.dumps(
        [version,scope,bar_at,checked_at,label],
        ensure_ascii=True,separators=(",",":")).encode("utf8")).digest()
    return day,family(scope),label,digest


def fold(rows, now_ms):
    if type(rows) is not list or len(rows)>_PAGE:
        raise ValueError("Unbounded quality evaluation page")
    groups=defaultdict(lambda:{"counts":defaultdict(int),"digests":[]})
    previous=None
    for row in rows:
        day,source,label,digest=validate(row,now_ms)
        key=(row[3],row[0],row[1],row[2])
        if previous is not None and key<=previous:
            raise ValueError("Unsorted or duplicate quality source")
        previous=key
        groups[(day,source)]["counts"][label]+=1
        groups[(day,source)]["digests"].append(digest)
    return groups


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_quality_eval_daily (
        day TEXT NOT NULL, family TEXT NOT NULL,
        records INTEGER NOT NULL DEFAULT 0,
        counts JSONB NOT NULL,
        receipt_chain_sha256 TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(day,family))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_quality_eval_cursor (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        checked_at BIGINT NOT NULL,version TEXT NOT NULL,
        scope TEXT NOT NULL,bar_at BIGINT NOT NULL,
        processed BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def capture(conn, now=None):
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    now_ms=int(now.timestamp()*1000)
    cutoff=now_ms-5*60*1000
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='2500ms'")
        conn.execute("SET LOCAL lock_timeout='300ms'")
        locked=conn.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))",
                            ("bob-quality-eval-v1",)).fetchone()
        if locked!=(True,):
            return {"status":"busy","deletionAuthorized":False}
        cursor=conn.execute("""SELECT checked_at,version,scope,bar_at,processed
            FROM bob_quality_eval_cursor WHERE singleton=1 FOR UPDATE""").fetchone()
        lower=cursor if cursor else (0,"","",-(2**63),0)
        rows=conn.execute(_SQL,(*lower[:4],cutoff,_PAGE)).fetchall()
        groups=fold(rows,now_ms)
        for (day,group),detail in groups.items():
            old=conn.execute("""SELECT records,counts,receipt_chain_sha256
                FROM bob_quality_eval_daily WHERE day=%s AND family=%s
                FOR UPDATE""",(day,group)).fetchone()
            total,counted,chain=(old if old else (0,{},"0"*64))
            if type(total) is not int or type(counted) is not dict or (
                    type(chain) is not str or len(chain)!=64):
                raise ValueError("Invalid stored evaluation")
            counts={k:v for k,v in counted.items()
                    if k in _STATES and type(v) is int and v>=0}
            for label,n in detail["counts"].items():
                counts[label]=counts.get(label,0)+n
            chain_hash=hashlib.sha256(bytes.fromhex(chain))
            for digest in detail["digests"]:
                chain_hash.update(digest)
            conn.execute("""INSERT INTO bob_quality_eval_daily
                (day,family,records,counts,receipt_chain_sha256)
                VALUES(%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT(day,family) DO UPDATE SET
                  records=excluded.records,counts=excluded.counts,
                  receipt_chain_sha256=excluded.receipt_chain_sha256,
                  updated_at=now()""",
                (day,group,total+len(detail["digests"]),
                 json.dumps(counts,sort_keys=True),chain_hash.hexdigest()))
        if rows:
            last=rows[-1]
            conn.execute("""INSERT INTO bob_quality_eval_cursor
                (singleton,checked_at,version,scope,bar_at,processed)
                VALUES(1,%s,%s,%s,%s,%s)
                ON CONFLICT(singleton) DO UPDATE SET
                  checked_at=excluded.checked_at,version=excluded.version,
                  scope=excluded.scope,bar_at=excluded.bar_at,
                  processed=excluded.processed,updated_at=now()""",
                (last[3],last[0],last[1],last[2],lower[4]+len(rows)))
    return {"status":"page-recorded" if rows else "caught-up-as-observed",
            "processed":len(rows),"fullHistoryVerified":False,
            "metricPassVerified":False,"sourceRowsModified":False,
            "deletionAuthorized":False,"physicalBytesFreed":None}


def report(conn):
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='500ms'")
            row=conn.execute("SELECT processed FROM bob_quality_eval_cursor "
                             "WHERE singleton=1").fetchone()
        n=row[0] if row and type(row[0]) is int and 0<=row[0]<=10**12 else None
        return {"status":"observed" if n is not None else "warming",
                "processedRecords":n,"sourceCoverage":"forward-only-not-replayed",
                "metricPassVerified":False,"fullHistoryVerified":False,
                "deletionAuthorized":False,"physicalBytesFreed":None}
    except Exception:
        return {"status":"not-observed","deletionAuthorized":False,
                "physicalBytesFreed":None}


@__import__("ocr_workload_priority").maintenance
def run_once(factory=None):
    if factory is None:
        factory=__import__("cold_metrics").connect
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError("Dedicated autocommit connection required")
        return capture(conn)


def start():
    global _THREAD
    if not os.environ.get("DATABASE_URL") or os.environ.get(
            "BOB_QUALITY_EVAL_DISABLED")=="1":
        return
    with _THREAD_LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(270)
            while True:
                try:
                    if __import__("archive_worker").status().get("status")=="running":
                        outcome={"status":"archive-running"}
                    else:
                        outcome=run_once()
                except Exception:
                    outcome={"status":"deferred"}
                print("BOB_QUALITY_EVALUATION "+json.dumps({
                    "status":outcome["status"],"sourceRowsModified":False,
                    "deletionAuthorized":False},sort_keys=True),flush=True)
                time.sleep(900)
        _THREAD=threading.Thread(target=loop,name="bob-quality-evaluation",
                                 daemon=True)
        _THREAD.start()
