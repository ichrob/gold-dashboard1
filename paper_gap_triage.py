"""Conservative correlation of bounded paper-gap evidence, never trade reconciliation.

A source sample close to a simulated gap is not evidence that the paper worker
received it, nor that a product bid or safe exit was available. A source
observation after a gap may NOT be treated as earlier data.
"""
import math

def _clock(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def assess(gap_correlation, spot_archive, analysis_archive, paper_input_archive=None):
    """Return one read-only review row per distinct recorded gap instant.

    Inputs are ALREADY redacted diagnostic projections. No SQL, market fetch,
    synthetic interpolation, recalculation of P&L or trading action.
    """
    correlation = gap_correlation if isinstance(gap_correlation, dict) else {}
    clusters = correlation.get("recentRecordedGapInstants") or []
    spot = spot_archive if isinstance(spot_archive, dict) else {}
    analysis = analysis_archive if isinstance(analysis_archive, dict) else {}
    worker = paper_input_archive if isinstance(paper_input_archive,dict) else {}
    def index(archive):
        result = {}
        for item in (archive.get("items") or [])[:20]:
            if isinstance(item, dict):
                at = _clock(item.get("eventAt"))
                if at is not None:
                    result[at] = item
        return result
    spot_by_time = index(spot)
    analysis_by_time = index(analysis)
    worker_by_time = index(worker)
    entries = []
    counts = {
        "originalAtOrBeforeWithin60s": 0,
        "originalAfterEventOnly": 0,
        "originalBeforeButOlderThan60s": 0,
        "noGoldApiOriginalIn90sWindow": 0,
        "spotArchiveUnavailableOrMissing": 0,
        "nearby15mNotReadyOrNotFresh": 0,
        "nearby15mReadyFreshUnlinked": 0,
        "analysisEvidenceMissingOrUnavailable": 0,
        "reviewableInputHandoffCandidates": 0,
        "workerCaptureBeforeOrAtGap": 0,
        "workerCaptureOnlyAfterGap": 0,
        "workerCaptureMissingOrUnavailable": 0,
    }
    for cluster in clusters[-12:]:
        if not isinstance(cluster, dict):
            continue
        at = _clock(cluster.get("recordedAt"))
        if at is None:
            continue
        source = spot_by_time.get(at, {})
        state = source.get("state")
        relation = source.get("timeRelation")
        delta = source.get("deltaSeconds")
        delta = delta if type(delta) in (int, float) and math.isfinite(delta) and delta >= 0 else None
        if state == "nearby-original-observed" and relation == "before-or-at-event":
            if delta is not None and delta <= 60:
                source_class = "original-nearby-before-or-at-gap"
                counts["originalAtOrBeforeWithin60s"] += 1
            else:
                source_class = "original-before-gap-but-not-current"
                counts["originalBeforeButOlderThan60s"] += 1
        elif state == "nearby-original-observed" and relation == "after-event":
            source_class = "original-only-observed-after-gap"
            counts["originalAfterEventOnly"] += 1
        elif state == "no-original-observed-in-90s-window":
            source_class = "no-gold-api-original-in-sampled-window"
            counts["noGoldApiOriginalIn90sWindow"] += 1
        else:
            source_class = "spot-archive-evidence-unavailable"
            counts["spotArchiveUnavailableOrMissing"] += 1
        observed = analysis_by_time.get(at, {})
        if observed.get("state") == "nearby-15m-analysis-observed":
            if observed.get("ready") is True and observed.get("priceFresh") is True:
                analysis_class = "other-15m-analysis-ready-and-fresh-unlinked"
                counts["nearby15mReadyFreshUnlinked"] += 1
            else:
                analysis_class = "other-15m-analysis-not-confirmed-ready-and-fresh"
                counts["nearby15mNotReadyOrNotFresh"] += 1
        else:
            analysis_class = "no-confirmed-nearby-15m-analysis"
            counts["analysisEvidenceMissingOrUnavailable"] += 1

        worker_observation = worker_by_time.get(at, {})
        worker_state = worker_observation.get("state")
        worker_relation = worker_observation.get("timeRelation")
        if worker_state == "worker-input-captured-near-gap" and worker_relation == "before-or-at-event":
            worker_class = "worker-capture-before-or-at-gap"
            counts["workerCaptureBeforeOrAtGap"] += 1
        elif worker_state == "worker-input-captured-near-gap" and worker_relation == "after-event":
            worker_class = "worker-capture-only-after-gap"
            counts["workerCaptureOnlyAfterGap"] += 1
        else:
            worker_class = "no-confirmed-worker-capture-for-gap"
            counts["workerCaptureMissingOrUnavailable"] += 1

        # A handoff/freshness mismatch is only a hypothesis to INVESTIGATE.
        # It does not establish root cause, a missed trade, or an original bid.
        candidate = (source_class == "original-nearby-before-or-at-gap" and
                     analysis_class != "other-15m-analysis-ready-and-fresh-unlinked")
        if candidate:
            counts["reviewableInputHandoffCandidates"] += 1
        next_check = (
            "compare-original-source-clock-with-paper-worker-input" if candidate else
            "never-backdate-later-original-observation" if source_class == "original-only-observed-after-gap" else
            "inspect-original-other-feeds-and-worker-clocks" if source_class == "no-gold-api-original-in-sampled-window" else
            "check-time-alignment-and-source-freshness" if source_class == "original-nearby-before-or-at-gap" else
            "inspect-archive-retention-and-instrumentation")
        entries.append({
            "recordedAt": at,
            "affectedVirtualCases": cluster.get("affectedVirtualCases") if
                type(cluster.get("affectedVirtualCases")) is int else None,
            "spotEvidence": source_class,
            "analysisEvidence": analysis_class,
            "paperWorkerEvidence": worker_class,
            "workerCapturedAt": _clock(worker_observation.get("capturedAt")),
            "workerInputProfiles": [
                {key: row.get(key) for key in ("profile","outcome","ready","priceFresh","dataAt","barAt")}
                for row in (worker_observation.get("profiles") or [])[:5]
                if isinstance(row,dict) and row.get("profile") in
                   ("conservative","balanced","offensive","early100","trend800")
            ],
            "sourceAt": _clock(source.get("nearestSourceAt")),
            "analysisAt": _clock(observed.get("analysisAt")),
            "sourceRelation": relation if relation in ("before-or-at-event","after-event") else None,
            "reviewHypothesis": "possible-input-handoff-or-freshness-mismatch" if candidate else "unresolved",
            "nextCheck": next_check,
            "rootCauseVerified": False,
            "productBidVerified": False,
            "executedExitVerified": False,
            "profitOrLossVerified": False,
        })
    return {
        "status": "observed" if entries else "unavailable",
        "readOnly": True,
        "realOrders": False,
        "sampledDistinctGapInstants": len(entries),
        "counts": counts,
        "items": entries,
        "scope": "last-twelve-distinct-recorded-paper-gap-clocks-only",
        "note": "An actual paper input capture shows only what the paper worker received, "
                "not whether an executable product quote existed. No capture before this "
                "instrumentation is no historical absence proof. Other source/analysis "
                "proximity remains a hypothesis, never a filled exit or P/L. "
                "A later source clock cannot reconstruct an earlier interval.",
    }
