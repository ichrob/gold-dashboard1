"""Fail-closed, source-only inventory of representative regression tests for 100 goals.

A matching test filename is not proof that it asserts an individual goal, ran
in a particular CI build or passed independently. Never set verified=True.
No dynamic imports, test execution, DB, network, account or Android access.
"""
from pathlib import Path
import re

_TEST = re.compile(r"test_[a-z0-9_]+\.(?:py|js|cjs)\Z")


def _safe_file(root, filename):
    if not isinstance(filename, str) or not _TEST.fullmatch(filename):
        return False
    path = (root / filename).resolve()
    return path.is_relative_to(root) and path.is_file()


def assess(root, goals, mapping):
    """Report code-to-test *candidates*, never an acceptance verdict."""
    unavailable = {"status": "unavailable", "readOnly": True,
                   "individuallyVerified": 0,
                   "reason": "invalid-or-unavailable-test-mapping"}
    if not isinstance(goals, list) or not isinstance(mapping, dict):
        return unavailable
    rows = mapping.get("goalEvidence")
    if (len(goals) != 100 or mapping.get("schemaVersion") != 1
            or mapping.get("testExecution") != "not-individually-attested"
            or not isinstance(rows, list) or len(rows) != 100
            or any(not isinstance(row, dict) for row in rows)
            or any(not isinstance(row, dict) for row in goals)):
        return unavailable
    try:
        if (sorted(g["id"] for g in goals) != list(range(1, 101))
                or sorted(r["id"] for r in rows) != list(range(1, 101))):
            return unavailable
    except (KeyError, TypeError):
        return unavailable
    by_id = {g["id"]: g for g in goals}
    root = Path(root).resolve()
    unique_tests = set()
    mapped = 0
    missing = []
    test_kinds = {"python": 0, "javascript": 0}
    for row in rows:
        number = row["id"]
        # This is only a mapping check. Separate acceptance guards validate
        # goal-7 seven-day archive, goal-8 health pair, goal-13 Render and goal-18 build.
        evidence_state = by_id[number].get("state")
        expected_verified = ((number == 18 and evidence_state == "verified-at-build")
                             or (number in (7, 8, 13) and evidence_state == "verified-at-sample"))
        if (row.get("claim") != "test-file-candidate-only"
                or by_id[number].get("verified") is not expected_verified):
            return unavailable
        filename = row.get("representativeTest")
        if not isinstance(filename, str) or not _TEST.fullmatch(filename):
            return unavailable
        unique_tests.add(filename)
        if _safe_file(root, filename):
            mapped += 1
            test_kinds["python" if filename.endswith(".py") else "javascript"] += 1
        else:
            missing.append(number)
    # These boundaries are user-consent/platform requirements, not silently
    # satisfiable server tests. Return only IDs (never raw source paths).
    devices = [i for i in range(1, 101) if by_id[i].get("state") == "requires-device"]
    client = [i for i in range(1, 101) if by_id[i].get("state") == "blocked-client"]
    return {
        "status": "test-candidates-mapped" if not missing else "partial",
        "readOnly": True, "total": 100,
        "goalTestCandidatesPresent": mapped,
        "goalTestCandidatesMissing": len(missing),
        "missingGoalIds": missing[:20],
        "uniqueTestFiles": len(unique_tests),
        "mappedTestKinds": test_kinds,
        "individualGoalAssertionsConfirmed": 0,
        "ciExecutionVerifiedPerGoal": 0,
        "individuallyVerified": 0,
        "deviceRequiredGoalIds": devices,
        "clientBlockedGoalIds": client,
        "scope": "representative-test-file-existence-not-individual-acceptance",
        "note": "A representative test file can cover other behavior. Passing group CI, "
                "file existence and a healthy worker are not independent goal acceptance. "
                "Live source, access-control, original-clock and negative evidence "
                "must be checked per goal before any goal is verified.",
    }
