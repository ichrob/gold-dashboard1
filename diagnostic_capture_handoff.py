"""Safe triage of sampled diagnostic handoff evidence, not event outcomes.

No provider, device, paper-account or market activity is triggered here.
A stage count does not correlate stages by trace; zero is never a lost event.
"""
STAGES = ('input', 'analysis', 'analysis-failed', 'push',
          'push-delivery', 'paper-input', 'health', 'transport')
_LIMIT = 20


def review(stage_coverage, paper=None):
    base = {
        'status': 'insufficient-evidence',
        'readOnly': True, 'realOrders': False,
        'originalEventCorrelationVerified': False,
        'androidDeliveryVerified': False,
        'virtualExecutionVerified': False,
        'continuousCaptureVerified': False,
        'scope': 'best-effort-eight-stage-samples-not-provider-or-market-proof',
    }
    if not isinstance(stage_coverage, dict):
        return {**base, 'reason': 'capture-summary-unavailable'}
    counts = stage_coverage.get('counts')
    total = stage_coverage.get('totalSampled')
    if (stage_coverage.get('status') not in ('observed', 'warming')
            or not isinstance(counts, dict)
            or set(counts) != set(STAGES)
            or any(type(counts[k]) is not int or not 0 <= counts[k] <= _LIMIT
                   for k in STAGES)
            or type(total) is not int or total != sum(counts.values())
            or stage_coverage.get('limitPerStage') != _LIMIT):
        return {**base, 'reason': 'capture-summary-malformed'}

    paper_state = 'unknown'
    session = 'unknown'
    if isinstance(paper, dict):
        if paper.get('state') in ('paused', 'running', 'stopped'):
            paper_state = paper['state']
        if paper.get('sessionMode') in ('trading', 'preparation', 'night', 'weekend'):
            session = paper['sessionMode']
    # Count categories *separately*: there is no trace join, so even two
    # positive counters do not identify a shared decision or delivery.
    has_push_decision = counts['push'] > 0
    has_provider_capture = counts['push-delivery'] > 0
    push_state = (
        'push-and-provider-stages-separately-captured-not-paired'
        if has_push_decision and has_provider_capture else
        'push-decision-sampled-provider-stage-not-observed'
        if has_push_decision else
        'provider-attempt-sampled-decision-stage-not-observed'
        if has_provider_capture else 'neither-push-stage-observed')
    paper_state_label = ('paper-input-stage-observed-not-fill-proof'
                         if counts['paper-input'] > 0
                         else 'paper-input-stage-not-observed')
    return {
        **base,
        'status': 'observed-sample' if total > 0 else 'insufficient-evidence',
        'totalSampled': total,
        'stageLimitPerType': _LIMIT,
        'push': {
            'decisionStageSampled': counts['push'],
            'providerAttemptStageSampled': counts['push-delivery'],
            'handoffState': push_state,
            'tracePaired': False, 'deviceReceived': False,
        },
        'paper': {
            'inputStageSampled': counts['paper-input'],
            'handoffState': paper_state_label,
            'workerStateAtRead': paper_state,
            'sessionModeAtRead': session,
            'tradeOutcomeVerified': False,
        },
        'reviewReason': (
            'Original handoff captures need review at a later active session; '
            'an empty bounded sample does NOT prove failed push, missing '
            'simulations, dropped reports or no previous market activity.'),
        'evidenceLimit': 'last-twenty-per-stage-in-seven-day-best-effort-journal',
    }
