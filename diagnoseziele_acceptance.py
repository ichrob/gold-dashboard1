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


def _valid_archived_health_pair(record):
    """Shape-check a *previously* observed private sample; never infer cause."""
    import math
    if (record.get("kind") != "two-private-health-observations-same-build-and-session"
            or record.get("source") != "Bob private diagnostic read-only"
            or not isinstance(record.get("build"), str)
            or not SHA.fullmatch(record["build"])):
        return False
    report = record.get("sourceReport")
    github = record.get("github")
    at = _utc(record.get("observedAt"))
    if (at is None or not isinstance(report, dict) or not isinstance(github, dict)
            or type(github.get("ciRun")) is not int or github["ciRun"] <= 0
            or type(github.get("liveSmokeRun")) is not int or github["liveSmokeRun"] <= 0
            or github.get("ciConclusion") != "success"
            or github.get("liveSmokeConclusion") != "success"
            or report.get("status") != "observed"
            or report.get("stateComparisonStatus") != "observed-comparison"
            or report.get("previousBuild") != record["build"]
            or report.get("currentBuild") != record["build"]
            or report.get("previousSession") != "weekend"
            or report.get("currentSession") != "weekend"
            or report.get("codeDeltaStatus") != "observed"
            or report.get("regressionAssessment") != "no-regression-in-observed-sample"
            or report.get("previousHealth") != "ok"
            or report.get("currentHealth") != "ok"
            or report.get("isRepairVerified") is not False
            or report.get("isDeploymentRegressionVerified") is not False):
        return False
    older, newer = report.get("previousAt"), report.get("currentAt")
    if (type(older) not in (int,float) or type(newer) not in (int,float)
            or not math.isfinite(older) or not math.isfinite(newer)
            or not 0 < older < newer
            or not 0 < newer-older <= 300):
        return False
    # Historical captures were part of the same observed bounded 7-day window.
    return 0 <= at.timestamp()-newer <= 300


_STAGES = frozenset(("input", "analysis", "analysis-failed", "push",
                     "push-delivery", "paper-input", "health", "transport"))


def _valid_archived_stage_window(record):
    """Verify a historic private 7-day sample's fixed, fully redacted shape.

    Source observations were taken independently through the connected
    read-only Bob diagnostics, not produced by this validator.
    """
    import math
    if (record.get("kind") != "private-seven-day-bounded-multistage-archive-sample"
            or record.get("source") != "Bob private diagnostic read-only"
            or not isinstance(record.get("build"), str)
            or not SHA.fullmatch(record["build"])):
        return False
    observed = _utc(record.get("observedAt"))
    github = record.get("github")
    sample = record.get("sample")
    if (observed is None or not isinstance(github, dict)
            or not isinstance(sample, dict)
            or type(github.get("ciRun")) is not int or github["ciRun"] <= 0
            or type(github.get("liveSmokeRun")) is not int
            or github["liveSmokeRun"] <= 0
            or github.get("ciConclusion") != "success"
            or github.get("liveSmokeConclusion") != "success"
            or sample.get("status") != "observed"
            or sample.get("scope") != "sampled-seven-day-best-effort-history-stage-counts"
            or sample.get("readOnly") is not True
            or sample.get("realOrders") is not False
            or sample.get("handsetDeliveryVerified") is not False
            or sample.get("paperExecutionVerified") is not False
            or sample.get("limitPerStage") != 20):
        return False
    counts = sample.get("counts")
    total = sample.get("totalSampled")
    if (not isinstance(counts, dict) or set(counts) != _STAGES
            or any(type(n) is not int or n < 0 or n > 20
                   for n in counts.values())
            or type(total) is not int or total != sum(counts.values())
            or total <= 0 or total > 160):
        return False
    # The sample record represents the successful private read performed on
    # its recorded historic build. Code paths, dates and numbers alone do not
    # prove future completeness or Android/market delivery.
    return True


def _valid_root_module_change(record):
    """Validate the dated root-file detection, not module execution or safety."""
    observed = _utc(record.get("observedAt"))
    github = record.get("github")
    tree = record.get("tree")
    report = record.get("report")
    if (record.get("kind") != "repository-root-new-module-detected-at-build"
            or record.get("source") != "GitHub repository root and Bob private diagnostic read-only"
            or record.get("build") != "e45f9a2e039eacb3cd9e1e4a247f02d4e430fbb7"
            or observed is None or not isinstance(github, dict)
            or github.get("ciRun") != 40244064380
            or github.get("liveSmokeRun") != 40244064379
            or github.get("ciConclusion") != "success"
            or github.get("liveSmokeConclusion") != "success"
            or not isinstance(tree, dict) or not isinstance(report, dict)):
        return False
    if (tree.get("baselineRecordedOn") != "2026-10-25"
            or tree.get("baselineSourceBlobSha") !=
               "a4acd2a55e27633ccd99295b63692b146b401dd6"
            or tree.get("newSourceFile") != "diagnoseziele_work_split.py"):
        return False
    required = {"recordedSourceModules": 236,
                "currentlySeenSourceModules": 237,
                "newPathsNotInBaseline": 1,
                "missingPathsFromBaseline": 0}
    if any(type(tree.get(k)) is not int or tree[k] != v
           for k, v in required.items()):
        return False
    kinds = tree.get("sourceKinds")
    if (not isinstance(kinds, dict)
            or set(kinds) != {"py", "js", "mjs", "cjs"}
            or any(type(v) is not int or v < 0 for v in kinds.values())
            or kinds != {"py": 201, "js": 36, "mjs": 0, "cjs": 0}
            or sum(kinds.values()) != tree["currentlySeenSourceModules"]):
        return False
    if (report.get("status") != "changed-since-recorded-tree"
            or report.get("traversal") != "bounded-direct-repository-root-only"
            or report.get("readOnly") is not True
            or report.get("realOrders") is not False
            or report.get("individualGoalsVerified") != 0
            or report.get("runtimeHealthVerified") is not False
            or report.get("newModulesFunctioningVerified") is not False):
        return False
    # Independent CI, private diagnostic read and GitHub root listing were
    # observed at this fixed historical SHA; a later build is NOT covered.
    return observed.isoformat().startswith("2026-10-26T03:38:17.")


def assess(goals, register):
    """Five narrowly dated, independent samples with distinct target-specific proof.

    These facts were read via connected Render/GitHub tools before recording.
    Code validates the immutable record's shape, not external provider truth.
    A sixth goal, mismatched source, or fake success fails closed.
    """
    invalid = {"status": "unavailable", "readOnly": True,
               "reason": "invalid-or-unsupported-goal-acceptance"}
    if (not isinstance(goals, list) or len(goals) != 100
            or not isinstance(register, dict)
            or register.get("schemaVersion") != 1
            or not isinstance(register.get("accepted"), list)
            or len(register["accepted"]) != 5):
        return invalid
    if not all(isinstance(g, dict) and type(g.get("id")) is int for g in goals):
        return invalid
    by_id = {g["id"]: g for g in goals}
    if sorted(by_id) != list(range(1, 101)):
        return invalid
    expected = {2: "verified-at-sample", 7: "verified-at-sample", 8: "verified-at-sample", 13: "verified-at-sample", 18: "verified-at-build"}
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
    if set(by_record) != set(expected) or len(by_record) != 5:
        return invalid
    build_record = by_record[18]
    metric_record = by_record[13]
    history_record = by_record[8]
    stage_record = by_record[7]
    module_record = by_record[2]
    if (not _valid_build_match(build_record)
            or not _valid_cpu_memory_window(metric_record)
            or not _valid_archived_health_pair(history_record)
            or not _valid_archived_stage_window(stage_record)
            or not _valid_root_module_change(module_record)):
        return invalid
    return {
        "status": "five-dated-independent-acceptances",
        "readOnly": True,
        "individuallyAcceptedAtRecordedBuild": 1,
        "individuallyAcceptedAtRecordedMetricWindow": 1,
        "individuallyAcceptedAtArchivedHealthPair": 1,
        "individuallyAcceptedAtArchivedStageWindow": 1,
        "individuallyAcceptedAtRootModuleChange": 1,
        "acceptedGoalIds": [2, 7, 8, 13, 18],
        "acceptedBuild": build_record["build"],
        "acceptedAt": build_record["checkedAt"],
        "metricSampleWindow": {
            "start": metric_record["windowStart"],
            "end": metric_record["windowEnd"],
            "services": 2,
            "resolutionSeconds": metric_record["resolutionSeconds"],
        },
        "healthPairSample": {
            "sourceBuild": history_record["build"],
            "observedAt": history_record["observedAt"],
            "previousAt": history_record["sourceReport"]["previousAt"],
            "currentAt": history_record["sourceReport"]["currentAt"],
            "session": "weekend",
            "causalRepairVerified": False,
        },
        "stageWindowSample": {
            "sourceBuild": stage_record["build"],
            "observedAt": stage_record["observedAt"],
            "sevenDayWindow": True,
            "limitPerStage": stage_record["sample"]["limitPerStage"],
            "totalSampled": stage_record["sample"]["totalSampled"],
            "counts": dict(stage_record["sample"]["counts"]),
            "handsetDeliveryVerified": False,
            "paperExecutionVerified": False,
            "noRecordedEventMeansNoRealEvent": False,
        },
        "moduleChangeSample": {
            "sourceBuild": module_record["build"],
            "observedAt": module_record["observedAt"],
            "recordedSourceModules": module_record["tree"]["recordedSourceModules"],
            "currentlySeenSourceModules": module_record["tree"]["currentlySeenSourceModules"],
            "newPathsNotInBaseline": 1,
            "runtimeHealthVerified": False,
            "newModulesFunctioningVerified": False,
        },
        "remainingUnaccepted": 95,
        "currentDeployProven": False,
        "continuouslyHealthyProven": False,
        "scope": "dated-ci-Render-metrics-private-health-stage-archive-and-repository-root-change", 
        "note": "The recorded external observations were read through connected tools. "
                "Local validation only checks record structure, not fresh Render data. "
                "No dated observation proves future capacity, uptime, trading "
                "signals or a permanent repair.",
    }
