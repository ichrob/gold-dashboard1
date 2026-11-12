"""Exact, redacted storage evidence for the entry/exit comparison.

Historical relation totals come only from existing fixed half-hour samples.
Component and logical deltas are reported only when both endpoint samples contain
the new fixed scalar measurement.  Missing endpoints are never estimated.
"""
from datetime import datetime, timezone
from contextlib import nullcontext
from zoneinfo import ZoneInfo

TABLE = "bob_entry_exit_comparison"
TAG = "_bobColdTestV1"
ZURICH = ZoneInfo("Europe/Zurich")
SLOT_SECONDS = 1800
MAX_BYTES = 10**13
STATUSES = ("waiting", "pending", "open", "exit-pending", "closed",
            "inconclusive", "no-entry")


def _uint(value):
    return type(value) is int and 0 <= value <= MAX_BYTES


def sample(conn):
    """Small fixed scalar snapshot; never returns an id or original payload."""
    row = conn.execute("""SELECT pg_relation_size(c.oid),pg_indexes_size(c.oid),
        pg_total_relation_size(c.oid),CASE WHEN c.reltoastrelid=0 THEN 0
        ELSE pg_total_relation_size(c.reltoastrelid) END
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=current_schema() AND c.relname=%s""", (TABLE,)).fetchone()
    if not row:
        return {}
    heap, indexes, total, toast = row
    counts = conn.execute("""SELECT count(*),
        count(*) FILTER (WHERE complete),count(*) FILTER (WHERE NOT complete),
        coalesce(sum(octet_length(payload::text)),0),
        coalesce(sum(octet_length(payload::text)) FILTER (WHERE complete),0),
        coalesce(sum(octet_length(payload::text)) FILTER (WHERE NOT complete),0),
        count(*) FILTER (WHERE payload ? %s)
        FROM bob_entry_exit_comparison""", (TAG,)).fetchone()
    result = {
        "totalBytes": total, "heapBytes": heap, "indexBytes": indexes,
        "toastBytes": toast, "otherBytes": total-heap-indexes-toast,
        "episodes": counts[0], "completeEpisodes": counts[1],
        "openEpisodes": counts[2], "logicalPayloadBytes": counts[3],
        "completeLogicalPayloadBytes": counts[4],
        "openLogicalPayloadBytes": counts[5], "archivedEpisodes": counts[6],
    }
    return result if all(_uint(value) for value in result.values()) else {}


def _rows(samples):
    result = {}
    for item in samples if isinstance(samples, (list, tuple)) else ():
        if not isinstance(item, (list, tuple)) or len(item) < 4:
            continue
        slot, database, relations = item[:3]
        metrics = item[4] if len(item) > 4 and type(item[4]) is dict else {}
        recorded = item[5] if len(item) > 5 else None
        if (not _uint(slot) or slot % SLOT_SECONDS or not _uint(database)
                or type(relations) is not dict):
            continue
        result[slot] = (database, relations, metrics, recorded)
    return result


def _slot(day, hour):
    return int(datetime(day.year, day.month, day.day, hour, tzinfo=ZURICH).timestamp())


def _component_delta(before, after):
    keys = ("totalBytes", "heapBytes", "indexBytes", "toastBytes", "otherBytes",
            "episodes", "completeEpisodes", "openEpisodes", "archivedEpisodes",
            "logicalPayloadBytes", "completeLogicalPayloadBytes",
            "openLogicalPayloadBytes")
    if not all(_uint(before.get(key)) and _uint(after.get(key)) for key in keys):
        return {"status": "needs-fixed-endpoint-measurement", "deltas": None}
    return {"status": "observed", "deltas": {
        key: after[key]-before[key] for key in keys}}


def _window(rows, day):
    start, end = _slot(day, 8), _slot(day, 22)
    first, last = rows.get(start), rows.get(end)
    if first is None or last is None:
        status = ("missing-both-endpoints" if first is None and last is None else
                  "missing-baseline" if first is None else "missing-endpoint")
        return {"status": status, "exact": False, "zurichDate": day.isoformat(),
                "startSlot": start, "endSlot": end, "relationBytesBefore": None,
                "relationBytesAfter": None, "relationBytesDelta": None,
                "databaseBytesBefore": first[0] if first else None,
                "databaseBytesAfter": last[0] if last else None,
                "databaseBytesDelta": None, "components": {
                    "status": "needs-fixed-endpoint-measurement", "deltas": None}}
    before, after = first[1].get(TABLE), last[1].get(TABLE)
    exact = _uint(before) and _uint(after)
    return {
        "status": "observed" if exact else "relation-missing-at-endpoint",
        "exact": exact, "zurichDate": day.isoformat(),
        "startSlot": start, "endSlot": end,
        "baselineRecordedAt": str(first[3]) if first[3] is not None else None,
        "endpointRecordedAt": str(last[3]) if last[3] is not None else None,
        "relationBytesBefore": before if _uint(before) else None,
        "relationBytesAfter": after if _uint(after) else None,
        "relationBytesDelta": after-before if exact else None,
        "databaseBytesBefore": first[0], "databaseBytesAfter": last[0],
        "databaseBytesDelta": last[0]-first[0],
        "components": _component_delta(first[2], last[2]),
    }


def report(conn, samples, now=None):
    now = datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(now, timezone.utc)
    rows = _rows(samples)
    statuses = {}
    try:
        # A nested psycopg transaction is a savepoint.  A timeout or legacy
        # schema therefore cannot poison the surrounding diagnostics read.
        with conn.transaction() if hasattr(conn, "transaction") else nullcontext():
            current = sample(conn)
            for status, count in conn.execute("""SELECT arm.value->>'status',count(*)
                FROM bob_entry_exit_comparison episode
                CROSS JOIN LATERAL jsonb_each(CASE
                  WHEN jsonb_typeof(episode.payload->'arms')='object' THEN episode.payload->'arms'
                  ELSE '{}'::jsonb END) arm
                GROUP BY arm.value->>'status'""").fetchall():
                if status in STATUSES and _uint(count):
                    statuses[status] = count
    except Exception:
        current = {}
        statuses = {}
    observed_days = sorted({datetime.fromtimestamp(slot, ZURICH).date()
                            for slot, row in rows.items() if TABLE in row[1]})
    completed = [day for day in observed_days if _slot(day, 22) <= now.timestamp()]
    first = _window(rows, completed[0]) if completed else None
    latest = _window(rows, completed[-1]) if completed else None
    complete = current.get("completeEpisodes") if current else None
    complete_bytes = current.get("completeLogicalPayloadBytes") if current else None
    return {
        "status": "observed" if current else "not-observed", "readOnly": True,
        "table": TABLE, "sampleSchemaFields": ["slot", "sampled_at",
            "database_bytes", "relation_bytes", "writer_stats", "entry_exit_metrics"],
        "tradeWindow": "08:00-22:00 Europe/Zurich",
        "firstCompletedTradeDay": first, "latestCompletedTradeDay": latest,
        "current": current or None, "armStatuses": statuses,
        "completeLogicalBytesPerCase": (complete_bytes/complete
            if _uint(complete_bytes) and type(complete) is int and complete > 0 else None),
        "physicalBytesFreed": None, "renderVolumeBytesDelta": None,
        "scope": "fixed-half-hour-relation-allocation-and-current-redacted-scalars",
        "note": "Historical relation totals include heap, indexes and TOAST. "
                "Historical component/logical deltas require both fixed endpoint metrics; "
                "current components are not retroactively imputed.",
    }
