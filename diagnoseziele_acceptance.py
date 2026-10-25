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


def _valid_build_match(record):
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
        return False
    names = set()
    for item in service_rows:
        if not isinstance(item, dict):
            return False
        finished = _utc(item.get("finishedAt"))
        if (item.get("service") not in SERVICES
                or item.get("service") in names
                or item.get("build") != build
                or item.get("status") != "live"
                or finished is None or not 0 <= (checked - finished).total_seconds() <= 3600):
            return False
        names.add(item["service"])
    return names == SERVICES


def _valid_cpu_memory_window(record):
    """Validate recorded Render observations, not reconstruct provider data."""
    import math
    start = _utc(record.get("windowStart"))
    end = _utc(record.get("windowEnd"))
    if (record.get("kind") != "two-services-readonly-cpu-memory-time-series"
            or record.get("source") != "Render metrics read-only"
            or type(record.get("resolutionSeconds")) is not int
            or record["resolutionSeconds"] != 300
            or start is None or end is None
            or not 0 < (end - start).total_seconds() <= 86400):
        return False
    rows = record.get("services")
    if not isinstance(rows, list) or len(rows) != 2:
        return False
    names = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        name = row.get("service")
        if name not in SERVICES or name in names:
            return False
        names.add(name)
        if (type(row.get("cpuObservations")) is not int
                or type(row.get("memoryObservations")) is not int
                or not 3 <= row["cpuObservations"] <= 300
                or not 3 <= row["memoryObservations"] <= 300):
            return False
        for low, high in (("cpuCoreMin", "cpuCoreMax"),
                          ("memoryBytesMin", "memoryBytesMax")):
            a, b = row.get(low), row.get(high)
            if (type(a) not in (int, float) or type(b) not in (int, float)
                    or not math.isfinite(a) or not math.isfinite(b)
                    or not 0 <= a <= b):
                return False
    return names == SERVICES


def assess(goals, register):
    """Two historical, independent target-specific kinds of acceptance.

    These facts were read via connected Render/GitHub tools before recording.
    Code validates the immutable record's shape, not external provider truth.
    A third goal, mismatched source, or fake success fails closed.
    """
    invalid = {"status": "unavailable", "readOnly": True,
               "reason": "invalid-or-unsupported-goal-acceptance"}
    if (not isinstance(goals, list) or len(goals) != 100
            or not isinstance(register, dict)
            or register.get("schemaVersion") != 1
            or not isinstance(register.get("accepted"), list)
            or len(register["accepted"]) != 2):
        return invalid
    if not all(isinstance(g, dict) and type(g.get("id")) is int for g in goals):
        return invalid
    by_id = {g["id"]: g for g in goals}
    if sorted(by_id) != list(range(1, 101)):
        return invalid
    expected = {13: "verified-at-sample", 18: "verified-at-build"}
    for id_, row in by_id.items():
        accepted = id_ in expected
        if row.get("verified") is not accepted:
            return invalid
        if accepted and row.get("state") != expected[id_]:
            return invalid
        if not accepted and row.get("state") in expected.values():
            return invalid
    records = register["accepted"]
    if any(not isinstance(r, dict) or type(r.get("id")) is not int
           for r in records):
        return invalid
    by_record = {r["id"]: r for r in records}
    if set(by_record) != set(expected) or len(by_record) != 2:
        return invalid
    build_record = by_record[18]
    metric_record = by_record[13]
    if not _valid_build_match(build_record) or not _valid_cpu_memory_window(metric_record):
        return invalid
    return {
        "status": "two-dated-independent-acceptances",
        "readOnly": True,
        "individuallyAcceptedAtRecordedBuild": 1,
        "individuallyAcceptedAtRecordedMetricWindow": 1,
        "acceptedGoalIds": [13, 18],
        "acceptedBuild": build_record["build"],
        "acceptedAt": build_record["checkedAt"],
        "metricSampleWindow": {
            "start": metric_record["windowStart"],
            "end": metric_record["windowEnd"],
            "services": 2,
            "resolutionSeconds": metric_record["resolutionSeconds"],
        },
        "remainingUnaccepted": 98,
        "currentDeployProven": False,
        "continuouslyHealthyProven": False,
        "scope": "historical-external-ci-and-two-live-builds-plus-Render-cpu-memory-series",
        "note": "The recorded external observations were read through connected tools. "
                "Local validation only checks record structure, not fresh Render data. "
                "Neither dated observation proves future capacity, uptime, trading "
                "signals or a permanent repair.",
    }
