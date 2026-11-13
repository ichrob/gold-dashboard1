"""Bounded, restart-safe-enough cold-analysis candidate discovery.

No schema/index changes. The original rows remain in SQL until separately
verified remote download, checksum and compare-and-swap succeed. A module-local
scan cursor is only an optimization: a process restart begins at the oldest
row again; reaching the end wraps around. Every observed row is reconsidered
after a completed pass, so neither a failed transfer nor an older insert is
silently declared archived.

A MATERIALIZED age/stage page bounds JSONB/TOAST size checks to at most
PAGE_ROWS existing entries instead of evaluating them across years of
already-archived or ineligible history. No query executes on unbounded sets
of original JSON in one call. This is not an archive writer.
"""
import threading
import time
from datetime import datetime
import cold_metrics as codec

PAGE_ROWS = 256
MAX_SCAN_PAGES = 8
SCAN_SECONDS = 5
TAG = "_bobColdAnalysisV1"
_CURSOR = None
_CURSOR_LOCK = threading.Lock()

_PAGE_START = """WITH page AS MATERIALIZED (
    SELECT id, recorded_at FROM bob_diagnostic_history
    WHERE stage='analysis' AND recorded_at < now()-interval '6 hours'
    ORDER BY recorded_at,id LIMIT %s
)
SELECT p.id,p.recorded_at,
    CASE WHEN h.payload ? %s THEN false
         WHEN pg_column_size(h.payload)<=512 THEN false
         ELSE octet_length(h.payload::text)<65536 END AS eligible
FROM page p JOIN bob_diagnostic_history h ON h.id=p.id
ORDER BY p.recorded_at,p.id"""

_PAGE_NEXT = """WITH page AS MATERIALIZED (
    SELECT id, recorded_at FROM bob_diagnostic_history
    WHERE stage='analysis' AND recorded_at < now()-interval '6 hours'
      AND (recorded_at,id)>(%s::timestamptz,%s::text)
    ORDER BY recorded_at,id LIMIT %s
)
SELECT p.id,p.recorded_at,
    CASE WHEN h.payload ? %s THEN false
         WHEN pg_column_size(h.payload)<=512 THEN false
         ELSE octet_length(h.payload::text)<65536 END AS eligible
FROM page p JOIN bob_diagnostic_history h ON h.id=p.id
ORDER BY p.recorded_at,p.id"""

# The full JSON is read ONLY for at most one indexed page of eligible IDs.
# Repeat the original eligibility checks because a row may change between
# page selection and its indexed identity lookup.
_FETCH = """SELECT id,stage,observed_at,build,payload,recorded_at
    FROM bob_diagnostic_history
    WHERE id=ANY(%s::text[]) AND stage='analysis'
      AND recorded_at<now()-interval '6 hours'
      AND NOT(payload ? %s)
      AND pg_column_size(payload)>512 AND octet_length(payload::text)<65536
    ORDER BY recorded_at,id"""


def cursor():
    with _CURSOR_LOCK:
        return _CURSOR


def commit_cursor(next_cursor):
    """Never persist an optimization cursor as backup or deletion evidence."""
    global _CURSOR
    if next_cursor is not None:
        if (not isinstance(next_cursor, tuple) or len(next_cursor)!=2
                or not isinstance(next_cursor[0], datetime)
                or next_cursor[0].tzinfo is None
                or type(next_cursor[1]) is not str):
            raise ValueError("Invalid scanner cursor")
    with _CURSOR_LOCK:
        _CURSOR = next_cursor


def scan(conn, initial_cursor=None):
    """Yield bounded exact original candidates plus a tentative cursor.

    Caller commits the cursor only after verified offload or a confirmed
    no-eligible result. Failures never advance it. Explicit tuple ordering
    handles equal timestamps, and the cursor never appears in log output.
    """
    if initial_cursor is not None:
        if (not isinstance(initial_cursor, tuple) or len(initial_cursor)!=2
                or not isinstance(initial_cursor[0], datetime)
                or initial_cursor[0].tzinfo is None
                or type(initial_cursor[1]) is not str):
            raise ValueError("Invalid scanner cursor")
    current = initial_cursor
    rows = []
    scanned = 0
    pages = 0
    end_reached = False
    budget = len(codec.encoded({"format": codec.FORMAT, "rows": []}))
    deadline = time.monotonic() + SCAN_SECONDS
    full = False
    while pages < MAX_SCAN_PAGES and time.monotonic() < deadline:
        if current is None:
            page = conn.execute(_PAGE_START, (PAGE_ROWS, TAG)).fetchall()
        else:
            page = conn.execute(_PAGE_NEXT, (*current, PAGE_ROWS, TAG)).fetchall()
        pages += 1
        if not page:
            current = None
            end_reached = True
            break
        # Page metadata contains IDs/clocks/eligibility bits only, no JSON.
        eligible_ids = [r[0] for r in page if len(r) == 3 and r[2] is True]
        originals = {}
        if eligible_ids:
            payloads = conn.execute(_FETCH, (eligible_ids, TAG)).fetchall()
            originals = {r[0]: r for r in payloads if len(r) == 6}
        for identity, recorded_at, eligible in page:
            if type(identity) is not str or not isinstance(recorded_at, datetime) or recorded_at.tzinfo is None:
                raise ValueError("Invalid bounded scan metadata")
            if eligible is True:
                original = originals.get(identity)
                if original and original[5] == recorded_at:
                    row = list(original[:5])
                    chunk = len(codec.encoded(row)) + (1 if rows else 0)
                    if budget + chunk > codec.MAX_RAW or len(rows) >= codec.MAX_ROWS:
                        full = True
                        break  # Do not advance beyond an unprocessed candidate.
                    rows.append(row)
                    budget += chunk
            current = (recorded_at, identity)
            scanned += 1
        if full:
            break
        if len(page) < PAGE_ROWS:
            current = None
            end_reached = True
            break
    return rows, current, {
        "scannedRows": scanned, "pages": pages,
        "atEndOfAvailableWindow": end_reached,
        "bounded": True, "sourceRowsChangedByScan": False,
    }
