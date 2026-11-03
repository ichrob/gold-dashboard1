"""Read-only retrospective daily capacity view over EXISTING fixed half-hour slots.

This module never queries or changes production data. It does not estimate absent
slots or claim PostgreSQL allocation differences as freed Render volume bytes.
"""
from storage_forensics import COUNTERS

TABLES = (
    "bob_diagnostic_history",
    "bob_candle_evidence",
    "bob_decision_audit",
    "bob_metric_checks",
    "bob_improvement_observations",
)
DAY_SECONDS = 86400
SLOT_SECONDS = 1800
REPORT_HOUR_UTC = 18
HISTORY_DAYS = 7
MAX_BYTES = 10**13


def _uint(value):
    return type(value) is int and 0 <= value <= MAX_BYTES


def _snapshots(samples):
    by_slot = {}
    for row in samples if isinstance(samples, (list, tuple)) else ():
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue
        slot, database, relations, writers = row[:4]
        if (not _uint(slot) or slot % SLOT_SECONDS
                or not _uint(database) or type(relations) is not dict):
            continue
        by_slot[slot] = (
            database, relations, writers if type(writers) is dict else {})
    return by_slot


def _table_pair(name, old, new):
    a = old[1].get(name)
    b = new[1].get(name)
    comparable = _uint(a) and _uint(b)
    result = {
        "table": name,
        "relationStatus": "observed" if comparable else "missing-in-slot",
        "allocatedBytesBefore": a if _uint(a) else None,
        "allocatedBytesAfter": b if _uint(b) else None,
        "netAllocatedBytes": b - a if comparable else None,
        "counterStatus": "missing-counter-snapshot",
        "writeCounters": None,
    }
    if not comparable:
        result["counterStatus"] = "relation-not-observed"
        return result
    before, after = old[2].get(name), new[2].get(name)
    if (type(before) is dict and type(after) is dict
            and all(_uint(before.get(key)) and _uint(after.get(key))
                    for key in COUNTERS)):
        differences = {key: after[key] - before[key] for key in COUNTERS}
        if all(value >= 0 for value in differences.values()):
            result["counterStatus"] = "observed-reset-unverified"
            result["writeCounters"] = differences
        else:
            result["counterStatus"] = "counter-decrease-reset-or-wrap"
    return result


def _window(snapshots, end_slot):
    start_slot = end_slot - DAY_SECONDS
    first, last = snapshots.get(start_slot), snapshots.get(end_slot)
    if first is None or last is None:
        status = (
            "missing-both-slots" if first is None and last is None else
            "missing-baseline-slot" if first is None else
            "missing-endpoint-slot"
        )
        return {
            "status": status, "startSlot": start_slot, "endSlot": end_slot,
            "databaseBytesBefore": first[0] if first else None,
            "databaseBytesAfter": last[0] if last else None,
            "databaseBytesDelta": None, "tables": [],
            "missingTables": list(TABLES), "diskBytesFreed": None,
        }
    tables = [_table_pair(name, first, last) for name in TABLES]
    missing = [r["table"] for r in tables if r["relationStatus"] != "observed"]
    return {
        "status": "partial-relations" if missing else "observed",
        "startSlot": start_slot, "endSlot": end_slot,
        "databaseBytesBefore": first[0], "databaseBytesAfter": last[0],
        "databaseBytesDelta": last[0] - first[0],
        "tables": tables, "missingTables": missing,
        "diskBytesFreed": None,
    }


def _summary(window):
    rows = {row["table"]: row for row in window["tables"]}
    observed = sum(
        row["counterStatus"] == "observed-reset-unverified"
        for row in rows.values())
    decreases = sum(
        row["counterStatus"] == "counter-decrease-reset-or-wrap"
        for row in rows.values())
    return {
        "startSlot": window["startSlot"], "endSlot": window["endSlot"],
        "status": window["status"],
        "databaseBytesDelta": window["databaseBytesDelta"],
        # Each position uses TABLES in the declared fixed order; null means
        # unavailable, never zero. No original payload or dynamic identifiers.
        "relationNetBytes": [
            rows[name]["netAllocatedBytes"] if name in rows else None
            for name in TABLES
        ],
        "observedCounterTablesResetUnverified": observed,
        "counterDecreaseTables": decreases,
    }


def report(samples):
    """Latest 18:00 UTC pair and up to seven retrospective daily comparisons.

    The source already keeps at most 336 half-hour snapshots. Earlier days can
    be missing because of that read bound or genuine collection gaps; neither
    situation is silently treated as an observed zero.
    """
    snapshots = _snapshots(samples)
    if not snapshots:
        return {
            "status": "no-valid-snapshots", "readOnly": True,
            "tableOrder": list(TABLES), "latest": None, "retrospective": [],
            "historyDaysRequested": HISTORY_DAYS,
            "statsResetTimestampStatus": "not-captured-in-snapshots",
            "diskBytesFreed": None, "walBytesDelta": None, "bloatBytes": None,
        }
    newest = max(snapshots)
    fixed_end = (
        (newest - REPORT_HOUR_UTC * 3600) // DAY_SECONDS * DAY_SECONDS
        + REPORT_HOUR_UTC * 3600
    )
    latest = _window(snapshots, fixed_end)
    history = [
        _summary(_window(snapshots, fixed_end - DAY_SECONDS * index))
        for index in range(HISTORY_DAYS)
    ]
    return {
        "status": latest["status"], "readOnly": True,
        "tableOrder": list(TABLES),
        "latest": latest,
        "retrospective": history,
        "historyDaysRequested": HISTORY_DAYS,
        "oldestLoadedSlot": min(snapshots),
        "newestLoadedSlot": newest,
        "statsResetTimestampStatus": "not-captured-in-snapshots",
        "writerCounterQualification": (
            "cumulative-differences-only-reset-not-independently-verified"),
        "scope": "exact-18-UTC-fixed-slot-history-from-existing-samples",
        "diskBytesFreed": None, "walBytesDelta": None, "bloatBytes": None,
    }
