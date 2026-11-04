"""Capped, resumable improvement-history labels; no source mutation or pruning.

The campaign/slot primary-key cursor is forward only: edits or backfilled
observations can invalidate the digest. The journal is NOT independent replay,
proof of a better strategy, archive permission, or physically reclaimed space.
"""
from collections import Counter
import hashlib
import json
import os
import threading
import time

PAGE_ROWS = 128
_THREAD = None
_START_LOCK = threading.Lock()
_STATES = frozenset(("verified", "rejected", "pending", "completed",
                     "failed", "testing", "unclassified"))
_SQL = """SELECT campaign,slot,coalesce(payload->>'status','unclassified')
    FROM bob_improvement_observations
    WHERE (campaign,slot)>(%s::text,%s::bigint)
    ORDER BY campaign,slot LIMIT %s"""
_LOCK = "bob-improvement-evaluation-v1"


def summarize(rows):
    """Bounded digest/labels; no original payload or campaign IDs in results."""
    if type(rows) is not list or len(rows)>PAGE_ROWS:
        raise ValueError("Invalid improvement page")
    counts = Counter()
    digest = hashlib.sha256(b"bob-improvement-v1\n")
    previous = None
    for row in rows:
        if (type(row) not in (tuple,list) or len(row)!=3 or
                type(row[0]) is not str or not 1<=len(row[0])<=256 or
                type(row[1]) is not int or not -(2**63)<=row[1]<2**63):
            raise ValueError("Unverifiable improvement source")
        key = (row[0],row[1])
        if previous is not None and key<=previous:
            raise ValueError("Unsorted or repeated improvement source")
        previous = key
        state = row[2] if type(row[2]) is str and row[2] in _STATES else "unclassified"
        counts[state]+=1
        digest.update(json.dumps([row[0],row[1],state],separators=(",",":"),
                                 ensure_ascii=True).encode("utf8"))
        digest.update(b"\n")
    return {"records":len(rows), "counts":dict(sorted(counts.items())),
            "fingerprint":digest.hexdigest() if rows else None}


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_improvement_eval_cursor (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        last_campaign TEXT NOT NULL, last_slot BIGINT NOT NULL,
        processed BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_improvement_eval_segments (
        fingerprint_sha256 TEXT PRIMARY KEY,
        records INTEGER NOT NULL CHECK(records BETWEEN 1 AND 128),
        counts JSONB NOT NULL,
        captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        source_status TEXT NOT NULL
            CHECK(source_status='forward-labels-not-replayed'))""")


def capture(conn):
    """Only a single indexed page and an atomic digest/cursor commit per call."""
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='2500ms'")
        conn.execute("SET LOCAL lock_timeout='300ms'")
        locked=conn.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))",
                            (_LOCK,)).fetchone()
        if locked!=(True,):
            return {"status":"busy","deletionAuthorized":False}
        state=conn.execute("""SELECT last_campaign,last_slot,processed
            FROM bob_improvement_eval_cursor WHERE singleton=1
            FOR UPDATE""").fetchone()
        last_campaign,last_slot,processed=(
            state if state else ("",-(2**63),0))
        rows=conn.execute(_SQL,(last_campaign,last_slot,PAGE_ROWS)).fetchall()
        page=summarize(rows)
        if not rows:
            return {"status":"caught-up-as-observed", "processed":0,
                    "sourceRowsChanged":False,"fullHistoryVerified":False,
                    "deletionAuthorized":False,"physicalBytesFreed":None}
        conn.execute("""INSERT INTO bob_improvement_eval_segments
            (fingerprint_sha256,records,counts,source_status)
            VALUES(%s,%s,%s::jsonb,'forward-labels-not-replayed')
            ON CONFLICT(fingerprint_sha256) DO NOTHING""",
            (page["fingerprint"],page["records"],
             json.dumps(page["counts"],sort_keys=True)))
        conn.execute("""INSERT INTO bob_improvement_eval_cursor
            (singleton,last_campaign,last_slot,processed) VALUES(1,%s,%s,%s)
            ON CONFLICT(singleton) DO UPDATE SET
            last_campaign=excluded.last_campaign,last_slot=excluded.last_slot,
            processed=excluded.processed,updated_at=now()""",
            (rows[-1][0],rows[-1][1],processed+len(rows)))
    return {"status":"page-recorded","processed":len(rows),
            "sourceRowsChanged":False, "fullHistoryVerified":False,
            "deletionAuthorized":False,"physicalBytesFreed":None}


def report(conn):
    """Never expose campaign names, slot values, or private source contents."""
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='500ms'")
            row=conn.execute("""SELECT processed
                FROM bob_improvement_eval_cursor WHERE singleton=1""").fetchone()
        count=row[0] if row and type(row[0]) is int and 0<=row[0]<=10**12 else None
        return {"status":"observed" if count is not None else "warming",
                "processedRecords":count, "sourceCoverage":"forward-only-not-replayed",
                "improvementVerified":False,"fullHistoryVerified":False,
                "deletionAuthorized":False,"physicalBytesFreed":None}
    except Exception:
        return {"status":"not-observed","processedRecords":None,
                "improvementVerified":False,"fullHistoryVerified":False,
                "deletionAuthorized":False,"physicalBytesFreed":None}


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
            "BOB_IMPROVEMENT_EVAL_DISABLED")=="1":
        return
    with _START_LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(360)
            while True:
                try:
                    if __import__("archive_worker").status().get("status")=="running":
                        outcome={"status":"archive-running"}
                    else:
                        outcome=run_once()
                except Exception:
                    outcome={"status":"deferred"}
                print("BOB_IMPROVEMENT_EVALUATION "+json.dumps({
                    "status":outcome["status"],"sourceRowsChanged":False,
                    "deletionAuthorized":False},sort_keys=True),flush=True)
                time.sleep(900)
        _THREAD=threading.Thread(target=loop,name="bob-improvement-evaluation",
                                 daemon=True)
        _THREAD.start()
