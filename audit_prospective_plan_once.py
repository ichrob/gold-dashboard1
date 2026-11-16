"""One-shot read-only PostgreSQL planner witness for the slow 30-day audit.

No production SQL execution: EXPLAIN without ANALYZE only. Reports bounded
numeric estimates and fixed node categories, not private predicates, values,
SQL text, credentials, index names or actual query rows.
"""
import json
import math
import os

import decision_audit

MAX_NODES = 48
_KINDS = frozenset((
    "Aggregate", "Append", "Bitmap Heap Scan", "Bitmap Index Scan",
    "CTE Scan", "Function Scan", "Gather", "Hash", "Hash Join",
    "Incremental Sort", "Index Only Scan", "Index Scan", "Limit",
    "Materialize", "Memoize", "Merge Join", "Nested Loop",
    "Result", "Seq Scan", "Sort", "Subquery Scan", "Tid Scan",
    "Unique", "Values Scan", "WorkTable Scan"
))


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def summarize(raw):
    """Bound an EXPLAIN JSON plan, stripping all provider/local identifier text."""
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list) or len(raw) != 1:
        raise ValueError("Invalid planner envelope")
    wrapper = raw[0]
    if not isinstance(wrapper, dict) or not isinstance(wrapper.get("Plan"), dict):
        raise ValueError("Invalid planner root")
    root = wrapper["Plan"]
    if not _finite_number(root.get("Total Cost")):
        raise ValueError("Invalid plan estimate")
    pending = [(root, 0)]
    counts = {}
    skipped = False
    nodes = 0
    max_depth = 0
    while pending:
        item, depth = pending.pop()
        if nodes >= MAX_NODES:
            skipped = True
            break
        if not isinstance(item, dict) or depth > 20:
            raise ValueError("Invalid plan node")
        name = item.get("Node Type")
        if not isinstance(name, str):
            raise ValueError("Invalid node type")
        name = name if name in _KINDS else "Other"
        counts[name] = counts.get(name, 0) + 1
        nodes += 1
        max_depth = max(max_depth, depth)
        children = item.get("Plans", [])
        if not isinstance(children, list) or len(children) > MAX_NODES:
            raise ValueError("Invalid plan children")
        pending.extend((child, depth + 1) for child in reversed(children))
    return {
        "estimatedRootCost": round(float(root["Total Cost"]), 3),
        "observedPlanNodes": nodes,
        "nodeCountByType": counts,
        "maxPlanDepth": max_depth,
        "planTruncated": skipped,
        "indexPlanNodes": sum(counts.get(n, 0) for n in
                               ("Index Scan", "Index Only Scan", "Bitmap Index Scan")),
        "sequentialPlanNodes": counts.get("Seq Scan", 0),
        "limitPlanNodes": counts.get("Limit", 0),
        "rowsReturned": 0,
        "sqlExecuted": False,
        "explainAnalyzeUsed": False,
    }


def inspect(conn):
    """One bounded planning-only EXPLAIN of exactly the existing research SQL."""
    sql, params = decision_audit._prospective_query(recent=False)
    if (not isinstance(sql, str) or "FROM bob_decision_audit" not in sql
            or "CROSS JOIN LATERAL" not in sql
            or not isinstance(params, tuple) or len(params) != 1):
        raise ValueError("Unexpected research query contract")
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='1500ms'")
        conn.execute("SET LOCAL lock_timeout='250ms'")
        conn.execute("SET LOCAL enable_seqscan=off")
        # Never add ANALYZE TRUE. The query is planned, never executed.
        row = conn.execute(
            "EXPLAIN (FORMAT JSON, ANALYZE FALSE, VERBOSE FALSE, "
            "BUFFERS FALSE, COSTS TRUE) " + sql, params).fetchone()
        if not row or len(row) != 1:
            raise ValueError("Missing planner result")
        result = summarize(row[0])
    return {
        "status": "bounded-planner-estimate",
        "readOnly": True, "realOrders": False,
        "scope": "existing-30-day-research-query-planned-only",
        "plannerMode": "enable_seqscan-off-like-current-research-read",
        "causeVerified": False,
        "liveLatencyVerified": False,
        "noTradingChange": True,
        **result,
    }


def run():
    """Explicit operator opt-in, private internal database route only."""
    if os.environ.get("BOB_AUDIT_PLAN_PROBE_ONCE") != "1":
        raise PermissionError("Audit plan probe not authorized")
    import psycopg
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5,
        application_name="bob_audit_plan_read_only_once",
        options="-c default_transaction_read_only=on "
                "-c statement_timeout=1500 -c lock_timeout=250 "
                "-c idle_in_transaction_session_timeout=5000"
    ) as conn:
        if conn.execute("SHOW default_transaction_read_only").fetchone() != ("on",):
            raise PermissionError("Read-only database enforcement missing")
        return inspect(conn)


if __name__ == "__main__":
    try:
        info = run()
    except Exception as exc:
        info = {"status": "unavailable", "readOnly": True, "realOrders": False,
                "causeVerified": False, "errorType": type(exc).__name__[:60],
                "scope": "operator-only-no-unverified-plan"}
    print(json.dumps(info, separators=(",", ":"), sort_keys=True), flush=True)
