"""Bounded comparison of already-restored original rows with immutable page manifests.

ISOLATED TEST / DRAFT ONLY. No CLI, service import, scheduler, Google Drive fetch,
archive operation, restoration, SQL write, data migration or deletion.

Callers must separately establish that the input rows came from the exact,
previously verified encrypted original archive on a different DB instance.
This helper cannot establish that provenance and NEVER grants full-history
verification, batch release, original replacement or physical savings.

The reviewed-evidence archive's current restore_check uses rolled-back
temporary tables. A past successful restore receipt does not leave a queryable
historical original table. A separately authorized isolated materialization
and immutable evaluation-manifest snapshot are prerequisites to using this
helper on real historical data.
"""
from datetime import datetime, timezone
import time

import storage_history_replay as independent

MAX_PAGES = 16
MAX_SECONDS = 15
QUERY_TIMEOUT_MS = 1500
READS = {
    "diagnoses": """SELECT id,recorded_at,stage,
        coalesce(payload->>'outcome','unclassified')
        FROM bob_diagnostic_history
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
        ORDER BY recorded_at,id LIMIT %s""",
    "decisions": """SELECT id,recorded_at,
        coalesce(payload->>'direction','unclassified'),
        coalesce(payload->>'marketEvaluable','unclassified')
        FROM bob_decision_audit
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
        ORDER BY recorded_at,id LIMIT %s""",
}


def _result(status, rows=0, pages=0):
    """Only safe counts and fixed statuses: never emit source IDs or clocks."""
    return {
        "status": status,
        "scope": "bounded-scalar-replay-against-operator-supplied-restored-rows",
        "replayedRows": rows,
        "matchedPages": pages,
        "fullOriginalReplayVerified": False,
        "archiveFileAndBatchBoundVerified": False,
        "restoreIsolationVerifiedByThisCheck": False,
        "sourceRowsModified": False,
        "deletionAuthorized": False,
        "physicalBytesFreed": None,
    }


def compare(conn, area, manifests, *, expected_rows, start=None, clock=time.monotonic):
    """Recompute exact page digests from a read-only, PRE-EXISTING source snapshot.

    The immutable manifest tuples have the preexisting format
    (digest, rows_count, categories, outcomes, first_at, last_at). They MUST
    be supplied in exact capture order from a separately authenticated
    evaluator-manifest snapshot. No manifest or original is fetched here.

    A matching digest proves only that these provided pages agree. It does
    NOT prove the source is the authenticated Drive archive or complete.
    """
    if (area not in READS or type(manifests) is not list or
            not 1 <= len(manifests) <= MAX_PAGES or
            type(expected_rows) is not int or not 1 <= expected_rows <=
                MAX_PAGES * independent.PAGE_ROWS):
        return _result("invalid-or-unbounded-request")
    if start is None:
        lower = (datetime(1970, 1, 1, tzinfo=timezone.utc), "")
    else:
        if (type(start) is not tuple or len(start) != 2 or
                not isinstance(start[0], datetime) or
                start[0].tzinfo is None or
                type(start[1]) is not str):
            return _result("invalid-or-unbounded-request")
        lower = start

    if any(type(m) not in (tuple, list) or len(m) != 6 or
           type(m[0]) is not str or len(m[0]) != 64 or
           type(m[1]) is not int or not 1 <= m[1] <= independent.PAGE_ROWS or
           not isinstance(m[4], datetime) or m[4].tzinfo is None or
           not isinstance(m[5], datetime) or m[5].tzinfo is None or
           m[4] > m[5] for m in manifests):
        return _result("invalid-or-unbounded-request")
    if sum(m[1] for m in manifests) != expected_rows:
        return _result("manifest-count-mismatch")

    count = pages = 0
    try:
        with conn.transaction():
            mode = conn.execute("SHOW transaction_read_only").fetchone()
            if not mode or mode[0] != "on":
                return _result("read-only-required")
            conn.execute("SET LOCAL statement_timeout='1500ms'")
            conn.execute("SET LOCAL lock_timeout='200ms'")
            deadline = clock() + MAX_SECONDS
            for manifest in manifests:
                if clock() >= deadline:
                    return _result("time-budget-exceeded", count, pages)
                rows = conn.execute(READS[area], (*lower, manifest[1])).fetchall()
                if not isinstance(rows, list) or not rows:
                    return _result("restored-original-page-missing", count, pages)
                # Strictly increasing across pages, including duplicate
                # timestamps with distinct original identifiers.
                if (rows[0][1], rows[0][0]) <= lower:
                    return _result("restored-source-not-monotonic", count, pages)
                if not independent.matches_manifest(area, rows, manifest):
                    return _result("original-or-manifest-mismatch", count, pages)
                last_key = (rows[-1][1], rows[-1][0])
                if last_key <= lower:
                    return _result("restored-source-not-monotonic", count, pages)
                count += len(rows)
                pages += 1
                lower = last_key
        return _result("matching-pages-provenance-unverified", count, pages)
    except Exception:
        # Never include SQL, rows, original IDs, query errors or DSNs.
        return _result("unavailable", count, pages)
