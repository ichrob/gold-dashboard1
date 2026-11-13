"""Read-only review of DEGIRO list images older than yesterday in Zurich.

Today's and yesterday's images are the hot window. Older images are REVIEW
candidates, never deletion candidates merely because of their age. Successful
imports, unfinished OCR, original product/venue proofs and training examples
cannot be discarded on the strength of a summary. Byte-exact per-batch archive,
independent restore, reader replay and separate authorization are still needed.

This view transports no image, device token, batch ID, ISIN or source price.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import threading
import time

_SAMPLE = 8
_CACHE_SECONDS = 900
_lock = threading.Lock()
_cached = None
_cached_at = 0.0
_ZURICH = ZoneInfo("Europe/Zurich")
_FINISHED = frozenset(("synced", "superseded", "stored"))
_ERROR = frozenset(("waiting-memory", "read-failed", "fetch-failed",
                    "store-failed"))
# PostgreSQL determines the Zurich midnight boundary, not UTC midnight or
# a rolling 48-hour age. A fixed cap and short read timeouts bound the probe.
_SQL = """WITH page AS MATERIALIZED (
    SELECT i.ctid,i.created_at
    FROM bob_android_list_images AS i
    WHERE i.created_at < (
        ((now() AT TIME ZONE 'Europe/Zurich')::date - 1)::timestamp
         AT TIME ZONE 'Europe/Zurich')
    ORDER BY i.created_at DESC, i.batch_id DESC LIMIT %s
)
SELECT page.created_at, i.import_receipt->>'stage',
    (i.parsed_items IS NOT NULL), i.processing_at,
    NULL::boolean
FROM page JOIN bob_android_list_images AS i ON i.ctid=page.ctid
ORDER BY page.created_at DESC,page.ctid DESC"""


def classify(row, now):
    """Return a bounded reason, never a deletion or migration authorization.

    The database does not yet prove which old screenshots contain unique
    leverage/KO/venue facts or are selected as OCR training exemplars. Treat
    all successfully imported images as evidence until a separate batch-scoped
    manifest and independently replayed archive proves otherwise.
    """
    if type(row) not in (tuple, list) or len(row) != 5:
        return "preserve-unknown"
    uploaded, stage, parsed, processing_at, pointer = row
    if (not isinstance(uploaded, datetime) or uploaded.tzinfo is None or
            not isinstance(now, datetime) or now.tzinfo is None or
            type(parsed) is not bool or pointer not in (True, False, None)):
        return "preserve-unknown"
    age = (now - uploaded).total_seconds()
    if age < 0:
        return "preserve-unknown"
    today = now.astimezone(_ZURICH).date()
    hot_start = today - timedelta(days=1)
    if uploaded.astimezone(_ZURICH).date() >= hot_start:
        return "hot-today-or-yesterday"
    if pointer:
        return "preserve-archived-reference"
    if parsed or stage in _FINISHED:
        return "preserve-product-proof-or-example"
    if (isinstance(processing_at, datetime) and
            processing_at.tzinfo is not None and
            0 <= (now - processing_at).total_seconds() < 86400):
        return "preserve-active-ocr"
    if stage in _ERROR:
        return "review-old-failed-original-for-archive"
    return "preserve-unknown"


def _not_observed(status="not-observed"):
    return {"status": status, "readOnly": True, "hotZurichCalendarDays": 2,
            "oldImageDeletionAuthorized": False, "originalRowsChanged": False,
            "physicalBytesFreed": None}


def _collect(rows, now):
    if type(rows) is not list or len(rows) > _SAMPLE:
        return _not_observed()
    counts = {key: 0 for key in (
        "preserve-archived-reference", "preserve-product-proof-or-example",
        "preserve-active-ocr", "review-old-failed-original-for-archive",
        "preserve-unknown")}
    for row in rows:
        classification = classify(row, now)
        if classification not in counts:
            # A database clock or a concurrent source shift may have made a
            # younger row appear. Keep all original content unchanged.
            counts["preserve-unknown"] += 1
        else:
            counts[classification] += 1
    return {
        "status": "sampled" if rows else "observed-empty",
        "readOnly": True, "hotZurichCalendarDays": 2,
        "oldWindow": "vorgestern-und-aelter",
        "sampledOldBatches": len(rows), "sampleCap": _SAMPLE,
        "olderBatchesMayExist": len(rows) == _SAMPLE,
        "protectedProductOrExampleBatches":
            counts["preserve-product-proof-or-example"],
        "protectedReferenceBatches": counts["preserve-archived-reference"],
        "referencePointerCoverage": False,
        "protectedActiveOcrBatches": counts["preserve-active-ocr"],
        "reviewOldFailedOriginalBatches":
            counts["review-old-failed-original-for-archive"],
        "unknownPreservedBatches": counts["preserve-unknown"],
        "evaluatedAndArchivedForEachBatch": False,
        "oldImageDeletionAuthorized": False,
        "originalRowsChanged": False,
        "physicalBytesFreed": None,
        "scope": "bounded-metadata-only-old-batch-age-review-not-complete-backup-or-deletion",
    }


def report(conn, now=None):
    """Cached, read-only, capped sample; no direct image export or DELETE."""
    global _cached, _cached_at
    instant = (datetime.now(timezone.utc) if now is None else now)
    if not isinstance(instant, datetime) or instant.tzinfo is None:
        return _not_observed()
    tick = time.monotonic()
    if _cached is not None and 0 <= tick - _cached_at < _CACHE_SECONDS:
        return dict(_cached)
    if not _lock.acquire(blocking=False):
        return _not_observed("busy")
    try:
        if _cached is not None and 0 <= tick - _cached_at < _CACHE_SECONDS:
            return dict(_cached)
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='1200ms'")
                conn.execute("SET LOCAL lock_timeout='250ms'")
                rows = conn.execute(_SQL, (_SAMPLE,)).fetchall()
            result = _collect(rows, instant)
        except Exception:
            result = _not_observed()
        _cached, _cached_at = dict(result), tick
        return result
    finally:
        _lock.release()
