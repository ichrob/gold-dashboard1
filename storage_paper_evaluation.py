"""Compact daily evaluation of immutable *model-gross-only* paper receipts.

Receipts have already passed strict closed-paper arithmetic checks elsewhere.
Never infer DEGIRO fills, net returns, source-quote validity or trade winners.
Source cases and receipts are never removed/changed by this module.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
import re
import threading
import time

_PAGE = 256
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_STATUS = "model-gross-arithmetic-consistent-v1"
_PROFILES = ("legacy","conservative","balanced","offensive","early100",
             "trend800","early1000oct","normal1000oct",
             "trend800nov","normal1000nov", "noema5000nov")
_THREAD = None
_LOCK = threading.Lock()
_QUERY = """SELECT profile,case_id,day,captured_at,original_sha256,
            result_kind,gross_pct
    FROM bob_paper_final_receipts
    WHERE (captured_at,profile,case_id)>(%s::timestamptz,%s::text,%s::text)
      AND captured_at<%s::timestamptz
    ORDER BY captured_at,profile,case_id LIMIT %s"""


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_paper_eval_daily (
        profile TEXT NOT NULL,day TEXT NOT NULL,
        source_receipts BIGINT NOT NULL DEFAULT 0,
        positive INTEGER NOT NULL DEFAULT 0,
        negative INTEGER NOT NULL DEFAULT 0,
        flat INTEGER NOT NULL DEFAULT 0,
        unclassified INTEGER NOT NULL DEFAULT 0,
        receipt_chain_sha256 TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(profile,day))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_paper_eval_cursor (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        captured_at TIMESTAMPTZ NOT NULL,
        profile TEXT NOT NULL,case_id TEXT NOT NULL,
        processed BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def classify(receipt):
    """Only known validated arithmetic receipts may contribute to sign counts."""
    if type(receipt) not in (tuple,list) or len(receipt)!=7:
        raise ValueError("Invalid receipt")
    profile,case_id,day,at,original_sha,kind,gross=receipt
    if (profile not in _PROFILES or type(case_id) is not str or not case_id
            or type(day) is not str or not _DAY.fullmatch(day)
            or not isinstance(at,datetime) or at.tzinfo is None):
        raise ValueError("Invalid identity/clock")
    if (type(original_sha) is not str or
            re.fullmatch("[0-9a-f]{64}",original_sha) is None):
        raise ValueError("Invalid receipt digest")
    try:
        gross_decimal = Decimal(str(gross))
    except Exception:
        gross_decimal = Decimal("NaN")
    if kind!=_STATUS or not gross_decimal.is_finite():
        label="unclassified"
    else:
        label="positive" if gross_decimal>0 else "negative" if gross_decimal<0 else "flat"
    # Hash binds the original final receipt and its model-only math label.
    digest=hashlib.sha256(json.dumps(
        (profile,case_id,day,at.isoformat(),original_sha,kind,str(gross)),
        separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
    return profile,day,label,digest


def fold(receipts):
    if type(receipts) is not list or len(receipts)>_PAGE:
        raise ValueError("Unbounded paper page")
    grouped=defaultdict(lambda:dict(positive=0,negative=0,flat=0,
                                    unclassified=0,digests=[]))
    previous=None
    for row in receipts:
        group_day=classify(row)
        cursor=(row[3],row[0],row[1])
        if previous is not None and cursor<=previous:
            raise ValueError("Unsorted paper source")
        previous=cursor
        profile,day,label,digest=group_day
        item=grouped[(profile,day)]
        item[label]+=1
        item["digests"].append(digest)
    return grouped


def capture(conn,now=None):
    now=datetime.now(timezone.utc) if now is None else now
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware now required")
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='2500ms'")
        conn.execute("SET LOCAL lock_timeout='300ms'")
        acquired=conn.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))",
                              ("bob-paper-evaluation-v1",)).fetchone()
        if acquired!=(True,):
            return {"status":"busy","deletionAuthorized":False}
        existing=conn.execute("""SELECT captured_at,profile,case_id,processed
            FROM bob_paper_eval_cursor WHERE singleton=1 FOR UPDATE""").fetchone()
        lower=existing if existing else (
            datetime(1970,1,1,tzinfo=timezone.utc),"","",0)
        rows=conn.execute(_QUERY,(lower[0],lower[1],lower[2],
                                 now-timedelta(minutes=5),_PAGE)).fetchall()
        groups=fold(rows)
        for (profile,day),item in groups.items():
            prior=conn.execute("""SELECT source_receipts,positive,negative,
                flat,unclassified,receipt_chain_sha256
                FROM bob_paper_eval_daily WHERE profile=%s AND day=%s
                FOR UPDATE""",(profile,day)).fetchone()
            old=prior if prior else (0,0,0,0,0,"0"*64)
            # Each original receipt is fed to the chain in canonical order.
            chain=hashlib.sha256(bytes.fromhex(old[5]))
            for piece in item["digests"]:
                chain.update(bytes.fromhex(piece))
            total=old[0]+len(item["digests"])
            values=(total,old[1]+item["positive"],old[2]+item["negative"],
                    old[3]+item["flat"],old[4]+item["unclassified"],chain.hexdigest())
            conn.execute("""INSERT INTO bob_paper_eval_daily
                (profile,day,source_receipts,positive,negative,flat,
                 unclassified,receipt_chain_sha256)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(profile,day) DO UPDATE SET
                source_receipts=excluded.source_receipts,
                positive=excluded.positive,negative=excluded.negative,
                flat=excluded.flat,unclassified=excluded.unclassified,
                receipt_chain_sha256=excluded.receipt_chain_sha256,
                updated_at=now()""",(profile,day,*values))
        if rows:
            last=rows[-1]
            conn.execute("""INSERT INTO bob_paper_eval_cursor
                (singleton,captured_at,profile,case_id,processed)
                VALUES(1,%s,%s,%s,%s)
                ON CONFLICT(singleton) DO UPDATE SET
                captured_at=excluded.captured_at,profile=excluded.profile,
                case_id=excluded.case_id,processed=excluded.processed,
                updated_at=now()""",(last[3],last[0],last[1],
                                    lower[3]+len(rows)))
    return {"status":"page-recorded" if rows else "caught-up-as-observed",
            "processed":len(rows), "grossModelOnly":True,
            "fullHistoryVerified":False,"netProfitVerified":False,
            "sourceRowsModified":False,"deletionAuthorized":False,
            "physicalBytesFreed":None}


def report(conn):
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='500ms'")
            row=conn.execute("SELECT processed FROM bob_paper_eval_cursor "
                             "WHERE singleton=1").fetchone()
        processed=row[0] if row and type(row[0]) is int else 0
        return {"status":"observed" if row else "warming","processedReceipts":processed,
                "grossModelOnly":True,"netProfitVerified":False,
                "fullHistoryVerified":False,"deletionAuthorized":False,
                "physicalBytesFreed":None}
    except Exception:
        return {"status":"not-observed","deletionAuthorized":False,
                "physicalBytesFreed":None}


@__import__("ocr_workload_priority").maintenance
def run_once(factory=None):
    if factory is None:
        factory=__import__("cold_metrics").connect
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError("Dedicated autocommit required")
        return capture(conn)


def start():
    global _THREAD
    if (not os.environ.get("DATABASE_URL") or
            os.environ.get("BOB_PAPER_EVAL_DISABLED")=="1"):
        return
    with _LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(210)
            while True:
                try:
                    if __import__("archive_worker").status().get("status")=="running":
                        result={"status":"archive-running"}
                    else:
                        result=run_once()
                except Exception:
                    result={"status":"deferred"}
                print("BOB_PAPER_EVALUATION "+json.dumps({
                    "status":result["status"],"grossModelOnly":True,
                    "deletionAuthorized":False},sort_keys=True),flush=True)
                time.sleep(900)
        _THREAD=threading.Thread(target=loop,name="bob-paper-evaluation",
                                 daemon=True)
        _THREAD.start()
