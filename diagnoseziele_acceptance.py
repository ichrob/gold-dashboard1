"""Validate narrowly accepted, dated *historical* diagnostic goals.

Only a fixed allowlisted acceptance type can be counted. The record itself
was checked externally against GitHub CI and two independent Render deployments.
This local validation cannot poll GitHub or prove current/continuous health.
"""
from datetime import datetime, timezone
import re

SHA = re.compile(r"[a-f0-9]{40}\Z")
SERVICES = frozenset(("bob-private-scanner", "bob-push-service"))


def _utc(s):
    if not isinstance(s, str) or len(s) > 42:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            return None
        return d.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def assess(goals, register):
    invalid = {"status": "unavailable", "readOnly": True,
               "reason": "invalid-or-unsupported-goal-acceptance"}
    if (not isinstance(goals, list) or len(goals) != 100
            or not isinstance(register, dict)
            or register.get("schemaVersion") != 1
            or not isinstance(register.get("accepted"), list)
            or len(register["accepted"]) != 1):
        return invalid
    by_id = {x.get("id"): x for x in goals if isinstance(x, dict)}
    if len(by_id) != 100:
        return invalid
    # Only one goal has independently recorded specific technical CI + live
    # evidence so far. Never infer approvals for other 99 feature objectives.
    record = register["accepted"][0]
    if not isinstance(record, dict) or record.get("id") != 18:
        return invalid
    goal = by_id.get(18) or {}
    if goal.get("state") != "verified-at-build" or goal.get("verified") is not True:
        return invalid
    if any((g.get("verified") is True) != (g.get("id") == 18)
           for g in goals if isinstance(g, dict)):
        return invalid
    build = record.get("build")
    github = record.get("github")
    service_rows = record.get("render")
    checked = _utc(record.get("checkedAt"))
    if (not isinstance(build, str) or not SHA.fullmatch(build)
            or record.get("kind") != "two-services-exact-build-at-sample"
            or not isinstance(github, dict)
            or type(github.get("ciRun")) is not int or github["ciRun"] <= 0
            or type(github.get("liveSmokeRun")) is not int or github["liveSmokeRun"] <= 0
            or github.get("ciConclusion") != "success"
            or github.get("liveSmokeConclusion") != "success"
            or not isinstance(service_rows, list) or len(service_rows) != 2
            or checked is None):
        return invalid
    names = set()
    for item in service_rows:
        if not isinstance(item, dict):
            return invalid
        finished = _utc(item.get("finishedAt"))
        if (item.get("service") not in SERVICES
                or item.get("service") in names
                or item.get("build") != build
                or item.get("status") != "live"
                or finished is None or not 0 <= (checked - finished).total_seconds() <= 3600):
            return invalid
        names.add(item["service"])
    if names != SERVICES:
        return invalid
    return {
        "status": "one-dated-build-acceptance",
        "readOnly": True,
        "individuallyAcceptedAtRecordedBuild": 1,
        "acceptedGoalIds": [18],
        "acceptedBuild": build,
        "acceptedAt": record["checkedAt"],
        "remainingUnaccepted": 99,
        "currentDeployProven": False,
        "continuouslyHealthyProven": False,
        "scope": "historical-sample-of-exact-ci-and-two-live-Render-builds",
        "note": "The recorded external CI/deploy checks were independently observed. "
                "Local validation checks record structure only; it cannot "
                "independently repeat GitHub/Render probes or guarantee later builds.",
    }
