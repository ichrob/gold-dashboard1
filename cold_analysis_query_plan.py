"""Operator-only, read-only PostgreSQL EXPLAIN for the cold-analysis candidate query.

This tool never executes the slow SELECT, reads a matching payload, changes a
schema or changes a live service. It is intentionally NOT wired to workers,
HTTP endpoints or routine background status reads.

Usage from an already-authorized PRIVATE server shell only:
    python -m cold_analysis_query_plan inspect

The output contains bounded plan node labels, estimated row counts/costs and
allowlisted index names. No SQL/filter text, identity, credentials or rows.
"""
import json
import math
import os
import re
import sys

# Keep byte-for-byte candidate SQL semantics synchronized with cold_analysis.
# Parameter values match the existing worker; EXPLAIN does not execute SELECT.
_CANDIDATES = """SELECT id,stage,observed_at,build,payload FROM bob_diagnostic_history
        WHERE stage='analysis' AND recorded_at<now()-interval '6 hours' AND NOT(payload ? %s)
        AND pg_column_size(payload)>512 AND octet_length(payload::text)<65536
        ORDER BY recorded_at,id LIMIT %s"""
_EXPLAIN = "EXPLAIN (FORMAT JSON, COSTS TRUE) " + _CANDIDATES
_TAG = "_bobColdAnalysisV1"
_LIMIT = 500
_NODE_TYPES = frozenset((
    "Limit", "Index Scan", "Index Only Scan", "Seq Scan", "Bitmap Heap Scan",
    "Bitmap Index Scan", "Sort", "Incremental Sort", "Gather", "Gather Merge",
    "Materialize", "Result", "Append", "Merge Append", "Nested Loop",
    "Hash Join", "Merge Join", "Hash", "Memoize", "Subquery Scan", "Aggregate"
))
_INDEXES = frozenset((
    "bob_diagnostic_history_time", "bob_diagnostic_history_stage",
    "bob_diagnostic_history_source_window", "bob_diagnostic_history_trace",
    "bob_diagnostic_history_pkey",
))


def _unavailable(reason="plan-unavailable"):
    return {"status": "unavailable", "reason": reason, "readOnly": True,
            "queryExecuted": False, "planEstimatedOnly": True,
            "sourceRowsModified": False, "maintenanceAuthorized": False,
            "scope": "cold-analysis-candidate-query-plan-only"}


def _number(value):
    if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**15:
        return value
    return None


def _project(raw):
    if not isinstance(raw, list) or len(raw) != 1:
        return _unavailable("invalid-plan-envelope")
    root = raw[0].get("Plan") if isinstance(raw[0], dict) else None
    if not isinstance(root, dict):
        return _unavailable("invalid-plan-envelope")
    nodes = []
    pending = [root]
    while pending and len(nodes) < 12:
        entry = pending.pop(0)
        if not isinstance(entry, dict):
            return _unavailable("invalid-plan-node")
        kind = entry.get("Node Type")
        if kind not in _NODE_TYPES:
            return _unavailable("unrecognized-plan-node")
        node = {"node": kind,
                "estimatedRows": _number(entry.get("Plan Rows")),
                "estimatedTotalCost": _number(entry.get("Total Cost"))}
        if node["estimatedRows"] is None or node["estimatedTotalCost"] is None:
            return _unavailable("invalid-plan-metric")
        if kind in ("Index Scan", "Index Only Scan", "Bitmap Index Scan"):
            index = entry.get("Index Name")
            node["index"] = index if index in _INDEXES else "other-or-unreported"
        # Boolean presence markers only; NEVER emit SQL expressions/filters.
        node["hasFilter"] = isinstance(entry.get("Filter"), str)
        node["hasIndexCondition"] = isinstance(entry.get("Index Cond"), str)
        nodes.append(node)
        children = entry.get("Plans", [])
        if not isinstance(children, list) or len(children) > 12:
            return _unavailable("invalid-plan-children")
        pending.extend(children)
    return {"status": "estimated-plan-observed",
            "readOnly": True, "queryExecuted": False,
            "planEstimatedOnly": True, "sourceRowsModified": False,
            "maintenanceAuthorized": False,
            "originalCandidateQueryParameters": "existing-fixed-tag-and-limit",
            "nodeLimit": 12, "nodeListTruncated": bool(pending),
            "nodes": nodes,
            "scope": "cold-analysis-candidate-query-plan-only",
            "note": "EXPLAIN without ANALYZE is an optimizer estimate, not evidence "
                    "of measured runtime, actual rows, I/O, lock delays or savings."}


def inspect(conn):
    """Fail closed unless the existing session is genuinely read-only."""
    try:
        with conn.transaction():
            mode = conn.execute("SHOW transaction_read_only").fetchone()
            if not mode or mode[0] != "on":
                return _unavailable("read-only-transaction-required")
            # Local GUCs cannot change the session's or worker's timeouts.
            conn.execute("SET LOCAL statement_timeout='750ms'")
            conn.execute("SET LOCAL lock_timeout='200ms'")
            plan = conn.execute(_EXPLAIN, (_TAG, _LIMIT)).fetchone()
            return _project(plan[0] if plan else None)
    except Exception:
        # No SQL text, exception message, IP, connection string or secrets.
        return _unavailable()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["inspect"]:
        print("Usage: python -m cold_analysis_query_plan inspect")
        return 2
    try:
        import psycopg
        with psycopg.connect(
                os.environ["DATABASE_URL"], connect_timeout=8,
                application_name="bob_cold_analysis_explain_readonly",
                options="-c default_transaction_read_only=on "
                        "-c statement_timeout=750 -c lock_timeout=200") as conn:
            result = inspect(conn)
    except Exception:
        result = _unavailable()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "estimated-plan-observed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
