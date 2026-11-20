"""Operator-only plan of the separate DEGIRO image-age SELECT; never executes it.

Read-only EXPLAIN without ANALYZE for the distinct 05:43 UTC timeout.
No HTTP route, startup hook, scheduler, source mutation, image read or export.
Only from an already authorized PRIVATE database session, and only after
a separate operator authorization for a production planning probe.
"""
import json
import math
import os
import sys

import android_image_age_review as image_age

# Reuse the existing SQL literally: do not substitute cold-analysis SQL.
_EXPLAIN = "EXPLAIN (FORMAT JSON, COSTS TRUE) " + image_age._SQL
_LIMIT = image_age._SAMPLE
_ALLOWED_NODES = frozenset((
    "Limit", "Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Index Scan",
    "Bitmap Heap Scan", "Sort", "Incremental Sort", "Gather", "Gather Merge",
    "Result", "Materialize", "Append", "Merge Append", "Subquery Scan",
    "Aggregate", "Nested Loop", "Memoize"
))
_ALLOWED_INDEXES = frozenset(("bob_android_list_images_pkey",))
_MAX_NODES = 12


def _blocked(reason="plan-unavailable"):
    return {"status": "unavailable", "reason": reason, "readOnly": True,
            "queryExecuted": False, "planEstimatedOnly": True,
            "oldImageDeletionAuthorized": False, "sourceRowsModified": False,
            "physicalBytesFreed": None,
            "scope": "image-age-inventory-query-plan-only"}


def _number(value):
    if type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 10**15:
        return value
    return None


def _project(plan):
    if type(plan) is not list or len(plan) != 1 or type(plan[0]) is not dict:
        return _blocked("invalid-plan-envelope")
    root = plan[0].get("Plan")
    if type(root) is not dict:
        return _blocked("invalid-plan-envelope")
    pending = [root]
    nodes = []
    while pending and len(nodes) < _MAX_NODES:
        node = pending.pop(0)
        if type(node) is not dict or node.get("Node Type") not in _ALLOWED_NODES:
            return _blocked("unrecognized-plan-node")
        row_estimate = _number(node.get("Plan Rows"))
        cost_estimate = _number(node.get("Total Cost"))
        if row_estimate is None or cost_estimate is None:
            return _blocked("invalid-plan-metric")
        kind = node["Node Type"]
        record = {"node": kind, "estimatedRows": row_estimate,
                  "estimatedTotalCost": cost_estimate,
                  "hasFilter": type(node.get("Filter")) is str,
                  "hasIndexCondition": type(node.get("Index Cond")) is str}
        if kind in ("Index Scan", "Index Only Scan", "Bitmap Index Scan"):
            name = node.get("Index Name")
            record["index"] = name if name in _ALLOWED_INDEXES else "other-or-unreported"
        nodes.append(record)
        children = node.get("Plans", [])
        if type(children) is not list or len(children) > _MAX_NODES:
            return _blocked("invalid-plan-children")
        pending.extend(children)
    return {"status": "estimated-plan-observed", "readOnly": True,
            "queryExecuted": False, "planEstimatedOnly": True,
            "oldImageDeletionAuthorized": False, "sourceRowsModified": False,
            "physicalBytesFreed": None, "nodeLimit": _MAX_NODES,
            "nodeListTruncated": bool(pending), "nodes": nodes,
            "scope": "image-age-inventory-query-plan-only",
            "note": "Planner estimates only; not runtime, locks, disk I/O, freed bytes or eligibility."}


def inspect(conn):
    """Fail closed on a write-capable transaction; EXPLAIN is never ANALYZE."""
    try:
        with conn.transaction():
            state = conn.execute("SHOW transaction_read_only").fetchone()
            if not state or state[0] != "on":
                return _blocked("read-only-transaction-required")
            conn.execute("SET LOCAL statement_timeout='750ms'")
            conn.execute("SET LOCAL lock_timeout='200ms'")
            result = conn.execute(_EXPLAIN, (_LIMIT,)).fetchone()
            return _project(result[0] if result else None)
    except Exception:
        # No statement, credentials, payloads or exception details leave the CLI.
        return _blocked()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["inspect"]:
        print("Usage: python -m android_image_age_query_plan inspect")
        return 2
    try:
        import psycopg
        with psycopg.connect(
                os.environ["DATABASE_URL"], connect_timeout=8,
                application_name="bob_android_image_age_explain_readonly",
                options="-c default_transaction_read_only=on "
                        "-c statement_timeout=750 -c lock_timeout=200") as conn:
            result = inspect(conn)
    except Exception:
        result = _blocked()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "estimated-plan-observed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
