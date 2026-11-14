"""Operator-only, bounded read-only analysis of metric evidence growth.

No scheduler or app hook. No archive/retention changes, DDL, VACUUM or
trading actions. SQL itself returns only fixed category names, MD5 digests,
numeric sizes and boolean classifications -- never source JSON, original
clocks, product identifiers or prices. Hash-count sameness is NOT a proof of
identical business events or permission to deduplicate historical rows.
"""
import json
import os
import re
import time

LIMIT = 256
KINDS = ("product", "display", "dmi", "trade", "other")
_DIGEST = re.compile(r"[0-9a-f]{32}\Z")


def summarize(rows):
    """Only emit safe aggregates; reject malformed or unbounded data."""
    if type(rows) not in (list, tuple) or len(rows) > LIMIT:
        raise ValueError("Sample exceeds bounded read")
    groups = {name: {"sampledRows": 0, "storedJsonbPayloadBytes": 0,
                     "allUnavailableRows": 0, "anyMismatchRows": 0,
                     "archivePointerRows": 0, "_full": set(),
                     "_content": set()} for name in KINDS}
    for row in rows:
        if type(row) not in (list, tuple) or len(row) != 7:
            raise ValueError("Invalid metric metadata shape")
        category, full, without_clock, stored, unavailable, mismatch, pointer = row
        if (category not in KINDS or type(category) is not str or
                type(full) is not str or not _DIGEST.fullmatch(full) or
                type(without_clock) is not str or
                not _DIGEST.fullmatch(without_clock) or
                type(stored) is not int or not 0 <= stored <= 2_000_000 or
                any(type(x) is not bool for x in (unavailable, mismatch, pointer))):
            raise ValueError("Invalid metric metadata")
        group = groups[category]
        group["sampledRows"] += 1
        group["storedJsonbPayloadBytes"] += stored
        group["allUnavailableRows"] += int(unavailable)
        group["anyMismatchRows"] += int(mismatch)
        group["archivePointerRows"] += int(pointer)
        group["_full"].add(full)
        group["_content"].add(without_clock)
    sanitized = {}
    for kind in KINDS:
        group = groups[kind]
        sanitized[kind] = {
            "sampledRows": group["sampledRows"],
            "storedJsonbPayloadBytes": group["storedJsonbPayloadBytes"],
            "fullPayloadDigestCount": len(group["_full"]),
            "withoutCheckClockDigestCount": len(group["_content"]),
            "allUnavailableRows": group["allUnavailableRows"],
            "anyMismatchRows": group["anyMismatchRows"],
            "archivePointerRows": group["archivePointerRows"],
        }
    return {"status": "bounded-read-only-sample", "readOnly": True,
            "sampleLimit": LIMIT, "sampledRows": len(rows),
            "truncated": len(rows) == LIMIT, "groups": sanitized,
            "physicalBytesFreed": None,
            "scope": "recent-256-indexed-metric-rows-not-day-totals-or-savings"}


# Only the existing checked_at index is needed for the bounded keyset.
# The MATERIALIZED page prevents evaluating expensive JSONB operations on
# history outside the most recent 256 records. SQL never returns payload text,
# source names, ISIN, account identifiers, timestamps or digest material.
_SQL = """
WITH limited AS MATERIALIZED (
  SELECT scope,payload FROM public.bob_metric_checks
  WHERE checked_at >= %s
  ORDER BY checked_at DESC LIMIT 256
)
SELECT CASE
    WHEN scope LIKE 'product:%%' THEN 'product'
    WHEN scope LIKE 'display:%%' THEN 'display'
    WHEN scope LIKE 'dmi:%%' THEN 'dmi'
    WHEN scope LIKE 'trade:%%' THEN 'trade'
    ELSE 'other'
  END AS category,
  md5(payload::text) AS full_digest,
  md5((payload - 'checkedAt')::text) AS comparable_content_digest,
  pg_column_size(payload) AS payload_column_bytes,
  CASE WHEN jsonb_typeof(payload->'metrics')='object'
             AND payload->'metrics' != '{}'::jsonb
       THEN NOT EXISTS (
         SELECT 1 FROM jsonb_each(payload->'metrics') AS kv
         WHERE jsonb_typeof(kv.value) != 'object'
            OR kv.value->>'status' IS DISTINCT FROM 'unavailable')
       ELSE FALSE END AS all_unavailable,
  EXISTS (
    SELECT 1 FROM jsonb_each(
      CASE WHEN jsonb_typeof(payload->'metrics')='object'
           THEN payload->'metrics' ELSE '{}'::jsonb END) AS kv
    WHERE kv.value->>'status'='mismatch') AS any_mismatch,
  (payload ? '_bobColdMetricV1' OR payload ? '_bobColdMetricV2')
    AS archived_pointer
FROM limited
"""


def sample(conn, *, now_ms=None):
    """One indexed bounded SELECT; caller must enforce DB read-only mode."""
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    if type(now_ms) is not int or now_ms < 86_400_000:
        raise ValueError("Invalid sampling clock")
    return summarize(conn.execute(_SQL, (now_ms - 86_400_000,)).fetchall())


def run():
    """Manual opt-in only. No private values are logged or returned."""
    if os.environ.get("BOB_METRIC_SCOPE_PROBE_ONCE") != "1":
        raise PermissionError("One-time read-only probe not enabled")
    import psycopg
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5,
        application_name="bob_metric_scope_read_only_once",
        options="-c default_transaction_read_only=on "
                "-c statement_timeout=2000 -c lock_timeout=250 "
                "-c idle_in_transaction_session_timeout=5000") as conn:
        if conn.execute("SHOW default_transaction_read_only").fetchone() != ("on",):
            raise PermissionError("Read-only SQL enforcement unavailable")
        return sample(conn)


if __name__ == "__main__":
    try:
        report = run()
    except Exception as error:
        report = {"status": "unavailable", "errorType": type(error).__name__,
                  "readOnly": True, "physicalBytesFreed": None}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
