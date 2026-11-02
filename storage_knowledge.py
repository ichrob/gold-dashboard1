"""Bounded five-area knowledge snapshots without deleting or rewriting evidence.

Snapshots are small *sampled* operational interpretations, never completed
research conclusions or proof that older originals may be deleted. The five
sources remain authoritative and the existing verified cold-storage readers
are the only supported route to original content.
"""
import hashlib
import json
from collections import Counter

SAMPLE_CAP = 64
AREAS = ("diagnoses", "decisions", "improvements", "simulations", "quality")
# Every query walks an existing leftmost index (or the PK), then projects only
# three small scalar values.  No unbounded aggregation or full JSON export.
QUERIES = {
    "diagnoses": """SELECT id,stage,coalesce(payload->>'outcome','unclassified')
        FROM bob_diagnostic_history ORDER BY recorded_at DESC LIMIT %s""",
    "decisions": """SELECT id,coalesce(payload->>'direction','unclassified'),
        coalesce(payload->>'marketEvaluable','unclassified')
        FROM bob_decision_audit ORDER BY recorded_at DESC LIMIT %s""",
    "improvements": """SELECT campaign || ':' || slot::text,'observation',
        coalesce(payload->>'status','unclassified')
        FROM bob_improvement_observations
        ORDER BY campaign DESC,slot DESC LIMIT %s""",
    "simulations": """SELECT id,CASE WHEN closed_at IS NULL THEN 'open' ELSE 'closed' END,
        coalesce(payload->>'status','unclassified')
        FROM bob_paper_cases ORDER BY day DESC,started_at DESC LIMIT %s""",
    "quality": """SELECT version || ':' || scope || ':' || bar_at::text,'metric',
        coalesce(payload->>'status','unclassified')
        FROM bob_metric_checks ORDER BY checked_at DESC LIMIT %s""",
}
_ALLOWED = {
    "diagnoses": ({"transport", "input", "analysis", "analysis-failed", "push",
                   "push-delivery", "paper-input", "health"},
                  {"ok", "completed", "failed", "error", "ready", "sent",
                   "skipped", "unavailable", "success", "not-ready"}),
    "decisions": ({"LONG", "SHORT", "WAIT", "ABWARTEN", "NEUTRAL"},
                  {"true", "false"}),
    "improvements": ({"observation"}, {"verified", "rejected", "pending",
                                       "completed", "failed", "testing"}),
    "simulations": ({"open", "closed"}, {"open", "closed", "completed",
                                        "pending", "failed", "stopped"}),
    "quality": ({"metric"}, {"matched", "mismatch", "unavailable"}),
}


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_knowledge_snapshots (
        area TEXT NOT NULL CHECK (area IN
            ('diagnoses','decisions','improvements','simulations','quality')),
        slot BIGINT NOT NULL, captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        summary JSONB NOT NULL, PRIMARY KEY(area,slot))""")


def fold(area, rows):
    """Classify proven source labels, not invent profitability or success."""
    if area not in AREAS:
        raise ValueError("Unknown knowledge area")
    if len(rows) > SAMPLE_CAP:
        raise ValueError("Unbounded source rows")
    seen = set()
    categories, results = Counter(), Counter()
    safe_categories, safe_results = _ALLOWED[area]
    keys = []
    for row in rows:
        if len(row) != 3 or not isinstance(row[0], str) or not row[0]:
            raise ValueError("Invalid sampled source identity")
        if row[0] in seen:
            raise ValueError("Repeated source identity")
        seen.add(row[0])
        keys.append(row[0])
        category = row[1] if row[1] in safe_categories else "unclassified"
        result = row[2] if row[2] in safe_results else "unclassified"
        categories[category] += 1
        results[result] += 1
    fingerprint = hashlib.sha256(json.dumps(
        keys, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return {
        "area": area, "status": "sampled" if rows else "observed-empty",
        "sampling": "indexed-bounded-recent-keys-not-complete-history",
        "sampleCap": SAMPLE_CAP, "sampledRows": len(rows),
        "moreSourceRowsMayExist": len(rows) == SAMPLE_CAP,
        "sourceKeyFingerprint": fingerprint,
        "categories": dict(sorted(categories.items())),
        "outcomes": dict(sorted(results.items())),
        "interpretationStatus": "descriptive-only-not-validated-learning",
        "archiveVerifiedForThisWindow": False,
        "deletionAuthorized": False,
        "physicalBytesFreed": None,
    }


def capture(conn, now):
    """Store tiny daily per-area snapshots; failures leave originals intact.

    The caller owns the normal half-hour storage sampler cadence. Each source
    is isolated in its own transaction/savepoint, with short SQL timeouts so a
    missing or slow table cannot block diagnostics or other summaries.
    """
    slot = int(now // 86400) * 86400
    statuses = {}
    for area in AREAS:
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='800ms'")
                rows = conn.execute(QUERIES[area], (SAMPLE_CAP,)).fetchall()
                summary = fold(area, rows)
                conn.execute("""INSERT INTO bob_knowledge_snapshots(area,slot,summary)
                    VALUES(%s,%s,%s::jsonb)
                    ON CONFLICT(area,slot) DO UPDATE SET
                        captured_at=now(),summary=excluded.summary
                    WHERE bob_knowledge_snapshots.summary IS DISTINCT
                        FROM excluded.summary""",
                    (area, slot, json.dumps(summary, sort_keys=True)))
                statuses[area] = summary["status"]
        except Exception:
            statuses[area] = "not-observed"
    return statuses


def report(conn):
    """Read only five latest aggregate receipts, never evidence or IDs."""
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='800ms'")
            rows = conn.execute("""SELECT DISTINCT ON (area) area,slot,summary
                FROM bob_knowledge_snapshots
                ORDER BY area,slot DESC LIMIT 5""").fetchall()
        entries = {area: dict(summary, slot=slot) for area, slot, summary in rows
                   if area in AREAS and isinstance(summary, dict)}
        return {
            "status": "observed" if entries else "warming",
            "readOnly": True, "coverage": "latest-bounded-sample-per-area",
            "areas": {area: entries.get(area, {"status": "not-observed"})
                      for area in AREAS},
            "deletionAuthorized": False, "physicalBytesFreed": None,
            "note": "Sampled classifications are not completed trading, "
                    "repair, or research conclusions. Verified source "
                    "archives and independent restore tests are mandatory "
                    "before any original replacement or disk reclamation.",
        }
    except Exception:
        return {"status": "not-observed", "readOnly": True,
                "deletionAuthorized": False, "physicalBytesFreed": None}
