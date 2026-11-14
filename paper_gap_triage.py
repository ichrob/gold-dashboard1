"""Conservative correlation of bounded paper-gap evidence, never trade reconciliation.

A source sample close to a simulated gap is not evidence that the paper worker
received it, nor that a product bid or safe exit was available. A source
observation after a gap may NOT be treated as earlier data.
"""
import math

def _clock(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def _aligned_clock(item, event_at, field):
    """Require an original clock that agrees with its declared relation and age.

    The source archives round distance to milliseconds. Reject contradictory,
    future-as-past or out-of-window records rather than promoting their status.
    """
    at = _clock(item.get(field))
    relation = 'before-or-at-event' if at is not None and at <= event_at else 'after-event'
    if (at is None or abs(at-event_at) > 90000
            or item.get('timeRelation') != relation):
        return False
    delta = item.get('deltaSeconds')
    if delta is not None and (type(delta) not in (int, float)
            or not math.isfinite(delta)
            or abs(delta - abs(at-event_at)/1000) > .006):
        return False
    return True


def assess(gap_correlation, spot_archive, analysis_archive, paper_input_archive=None):
    """Return one read-only review row per distinct recorded gap instant.

    Inputs are ALREADY redacted diagnostic projections. No SQL, market fetch,
    synthetic interpolation, recalculation of P&L or trading action.
    """
    correlation = gap_correlation if isinstance(gap_correlation, dict) else {}
    recorded = correlation.get("recentRecordedGapInstants")
    clusters = recorded if isinstance(recorded, list) else []
    # Empty *observed* recent case sets are not source-query failures. An
    # empty or malformed unverified report, however, cannot imply health.
    no_recent_gaps_observed = (correlation.get("sampleCoverage") == "observed"
                               and isinstance(recorded, list) and not recorded)
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
        "spotArchiveClockInconsistent": 0,
        "nearby15mNotReadyOrNotFresh": 0,
        "analysisOnlyAfterGap": 0,
        "analysisArchiveClockInconsistent": 0,
        "nearby15mReadyFreshUnlinked": 0,
        "analysisEvidenceMissingOrUnavailable": 0,
        "reviewableInputHandoffCandidates": 0,
        "workerCaptureBeforeOrAtGap": 0,
        "workerCaptureOnlyAfterGap": 0,
        "workerCaptureMissingOrUnavailable": 0,
        "workerArchiveClockInconsistent": 0,
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
        if state == "nearby-original-observed" and not _aligned_clock(source, at, "nearestSourceAt"):
            source_class = "spot-archive-clock-inconsistent"
            counts["spotArchiveClockInconsistent"] += 1
        elif state == "nearby-original-observed" and relation == "before-or-at-event":
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
            if not _aligned_clock(observed, at, "analysisAt"):
                analysis_class = "analysis-archive-clock-inconsistent"
                counts["analysisArchiveClockInconsistent"] += 1
            elif observed["analysisAt"] > at:
                # A healthy *later* evaluator is not evidence at the gap clock.
                analysis_class = "other-15m-analysis-only-after-gap-unlinked"
                counts["analysisOnlyAfterGap"] += 1
            elif observed.get("ready") is True and observed.get("priceFresh") is True:
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
        worker_valid = (worker_state == "worker-input-captured-near-gap"
                        and _aligned_clock(worker_observation, at, "capturedAt"))
        if worker_state == "worker-input-captured-near-gap" and not worker_valid:
            worker_class = "worker-archive-clock-inconsistent"
            counts["workerArchiveClockInconsistent"] += 1
        elif worker_valid and worker_relation == "before-or-at-event":
            worker_class = "worker-capture-before-or-at-gap"
            counts["workerCaptureBeforeOrAtGap"] += 1
        elif worker_valid and worker_relation == "after-event":
            worker_class = "worker-capture-only-after-gap"
            counts["workerCaptureOnlyAfterGap"] += 1
        else:
            worker_class = "no-confirmed-worker-capture-for-gap"
            counts["workerCaptureMissingOrUnavailable"] += 1

        # A handoff/freshness mismatch is only a hypothesis to INVESTIGATE.
        # It does not establish root cause, a missed trade, or an original bid.
        candidate = (source_class == "original-nearby-before-or-at-gap" and
                     analysis_class not in ("other-15m-analysis-ready-and-fresh-unlinked",
                                            "analysis-archive-clock-inconsistent") and
                     worker_class != "worker-archive-clock-inconsistent")
        if candidate:
            counts["reviewableInputHandoffCandidates"] += 1
        next_check = (
            "inspect-inconsistent-archive-clocks" if (
                source_class == "spot-archive-clock-inconsistent" or
                analysis_class == "analysis-archive-clock-inconsistent" or
                worker_class == "worker-archive-clock-inconsistent") else
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
            "workerCapturedAt": _clock(worker_observation.get("capturedAt")) if worker_valid else None,
            "workerInputProfiles": [
                {key: row.get(key) for key in ("profile","outcome","ready","priceFresh","dataAt","barAt")}
                for row in (worker_observation.get("profiles") or [])[:5]
                if isinstance(row,dict) and row.get("profile") in
                   ("conservative","balanced","offensive","early100","trend800")
            ] if worker_valid else [],
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
        "status": ("partial" if any(counts[key] for key in
                   ("spotArchiveClockInconsistent", "analysisArchiveClockInconsistent",
                    "workerArchiveClockInconsistent")) else
                   "observed" if entries else
                   "no-recorded-gaps-in-sample" if no_recent_gaps_observed else
                   "unavailable"),
        "readOnly": True,
        "realOrders": False,
        "sampledDistinctGapInstants": len(entries),
        "fullHistoricalGapCoverageVerified": False,
        "noRecentGapEventsObserved": no_recent_gaps_observed,
        "counts": counts,
        "items": entries,
        "scope": "last-twelve-distinct-recorded-paper-gap-clocks-only",
        "note": "An actual paper input capture shows only what the paper worker received, "
                "not whether an executable product quote existed. No capture before this "
                "instrumentation is no historical absence proof. Other source/analysis "
                "proximity remains a hypothesis, never a filled exit or P/L. "
                "A later source clock cannot reconstruct an earlier interval.",
    }


def assess_archived(gap_evidence):
    """Independently review *stored* original gap clocks, not today's empty cases.

    Accept only fixed, already-redacted 90-second archive projections from the
    existing bounded read-only comparison report. In particular, a matching
    nearby quote, a *later* worker capture, or an archived encrypted object
    never becomes an original simulated fill, realized P/L or replay success.
    No SQL, network, mutations, secrets or archive-reader operations here.
    """
    base = {
        "status": "unavailable",
        "readOnly": True, "realOrders": False,
        "fullHistoricalGapCoverageVerified": False,
        "originalTradeReplayVerified": False,
        "productBidVerified": False, "profitOrLossVerified": False,
        "sampledDistinctGapInstants": 0,
        "counts": {"outsideRetentionOrFuture": 0, "sourceBeforeOrAt": 0,
                   "sourceOnlyAfter": 0, "sourceMissingOrUnverified": 0,
                   "originalClockInconsistent": 0},
        "items": [],
        "scope": "bounded-archived-gap-source-clocks-not-full-simulation-history",
        "note": "An expired local archive window is NOT proof of permanent original loss. "
                "Nearby sources do not prove worker receipt, a product bid, an exit or P/L. "
                "Older originals require independent scoped manifest/restore verification."
    }
    if not isinstance(gap_evidence, dict):
        return dict(base, reason="gap-archive-projections-missing")
    names = ("spotGapArchive", "analysisGapArchive", "paperInputArchive")
    sources = [gap_evidence.get(name) for name in names]
    if not all(isinstance(s, dict) and s.get("status") == "observed"
               and s.get("readOnly") is True and s.get("realOrders") is False
               and s.get("windowSeconds") == 90
               and s.get("truncated") is False
               and isinstance(s.get("items"), list) for s in sources):
        return dict(base, reason="archive-projections-incomplete-or-truncated")
    spot, analysis, worker = sources
    if spot.get("source") != "Gold-API-original-spot-archive":
        return dict(base, reason="wrong-original-source")
    clock_sets = []
    for source in sources:
        items = source["items"]
        total = source.get("totalDistinctClocks")
        count = source.get("sampledDistinctClocks")
        clocks = [_clock(item.get("eventAt")) if isinstance(item, dict) else None
                  for item in items]
        if (type(total) is not int or type(count) is not int
                or not 0 <= count <= total
                or count != len(items) or len(items) > 12
                or any(t is None for t in clocks)
                or len(set(clocks)) != len(clocks)):
            return dict(base, reason="archive-clock-coverage-invalid-or-over-limit")
        clock_sets.append(set(clocks))
    # A missing analysis/worker clock cannot prove an earlier absent worker.
    coverage_matched = clock_sets[0] == clock_sets[1] == clock_sets[2]
    instants = sorted(clock_sets[0])
    if not instants:
        return dict(base, status="no-archived-gaps-in-bounded-sample",
                    reason="no-sampled-archive-events")
    correlation = {"recentRecordedGapInstants": [
        {"recordedAt": at, "affectedVirtualCases": None}
        for at in instants]}
    # The existing triage validates original event timestamps against
    # timeRelation/deltaSeconds before recognizing "before-or-at" evidence.
    triage = assess(correlation, spot, analysis, worker)
    if len(triage["items"]) != len(instants):
        return dict(base, reason="archive-correlation-incomplete")
    spot_by_time = {item["eventAt"]: item for item in spot["items"]}
    counts = dict(base["counts"])
    items = []
    for row in triage["items"]:
        original = spot_by_time[row["recordedAt"]]
        source_state = original.get("state")
        if source_state == "outside-retention-or-future":
            archive_class = "outside-retention-or-future-not-replayed"
            next_step = "locate-matching-earlier-archive-manifest-and-isolated-original"
            counts["outsideRetentionOrFuture"] += 1
        elif row["spotEvidence"] == "original-nearby-before-or-at-gap":
            archive_class = "nearby-original-before-or-at-event-only"
            next_step = "compare-paper-worker-original-input-and-product-bid"
            counts["sourceBeforeOrAt"] += 1
        elif row["spotEvidence"] == "original-only-observed-after-gap":
            archive_class = "nearby-original-after-event-only"
            next_step = "do-not-backdate-later-quote"
            counts["sourceOnlyAfter"] += 1
        elif row["spotEvidence"] == "spot-archive-clock-inconsistent":
            archive_class = "source-clock-inconsistent"
            next_step = "verify-original-source-timestamps"
            counts["originalClockInconsistent"] += 1
        else:
            archive_class = "original-evidence-missing-or-unverified"
            next_step = "inspect-matching-original-archive-provenance"
            counts["sourceMissingOrUnverified"] += 1
        items.append({
            "recordedAt": row["recordedAt"],
            "archiveEvidence": archive_class,
            "analysisEvidence": row["analysisEvidence"],
            "workerEvidence": row["paperWorkerEvidence"],
            "nextCheck": next_step,
            "originalTradeReplayVerified": False,
            "productBidVerified": False,
            "executedExitVerified": False,
            "profitOrLossVerified": False
        })
    return dict(
        base,
        status="partial" if (not coverage_matched
                            or counts["outsideRetentionOrFuture"]
                            or counts["originalClockInconsistent"]
                            or counts["sourceMissingOrUnverified"]
                            or triage["status"] != "observed") else "observed",
        sampledDistinctGapInstants=len(items),
        archiveClockSetsMatched=coverage_matched,
        counts=counts, items=items,
        reason=("older-original-archive-proof-required"
                if counts["outsideRetentionOrFuture"] else
                "archive-clock-coverage-mismatch" if not coverage_matched else
                "bounded-originals-not-execution-proof")
    )
