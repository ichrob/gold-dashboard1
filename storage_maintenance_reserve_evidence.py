"""Pure, operator-only WAL/scratch/lock evidence budget for a future storage pilot.

No PostgreSQL connection, no Render API call, no filesystem inspection,
no maintenance/restart/archiving/deletion and no automatic runtime hook.
Inputs must come from independently authorized, timestamped operator probes.
The evaluator NEVER grants a production operation. A single lock snapshot
cannot prove that a future lock will be available.
"""
import math

from storage_capacity import ALLOCATION_BYTES

RESOURCE = "dpg-datjno1srm7s738vv500-a"
TARGET = "public.bob_improvement_observations"
MAX_AGE_SECONDS = 120
MIN_BUFFER_BYTES = 120_000_000
MAX_NUMBER = 10**12


def _scalar(v, *, positive=False):
    return (type(v) is int and
            (0 < v <= MAX_NUMBER if positive else 0 <= v <= MAX_NUMBER))


def _time(v, now):
    return (type(v) in (int, float) and math.isfinite(v)
            and 0 <= now - v <= MAX_AGE_SECONDS)


def _out(status, *, missing=(), capacity_remaining=None, expected_peak=None):
    return {
        "status": status,
        "target": TARGET,
        "missingEvidence": list(missing),
        "independentVolumeHeadroomBytes": capacity_remaining,
        "conservativeEstimatedPeakBytes": expected_peak,
        "independentActualWALPeakProven": False,
        "futureLockAvailabilityProven": False,
        "scratchOnCorrectHostProvenByThisEvaluator": False,
        "providerMaintenanceBeforeAfterPairVerified": False,
        "storageCleanupAuthorized": False,
        "readyToExecute": False,
        "readOnly": True,
        "productionRowsChanged": False,
        "deletionAuthorized": False,
        "physicalBytesFreed": None,
    }


def assess(*, now, volume=None, wal=None, scratch=None, locks=None,
           isolated_workload=None):
    """Check completeness and arithmetic of bounded externally measured inputs.

    'Candidate' means that the supplied figures can be cross-checked. It is
    not permission and not a complete resource or concurrency proof.
    """
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        return _out("invalid-clock")
    missing = []
    valid_volume = (
        type(volume) is dict and
        volume.get("status") == "observed" and
        volume.get("source") == "render-metrics-api" and
        volume.get("resource") == RESOURCE and
        volume.get("scope") == "volume-usage" and
        volume.get("unit") == "bytes" and
        _time(volume.get("observedAt"), now) and
        _scalar(volume.get("diskUsage"), positive=True) and
        volume["diskUsage"] < ALLOCATION_BYTES
    )
    if not valid_volume:
        missing.append("fresh-provider-volume")
    valid_wal = (
        type(wal) is dict and
        wal.get("source") == "pg-stat-wal-and-waldir" and
        _time(wal.get("observedAt"), now) and
        _scalar(wal.get("walDirectoryBytes")) and
        _scalar(wal.get("generatedBytesDelta")) and
        wal.get("statsResetUnchanged") is True and
        type(wal.get("windowSeconds")) in (int, float) and
        math.isfinite(wal["windowSeconds"]) and
        10 <= wal["windowSeconds"] <= 90
    )
    if not valid_wal:
        missing.append("fresh-wal-counters-and-directory")
    valid_scratch = (
        type(scratch) is dict and
        scratch.get("source") == "filesystem-free-space-probe" and
        _time(scratch.get("observedAt"), now) and
        scratch.get("sameWorkDirectory") is True and
        _scalar(scratch.get("freeBytes"), positive=True)
    )
    if not valid_scratch:
        missing.append("scratch-free-space-at-actual-workdir")
    valid_locks = (
        type(locks) is dict and
        locks.get("source") == "postgres-pg-stat-activity" and
        _time(locks.get("observedAt"), now) and
        _scalar(locks.get("waitingOnLock")) and
        _scalar(locks.get("idleInTransaction")) and
        _scalar(locks.get("activeSessions"))
    )
    if not valid_locks:
        missing.append("fresh-lock-observation")
    valid_workload = (
        type(isolated_workload) is dict and
        isolated_workload.get("source") == "isolated-same-workload-measurement" and
        isolated_workload.get("table") == TARGET and
        _scalar(isolated_workload.get("targetTableBytes"), positive=True) and
        _scalar(isolated_workload.get("worstCaseWalBytes"), positive=True) and
        _scalar(isolated_workload.get("peakScratchBytes"), positive=True) and
        isolated_workload.get("independentReplayVerified") is True
    )
    if not valid_workload:
        missing.append("independently-measured-same-workload-peaks")
    if missing:
        return _out("evidence-incomplete", missing=missing)
    # The two-copy envelope is a conservative feasibility calculation, NOT
    # evidence of runtime WAL reserve or a guarantee of free locks.
    expected_peak = (
        2 * isolated_workload["targetTableBytes"] +
        isolated_workload["worstCaseWalBytes"] +
        isolated_workload["peakScratchBytes"] +
        MIN_BUFFER_BYTES
    )
    available = ALLOCATION_BYTES - volume["diskUsage"]
    if scratch["freeBytes"] < isolated_workload["peakScratchBytes"]:
        return _out("scratch-envelope-insufficient",
                    capacity_remaining=available, expected_peak=expected_peak)
    if available <= expected_peak:
        return _out("provider-capacity-envelope-insufficient",
                    capacity_remaining=available, expected_peak=expected_peak)
    if locks["waitingOnLock"] or locks["idleInTransaction"]:
        return _out("lock-contention-observed",
                    capacity_remaining=available, expected_peak=expected_peak)
    return _out("operator-evidence-envelope-plausible-not-authorized",
                capacity_remaining=available, expected_peak=expected_peak)
