"""Operator-only JSONB compression sizing on the EXISTING isolated restore DB.

No production connection is opened. All inserts are synthetic and go to
session-local TEMP tables on the independently provisioned restore instance.
No live writer is modified, and no result authorizes a migration or VACUUM.
"""
import json
import os

RESTORE_DB = "bob_archive_restore_test"
LIMIT_ROWS = 96
LIMIT_JSON_BYTES = 2_000_000
METHODS = ("pglz", "lz4")


def fixtures():
    """Deterministic, nonmarket synthetic rows: small inputs and large audits."""
    rows = []
    for i in range(48):
        rows.append({"kind": "input-synthetic", "sourceAt": 1_800_000_000 + i,
                     "trace": ("%032x" % i),
                     "payload": {"source": "synthetic", "frame": "5m",
                                 "status": "observed", "value": i}})
    for i in range(48):
        rows.append({"kind": "decision-synthetic", "sourceAt": 1_800_000_000 + i,
                     "trace": ("%032x" % (i + 48)),
                     "payload": {
                         "direction": ("LONG" if i % 2 == 0 else "WAIT"),
                         "products": [
                             {"index": j, "code": "SYNTHETIC-%02d" % j,
                              "notes": ("completely synthetic evidence " * 10) + str(j),
                              "values": list(range(18))}
                             for j in range(8)],
                         "clock": 1_800_000_000 + i}})
    return rows


def validate_fixtures(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= LIMIT_ROWS:
        raise ValueError("Bounded synthetic list required")
    encoded = [json.dumps(row, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
               for row in rows]
    if sum(len(item.encode("utf-8")) for item in encoded) > LIMIT_JSON_BYTES:
        raise ValueError("Synthetic byte limit exceeded")
    if any(type(row) is not dict or row.get("kind") not in
           ("input-synthetic", "decision-synthetic") for row in rows):
        raise ValueError("Only known synthetic rows accepted")
    return encoded


def require_isolated_restore(conn, source_dsn, restore_dsn, enabled):
    """Fail closed on aliases. Never connect to the production source DSN."""
    from psycopg.conninfo import conninfo_to_dict
    if enabled != "1":
        raise PermissionError("Operator-only probe disabled")
    if not source_dsn or not restore_dsn:
        raise ValueError("Both existing database identities required")
    source = conninfo_to_dict(source_dsn)
    target = conninfo_to_dict(restore_dsn)
    if (not source.get("host") or not target.get("host")
            or source["host"] == target["host"]
            or source.get("dbname") == target.get("dbname")
            or target.get("dbname") != RESTORE_DB):
        raise ValueError("Separate named restore host required")
    row = conn.execute("SELECT current_database()").fetchone()
    if row != (RESTORE_DB,):
        raise ValueError("Not the existing isolated restore database")


def confirm_exact_reader(rows, readback):
    """All original synthetic fields/clocks must survive JSONB round-trips."""
    if len(rows) != len(readback):
        raise ValueError("Row count mismatch")
    for i, (row_id, payload_text) in enumerate(readback):
        if type(row_id) is not int or row_id != i:
            raise ValueError("Row identity mismatch")
        if json.loads(payload_text) != rows[i]:
            raise ValueError("JSONB reader mismatch")
    return True


def run(source_dsn, restore_dsn, enabled=None):
    """At most 96 local inserts per temporary table; no permanent SQL writes."""
    import psycopg
    rows = fixtures()
    payloads = validate_fixtures(rows)
    enabled = os.environ.get("BOB_STORAGE_COMPRESSION_PROBE_ONCE") if enabled is None else enabled
    results = {}
    with psycopg.connect(
            restore_dsn, connect_timeout=10, autocommit=True,
            application_name="bob_isolated_synthetic_jsonb_probe",
            options="-c statement_timeout=10000 -c lock_timeout=1000") as conn:
        require_isolated_restore(conn, source_dsn, restore_dsn, enabled)
        for method in METHODS:
            # Only hardcoded names; never interpolate user strings into SQL.
            table = "pg_temp.bob_jsonb_synthetic_" + method
            try:
                conn.execute("CREATE TEMP TABLE " + table +
                             " (row_id integer PRIMARY KEY, payload jsonb COMPRESSION " +
                             method + ") ON COMMIT PRESERVE ROWS")
                with conn.cursor() as cur:
                    cur.executemany("INSERT INTO " + table +
                                    " (row_id,payload) VALUES (%s,%s::jsonb)",
                                    list(enumerate(payloads)))
                readback = conn.execute(
                    "SELECT row_id,payload::text FROM " + table +
                    " ORDER BY row_id").fetchall()
                confirm_exact_reader(rows, readback)
                allocated = conn.execute(
                    "SELECT pg_total_relation_size(%s::regclass)",
                    (table,)).fetchone()[0]
                counts = conn.execute(
                    "SELECT coalesce(pg_column_compression(payload),'none'),count(*) "
                    "FROM " + table +
                    " GROUP BY 1 ORDER BY 1").fetchall()
                results[method] = {"status": "verified-synthetic",
                                   "temporaryRelationBytes": allocated,
                                   "rowsVerified": len(readback),
                                   "compression": {name: count for name, count in counts}}
            except psycopg.errors.FeatureNotSupported:
                # The instance might not provide LZ4. Not a safety failure.
                if method == "pglz":
                    raise
                results[method] = {"status": "method-unavailable"}
    baseline = results.get("pglz", {})
    alternative = results.get("lz4", {})
    difference = (baseline["temporaryRelationBytes"] -
                  alternative["temporaryRelationBytes"]
                  if baseline.get("status") == alternative.get("status") ==
                  "verified-synthetic" else None)
    return {"status": "isolated-synthetic-probe",
            "rows": len(rows), "methods": results,
            "lz4VersusPglzTemporaryBytes": difference,
            "readerEquality": True, "productionRowsChanged": False,
            "physicalBytesFreed": None,
            "scope": "temporary-synthetic-sizing-not-real-data-or-provider-savings"}


if __name__ == "__main__":
    try:
        # Explicitly do not print hostnames, connection settings or exceptions.
        result = run(os.environ.get("DATABASE_URL"),
                     os.environ.get("BOB_ARCHIVE_RESTORE_DATABASE_URL"))
    except Exception as exc:
        result = {"status": "refused", "errorType": type(exc).__name__,
                  "productionRowsChanged": False, "physicalBytesFreed": None}
    print(json.dumps(result, sort_keys=True))
