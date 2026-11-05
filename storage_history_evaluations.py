"""Resumable, capped historical evaluations for two indexed Bob journals.

Reads only short, indexed scalar projections from source evidence; records
immutable page evaluation manifests. Never deletes an original, asserts
win/loss, treats a digest as a recoverable backup, or grants migration.
Older/changed historical source rows may require a separate replay audit.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import threading
import time

PAGE_ROWS = 400
_STABLE_DAYS = 2
_AREAS = ("diagnoses", "decisions")
_SOURCES = {
    "diagnoses": """SELECT id,recorded_at,stage,
        coalesce(payload->>'outcome','unclassified')
        FROM bob_diagnostic_history
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
          AND recorded_at<%s::timestamptz
        ORDER BY recorded_at,id LIMIT %s""",
    "decisions": """SELECT id,recorded_at,
        coalesce(payload->>'direction','unclassified'),
        coalesce(payload->>'marketEvaluable','unclassified')
        FROM bob_decision_audit
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
          AND recorded_at<%s::timestamptz
        ORDER BY recorded_at,id LIMIT %s""",
}
_LOCK_NAME = "bob-history-evaluation-v1"
_THREAD = None
_START_LOCK = threading.Lock()


def init(conn):
    """Separate small result journal; never change existing source tables."""
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_history_eval_cursor (
        area TEXT PRIMARY KEY, last_at TIMESTAMPTZ NOT NULL,
        last_id TEXT NOT NULL, processed BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK(area IN ('diagnoses','decisions')))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_history_eval_segments (
        page_sha256 TEXT PRIMARY KEY, area TEXT NOT NULL,
        first_at TIMESTAMPTZ NOT NULL, last_at TIMESTAMPTZ NOT NULL,
        rows_count INTEGER NOT NULL CHECK(rows_count BETWEEN 1 AND 400),
        categories JSONB NOT NULL, outcomes JSONB NOT NULL,
        captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        source_status TEXT NOT NULL
            CHECK(source_status='sampled-original-not-replayed'))""")


def summarize(area, rows):
    """Hash original source identity + its recorded labels without copying it."""
    if area not in _AREAS or not isinstance(rows,list) or len(rows)>PAGE_ROWS:
        raise ValueError("Invalid evaluation page")
    allowed = __import__("storage_knowledge")._ALLOWED[area]
    categories, outcomes = Counter(), Counter()
    digest = hashlib.sha256()
    digest.update(area.encode('ascii') + b'\n')
    previous = None
    for row in rows:
        if (type(row) not in (list,tuple) or len(row)!=4 or
                type(row[0]) is not str or not row[0] or
                not isinstance(row[1],datetime) or row[1].tzinfo is None):
            raise ValueError("Invalid source tuple")
        key = (row[1], row[0])
        if previous is not None and key <= previous:
            raise ValueError("Unsorted or duplicated source")
        previous = key
        category = row[2] if type(row[2]) is str and row[2] in allowed[0] else "unclassified"
        outcome = row[3] if type(row[3]) is str and row[3] in allowed[1] else "unclassified"
        categories[category] += 1
        outcomes[outcome] += 1
        # No source IDs, raw JSON or prices in the stored summary/manifest.
        digest.update(json.dumps((row[0], row[1].isoformat(), category, outcome),
                                 ensure_ascii=True, separators=(",",":")).encode())
        digest.update(b"\n")
    return {"rows":len(rows), "categories":dict(sorted(categories.items())),
            "outcomes":dict(sorted(outcomes.items())),
            "digest":digest.hexdigest() if rows else None}


def capture(conn, now=None):
    """One max-400-row page per area per call, each in an atomic transaction."""
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    cutoff = now.astimezone(timezone.utc) - timedelta(days=_STABLE_DAYS)
    result = {}
    for area in _AREAS:
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='2500ms'")
                conn.execute("SET LOCAL lock_timeout='300ms'")
                got = conn.execute(
                    "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
                    (_LOCK_NAME+"-"+area,)).fetchone()
                if got != (True,):
                    result[area] = "busy"
                    continue
                state = conn.execute("""SELECT last_at,last_id,processed
                    FROM bob_history_eval_cursor WHERE area=%s FOR UPDATE""",
                                     (area,)).fetchone()
                last_at,last_id,processed = (state if state else
                    (datetime(1970,1,1,tzinfo=timezone.utc),"",0))
                rows = conn.execute(_SOURCES[area],
                                    (last_at,last_id,cutoff,PAGE_ROWS)).fetchall()
                page = summarize(area,rows)
                if not rows:
                    result[area] = "caught-up-as-observed"
                    continue
                tail_at, tail_id = rows[-1][1], rows[-1][0]
                # Atomic journal + cursor; no partial page can count as complete.
                conn.execute("""INSERT INTO bob_history_eval_segments
                    (page_sha256,area,first_at,last_at,rows_count,
                     categories,outcomes,source_status)
                    VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,
                           'sampled-original-not-replayed')
                    ON CONFLICT(page_sha256) DO NOTHING""",
                    (page["digest"],area,rows[0][1],tail_at,page["rows"],
                     json.dumps(page["categories"],sort_keys=True),
                     json.dumps(page["outcomes"],sort_keys=True)))
                conn.execute("""INSERT INTO bob_history_eval_cursor
                    (area,last_at,last_id,processed)
                    VALUES(%s,%s,%s,%s)
                    ON CONFLICT(area) DO UPDATE
                    SET last_at=excluded.last_at,last_id=excluded.last_id,
                        processed=excluded.processed,updated_at=now()""",
                    (area,tail_at,tail_id,processed+page["rows"]))
                result[area] = "page-recorded"
        except Exception:
            # No source IDs, SQL errors or account details escape.
            result[area] = "deferred"
    return {"status":"observed", "areas":result,
            "readOnlySources":True, "deletionAuthorized":False,
            "physicalBytesFreed":None}


def report(conn):
    """Compact read-only coverage; no raw keys or unverifiable success claims."""
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='500ms'")
            rows=conn.execute("""SELECT area,processed,updated_at FROM
                bob_history_eval_cursor WHERE area IN ('diagnoses','decisions')
                ORDER BY area LIMIT 2""").fetchall()
        coverage={area:{"processedRows":n, "updatedAt":str(at)}
                  for area,n,at in rows if area in _AREAS and
                  type(n) is int and 0<=n<=10**12}
        return {"status":"observed" if coverage else "warming",
                "areas":coverage, "pageSize":PAGE_ROWS,
                "sourceCoverage":"forward-pages-only-no-independently-replayed-completeness",
                "sourceRowsChangedByThisWorker":False, "deletionAuthorized":False,
                "physicalBytesFreed":None}
    except Exception:
        return {"status":"not-observed", "deletionAuthorized":False,
                "physicalBytesFreed":None}


def run_once(factory=None):
    """Dedicated autocommit connection, separate from signal/market workers."""
    if factory is None:
        factory=__import__("cold_metrics").connect
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError("Autocommit connection required")
        return capture(conn)


def start():
    """Slow best-effort backlog evaluation with no source mutation."""
    global _THREAD
    if (not os.environ.get("DATABASE_URL") or
            os.environ.get("BOB_HISTORY_EVALUATIONS_DISABLED")=="1"):
        return
    with _START_LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(180)
            while True:
                try:
                    if __import__("archive_worker").status().get("status")=="running":
                        result={"areas":{},"status":"archive-running"}
                    else:
                        result=run_once()
                except Exception:
                    result={"areas":{},"status":"deferred"}
                states=result.get("areas") or {}
                print("BOB_HISTORY_EVALUATION "+json.dumps({
                    "status":result["status"],
                    "pagesRecorded":sum(v=="page-recorded" for v in states.values()),
                    "deferred":sum(v in ("busy","deferred") for v in states.values()),
                    "sourceRowsChangedByThisWorker":False,"deletionAuthorized":False},
                    sort_keys=True),flush=True)
                time.sleep(900)
        _THREAD=threading.Thread(target=loop,name="bob-history-evaluation",
                                 daemon=True)
        _THREAD.start()
