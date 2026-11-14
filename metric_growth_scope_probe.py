"""Operator-only, bounded, READ-ONLY metric evidence growth diagnosis.

No automatic scheduler, no app hook, no migration, no archive claim, no DDL.
Observes at most 256 most recent metric checks from an existing indexed
source (without reading orders, credentials or personal product identifiers).
Only sanitized aggregates leave the process; identities and raw payloads
never appear in output. A repeated value after excluding checkedAt is NOT
proof an event can be discarded or relocated.
"""
import hashlib
import json
import os
import time

LIMIT = 256
MAX_JSON_TEXT = 16_384
MAX_TOTAL_TEXT = 2_000_000
KINDS = ("product", "display", "dmi", "trade", "other")


def kind_for(scope):
    if type(scope) is not str or not 0 < len(scope) <= 256:
        raise ValueError("Invalid metric scope")
    for name in KINDS[:-1]:
        if scope.startswith(name + ":"):
            return name
    return "other"


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).digest()


def summarize(rows):
    """Aggregate one bounded sample; never emit original JSON, times or hashes."""
    if type(rows) not in (list, tuple) or len(rows) > LIMIT:
        raise ValueError("Metric sample size is not bounded")
    totals = {kind: {"sampledRows": 0, "storedJsonbPayloadBytes": 0,
                     "allUnavailableRows": 0, "anyMismatchRows": 0,
                     "archivePointerRows": 0, "_full": set(),
                     "_withoutCheckClock": set()} for kind in KINDS}
    text_bytes = 0
    for row in rows:
        if type(row) not in (list, tuple) or len(row) != 4:
            raise ValueError("Malformed metric result")
        scope, checked_at, payload_text, stored = row
        kind = kind_for(scope)
        if (type(checked_at) is not int or checked_at < 0 or
                type(payload_text) is not str or type(stored) is not int or
                stored < 0 or stored > MAX_JSON_TEXT):
            raise ValueError("Malformed metric original")
        text_length = len(payload_text.encode("utf-8"))
        text_bytes += text_length
        if text_length > MAX_JSON_TEXT or text_bytes > MAX_TOTAL_TEXT:
            raise ValueError("Metric sample exceeds memory budget")
        payload = json.loads(payload_text)
        if type(payload) is not dict:
            raise ValueError("Metric payload must be an object")
        entry = totals[kind]
        entry["sampledRows"] += 1
        entry["storedJsonbPayloadBytes"] += stored
        entry["_full"].add(_digest(payload))
        # This removes only a duplicated *check clock* in the analysis
        # fingerprint. A complete original row (including checkedAt) stays
        # untouched and this never grants permission to deduplicate.
        no_clock = {key: value for key, value in payload.items()
                    if key != "checkedAt"}
        entry["_withoutCheckClock"].add(_digest(no_clock))
        metrics = payload.get("metrics")
        if type(metrics) is dict and metrics:
            statuses = [v.get("status") for v in metrics.values()
                        if type(v) is dict]
            if statuses and len(statuses) == len(metrics):
                if all(s == "unavailable" for s in statuses):
                    entry["allUnavailableRows"] += 1
                if any(s == "mismatch" for s in statuses):
                    entry["anyMismatchRows"] += 1
        if any(tag in payload for tag in ("_bobColdMetricV1", "_bobColdMetricV2")):
            entry["archivePointerRows"] += 1
    safe = {}
    for kind in KINDS:
        d = totals[kind]
        safe[kind] = {
            "sampledRows": d["sampledRows"],
            "storedJsonbPayloadBytes": d["storedJsonbPayloadBytes"],
            "fullPayloadDigestsDistinct": len(d["_full"]),
            "withoutCheckClockDigestsDistinct": len(d["_withoutCheckClock"]),
            "allUnavailableRows": d["allUnavailableRows"],
            "anyMismatchRows": d["anyMismatchRows"],
            "archivePointerRows": d["archivePointerRows"],
        }
    return {
        "status": "bounded-read-only-sample",
        "readOnly": True,
        "sampleLimit": LIMIT,
        "sampledRows": len(rows),
        "truncated": len(rows) == LIMIT,
        "groups": safe,
        "physicalBytesFreed": None,
        "scope": "latest-indexed-metric-rows-not-day-totals-or-reclaimable-bytes",
    }


_SQL = """SELECT scope,checked_at,payload::text,pg_column_size(payload)
          FROM public.bob_metric_checks
          WHERE checked_at >= %s
          ORDER BY checked_at DESC
          LIMIT 256"""


def sample(conn, *, now_ms=None):
    """Single indexed bounded SELECT. Caller provides read-only connection."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if type(now_ms) is not int or now_ms < 86_400_000:
        raise ValueError("Invalid clock")
    rows = conn.execute(_SQL, (now_ms - 86_400_000,)).fetchall()
    return summarize(rows)


def run():
    """Manual invocation only; no scheduler or startup-time call sites."""
    if os.environ.get("BOB_METRIC_SCOPE_PROBE_ONCE") != "1":
        raise PermissionError("Explicit owner-only sampling opt-in missing")
    # Never create a production write connection. PostgreSQL itself enforces
    # default_transaction_read_only, short statement and lock timeouts.
    import psycopg
    with psycopg.connect(
            os.environ["DATABASE_URL"],
            connect_timeout=5,
            application_name="bob_metric_scope_read_only_once",
            options="-c default_transaction_read_only=on "
                    "-c statement_timeout=2000 -c lock_timeout=250 "
                    "-c idle_in_transaction_session_timeout=5000") as conn:
        if conn.execute("SHOW default_transaction_read_only").fetchone() != ("on",):
            raise PermissionError("Read-only database mode not confirmed")
        return sample(conn)


if __name__ == "__main__":
    try:
        result = run()
    except Exception as exc:
        result = {"status": "unavailable", "errorType": type(exc).__name__,
                  "readOnly": True, "physicalBytesFreed": None}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
