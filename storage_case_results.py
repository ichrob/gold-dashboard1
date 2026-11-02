"""Immutable, bounded model-gross receipts for settled virtual paper cases.

Original virtual trade, entry/exit quote, clocks, paper control, and event JSON
remain in their existing tables. These receipts are NOT broker executions,
net profits, verified source quotes, or permission to delete/repack originals.
"""
import hashlib
import json
import math
import re

# Fixed names only: never construct a table name from a request or stored data.
_PROFILES = ("conservative", "balanced", "offensive", "early100",
             "trend800", "early1000oct", "normal1000oct")
_PAGE = 8
_RECEIPT = "model-gross-arithmetic-consistent-v1"
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


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
    """Bounded one-pass check; never change/delete source cases.

    The 7 isolated ledgers and legacy ledger each contribute at most 8 newest
    cases. A full page is not a full population audit. Failed/missing ledgers
    remain unavailable and do not lead to a false result or deletion.
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
                rows = conn.execute(
                    "SELECT id,day,started_at,closed_at,payload FROM "
                    + table + " ORDER BY started_at DESC LIMIT %s",
                    (_PAGE,)).fetchall()
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
                                or str(old[2]) != receipt["grossPct"]):
                            conflicts += 1
                        else:
                            existing += 1
                results[profile] = {
                    "status": "source-mismatch" if conflicts else "checked",
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
            "scope": "latest-eight-per-paper-ledger-no-full-history-risk2000-excluded",
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
