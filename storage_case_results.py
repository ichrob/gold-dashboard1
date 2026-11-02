"""Immutable, bounded model-gross receipts for settled virtual paper cases.

Original virtual trade, entry/exit quote, clocks, paper control, and event JSON
remain in their existing tables. These receipts are NOT broker executions,
net profits, verified source quotes, or permission to delete/repack originals.
"""
import hashlib
import json
import math
import re
import os
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

# Fixed names only: never construct a table name from a request or stored data.
_PROFILES = ("conservative", "balanced", "offensive", "early100",
             "trend800", "early1000oct", "normal1000oct")
_PAGE = 8
_RECEIPT = "model-gross-arithmetic-consistent-v1"
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_THREAD = None
_START_LOCK = threading.Lock()


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_paper_final_receipts (
        profile TEXT NOT NULL,
        case_id TEXT NOT NULL,
        day TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL,
        closed_at TIMESTAMPTZ NOT NULL,
        original_sha256 TEXT NOT NULL,
        result_kind TEXT NOT NULL,
        gross_pct NUMERIC NOT NULL,
        captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(profile,case_id))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS bob_paper_final_receipts_recent
        ON bob_paper_final_receipts(captured_at DESC)""")
    # Immutable receipts are separate from the bounded, restartable scan.
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_paper_final_receipt_scan (
        profile TEXT PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL,
        case_id TEXT NOT NULL)""")


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def qualify(profile, row):
    """Cross-check only final arithmetic with original data, never infer a fill.

    Do not convert inconclusive, missing-exit, KO-unknown, no-trade or active
    cases into finalized outcomes. In particular, netReturnKnown=true would
    need a separate verified fee methodology and is NOT accepted here.
    """
    if profile not in ("legacy", *_PROFILES) or len(row) != 5:
        raise ValueError("Unexpected paper source")
    key, day, started, closed, original = row
    if (not isinstance(key, str) or not key or not isinstance(day, str)
            or not _DAY.fullmatch(day) or started is None or closed is None
            or not isinstance(original, dict)
            or original.get("status") != "closed"
            or original.get("modelOnly") is not True
            or original.get("productReturnKnown") is not True
            or original.get("netReturnKnown") is not False
            or original.get("pendingUnits") != 0
            or original.get("remainingUnits") != 0
            or original.get("remaining") not in (0, 0.0)):
        return None
    quantity = original.get("quantity")
    booked = original.get("bookedUnits")
    if (type(quantity) is not int or quantity <= 0
            or type(booked) is not int or booked != quantity):
        return None
    allocated = original.get("allocated")
    released = original.get("cashReleased")
    reported = original.get("productGrossPct")
    if (not all(_finite(v) for v in (allocated, released, reported))
            or allocated <= 0 or released < 0):
        return None
    calculated = 100.0 * (released / allocated - 1.0)
    if not math.isfinite(calculated) or abs(calculated-reported) > 0.0001:
        return None
    # SHA-256 binds this compact receipt to the complete original case, its
    # original SQL clocks and source ledger. It is not a remote backup proof.
    from cold_metrics import encoded
    original_bytes = encoded([profile, key, day, started.isoformat(),
                              closed.isoformat(), original])
    return {
        "profile": profile, "caseId": key, "day": day,
        "startedAt": started, "closedAt": closed,
        "originalSha256": hashlib.sha256(original_bytes).hexdigest(),
        "resultKind": _RECEIPT,
        "grossPct": str(reported),
    }


def capture(conn):
    """Bounded restartable historical sweep; never change/delete source cases.

    Each of 7 isolated ledgers and legacy ledger contributes at most 8 source
    cases per cycle. A full page is not a full population audit. A completed
    scan restarts from the beginning to catch late-settled older cases.
    """
    import paper_portfolios
    if set(_PROFILES) != set(paper_portfolios.POLICIES):
        return {"status": "inventory-changed", "sourceWrites": 0,
                "deletionAuthorized": False, "physicalBytesFreed": None}
    candidates = [("legacy", "bob_paper_cases")] + [
        (name, paper_portfolios.names(name)["bob_paper_cases"])
        for name in _PROFILES]
    results = {}
    for profile, table in candidates:
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='1s'")
                cursor = conn.execute(
                    "SELECT started_at,case_id FROM bob_paper_final_receipt_scan "
                    "WHERE profile=%s", (profile,)).fetchone()
                lower = cursor or (datetime(1,1,1,tzinfo=timezone.utc), "")
                # Oldest-first pages eventually examine historical cases too.
                # Restarting after each complete sweep also catches cases
                # that were open when an earlier sweep passed their key.
                rows = conn.execute(
                    "SELECT id,day,started_at,closed_at,payload FROM "
                    + table + " WHERE (started_at,id)>(%s,%s) "
                    "ORDER BY started_at,id LIMIT %s",
                    (lower[0], lower[1], _PAGE)).fetchall()
                written = existing = conflicts = eligible = 0
                for row in rows:
                    receipt = qualify(profile, row)
                    if receipt is None:
                        continue
                    eligible += 1
                    inserted = conn.execute("""INSERT INTO bob_paper_final_receipts
                        (profile,case_id,day,started_at,closed_at,
                         original_sha256,result_kind,gross_pct)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(profile,case_id) DO NOTHING
                        RETURNING profile""",
                        (receipt["profile"], receipt["caseId"],
                         receipt["day"], receipt["startedAt"],
                         receipt["closedAt"], receipt["originalSha256"],
                         receipt["resultKind"], receipt["grossPct"])).fetchone()
                    if inserted:
                        written += 1
                    else:
                        old = conn.execute("""SELECT original_sha256,result_kind,
                            gross_pct,started_at,closed_at FROM
                            bob_paper_final_receipts
                            WHERE profile=%s AND case_id=%s""",
                            (profile, receipt["caseId"])).fetchone()
                        if (not old or old[0] != receipt["originalSha256"]
                                or old[1] != receipt["resultKind"]
                                or old[3] != receipt["startedAt"]
                                or old[4] != receipt["closedAt"]
                                or Decimal(str(old[2])) !=
                                Decimal(receipt["grossPct"])):
                            conflicts += 1
                        else:
                            existing += 1
                # One bounded cursor change after all original comparisons.
                # A source mismatch never authorizes any source mutation.
                if rows:
                    last = rows[-1]
                    conn.execute("""INSERT INTO bob_paper_final_receipt_scan
                        (profile,started_at,case_id) VALUES(%s,%s,%s)
                        ON CONFLICT(profile) DO UPDATE SET
                            started_at=excluded.started_at,
                            case_id=excluded.case_id""",
                        (profile,last[2],last[0]))
                else:
                    conn.execute("DELETE FROM bob_paper_final_receipt_scan "
                                 "WHERE profile=%s", (profile,))
                results[profile] = {
                    "status": "source-mismatch" if conflicts else "checked",
                    "sweepRestarted": not bool(rows),
                    "sampledRows": len(rows), "sampleCap": _PAGE,
                    "moreOlderCasesMayExist": len(rows) == _PAGE,
                    "eligibleGrossOnly": eligible, "newReceipts": written,
                    "identicalReceipts": existing, "conflicts": conflicts,
                    "netProfitVerified": False,
                }
        except Exception:
            results[profile] = {"status": "not-observed",
                                "newReceipts": 0}
    return {"status": "checked" if all(
                x["status"] == "checked" for x in results.values())
                else "partial",
            "areas": results,
            "sourceWrites": 0, "deletionAuthorized": False,
            "physicalBytesFreed": None,
            "scope": "restartable-index-cursor-eight-per-paper-ledger-risk2000-excluded",
            "note": "Arithmetic consistency for model gross percentages only. "
                    "No DEGIRO execution, verified net return, complete replay "
                    "or authority to remove original virtual trades."}


def report(conn):
    """Aggregate-only private status, no case identities or gross amounts."""
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='1s'")
            rows = conn.execute("""SELECT profile,result_kind FROM
                bob_paper_final_receipts ORDER BY captured_at DESC LIMIT 64"""
                ).fetchall()
        counts = {}
        for profile, kind in rows:
            if profile in ("legacy", *_PROFILES) and kind == _RECEIPT:
                counts[profile] = counts.get(profile, 0) + 1
        return {
            "status": "sampled" if rows else "observed-empty",
            "readOnly": True, "sampledReceipts": len(rows),
            "moreOlderReceiptsMayExist": len(rows) == 64,
            "grossOnlyReceiptsByLedger": counts,
            "netProfitVerified": False, "realOrders": False,
            "fullHistoryVerified": False, "independentRestoreVerified": False,
            "deletionAuthorized": False, "physicalBytesFreed": None,
        }
    except Exception:
        return {"status": "not-observed", "readOnly": True,
                "deletionAuthorized": False, "physicalBytesFreed": None}


def run_once(factory=None):
    """Own database connection; never block a market or diagnostic writer."""
    if factory is None:
        factory = __import__("cold_metrics").connect
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError("Dedicated autocommit connection required")
        if not conn.execute("""SELECT pg_try_advisory_lock(
            hashtext('bob-paper-final-receipts-v1'))""").fetchone()[0]:
            return {"status": "busy", "sourceWrites": 0}
        return capture(conn)


def start():
    """Periodic bounded reader/writer separate from all live trade workers."""
    global _THREAD
    if (not os.environ.get("DATABASE_URL")
            or os.environ.get("BOB_PAPER_FINAL_RECEIPTS_DISABLED") == "1"):
        return
    with _START_LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(240)
            while True:
                try:
                    if __import__("archive_worker").status().get("status") == "running":
                        outcome = {"status": "archive-running"}
                    else:
                        outcome = run_once()
                except Exception as exc:
                    outcome = {"status": "deferred", "errorType": type(exc).__name__}
                # No source IDs, prices, receipts, device data or secrets in logs.
                statuses = outcome.get("areas") or {}
                print("BOB_PAPER_FINAL_RECEIPTS "
                      + json.dumps({"status": outcome["status"],
                                    "ledgersChecked": sum(
                                        v.get("status") == "checked" for v in statuses.values()),
                                    "ledgerConflicts": sum(
                                        v.get("conflicts", 0) for v in statuses.values())},
                                   sort_keys=True), flush=True)
                time.sleep(1800)
        _THREAD = threading.Thread(target=loop, name="bob-paper-final-receipts",
                                   daemon=True)
        _THREAD.start()
