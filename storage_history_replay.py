"""Operator-only independent replay of immutable history evaluation projections.

Recomputes source-page fingerprints from a repeatable-read, read-only database
snapshot, independently of the writer's summarizer. Compares every stored page
manifest and cursor before reporting coverage. This is NOT an original JSON,
cold-reader or isolated Drive restore, and never authorizes archival mutation.

Usage (in an existing authorized runtime): python -m storage_history_replay inspect
No startup hook, background worker, public route, DDL or source updates.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import sys
import time

PAGE_ROWS = 400
MAX_PAGES = 200
AREAS = ("diagnoses", "decisions")
ALLOWED = {
    "diagnoses": (
        frozenset(("transport", "input", "analysis", "analysis-failed",
                   "push", "push-delivery", "paper-input", "health")),
        frozenset(("ok", "completed", "failed", "error", "ready", "sent",
                   "skipped", "unavailable", "success", "not-ready"))),
    "decisions": (
        frozenset(("LONG", "SHORT", "WAIT", "ABWARTEN", "NEUTRAL")),
        frozenset(("true", "false"))),
}
# Independent SQL projection, deliberately not imported from the capture worker.
SOURCE_SQL = {
    "diagnoses": """SELECT id,recorded_at,stage,
        coalesce(payload->>'outcome','unclassified')
        FROM bob_diagnostic_history
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
          AND (recorded_at,id)<=(%s::timestamptz,%s::text)
        ORDER BY recorded_at,id LIMIT %s""",
    "decisions": """SELECT id,recorded_at,
        coalesce(payload->>'direction','unclassified'),
        coalesce(payload->>'marketEvaluable','unclassified')
        FROM bob_decision_audit
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
          AND (recorded_at,id)<=(%s::timestamptz,%s::text)
        ORDER BY recorded_at,id LIMIT %s""",
}
TAIL_SQL = {
    "diagnoses": """SELECT id FROM bob_diagnostic_history
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
        AND recorded_at<%s::timestamptz
        ORDER BY recorded_at,id LIMIT 1""",
    "decisions": """SELECT id FROM bob_decision_audit
        WHERE (recorded_at,id)>(%s::timestamptz,%s::text)
        AND recorded_at<%s::timestamptz
        ORDER BY recorded_at,id LIMIT 1""",
}


def replay_page(area, rows):
    """Independent canonical projection digest, without exporting source IDs."""
    if area not in AREAS or not isinstance(rows, list) or len(rows) > PAGE_ROWS:
        raise ValueError("Invalid replay page")
    categories, outcomes = Counter(), Counter()
    digest = hashlib.sha256()
    digest.update(area.encode("ascii") + b"\n")
    previous = None
    for row in rows:
        if (type(row) not in (tuple, list) or len(row) != 4 or
                type(row[0]) is not str or not row[0] or
                not isinstance(row[1], datetime) or row[1].tzinfo is None):
            raise ValueError("Invalid replay source")
        key = (row[1], row[0])
        if previous is not None and key <= previous:
            raise ValueError("Replay source out of order")
        previous = key
        category = row[2] if type(row[2]) is str and row[2] in ALLOWED[area][0] else "unclassified"
        outcome = row[3] if type(row[3]) is str and row[3] in ALLOWED[area][1] else "unclassified"
        categories[category] += 1
        outcomes[outcome] += 1
        digest.update(json.dumps((row[0], row[1].isoformat(), category, outcome),
                                 ensure_ascii=True, separators=(",", ":")).encode())
        digest.update(b"\n")
    return {"rows": len(rows), "categories": dict(sorted(categories.items())),
            "outcomes": dict(sorted(outcomes.items())),
            "digest": digest.hexdigest() if rows else None}


def matches_manifest(area, rows, manifest):
    """A stored manifest is not verified merely because its row count matches."""
    if type(manifest) not in (tuple, list) or len(manifest) != 6 or not rows:
        return False
    sha, count, categories, outcomes, first_at, last_at = manifest
    page = replay_page(area, rows)
    return (type(sha) is str and len(sha) == 64 and
            type(count) is int and page["rows"] == count and
            page["digest"] == sha and
            page["categories"] == categories and page["outcomes"] == outcomes and
            first_at == rows[0][1] and last_at == rows[-1][1])


def inspect_area(conn, area, cutoff, *, max_pages=MAX_PAGES, deadline=None):
    """Replay all manifests up to the durable cursor; report stable-tail gaps."""
    if area not in AREAS or type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES:
        raise ValueError("Invalid replay limit")
    cursor = conn.execute("""SELECT last_at,last_id,processed
        FROM bob_history_eval_cursor WHERE area=%s""", (area,)).fetchone()
    if not cursor:
        return {"status": "not-started", "replayedRows": 0}
    end_at, end_id, expected_rows = cursor
    if (not isinstance(end_at, datetime) or end_at.tzinfo is None or
            type(end_id) is not str or not end_id or
            type(expected_rows) is not int or expected_rows <= 0 or
            end_at >= cutoff):
        return {"status": "invalid-or-unstable-cursor", "replayedRows": 0}
    # Fixed upper bound; never load an unbounded metadata or source table.
    segments = conn.execute("""SELECT page_sha256,rows_count,categories,outcomes,
        first_at,last_at FROM bob_history_eval_segments WHERE area=%s
        ORDER BY captured_at,page_sha256 LIMIT %s""",
        (area, max_pages + 1)).fetchall()
    if len(segments) > max_pages:
        return {"status": "page-budget-exceeded", "replayedRows": 0,
                "manifestPagesAtLeast": len(segments)}
    if (not segments or
            any(type(x[1]) is not int or not 1 <= x[1] <= PAGE_ROWS
                for x in segments) or
            sum(x[1] for x in segments) != expected_rows):
        return {"status": "manifest-count-mismatch", "replayedRows": 0}
    lower_at, lower_id = datetime(1970, 1, 1, tzinfo=timezone.utc), ""
    count = 0
    for manifest in segments:
        if deadline is not None and time.monotonic() >= deadline:
            return {"status": "time-budget-exceeded", "replayedRows": count}
        # A capture can record fewer than 400 rows when catching up; later
        # pages must not be pulled into that older manifest's replay window.
        # The persisted count is bound by the validated page budget above.
        rows = conn.execute(SOURCE_SQL[area],
                            (lower_at, lower_id, end_at, end_id, manifest[1])).fetchall()
        if not matches_manifest(area, rows, manifest):
            return {"status": "source-or-manifest-mismatch", "replayedRows": count}
        count += len(rows)
        lower_at, lower_id = rows[-1][1], rows[-1][0]
    if count != expected_rows or (lower_at, lower_id) != (end_at, end_id):
        return {"status": "cursor-mismatch", "replayedRows": count}
    # The source may have grown since the final captured page. A verified prefix
    # must never be presented as complete stable-history coverage.
    pending = conn.execute(TAIL_SQL[area], (end_at, end_id, cutoff)).fetchone()
    return {"status": ("verified-prefix-catchup-pending" if pending else
                       "verified-stable-projection"),
            "replayedRows": count, "manifestPages": len(segments)}


def inspect(conn, now=None, *, max_pages=MAX_PAGES):
    """One repeatable-read snapshot; status is never a source deletion grant."""
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Aware clock required")
    cutoff = now.astimezone(timezone.utc) - timedelta(days=2)
    output = {"status": "partial", "scope": "independent-scalar-projections-only",
              "areas": {}, "fullOriginalReplayVerified": False,
              "batchBoundRestoreVerified": False, "deletionAuthorized": False,
              "sourceRowsModified": False, "physicalBytesFreed": None}
    try:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout='2500ms'")
            conn.execute("SET LOCAL lock_timeout='300ms'")
            deadline = time.monotonic() + 20
            for area in AREAS:
                output["areas"][area] = inspect_area(
                    conn, area, cutoff, max_pages=max_pages, deadline=deadline)
        if all(output["areas"][a]["status"] == "verified-stable-projection"
               for a in AREAS):
            output["status"] = "projections-verified-only"
    except Exception:
        # A failed snapshot cannot produce a permission or leak source fields.
        output["status"] = "unavailable"
        output["areas"] = {}
    return output


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["inspect"]:
        print("Usage: python -m storage_history_replay inspect")
        return 2
    try:
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=8,
                application_name="bob_independent_history_replay",
                options="-c default_transaction_read_only=on -c statement_timeout=2500") as conn:
            report = inspect(conn)
    except Exception:
        report = {"status": "unavailable", "scope": "independent-scalar-projections-only",
                  "fullOriginalReplayVerified": False,
                  "deletionAuthorized": False, "physicalBytesFreed": None}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "projections-verified-only" else 3


if __name__ == "__main__":
    raise SystemExit(main())
