"""Bounded read-only operational observations; never invoke repair or trading."""
import paper_case_review
from datetime import datetime, timezone, timedelta
from pathlib import Path
import math
import time
import re
import threading


def fields(value, keys):
    value = value if isinstance(value, dict) else {}
    out = {}
    for key in keys:
        item = value.get(key)
        if item is None or isinstance(item, bool):
            out[key] = item
        elif isinstance(item, str):
            out[key] = clean_text(item)
        elif type(item) in (int, float) and math.isfinite(item):
            out[key] = item
    return out



def collection_cycle_snapshot(value, now=None):
    """Project only bounded scheduler counters from Bob's in-process collection.

    A worker start gap is not independently verified loss of any market tick.
    Unknown, malformed, future-dated or forged availability stays unavailable.
    """
    unavailable = {'status':'unavailable', 'readOnly':True,
                   'workerMissedCyclesVerified':False,
                   'scope':'process-local-worker-starts-not-market-tick-proof'}
    if (not isinstance(value, dict)
            or value.get('readOnly') is not True
            or value.get('workerMissedCyclesVerified') is not False
            or value.get('scope') != unavailable['scope']):
        return unavailable
    status = value.get('status')
    if status == 'not-observed':
        if type(value.get('observedCycles')) is not int or value['observedCycles'] != 0:
            return unavailable
        return dict(unavailable, status='not-observed', observedCycles=0)
    if status != 'observed':
        return unavailable
    integer = lambda key, lo, hi: (type(value.get(key)) is int
                                   and lo <= value[key] <= hi)
    finite = lambda key, lo, hi: (type(value.get(key)) in (int, float)
                                  and math.isfinite(value[key])
                                  and lo <= value[key] <= hi)
    if (not integer('observedCycles', 1, 20)
            or not integer('comparableStartIntervals', 0, 19)
            or value['comparableStartIntervals'] > value['observedCycles']-1
            or not integer('lastDurationMs', 0, 3600000)
            or not integer('configuredSeconds', 1, 1800)
            or not finite('plannedWaitSeconds', 1, 1800)):
        return unavailable
    gaps = ('maxObservedStartGapSeconds', 'lastObservedStartGapSeconds')
    for name in gaps:
        if value.get(name) is not None and not finite(name, 0, 86400):
            return unavailable
    if ((value['comparableStartIntervals'] == 0)
            != (value.get('maxObservedStartGapSeconds') is None)):
        return unavailable
    clocks = []
    for name in ('lastStartedAt', 'lastCompletedAt'):
        t = value.get(name)
        if not isinstance(t, str) or len(t) > 42:
            return unavailable
        try:
            dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return unavailable
            clocks.append(dt.astimezone(timezone.utc))
        except (TypeError, ValueError, OverflowError):
            return unavailable
    current = datetime.now(timezone.utc) if now is None else now
    if not isinstance(current, datetime) or current.tzinfo is None:
        return unavailable
    current = current.astimezone(timezone.utc)
    age = (current - clocks[1]).total_seconds()
    if (not 0 <= (clocks[1]-clocks[0]).total_seconds() <= 3600
            or age < -2):
        return unavailable
    age = max(0, age)
    # Three nominal cadences distinguish recent from old process-local
    # observations. 'stale' never asserts that a market tick was missed.
    stale_after = max(90, value['configuredSeconds'] * 3)
    freshness = 'stale' if age > stale_after else 'current'
    return {**unavailable, 'status':'observed' if freshness == 'current' else 'stale',
            'freshness':freshness, 'lastCompletionAgeSeconds':round(age, 3),
            'staleAfterSeconds':stale_after,
            **fields(value, ('observedCycles','comparableStartIntervals',
                             'maxObservedStartGapSeconds','lastStartedAt',
                             'lastCompletedAt','lastDurationMs',
                             'configuredSeconds','plannedWaitSeconds',
                             'lastObservedStartGapSeconds'))}



def evaluator_queue_log_sample(logs, *, window_start, window_end,
                               resource_id, has_more=False):
    """Classify a bounded Render evaluator sample without inferring lost work.

    Cumulative counters belong to ONE runtime instance. Never sum them across
    rolling deployments; process-local zero is not verified system recovery.
    Caller-supplied logs cannot independently prove provider provenance.
    """
    import json
    invalid = {'status':'insufficient-evidence', 'readOnly':True,
               'realOrders':False, 'liveVerified':False,
               'completeTrafficProven':False,
               'queueLossVerified':False}
    def clock(value):
        if not isinstance(value, str) or not 10 <= len(value) <= 42:
            return None
        try:
            t = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return t.astimezone(timezone.utc) if t.tzinfo else None
        except (ValueError, OverflowError):
            return None
    start, end = clock(window_start), clock(window_end)
    if (not isinstance(logs, list) or not start or not end or start >= end
            or not isinstance(resource_id, str) or not resource_id.startswith('srv-')
            or len(resource_id) > 100 or type(has_more) is not bool):
        return invalid
    samples = {}
    ignored = 0
    for row in logs[:100]:
        stamp = clock(row.get('timestamp')) if isinstance(row, dict) else None
        if stamp is None or not start <= stamp <= end:
            ignored += 1
            continue
        labels = row.get('labels')
        if not isinstance(labels, list):
            ignored += 1
            continue
        labelmap = {}
        for label in labels:
            if isinstance(label, dict) and label.get('name') in ('resource','instance','type'):
                labelmap[label['name']] = label.get('value')
        instance = labelmap.get('instance')
        message = row.get('message')
        if (labelmap.get('resource') != resource_id
                or labelmap.get('type') != 'app'
                or not isinstance(instance, str) or not instance.startswith(resource_id+'-')
                or len(instance) > 150
                or not isinstance(message, str)
                or not message.startswith('BOB_EVALUATOR ')
                or len(message) > 1024):
            ignored += 1
            continue
        try:
            data = json.loads(message[len('BOB_EVALUATOR '):])
        except (ValueError, TypeError):
            ignored += 1
            continue
        keys = ('completed','failed','queueTimeouts','shared',
                'waiting','lastWaitMs','lastDurationMs')
        if (not isinstance(data, dict)
                or any(type(data.get(key)) is not int or not 0 <= data[key] <= 1000000000
                       for key in keys)):
            ignored += 1
            continue
        samples.setdefault(instance, []).append((stamp, data))
    ordered = []
    regressions = 0
    for values in samples.values():
        values.sort(key=lambda item:item[0])
        for (_, previous), (_, following) in zip(values, values[1:]):
            if any(following[k] < previous[k]
                   for k in ('completed','failed','queueTimeouts','shared')):
                regressions += 1
        ordered.extend(v for _, v in values)
    if not ordered:
        return {**invalid, 'sampledRecords':min(100,len(logs)),
                'invalidOrIgnoredRecords':ignored,
                'sampleTruncated':len(logs)>100 or has_more}
    return {'status':'classified-sample', 'readOnly':True, 'realOrders':False,
            'liveVerified':False, 'completeTrafficProven':False,
            'queueLossVerified':False,
            'source':'caller-supplied-bounded-Render-app-log-observations',
            'windowStart':start.isoformat(), 'windowEnd':end.isoformat(),
            'sampledRecords':min(100,len(logs)),
            'validEvaluatorRecords':len(ordered),
            'invalidOrIgnoredRecords':ignored,
            'sampleTruncated':len(logs)>100 or has_more,
            'distinctProcessInstances':len(samples),
            'sameInstanceCounterRegressions':regressions,
            'maxObservedWaiting':max(v['waiting'] for v in ordered),
            'maxLastWaitMs':max(v['lastWaitMs'] for v in ordered),
            'observedNonzeroFailureCounter':any(v['failed']>0 for v in ordered),
            'observedNonzeroQueueTimeoutCounter':any(v['queueTimeouts']>0
                                                      for v in ordered),
            'note':'Process counters restart per instance. Samples cannot prove '
                   'unobserved queue items were not lost, full traffic coverage, '
                   'root cause or repaired alerts. No account or message data.'}



def database_contention_log_sample(logs, *, resource_id, window_start,
                                   window_end, has_more=False):
    """Classify caller-supplied, bounded Render *application* error logs.

    QueryCanceled is NOT necessarily a server-side statement timeout;
    LockNotAvailable is NOT proof that one specified migration caused it.
    The tool never reads or writes a database or returns user/SQL/instance data.
    """
    def unavailable():
        return {'status':'insufficient-evidence', 'readOnly':True,
                'realOrders':False, 'providerVerified':False,
                'fullDatabaseAuditVerified':False, 'causeVerified':False,
                'completeTrafficProven':False}
    def utc(value):
        if not isinstance(value,str) or not 10 <= len(value) <= 42:
            return None
        try:
            t=datetime.fromisoformat(value.replace('Z','+00:00'))
            return t.astimezone(timezone.utc) if t.tzinfo else None
        except (ValueError, OverflowError):
            return None
    start,end=utc(window_start),utc(window_end)
    if (not isinstance(logs,list) or type(has_more) is not bool
            or start is None or end is None or start>=end
            or not isinstance(resource_id,str) or not resource_id.startswith('srv-')
            or len(resource_id)>100):
        return unavailable()
    # Only previously observed fixed, non-personal log markers and paths.
    markers=frozenset(('BOB_RANKING','BOB_METRIC_PRODUCT',
                       'BOB_PRECISION_CAPTURE','BOB_METRIC_CAPTURE','BOB_VIDEO_OCR'))
    routes=frozenset(('/diagnostic-history','/youtube-feed/write',
                      '/research-transcript/read','/research-enhancement/read',
                      '/market-validations/write'))
    counts={'QueryCanceled':0,'LockNotAvailable':0}
    source_counts={}
    accepted=0
    ignored=0
    for row in logs[:100]:
        if not isinstance(row,dict):
            ignored+=1
            continue
        stamp=utc(row.get('timestamp'))
        labels=row.get('labels')
        if stamp is None or stamp<start or stamp>end or not isinstance(labels,list):
            ignored+=1
            continue
        meta={}
        for label in labels:
            if isinstance(label,dict) and label.get('name') in ('resource','type','instance'):
                meta[label['name']]=label.get('value')
        instance=meta.get('instance')
        if (meta.get('resource')!=resource_id or meta.get('type')!='app'
                or not isinstance(instance,str) or len(instance)>150
                or not instance.startswith(resource_id+'-')):
            ignored+=1
            continue
        message=row.get('message')
        if not isinstance(message,str) or len(message)>512:
            ignored+=1
            continue
        parts=message.split()
        if len(parts)==3 and parts[0]=='BOB_PUSH' and parts[1]=='database_busy':
            path=parts[2]  # reject; normal marker needs path and error tokens
            ignored+=1
            continue
        if (len(parts)==4 and parts[0]=='BOB_PUSH'
                and parts[1]=='database_busy'
                and parts[2].startswith('path=')
                and parts[3].startswith('error=')):
            raw=parts[2][len('path='):]
            source=raw if raw in routes else 'other-unclassified'
            error=parts[3][len('error='):]
        elif len(parts)==2 and parts[0] in markers and parts[1].startswith('error='):
            source=parts[0]
            error=parts[1][len('error='):]
        else:
            ignored+=1
            continue
        if error not in counts:
            ignored+=1
            continue
        accepted+=1
        counts[error]+=1
        entry=source_counts.setdefault(source,{'QueryCanceled':0,'LockNotAvailable':0})
        entry[error]+=1
    result=unavailable()
    result.update(status='classified-sample' if accepted else 'insufficient-evidence',
                  source='caller-supplied-bounded-Render-application-error-logs',
                  windowStart=start.isoformat(),windowEnd=end.isoformat(),
                  sampledRecords=min(len(logs),100),validDatabaseErrorRecords=accepted,
                  invalidOrIgnoredRecords=ignored,sampleTruncated=(len(logs)>100 or has_more),
                  errorTypes=counts,
                  sources=[{'source':name,**source_counts[name]}
                           for name in sorted(source_counts)],
                  note='Only fixed log markers and static route names are shown. '
                       'One observed SQL error type does not prove root cause, '
                       'which query was canceled, or 30-day audit completion. '
                       'Missing logs do not establish a healthy database.')
    return result


def market_snapshot(live, cached_at, now=None):
    now = time.time() if now is None else now
    live = live if isinstance(live, dict) else {}
    age = now - cached_at if cached_at else None
    bars = (live.get('history') or {}).get('bars_by_tf') or {}
    from market_review import frame_health
    from background_push import degiro_session
    # The user's 08:00–22:00 routine is not an exchange closure signal.
    # Report it as context only; do not turn stale candles into fresh candles.
    session_mode = degiro_session(now * 1000)
    return {'status': 'unavailable' if not live else 'stale' if age is None or not 0 <= age <= 120 else live.get('status', 'observed'),
            'sessionMode': session_mode,
            'cacheAgeSeconds': age, 'cachedAt': cached_at or None,
            'source': fields(live.get('spots'), ('spot_price_as_of', 'primary', 'xaus_is_spot', 'is_genuine_xauusd_spot')),
            'candles': {tf: {'integrity':frame_health(bars.get(tf, []), tf, now*1000), 'count':len(bars.get(tf, [])),
                            'last': fields(bars[tf][-1], ('openTime','source','instrument')) if bars.get(tf) else None}
                        for tf in ('1m','5m','15m','30m','1h','4h')},
            'scope':'cached-input-diagnostics-not-forecast-quality',
            'freshnessNote':'120s cache threshold; compare collection cadence and session mode before diagnosing a stalled job'}


def collect(readers):
    areas = {}
    for name, reader in readers.items():
        try:
            result = reader()
            areas[name] = result if isinstance(result, dict) else {'status':'unavailable'}
        except Exception:
            # Exception messages can contain URLs, credentials or database values.
            areas[name] = {'status':'unavailable'}
    # The web process may not run the evaluator itself. Prefer real observations
    # from the push worker when its local capture is unavailable; never recompute.
    worker_analysis = (areas.get('simulationAndPush') or {}).get('analysis')
    runtime_watchdog = (areas.get('simulationAndPush') or {}).get('runtimeWatchdog')
    if isinstance(runtime_watchdog, dict):
        areas['runtimeWatchdog'] = runtime_watchdog
    gap_evidence = (areas.get('simulationAndPush') or {}).get('gapEvidence')
    if isinstance(gap_evidence, dict):
        areas['gapEvidence'] = gap_evidence
        areas['simulationAndPush'] = dict(areas['simulationAndPush'])
        areas['simulationAndPush'].pop('gapEvidence', None)
    entry_blocks = (areas.get('simulationAndPush') or {}).get('entryBlockEvidence')
    if isinstance(entry_blocks, dict):
        # Saved paper-day decisions are independent of the sampled seven-day
        # journal. Keep their bounded, read-only projection separately so an
        # oversized operational history cannot erase the evidence again.
        areas['entryBlockEvidence'] = entry_blocks
        areas['simulationAndPush'] = dict(areas['simulationAndPush'])
        areas['simulationAndPush'].pop('entryBlockEvidence', None)
    # The full multi-stage journal may exceed the response size limit.
    # Preserve only the strictly bounded, already-redacted comparison results
    # as a separate area; never present missing archive data as healthy.
    history = (areas.get('simulationAndPush') or {}).get('history')
    journal = ((history.get('areas') or {}).get('journal')
               if isinstance(history, dict) else None)
    if isinstance(journal, dict):
        before = journal.get('stateComparison')
        deployment = journal.get('deploymentComparison')
        areas['historicalComparisons'] = {
            'status': ('observed' if isinstance(before, dict)
                       and before.get('status') == 'observed-comparison'
                       else 'insufficient'),
            'stateComparison': before if isinstance(before, dict) else
                {'status': 'insufficient-evidence'},
            'deploymentComparison': deployment if isinstance(deployment, dict) else
                {'status': 'insufficient-evidence'},
            'scope': 'bounded-health-journal-comparisons-not-feature-or-trade-proof',
        }
    # Two worker-related goals: compare only previously recorded passive
    # health captures, not trade cycles. Keep this aggregate even when the
    # larger historical journal is omitted by the response-size cap.
    cadence = journal.get('healthCadence') if isinstance(journal, dict) else None
    if isinstance(cadence, dict):
        safe_state = cadence.get('state')
        if safe_state not in ('insufficient-evidence',
                              'outside-trading-window-observation',
                              'sampled-health-capture-timing'):
            safe_state = 'insufficient-evidence'
        safe_status = ('observed' if cadence.get('status') == 'observed'
                       else 'insufficient')
        numeric = ('sampledHealthCaptures', 'sameBuildSessionIntervals',
                   'crossBuildOrSessionBoundariesSkipped',
                   'observedTradingWindowIntervals',
                   'tradingCaptureIntervalsOver90s',
                   'maxTradingCaptureGapSeconds',
                   'observedNonTradingWindowIntervals', 'latestCapturedAt')
        area = {'status':safe_status, 'state':safe_state,
                'readOnly':True, 'realOrders':False,
                'workerMissed30sCyclesVerified':False,
                'workerStoppedVerified':False,
                'scope':'passive-archive-sample-not-worker-heartbeat-proof'}
        area.update({key:value for key in numeric
                     if (value := cadence.get(key)) is not None
                     and type(value) in (int, float) and math.isfinite(value)
                     and value >= 0})
        session = cadence.get('latestSession')
        area['latestSession'] = session if session in (
            'trading','preparation','night','weekend') else 'unknown'
        areas['healthCadence'] = area
    # Carry only the eight safe stage counts across size-limited MCP reports.
    # Never copy the raw journal, timestamps, trace IDs or push payloads.
    if isinstance(journal, dict):
        source = journal.get('stageCoverage')
        keys = ('input', 'analysis', 'analysis-failed', 'push',
                'push-delivery', 'paper-input', 'health', 'transport')
        values = source.get('counts') if isinstance(source, dict) else None
        total = source.get('totalSampled') if isinstance(source, dict) else None
        if (isinstance(values, dict) and set(values) == set(keys)
                and all(type(values[k]) is int and 0 <= values[k] <= 20
                        for k in keys)
                and type(total) is int and total == sum(values.values())
                and source.get('limitPerStage') == 20
                and source.get('status') in ('observed', 'warming')):
            areas['diagnosticStageCoverage'] = {
                'status': source['status'], 'readOnly': True,
                'realOrders': False, 'totalSampled': total,
                'limitPerStage': 20,
                'counts': {k: values[k] for k in keys},
                'handsetDeliveryVerified': False,
                'paperExecutionVerified': False,
                'scope': 'sampled-seven-day-best-effort-history-stage-counts',
            }
        else:
            areas['diagnosticStageCoverage'] = {
                'status':'insufficient', 'readOnly':True, 'realOrders':False,
                'handsetDeliveryVerified':False,
                'paperExecutionVerified':False,
                'scope':'history-stage-counts-missing-or-malformed',
            }
    # Deliberately separate "no archived capture" from failed deliveries or
    # market/paper events. Only the already-sanitized eight-stage aggregate is
    # used; never fetch another database page or join private traces.
    try:
        from diagnostic_capture_handoff import review as review_capture_handoff
        paper_runtime = (areas.get('simulationAndPush') or {}).get('paper')
        areas['diagnosticCaptureHandoff'] = review_capture_handoff(
            areas.get('diagnosticStageCoverage'), paper_runtime)
    except Exception:
        areas['diagnosticCaptureHandoff'] = {
            'status':'insufficient-evidence', 'readOnly':True, 'realOrders':False,
            'originalEventCorrelationVerified':False, 'androidDeliveryVerified':False,
            'virtualExecutionVerified':False, 'continuousCaptureVerified':False,
            'scope':'capture-review-unavailable',
        }
    comparisons = (areas.get('simulationAndPush') or {}).get('comparisonHealth')
    if isinstance(comparisons, dict):
        areas['comparisonHealth'] = comparisons
        areas['simulationAndPush'] = dict(areas['simulationAndPush'])
        areas['simulationAndPush'].pop('comparisonHealth', None)
    stored_research = (areas.get('simulationAndPush') or {}).get('researchReports')
    if isinstance(stored_research, dict):
        # A large simulation/transition area may itself be omitted. Research
        # remains a separate bounded area under the same diagnostic permission.
        areas['strategyReport'] = stored_research
        areas['simulationAndPush'] = dict(areas['simulationAndPush'])
        areas['simulationAndPush'].pop('researchReports', None)
    if (areas.get('analysis') or {}).get('status') == 'unavailable' and isinstance(worker_analysis, dict) and worker_analysis.get('status') == 'observed':
        areas['analysis'] = {**worker_analysis, 'observationSource':'push-worker'}
    return {'readOnly':True, 'realOrders':False,
            'observedAt':datetime.now(timezone.utc).isoformat(),
            'status':'partial' if any(a.get('status') == 'unavailable' for a in areas.values()) else 'observed',
            'schemaVersion':2, 'summary':summary(areas),
            'scope':'operational-observations-not-complete-feature-validation', 'areas':areas}


def recent_paper_outcomes(accounts):
    """Only bounded saved paper-case labels, without financial performance claims."""
    groups=[a.get('recentCases') or {} for a in accounts if isinstance(a,dict)]
    stored=[c for group in groups if group.get('status') == 'observed'
            for c in group.get('items',[]) if isinstance(c,dict)]
    unresolved=[c for c in stored if c.get('status')=='inconclusive']
    def event_present(case, kinds):
        return any(isinstance(e,dict) and e.get('kind') in kinds
                   for e in case.get('events',[])[:20]) if isinstance(case.get('events'),list) else False
    # Causes may overlap, and absent event proof does not imply a normal fill.
    # A model may obtain a later original product quote after its missing-data
    # interval. That is not proof of a correctly timed virtual sale.
    later_priced = sum(c.get('productReturnKnown') is True and
                       event_present(c,{'deferred-sale'}) for c in unresolved)
    pending_price = sum(c.get('productReturnKnown') is False or
                        c.get('productReturnKnown') is None for c in unresolved)
    reasons={
        'recordedGoldDataGap':sum(event_present(c,{'data-gap'}) for c in unresolved),
        'recordedKoOrProductEnd':sum(event_present(c,{'knockout-confirmed',
            'product-terminated','ko-barrier-crossed-observed'}) for c in unresolved),
        'deferredModelSale':sum(event_present(c,{'deferred-sale'}) for c in unresolved),
        'unclassified':sum(not event_present(c,{'data-gap','knockout-confirmed',
            'product-terminated','ko-barrier-crossed-observed','deferred-sale'})
            for c in unresolved)
    }
    return {
        'state':'partial' if any(g.get('status') != 'observed' for g in groups) else 'observed',
        'scope':'last-five-cases-per-paper-account-only-not-full-performance',
        'inconclusiveRecordedCauses':reasons,
        'inconclusivePriceEvidence':{
            'laterModelPricePresentButOriginalExitUnverified':later_priced,
            'originalExitStillUnverified':len(unresolved),
            'noConfirmedLaterModelPrice':pending_price,
            'note':'A fresh issuer price observed later can settle only a virtual model '
                   'at that later clock. It cannot reconstruct the missing original exit, '
                   'DEGIRO execution, net return or win/loss.'},
        'causeScope':'overlap-possible-recorded-events-only-not-ground-truth',
        'observedCases':len(stored),
        'closed':sum(c.get('status') == 'closed' for c in stored),
        'open':sum(c.get('status') == 'open' for c in stored),
        'inconclusive':sum(c.get('status') == 'inconclusive' for c in stored),
        'accountsUnavailable':sum(g.get('status') != 'observed' for g in groups),
        'realOrders':False,'missingResultsAreLosses':False,
        'note':'Unbestätigte Simulationen sind weder realisierte Verluste '
               'noch automatisch behobene Datenlücken.'}


def entry_block_evidence(conn, portfolios, limit=5):
    """Bounded SELECT-only view of saved paper entry decisions.

    The per-day paper records are independent of the sampled seven-day
    diagnostic journal. Product identifiers are deliberately excluded.
    """
    accounts = []
    unavailable = 0
    allowed_directions = {'LONG', 'SHORT', 'NEUTRAL'}
    for profile in portfolios.POLICIES:
        table = portfolios.names(profile)['bob_paper_days']
        try:
            row = conn.execute(
                f'SELECT day,payload FROM {table} ORDER BY day DESC LIMIT 1'
            ).fetchone()
            if not row:
                accounts.append({'profile':profile, 'status':'unavailable',
                    'reason':'no-saved-paper-day'})
                unavailable += 1
                continue
            day, payload = row
            payload = payload if isinstance(payload, dict) else {}
            blocks = payload.get('entryBlocks')
            blocks = blocks if isinstance(blocks, list) else []
            counts = payload.get('entryBlockCounts')
            counts = counts if isinstance(counts, dict) else {}
            safe_counts = []
            total_checks = 0
            for reason, count in counts.items():
                if type(count) not in (int, float) or not math.isfinite(count) or count < 0:
                    continue
                count = int(count)
                total_checks += count
                safe_counts.append({'reason':clean_text(str(reason))[:500],
                                    'checks':count})
            safe_counts.sort(key=lambda item: (-item['checks'], item['reason']))
            latest = []
            for record in blocks[-limit:]:
                if not isinstance(record, dict):
                    continue
                item = {
                    'reason':clean_text(str(record.get('reason') or ''))[:500],
                    'direction':(record.get('direction')
                        if record.get('direction') in allowed_directions else 'unknown'),
                    'checks':(int(record.get('checks'))
                        if type(record.get('checks')) in (int, float)
                        and math.isfinite(record.get('checks'))
                        and record.get('checks') >= 0 else None),
                }
                for source, target in (('at', 'at'), ('lastAt', 'lastAt'),
                                       ('goldAt', 'sourceAt')):
                    value = record.get(source)
                    if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                        item[target] = value
                for key, maximum in (('signalSource', 80), ('ruleVersion', 100)):
                    value = record.get(key)
                    if isinstance(value, str):
                        item[key] = clean_text(value)[:maximum]
                if isinstance(record.get('plan'), dict):
                    item['plan'] = project(record['plan'],
                        shape('kind', 'entry', 'stop', 'target', 'unit'))
                latest.append(item)
            accounts.append({
                'profile':profile, 'status':'observed', 'day':str(day),
                'totalChecks':total_checks,
                'distinctReasons':len(safe_counts),
                'reasonCounts':safe_counts[:limit],
                'reasonCountsTruncated':len(safe_counts) > limit,
                'storedRecords':len(blocks), 'returnedRecords':len(latest),
                'omittedRecords':max(0, len(blocks) - len(latest)),
                'sourceTruncated':payload.get('entryBlocksTruncated') is True,
                'latest':latest,
            })
        except Exception:
            accounts.append({'profile':profile, 'status':'unavailable',
                             'reason':'entry-block-read-unavailable'})
            unavailable += 1
    observed = len(accounts) - unavailable
    return {
        'status':('observed' if unavailable == 0 else
                  'partial' if observed else 'unavailable'),
        'readOnly':True, 'realOrders':False, 'accounts':accounts,
        'entryBlockRecordLimitPerAccountDay':200,
        'diagnosticJournalRetentionDays':7,
        'paperDayRetention':'separate-per-day-records',
        'scope':'latest-saved-paper-day-per-account-bounded-projection',
        'note':'Counts remain separate from the capped detail sequence. '
               'A later record does not reconstruct an earlier missing decision.',
    }


def push_snapshot(conn, evaluator, paper_health, portfolios, extended=False):
    """Only SELECT statements; fixed tables and explicit private diagnostic projections."""
    accounts = []
    for profile in portfolios.POLICIES:
        table = portfolios.names(profile)['bob_paper_control']
        row = conn.execute(f'SELECT payload FROM {table} WHERE id=1').fetchone()
        accounts.append({'profile':profile, **fields(row[0] if row else {},
            ('enabled','status','checkedAt','startAt','endAt','campaign','signalSource','reason','currency','initialCapital','cash','equity','dayProfit','totalProfit','realizedProfit','costsDebitedEur','costPeriodProfit','costsStartedAt','costsNote'))})
    # Single bounded aggregate: distinguish no installed subscription from
    # an existing subscription whose notifications are disabled. No endpoints,
    # tokens, personal portfolio rows, or permission claims leave the server.
    row = conn.execute(
        'SELECT count(*) FILTER (WHERE general_enabled=TRUE OR '
        '(trade_enabled=TRUE AND active_trade=TRUE)), count(*) '
        'FROM subscriptions'
    ).fetchone()
    enabled, registered = row
    result = {'status':'observed', 'paper':paper_health.snapshot(conn), 'accounts':accounts,
            'push': {'activeMonitors':enabled, 'registeredSubscriptions':registered,
                     'subscriptionState':('not-registered' if registered == 0 else
                        'registered-disabled' if enabled == 0 else 'enabled'),
                     'devicePermissionStatus':'not-verified',
                     'deliveryStatus':'not-verified',
                     # Subscription eligibility is not proof of a delivered Android
                     # notification, and no subscriptions is not a push transport failure.
                     'monitorState':('none-enabled' if enabled == 0 else 'subscriptions-observed'),
                     'deliveryNote':('Keine registrierten Push-Subscriptions. '
                         'Geräteberechtigung und tatsächliche Zustellung sind nicht geprüft.'
                         if registered == 0 else
                         'Registrierte Push-Subscriptions vorhanden, aber keine aktiven '
                         'Monitore. Geräteeinstellung und tatsächliche Zustellung sind nicht geprüft.'
                         if enabled == 0 else
                         'Empfangsberechtigte Subscriptions vorhanden; tatsächlicher '
                         'Geräteempfang noch nicht nachgewiesen.'),
                     'evaluator':fields(evaluator.status(), ('completed','failed','queueTimeouts','shared','busy','waiting','inFlight','lastDurationMs','lastWaitMs'))}}
    # Separately observe report-read admission; no SQL, cached report keys or traffic identifiers.
    import report_admission
    result['reportAdmission'] = report_admission.status()
    # Sample the last audit *attempt* without asking the DB for another
    # expensive 30-day query. A fresh Render instance can correctly say unknown.
    import decision_audit
    result['databaseAudit'] = decision_audit.prospective_query_probe()
    if extended:
        result['comparisonHealth'] = __import__('comparison_health').report(conn)
        result['entryBlockEvidence'] = entry_block_evidence(conn, portfolios)
        for account in accounts:
            table = portfolios.names(account['profile'])['bob_paper_cases']
            try:
                with conn.transaction():
                    cases = conn.execute(f'SELECT payload FROM {table} ORDER BY started_at DESC LIMIT 5').fetchall()
                account['recentCases'] = {'status':'observed','items':[project(paper_case_review.project_case(row[0], account['profile']), CASE) for row in cases]}
            except Exception:
                account['recentCases'] = {'status':'unavailable'}
        # Evidence-only recent-case tally. Never turn unknown/deferred results
        # into closed profits, losses, filled orders or proven source recovery.
        result['recentPaperOutcomes'] = recent_paper_outcomes(accounts)
        # Indexed, SELECT-only probe of nearby *original Gold-API* timestamps.
        # A proximity match is not sufficient evidence to settle any paper trade.
        try:
            result['spotGapArchive'] = __import__('paper_gap_archive').report(conn,accounts)
        except Exception:
            result['spotGapArchive'] = {'status':'unavailable','readOnly':True,
                'reason':'archive-inspection-unavailable'}
        try:
            result['analysisGapArchive'] = __import__('paper_gap_analysis_archive').report(conn,accounts)
        except Exception:
            result['analysisGapArchive'] = {'status':'unavailable','readOnly':True,
                'reason':'analysis-history-inspection-unavailable'}
        # Separate observations of market data actually handed to virtual
        # account evaluators. Historical gaps before this capture stay unknown.
        try:
            result['paperInputArchive'] = __import__('paper_input_evidence').report(conn,accounts)
        except Exception:
            result['paperInputArchive'] = {'status':'unavailable','readOnly':True,
                'reason':'paper-input-history-unavailable'}
        try:
            result['paperInputLatest'] = __import__('paper_input_evidence').latest(conn)
        except Exception:
            result['paperInputLatest'] = {'status':'unavailable','readOnly':True,
                'reason':'paper-input-latest-unavailable'}
        result['history'] = collect({'journal':lambda:__import__('diagnostic_history').report(conn)})
        result['details'] = stored_details(conn)
        # Keep the research report independently addressable when oversized
        # operational history/details are omitted by the response budget.
        result['researchReports'] = result['details']['areas'].get('learning', {'status':'unavailable'})
        result['gapEvidence'] = result['details']['areas'].get('gapModels', {}).get('evidenceSummary', {'status':'unavailable'})
        result['analysis'] = analysis_snapshot()
        try:
            with conn.transaction():
                history = __import__('signal_history').report(conn)
                if len(history['records']) > 20:
                    history['records'] = history['records'][:20]
                    history['nextOffset'] = 20
                result['signalHistory'] = history
        except Exception:
            result['signalHistory'] = {'status':'unavailable','readOnly':True}
    return result


def simulation_status(conn, evaluator, paper_health, portfolios):
    """Fast live controls and today's indexed case sample; no history scans."""
    from zoneinfo import ZoneInfo
    result = push_snapshot(conn, evaluator, paper_health, portfolios, extended=False)
    result['observedAt'] = datetime.now(timezone.utc).isoformat()
    result['analysis'] = analysis_snapshot()
    result['scope'] = 'live-controls-and-current-day-case-sample'
    result['historicalEvidence'] = {'status':'not-requested',
        'reason':'extended-history-is-separate-from-live-simulation-status'}
    day = datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()
    for account in result['accounts']:
        table = portfolios.names(account['profile'])['bob_paper_cases']
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='500ms'")
                # Uses the existing (day, started_at) index on each portfolio.
                rows = conn.execute(f'SELECT payload FROM {table} WHERE day=%s ORDER BY started_at DESC LIMIT 5', (day,)).fetchall()
                conn.execute("SET LOCAL statement_timeout='3s'")
            account['recentCases'] = {'status':'observed', 'day':day,
                'scope':'current-day-latest-five-not-complete-history',
                'items':[project(paper_case_review.project_case(row[0], account['profile']), CASE) for row in rows]}
        except Exception:
            account['recentCases'] = {'status':'unavailable', 'day':day,
                'reason':'current-day-case-read-unavailable'}
    result['recentPaperOutcomes'] = recent_paper_outcomes(result['accounts'])
    return result


def comparison_status(conn, portfolios):
    """Independent bounded stored evidence; never hides live simulation status."""
    comparison = __import__('comparison_health').report(conn)
    blocks = entry_block_evidence(conn, portfolios)
    samples = []
    for profile in portfolios.POLICIES:
        table = portfolios.names(profile)['bob_paper_cases']
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='500ms'")
                rows = conn.execute(
                    f'SELECT payload FROM {table} ORDER BY started_at DESC LIMIT 5'
                ).fetchall()
                conn.execute("SET LOCAL statement_timeout='3s'")
            recent = {'status':'observed',
                'scope':'latest-five-not-complete-history',
                'items':[project(paper_case_review.project_case(row[0], profile), CASE)
                         for row in rows]}
        except Exception:
            recent = {'status':'unavailable',
                'reason':'bounded-case-evidence-read-unavailable'}
        samples.append({'profile':profile, 'recentCases':recent})
    partial = (comparison.get('status') == 'partial'
               or blocks.get('status') == 'unavailable'
               or any(row['recentCases']['status'] == 'unavailable'
                      for row in samples))
    return {'status':'partial' if partial else 'observed',
            'readOnly':True, 'realOrders':False,
            'observedAt':datetime.now(timezone.utc).isoformat(),
            'comparisonHealth':comparison,
            'entryBlockEvidence':blocks,
            'accountSamples':samples,
            'scope':'bounded-stored-comparisons-and-latest-case-evidence',
            'note':'Stored evidence is not a completed study, executable trade or profit proof.'}


# Projection schemas are explicit: credentials, raw logs, subscription endpoints,
# document bodies, receipt identifiers and arbitrary nested payloads never pass.
def clean_text(value):
    value = re.sub(r'https?://[^\s<>"\']+', '[URL omitted]', value)
    value = re.sub(r'(?i)(?:bearer\s+\S+|(?:boa_|bor_|boc_|sk-)[A-Za-z0-9_-]+)', '[redacted]', value)
    value = re.sub(r'(?i)(password|token|secret|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+', r'\1=[redacted]', value)
    return value[:300]


def project(value, schema):
    if isinstance(schema, list):
        return [project(v, schema[0]) for v in value[:20]] if isinstance(value,list) else []
    if isinstance(schema, dict):
        value = value if isinstance(value,dict) else {}
        return {k: project(value.get(k), shape) for k,shape in schema.items()}
    return fields({'value':value}, ('value',)).get('value')


def shape(*keys, **nested):
    return {**dict.fromkeys(keys), **nested}


CASE = shape('performanceEligible','performanceExclusionReason','modelSettlementGrossPct','status','startedAt','closedAt','lastAt','direction','modelOnly','netReturnKnown','productReturnKnown','productGrossPct','goldR','capitalMode','ledgerCostsDebited','ledgerFeesEur','ledgerSlippageEur','ledgerModelNetEur',
    evidenceChain=shape('version','sourceAt','startedAt','complete','performanceExcluded','pushLinkVerified','brokerExecutionVerified','note', stages=[shape('label','observed')]),
    administrativeReview=shape('status','label','decidedAt','caseReviewId','resultVerified','reopenOnlyWithOriginalEvidence'),
    ledgerCostModel=shape('version','feeEurPerOrder','slippageBpsPerSide','extraHoldingBpsPerDay'),
    events=[shape('kind','at','recordedAt','reason')])

INDICATORS = shape('timeframe','score','rsi','macd','sig','hist','atr','adx','ema20','ema50','ema200','R','at','e20','e50','e200','trend','trend2','bbPos','bbp','momentum')
PLAN = shape('available','reason','dir','entry','stop','target','computedAt','dataAt','currency','method','stale')
EARLY_WARNING = shape('version','monitoring','available','state','direction','checkedAt','signalBarAt','expiresAt','invalidationPrice','extensionRisk','comparisonOnly','affectsApproval','reason')
ANALYSIS = shape('ready','priceFresh','dataAt','analysisBarAt','price','direction','baseDirection','mtf','score','atr','macd','signal','decisionReason','ruleVersion','suggestedStop','suggestedTarget',
    earlyWarning=EARLY_WARNING, analysisSnapshot=INDICATORS, trendContext=shape('available','direction','intact','reason'),
    entryTimingGate=shape('allowed','reason','status'),session=shape('phase','entryAllowed','reason'),
    dmi=shape('available','mode','direction','reason',
        frames={tf:shape('available','adx','plusDI','minusDI','direction','reason','barAt')
                for tf in ('5m','15m','1h')}),continuedPlan=PLAN)
STATE = shape('healthy','dataStatus','direction','mtf','journalCheckedAt',lastAnalysis=ANALYSIS,
    continuedCalculation=shape('available','stale','marketClosed','computedAt','dataAt','price','score','analysisBarAt','stopDistance','targetDistance','productEstimate',plan=PLAN),
    trade=shape('dir','entry','stop','target','initialRisk'),
    pushHistory=[shape('at','kind','outcome','reason',events=[None])])
_analysis_lock = threading.Lock()
_analyses = {}


def observe_analysis(result, timeframe):
    """Passive capture after an existing evaluator run; never starts a calculation."""
    if timeframe not in ('1m','5m','15m','30m','1h','4h'):
        timeframe = 'unknown'
    value = project(result, ANALYSIS)
    with _analysis_lock:
        _analyses[timeframe] = {'capturedAt':time.time(), 'result':value}


def analysis_snapshot():
    with _analysis_lock:
        import copy
        values = copy.deepcopy(_analyses)
    return {'status':'observed' if values else 'unavailable', 'timeframes':values,
            'availabilityReason':None if values else 'no-evaluation-observed-in-this-process',
            'scope':'actual-evaluator-results-since-process-start-not-recomputed'}


def stored_details(conn):
    """Bounded SELECTs in savepoints isolate unavailable tables. No repair calls."""
    def rows(sql, schema):
        with conn.transaction():
            values = conn.execute(sql).fetchall()
        return {'status':'observed','items':[project(row[0],schema) for row in values],
                'bounded':True, 'emptyMeans':'no-stored-observations'}
    def gap_models():
        import model_gap_review
        with conn.transaction():return model_gap_review.report(conn)
    def research_report(conn):
        from research_readout import read
        with conn.transaction():return read(conn)
    return collect({
        'gapModels':gap_models,
        'decisionArchive':lambda:rows("SELECT payload FROM bob_decision_audit ORDER BY recorded_at DESC LIMIT 20",
            shape('recordedAt','barAt','priceAt','price','direction','baseDirection','shadowDirection','reason','score','ruleVersion','build','origin','marketEvaluable',
                decisionContext=shape('version','ready','priceFresh',indicators=shape('timeframe','barAt','score','rsi','macd','signal','hist','atr','adx','ema20','ema50','ema200','bbPos'),
                    entryTiming=shape('allowed','reason','status'),session=shape('entryAllowed','reason','phase'),dmi=shape('available','mode','direction','reason')),
                indicators=INDICATORS,gateReasons=[None],plan=shape('kind','direction','entry','stop','target','unit','at'))),
        'tradeMonitoring':lambda:rows("SELECT jsonb_build_object('updatedAt',updated_at,'active',active,'direction',snapshot->'dir','product',snapshot->'product','state',state) FROM bob_real_trades ORDER BY updated_at DESC LIMIT 10",
            shape('updatedAt','active','direction',product=shape('isin','currency','entry'),state=STATE)),
        'tradeEvents':lambda:rows("SELECT jsonb_build_object('at',recorded_at,'kind',kind,'evidence',payload) FROM bob_real_trade_events ORDER BY seq DESC LIMIT 20",
            shape('at','kind',evidence=shape('at','outcome','error','delivery','dataAt','price','direction','decisionReason','suggestedStop','suggestedTarget',analysisSnapshot=INDICATORS))),
        'pushObservations':lambda:rows("SELECT jsonb_build_object('updatedAt',updated_at,'generalEnabled',general_enabled,'tradeEnabled',trade_enabled,'activeTrade',active_trade,'state',background_state) FROM subscriptions ORDER BY updated_at DESC LIMIT 10",
            shape('updatedAt','generalEnabled','tradeEnabled','activeTrade',state=STATE)),
        'learning':lambda:research_report(conn),
        'researchMedia':lambda:rows("SELECT jsonb_build_object('video',video_id,'updatedAt',updated_at,'frameAttempt',frame_attempt,'summaryAttempt',summary_attempt,'frameStatus',frame_status,'summaryError',summary_error,'summaryFailures',summary_failures,'frames',frames,'summary',summary) FROM bob_research_enhancements ORDER BY updated_at DESC LIMIT 10",
            shape('video','updatedAt','frameAttempt','summaryAttempt','frameStatus','summaryError','summaryFailures',
                frames=[shape('at','requestedAt','isCover','userProvided','width','height')],
                summary=shape('kind','model','partial',visualNotes=[shape('at','kind','reason')]))),
        'repairs':lambda:rows("SELECT jsonb_build_object('at',event_at,'recordedAt',recorded_at,'kind',kind,'code',code) FROM bob_self_heal_events ORDER BY recorded_at DESC LIMIT 20",
            shape('at','recordedAt','kind','code')),
    })


def simulation_evidence_snapshot(simulation):
    """Bounded read-only evidence about recent virtual cases, never broker fills.

    Correlate exact *recorded* gap event clocks across independently simulated
    profiles; a repeated clock is not another source outage or original price.
    Only fixed reason codes are projected; raw messages are not exported.
    """
    if not isinstance(simulation,dict) or simulation.get('status')!='observed':
        return {'status':'unavailable','readOnly':True,
                'reason':'simulation-source-unavailable'}
    accounts=simulation.get('accounts')
    if not isinstance(accounts,list) or not accounts:
        return {'status':'unavailable','readOnly':True,
                'reason':'simulation-accounts-unavailable'}
    evidence=[]
    gap_times={}
    reason_counts={'missing-current-market':0,'bar-gap-over-90s':0,'unclassified':0}
    missing_recorded_time=0
    sampled_inconclusive=0
    for account in accounts[:10]:
        if not isinstance(account,dict):
            continue
        record=account.get('recentCases')
        observed=(isinstance(record,dict) and
                  record.get('status')=='observed' and
                  isinstance(record.get('items'),list))
        cases=record['items'][:5] if observed else []
        kinds={'open':0,'closed':0,'inconclusive':0,'other':0}
        data_gaps=deferred=terminal=administratively_closed=0
        for c in cases:
            if not isinstance(c,dict):
                kinds['other']+=1
                continue
            status=c.get('status')
            administratively_closed += int((c.get('administrativeReview') or {}).get('status') == paper_case_review.STATUS)
            kinds[status if status in ('open','closed','inconclusive') else 'other']+=1
            events=[e for e in (c.get('events') or [])[-40:] if isinstance(e,dict)]
            event_kinds=[e.get('kind') for e in events]
            data_gaps+=int('data-gap' in event_kinds)
            deferred+=int('deferred-sale' in event_kinds)
            terminal+=int(any(kind in ('product-terminated','knockout-confirmed',
                                        'ko-barrier-crossed-observed') for kind in event_kinds))
            if status!='inconclusive':
                continue
            sampled_inconclusive+=1
            for event in events:
                if event.get('kind')!='data-gap':
                    continue
                reason=event.get('reason')
                if reason=='Aktuelle Goldkursabdeckung fehlt; kein belegter Ausstieg':
                    code='missing-current-market'
                elif reason=='Goldkurslücke über 90 Sekunden; Reihenfolge unbekannt':
                    code='bar-gap-over-90s'
                else:
                    code='unclassified'
                reason_counts[code]+=1
                recorded=event.get('recordedAt')
                if type(recorded) not in (int,float) or not math.isfinite(recorded) or recorded<=0:
                    missing_recorded_time+=1
                    continue
                item=gap_times.setdefault(recorded,{'recordedAt':recorded,
                    'affectedVirtualCases':0,'reasonCodes':set()})
                item['affectedVirtualCases']+=1
                item['reasonCodes'].add(code)
        identity=fields(account,('profile','status','checkedAt','enabled'))
        evidence.append({**identity,
            'sampleStatus':'observed' if observed else 'unavailable',
            'sampleSize':len(cases),'counts':kinds,
            'administrativelyClosed':administratively_closed,
            'openOutcomeReviews':kinds['inconclusive']-administratively_closed,
            'casesWithRecordedDataGap':data_gaps,
            'casesWithRecordedDeferredSale':deferred,
            'casesWithRecordedTerminationEvidence':terminal,
            'netProductReturnsVerified':False,
            'note':'Only latest five sanitized virtual cases; event lists can be truncated. '
                   'No past-case totals, original quote proof, executed trade or return validation.'})
    clusters=[{'recordedAt':v['recordedAt'],
               'affectedVirtualCases':v['affectedVirtualCases'],
               'reasonCodes':sorted(v['reasonCodes'])}
              for v in sorted(gap_times.values(),key=lambda item:item['recordedAt'])]
    return {'status':'observed' if evidence else 'unavailable',
            'readOnly':True,'realOrders':False,'accountSamples':evidence,
            'spotGapArchive':project(simulation.get('spotGapArchive'),
                shape('status','readOnly','realOrders','source','windowSeconds',
                    'sampledDistinctClocks','totalDistinctClocks','truncated',
                    'note','reason',
                    counts=shape('nearbyOriginal','notObservedNearEvent',
                                 'outsideRetention','queryUnavailable'),
                    items=[shape('eventAt','state','nearestSourceAt',
                                 'deltaSeconds','timeRelation')])),
            'analysisGapArchive':project(simulation.get('analysisGapArchive'),
                shape('status','readOnly','realOrders','windowSeconds',
                    'sampledDistinctClocks','totalDistinctClocks','truncated',
                    'scope','note','reason',
                    counts=shape('nearby15mAnalysis','readyFresh15mAnalysis',
                                 'no15mAnalysisInWindow','outsideRetention','queryUnavailable'),
                    items=[shape('eventAt','state','analysisAt','timeRelation',
                                 'deltaSeconds','ready','priceFresh',
                                 'sourceAgeAtAnalysisSeconds')])),
            'gapCorrelation':{
                'sampledInconclusiveCases':sampled_inconclusive,
                'gapEventReasonCounts':reason_counts,
                'distinctRecordedGapInstants':len(clusters),
                'repeatedGapInstants':sum(1 for v in clusters if v['affectedVirtualCases']>1),
                'gapEventsWithoutRecordedAt':missing_recorded_time,
                'recentRecordedGapInstants':clusters[-10:],
                'scope':'exact-recordedAt-correlation-in-last-five-cases-per-account',
                'note':'Distinct recorded event clocks, not independent outages. '
                       'A reason classification does not prove root cause or missing trade price.'},
            'paperInputLatest':project(simulation.get('paperInputLatest'),
                shape('status','readOnly','realOrders','sessionMode','state',
                      'observedAt','ageSeconds','profilesObserved',
                      'profilesChecked','profilesFreshReady','profilesExpected',
                      'scope','note','reason',
                      profiles=[shape('profile','outcome','ready','priceFresh',
                                      'originalDataAt','originalBarAt',
                                      'sourceAgeAtCaptureSeconds')])),
            'paperInputArchive':project(simulation.get('paperInputArchive'),
                shape('status','readOnly','realOrders','windowSeconds','sampledDistinctClocks',
                    'totalDistinctClocks','truncated','scope','note','reason',
                    counts=shape('workerInputNearby','noWorkerCaptureNearby','outsideRetention',
                        'queryUnavailable','nearbyProfileInputFresh','nearbyProfileInputUnfreshOrError'),
                    items=[shape('eventAt','state','capturedAt','timeRelation','deltaSeconds',
                        profiles=[shape('profile','outcome','ready','priceFresh','dataAt','barAt')])])),
            'gapReview':__import__('paper_gap_triage').assess(
                {'recentRecordedGapInstants':clusters[-10:]},
                simulation.get('spotGapArchive'),simulation.get('analysisGapArchive'),
                simulation.get('paperInputArchive')),
            'scope':'bounded-paper-case-evidence-not-fills-or-profit',
            'note':'A source data-gap cannot be repaired by interpolation or re-dating quotes.'}



def new_feature_snapshot(areas, *, mobile_asset_loaded=False):
    """Passive read coverage for newly added Bob functions, not proof of client operation.

    No browser interaction, device connection, evaluator execution or broker call.
    Existing cached diagnostics are the only dynamic inputs. A missing saved
    self-review is explicitly unknown, even when research ran successfully.
    """
    areas = areas if isinstance(areas, dict) else {}
    reports = (areas.get('strategyReport') or {}).get('items') or []
    latest = next((row for row in reports if isinstance(row, dict)), None)
    latest_report = (latest or {}).get('report') or {}
    cycle = latest_report.get('learningCycle') if isinstance(latest_report, dict) else None
    raw_review = cycle.get('selfReview') if isinstance(cycle, dict) else None
    verified_review = isinstance(raw_review, dict) and raw_review.get('mode') == 'RESEARCH_ONLY'
    review = project(raw_review, shape(
        'mode', 'status', 'confidence', 'reason', 'sessions', 'trades',
        'baselineTrades', 'liveRuleChanged', 'automaticOrder',
        'productNetValidated', 'actionable')) if verified_review else None

    runtime = areas.get('runtime') if isinstance(areas.get('runtime'), dict) else {}
    snaptrade = runtime.get('snaptradePersonal') if isinstance(runtime.get('snaptradePersonal'), dict) else {}
    return {
        'status': 'observed',
        'scope': 'read-coverage-only-not-feature-health-or-trade-approval',
        'androidCompanion': {
            'runtime': 'not-observable',
            'voiceCommands': 'not-observable',
            'screenshotSeries': 'not-observable',
            'remotePairing': 'not-implemented',
            'deviceConsentRequired': True,
            'note': 'Phone-local actions are not transmitted to this server diagnostic. '
                    'No authenticated remote Android pairing exists.'
        },
        'unifiedMobileWorkspace': {
            'serverAsset': 'loaded' if mobile_asset_loaded else 'unavailable',
            'browserSession': 'not-observable',
            'lastClientAction': None,
            'note': 'Server asset presence does not prove browser or handset behavior.'
        },
        'researchSelfReview': {
            'status': 'observed' if verified_review else 'unavailable',
            'sourceReportAt': fields(latest, ('calculatedAt',)).get('calculatedAt'),
            'reason': None if verified_review else
                      'No self-review in latest persisted research report; do not infer completion.',
            'result': review,
        },
        'snaptradeReadOnly': {
            'connectionCode': fields(snaptrade, ('code',)).get('code'),
            'dataFresh': snaptrade.get('fresh') is True,
            'tradingEnabled': False,
            'liveBrokerQuotes': False,
            'sourceRole':'depot-history-and-issuer-observations-only',
            'directDegiroSync': fields(areas.get('degiroSync'), ('code','status','running')),
            'note': 'SnapTrade holdings and separate issuer observations are not '
                    'DEGIRO executable live quotes. Direct DEGIRO read sync is separate '
                    'and never starts merely because SnapTrade responds.'
        }
    }


def research_snapshot(value):
    return project(value,shape('checkedAt','fresh','successfulFeeds','intervalSeconds','videosFound','videosAnalyzed','mcoOutlook','mcoReason','accessFallback',
        restrictedUploads=[shape('title','publishedAt','transcriptAccess')],
        sources=[shape('id','status','checkedAt','scanned','relevant','error')],
        items=[shape('title','publishedAt','outlook','current','coverage','transcriptAnalyzed','trustedTranscript','transcriptAccess','transcriptProvider','transcriptLanguage','transcriptWords','analysisStatus','error','publicFallback','accessNote',
            enhancements=shape('summaryStatus','frameStatus',frames=[shape('at','isCover','width','height')],summary=shape('kind','partial')), 
            visualAnalysis=shape('status','method','framesAnalyzed','reason'),frames=[shape('at','status','source')])]))


def product_snapshot(value):
    return project(value,shape('status','lastCheckedAt','listUploadedAt','total','incomplete','needsHelp','readOnly','degiroConnected',
        items=[shape('isin','direction','state','source','quoteSourceAt','leverageSourceAt','dataQuoteSource','dataQuoteKind','nativeCurrency','tradeApproved','identityEvidence',
            missing=[None],messages=[None],sourceRecovery=[shape('stage','state','scope','retryAfterSeconds')],
            leverageObservation=shape('value','leverage','source','at','current','calculated','method','kind','researchOnly','label'),
            timeEvidence=shape('leverageBasis', terms={key:shape(
                'at','dateText','reviewedAt','sourceField','sourceTimeRaw',
                'conditionVerified','validityUnconfirmed') for key in ('ko','strike')}),
            sourceObservations=[shape('source','at','bidAt','askAt','bid','ask','currency','kind','priceKind','isExecutableQuote')],
            fieldRecovery=shape('status','state','source','checkedAt','reason',
                conflicts=[None], unresolvedConflicts=[None],
                sourceDecisions={key:shape('state','reason','source','dateText',
                    'sourceTimeRaw','primaryValue','referenceValue')
                    for key in ('ko','strike','ratio','currency')}))]))


def summary(areas):
    findings=[]
    def walk(value,path):
        if isinstance(value,list):
            for i,item in enumerate(value[:20]):walk(item,path+'.'+str(i))
            return
        if not isinstance(value,dict):return
        state=value.get('status',value.get('state'))
        if state == 'conflict' and path.endswith('.fieldRecovery'):
            conflict_fields=value.get('conflicts') or []
            decisions=value.get('sourceDecisions') or {}
            if (conflict_fields and not value.get('unresolvedConflicts') and isinstance(decisions,dict)
                and all(isinstance(decisions.get(k),dict) and decisions[k].get('state')=='dated-issuer-selected' for k in conflict_fields)):
                state='differences-explained'
        if state == 'inconclusive' and (value.get('administrativeReview') or {}).get('status') == paper_case_review.STATUS:
            return
        if state in ('unavailable','stale','degraded','failed','retry','partial','wrong-basis','invalid-ohlc','recent-gap','missing','insufficient','incomplete','conflict','inconclusive','recurred'):
            finding = {'area':path,'state':state}
            if value.get('reason') == 'omitted-response-size-limit':
                finding['meaning'] = 'response-size-omission-not-source-failure'
                finding['sourceStatus'] = value.get('sourceStatus', 'unknown')
            findings.append(finding)
        if path.endswith('.dmi') and value.get('available') is False:
            findings.append({'area':path,'state':'incomplete'})
        if (path.startswith('products.items.') and '.timeEvidence.terms.' in path
                and value.get('validityUnconfirmed') is True):
            findings.append({'area':path,'state':'incomplete',
                             'meaning':'original-term-validity-unconfirmed'})
        for key,item in value.items():
            # The outage event log is historical evidence. Its old "stale" /
            # "incomplete" transitions must not be counted as LIVE alerts.
            # Keep history in the report and current source state above.
            if key == 'events' and path.startswith('sourceReliability.sources.'):
                continue
            if isinstance(item,(dict,list)):walk(item,path+'.'+key)
    for name,area in areas.items():walk(area,name)
    # A stale *backup* is not the same as a broken selected candle source.
    # Keep both observations, annotate their roles without falsely clearing any
    # actual source fault. Inconclusive paper cases are not realised losses.
    active = {}
    market = areas.get('market') if isinstance(areas.get('market'),dict) else {}
    for frame,candle in (market.get('candles') or {}).items():
        if not isinstance(candle,dict):continue
        integrity = candle.get('integrity') or {}
        name = str((integrity if isinstance(integrity,dict) else {}).get('source')
                   or (candle.get('last') or {}).get('source') or '').lower()
        active[str(frame)] = ('biquote' if 'biquote' in name else
                              'xaus' if 'xaus' in name else 'unknown')
    for item in findings:
        path=item['area']
        if path.startswith('sourceReliability.sources.'):
            parts=path[len('sourceReliability.sources.'):].split('/')
            if len(parts)>=2 and parts[0] in ('xaus','biquote'):
                current=active.get(parts[1],'unknown')
                item['sourceRole']='selected' if current==parts[0] else (
                    'alternate' if current!='unknown' else 'undetermined')
        if path.startswith('market.candles.') and path.endswith('.integrity'):
            session = market.get('sessionMode')
            if session in ('preparation', 'night', 'weekend'):
                item['sessionMode'] = session
                item['meaning'] = 'source-clock-stale-or-incomplete-outside-user-trading-window-not-proof-of-worker-outage'
        if path == 'analysis' and item['state'] == 'unavailable':
            # Web process may have no evaluator. Preserve warning without
            # claiming the separate process stopped running.
            observation = areas.get('analysis')
            if isinstance(observation, dict) and observation.get('availabilityReason') == 'no-evaluation-observed-in-this-process':
                item['meaning'] = 'no-local-evaluator-capture-not-a-confirmed-global-outage'
        if path.startswith('simulationAndPush.accounts.') and item['state']=='inconclusive':
            item['meaning']='paper-result-unconfirmed-not-a-realised-loss'
    for item in findings:
        if (item.get('meaning') == 'response-size-omission-not-source-failure'
                and item.get('sourceStatus') == 'observed'):
            item['severity']='info'
        elif item.get('sourceRole')=='alternate':
            item['severity']='info'
            item['meaning']='backup-source-unavailable-selected-feed-assessed-separately'
        else:item['severity']='warning'
    return {'attention':findings[:40], 'assessment':'needs-attention' if any(x['severity']=='warning' for x in findings) else 'observed-only',
            'note':'A stale alternate quote source does not by itself prove the selected candle feed failed. Inconclusive paper results are not realised losses. Original timestamps remain authoritative.'}


def broker_sync_snapshot(value):
    """Operational session metadata only; never holdings or account identifiers."""
    result = fields(value, ('code', 'running', 'fresh', 'ageSeconds', 'authReason',
                            'intervalSeconds', 'liveOrdersEnabled', 'liveQuotes'))
    result['lastConnectionTest'] = fields(value.get('lastConnectionTest') if isinstance(value, dict) else None,
                                         ('code', 'checkedAt', 'authReason'))
    from degiro_readonly import safe_login_response
    result['loginResponse'] = safe_login_response(value.get('loginResponse') if isinstance(value, dict) else None)
    last_test = value.get('lastConnectionTest') if isinstance(value, dict) else None
    result['lastConnectionTest']['loginResponse'] = safe_login_response(last_test.get('loginResponse') if isinstance(last_test, dict) else None)
    snapshot = value.get('snapshot') if isinstance(value, dict) else None
    result['lastSuccessAt'] = fields(snapshot, ('observedAt',)).get('observedAt')
    result['status'] = ('fresh' if result.get('fresh') is True else
                        'stale' if result['lastSuccessAt'] else 'unavailable')
    # The optional DEGIRO SDK session is manually triggered and NOT the
    # connected SnapTrade read-only portfolio. Absence of SDK credentials
    # before any start attempt must not be reported as a broken live feed.
    if result.get('code') in ('NOT_STARTED', 'SETUP_REQUIRED') and not result['lastSuccessAt']:
        from degiro_readonly import status as sdk_status
        result['status'] = 'not-started' if sdk_status().get('ready') else 'not-configured'
        result['connectionKind'] = 'optional-direct-degiro-sdk-readonly'
    return result


# Stable, permission-preserving views of the *existing sanitized* report.
# They do not add database queries, OAuth grants, device access, or evaluations.
DIAGNOSTIC_FOCUS = ('overview', 'simulation', 'trades', 'signals',
                    'sources', 'research', 'repairs', 'mobile', 'products')
_FOCUS_AREAS = {
    'simulation': ('simulationEvidence', 'simulationAndPush', 'comparisonEvidence',
                   'comparisonHealth', 'entryBlockEvidence', 'background', 'collection',
                   'gapEvidence', 'diagnosticStageCoverage', 'diagnosticCaptureHandoff'),
    'sources': ('market', 'sourceReliability', 'collection', 'background', 'analysis'),
    'research': ('research', 'strategyResearch', 'strategyReport', 'newFeatures'),
    'mobile': ('newFeatures', 'runtime', 'degiroSync', 'products'),
    'products': ('products', 'degiroSync', 'gapEvidence'),
    'repairs': ('selfHealing', 'problems', 'background', 'diagnosticTriage', 'operationsSummary',
                'healthCadence', 'diagnosticStageCoverage', 'diagnosticCaptureHandoff'),
    'trades': ('background', 'diagnosticTriage'),
    'signals': ('analysis', 'background', 'diagnosticTriage', 'pushDeliveries',
                'diagnosticStageCoverage', 'diagnosticCaptureHandoff'),
}


def read_access_coverage(manifest):
    """Bounded diagnostic inventory with one dated, build-specific service-match acceptance.

    This is documentation coverage, not evidence that a feature works.
    Never exposes raw repository text, credentials or individual user data.
    """
    try:
        rows = manifest['tasks']
        ids = [row['id'] for row in rows]
        allowed = {'partial', 'planned', 'blocked-client', 'requires-device',
                   'verified-at-build', 'verified-at-sample'}
        if (manifest.get('schemaVersion') != 1 or manifest.get('total') != 100
                or len(rows) != 100 or sorted(ids) != list(range(1,101))
                or any(row.get('state') not in allowed or
                       row.get('verified') is not
                       (row.get('state') in ('verified-at-build', 'verified-at-sample'))
                       for row in rows)):
            raise ValueError('coverage manifest invalid')
        counts = {k:sum(row['state']==k for row in rows) for k in sorted(allowed)}
        # Check only code-owned, strictly relative named paths. Mere file
        # existence is not functional, integration or live verification.
        paths = [row.get('codeEvidence') for row in rows]
        if any(not isinstance(p, str) or not p or not re.fullmatch(r'[A-Za-z0-9_./-]+', p)
               or p.startswith('/') or any(s in ('', '.', '..') for s in p.split('/'))
               for p in paths):
            raise ValueError('coverage manifest invalid code path')
        root = Path(__file__).resolve().parent
        unique_paths = sorted(set(paths))
        present = sum((root / p).is_file() for p in unique_paths)
        # Structural graph: inspect source syntax only, never import or execute Bob
        # modules. Keep detailed paths in the code-owned inspector; the bounded
        # runtime report publishes aggregate counts, not source or secrets.
        try:
            from diagnoseziele_module_map import inspect as inspect_modules
            inventory = inspect_modules(root, rows)
            module_summary = {k: inventory.get(k) for k in (
                'status', 'moduleCount', 'goalCount', 'pythonModulesParsed',
                'javascriptModulesScanned', 'otherModulesNotParsed',
                'mappedDependencyEdges',
                'scope', 'limitations', 'individuallyVerified')}
        except Exception:
            module_summary = {'status': 'unavailable'}
        # Goal #2: compare only bounded repository-root module filenames
        # against the dated, read-only tree baseline. Never import discovered
        # modules, infer health or publish source filenames/secret contents.
        root_discovery = {'status':'unavailable', 'readOnly':True}
        try:
            import json
            from bob_source_module_inventory import inspect as inspect_root_modules
            baseline = json.loads(
                (root / 'Besser_werden/module_root_baseline_20261025.json')
                .read_text(encoding='utf-8'))
            root_discovery = inspect_root_modules(root, baseline, paths)
        except (OSError, TypeError, ValueError, KeyError):
            root_discovery = {'status':'unavailable', 'readOnly':True,
                              'reason':'module-baseline-not-readable'}
        # Candidate test names make the remaining 100 individual acceptance
        # tasks auditable. Presence is not proof of execution, coverage, runtime
        # correctness or a passing device test.
        test_evidence = {'status':'unavailable'}
        try:
            import json
            from diagnoseziele_testplan import assess as inspect_test_candidates
            mapped = json.loads((root/'Besser_werden/diagnoseziele_100_testzuordnung.json')
                .read_text(encoding='utf-8'))
            test_evidence = inspect_test_candidates(root, rows, mapped)
        except (OSError, ValueError, TypeError, KeyError):
            test_evidence = {'status':'unavailable', 'reason':'test-map-not-readable'}
        # Complete, non-authorizing Sunday/Monday handoff; no new SQL,
        # broker calls or device controls. Any absent plan stays unknown.
        work_split = {'status':'unavailable'}
        try:
            from diagnoseziele_work_split import assess as inspect_handoff
            work_plan = json.loads((root/'Besser_werden/sonntag_montag_100_plan.json')
                .read_text(encoding='utf-8'))
            work_split = inspect_handoff(rows, work_plan)
        except (OSError, ValueError, TypeError, KeyError):
            work_split = {'status':'unavailable',
                          'reason':'work-split-plan-missing-or-invalid'}
        # A historical acceptance is a narrow, independently observed
        # CI + two-service live-deployment sample, never automatic trade or
        # current runtime approval. Fail closed if any proof is malformed.
        import json
        from diagnoseziele_acceptance import assess as inspect_acceptance
        acceptance_data = json.loads(
            (root/'Besser_werden/diagnoseziele_100_abnahmen.json')
            .read_text(encoding='utf-8'))
        historical_acceptance = inspect_acceptance(rows, acceptance_data)
        if (historical_acceptance.get('status') != 'six-dated-independent-acceptances'
                or counts.get('verified-at-build') != 1
                or counts.get('verified-at-sample') != 5):
            raise ValueError('acceptance proof missing or inconsistent')
        # Dated evidence matrix is not an acceptance flag. Preserve original statuses.
        review = {'status':'not-available'}
        try:
            import json
            evidence = json.loads((root/'Besser_werden/diagnoseziele_100_nachweise_20261024.json')
                .read_text(encoding='utf-8'))
            goals=evidence.get('goals')
            if (evidence.get('reportVersion') == 1 and isinstance(goals,list)
                    and len(goals)==100
                    and sorted(row.get('id') for row in goals)==list(range(1,101))
                    and all(row.get('finalVerification')=='unverified' for row in goals)):
                partial_live=sum(row.get('live',{}).get('level')=='partial-operational-observation'
                                 for row in goals)
                baseline=evidence.get('liveBaseline') or {}
                ci=evidence.get('ciBaseline') or {}
                review={'status':'historical-evidence-baseline-not-feature-validation',
                    'reviewedAt':evidence.get('reviewedAt'),
                    'sourceBuild':baseline.get('build'),
                    'ciConclusionAtSourceBuild':ci.get('conclusion'),
                    'sourceCIRunId':ci.get('runId'),
                    'goalsReviewed':100,
                    'goalsWithPartialLiveObservations':partial_live,
                    'individuallyVerified':0,
                    'note':'Code file, group-level CI and sampled weekend runtime snapshots '
                           'are not individual end-to-end acceptance; the dated baseline '
                           'must not be mistaken for a test of a later build.'}
        except (OSError, ValueError, TypeError, KeyError):
            review={'status':'unavailable','reason':'evidence-matrix-missing-or-invalid'}
        return {'status':'inventory-only','total':100,'verified':6,
                'unverified':94,'counts':counts,'recordedAt':manifest.get('asOf'),
                'buildBoundAcceptance':historical_acceptance,
                'codeFilesMapped':len(unique_paths),'codeFilesPresent':present,
                'codeFilesMissing':len(unique_paths)-present,
                'codeFileScope':'existence-only-not-test-or-live-proof',
                'evidenceReview':review, 'moduleInventory':module_summary,
                'moduleDiscovery':root_discovery, 'testEvidenceInventory':test_evidence,
                'workSplit':work_split,
                'note':'Six goals have narrow dated original observations: module-root change, seven-day journal '
                       'sample, archived health comparison, Render CPU/RAM, and historic '
                       'dual-service build match plus three manually observed handset notifications. 94 remain unaccepted; no continuous '
                       'deployment, universal device delivery, causal repair or trade approval.'}
    except (KeyError, TypeError, ValueError, AttributeError, OSError):
        return {'status':'unavailable',
                'reason':'read-access-manifest-missing-or-inconsistent'}


def focused_report(report, focus='overview'):
    """Select only fixed sanitized diagnostics; invalid focus is rejected."""
    if focus not in DIAGNOSTIC_FOCUS:
        raise ValueError('Unknown diagnostic focus')
    if not isinstance(report, dict) or focus == 'overview':
        return report
    original = report.get('areas') or {}
    areas = {name: original[name] for name in _FOCUS_AREAS[focus]
             if name in original}
    if focus in ('trades', 'signals', 'repairs'):
        sim = original.get('simulationAndPush')
        if isinstance(sim, dict):
            selected = {
                'trades': ('tradeMonitoring', 'tradeEvents', 'pushObservations'),
                'signals': ('decisionArchive',),
                'repairs': ('repairs',),
            }[focus]
            detail = sim.get('details') if isinstance(sim.get('details'), dict) else {}
            inner = detail.get('areas') if isinstance(detail.get('areas'), dict) else {}
            areas['simulationAndPush'] = {'status':sim.get('status', 'unavailable'),
                'details': {'status':detail.get('status', 'unavailable'),
                            'areas':{k:inner.get(k, {'status':'unavailable'})
                                     for k in selected}}}
            if focus == 'signals':
                areas['simulationAndPush']['signalHistory'] = sim.get(
                    'signalHistory', {'status':'unavailable'})
            if focus == 'repairs':
                journal = sim.get('history') if isinstance(sim.get('history'), dict) else {}
                areas['simulationAndPush']['history'] = {
                    'status':journal.get('status','unavailable'),
                    'journal':journal.get('journal', {'status':'unavailable'})}
        else:
            areas['simulationAndPush'] = {'status':'unavailable'}
    reduced = {key:report[key] for key in ('readOnly', 'realOrders',
        'observedAt', 'schemaVersion', 'scope') if key in report}
    # Reflect nested stale/partial/unavailable evidence in the focused
    # envelope. A top-level "observed" otherwise masks exactly the problem
    # the caller selected for diagnosis (e.g. stale 1m candles).
    finding = summary(areas)
    reduced.update(focus=focus, status='observed', areas=areas, summary=finding)
    if (not areas or finding['assessment'] == 'needs-attention'
            or any(isinstance(v,dict) and v.get('status') in
                   ('unavailable','stale','partial','degraded','failed')
                   for v in areas.values())):
        reduced['status'] = 'partial'
    # "partial" describes observation coverage, not a global outage and not
    # trading permission. Original provider timestamps are kept untouched.
    return reduced


def triage_snapshot(areas):
    """Small operator checklist from previously sanitized observations only.

    Source history is not current-feed proof; missing cases are not failed trades.
    Original source and report times are retained instead of stamping a fake fix.
    """
    areas = areas if isinstance(areas,dict) else {}
    findings=[]
    def add(code, priority, evidence_at, explanation, next_check):
        if len(findings) < 10:
            findings.append({'code':code,'priority':priority,
                             'evidenceAt':evidence_at,
                             'finding':explanation,'nextCheck':next_check,
                             'repairVerified':False,'tradeApproval':False})
    background = areas.get('background') or {}
    if background.get('status') not in ('ok','observed'):
        add('BACKGROUND_NOT_CONFIRMED','high',
            background.get('lastSuccessAt'), 'Hintergrundstatus nicht bestätigt.',
            'Worker-Ereignisse und letzten erfolgreichen Durchlauf vergleichen.')
    products = areas.get('products') or {}
    missing = [p.get('isin') for p in (products.get('items') or [])
               if isinstance(p,dict) and p.get('state') == 'incomplete'
               and isinstance(p.get('isin'),str)]
    if missing:
        add('PRODUCT_EVIDENCE_GAPS','high',products.get('lastCheckedAt'),
            str(len(missing))+' Produktnachweise unvollständig: '+', '.join(missing[:6])+'.',
            'Fehlende Originalquellen pro ISIN prüfen; keine Freigabe aus Schätzungen ableiten.')
    sources = (areas.get('sourceReliability') or {}).get('sources') or {}
    bad = [name for name,value in sources.items()
           if isinstance(value,dict) and value.get('state') in ('stale','failed','degraded')]
    # Source-reliability tracks every observed feed, including backups.
    # Match it to the actual source of the cached analysis bars before calling
    # a failed backup a failure of the currently selected market feed.
    active = {}
    for frame, candle in ((areas.get('market') or {}).get('candles') or {}).items():
        if not isinstance(candle,dict):
            continue
        evidence = candle.get('integrity') if isinstance(candle.get('integrity'),dict) else {}
        source = evidence.get('source') or (candle.get('last') or {}).get('source')
        if not isinstance(source,str):
            continue
        label = source.lower()
        provider = 'biquote' if 'biquote' in label else 'xaus' if 'xaus' in label else None
        if provider:
            active[str(frame)] = provider
    selected_bad, alternate_bad, unknown_bad = [], [], []
    for name in bad:
        if not isinstance(name,str) or '/' not in name:
            unknown_bad.append(name)
            continue
        provider, tf = name.split('/',1)
        selected = active.get(tf)
        if selected == provider:
            selected_bad.append(name)
        elif selected and provider in ('biquote','xaus'):
            alternate_bad.append(name)
        else:
            unknown_bad.append(name)
    if selected_bad:
        add('SOURCE_SELECTED_DEGRADED','high',None,
            str(len(selected_bad))+' aktuell gewählte Kerzenquellen mit Warnzustand: '+
            ', '.join(selected_bad[:5])+'.',
            'Originalzeit und Integrität des verwendeten Zeitfensters prüfen; keine frischen Kurse annehmen.')
    if alternate_bad:
        add('SOURCE_ALTERNATIVE_STALE','info',None,
            str(len(alternate_bad))+' alternative Kerzenquellen mit Warnzustand: '+
            ', '.join(alternate_bad[:5])+'.',
            'Verwendete Quelle getrennt prüfen; Ersatzquelle ist nicht automatisch ein aktiver Signalausfall.')
    if unknown_bad:
        add('SOURCE_HEALTH_HISTORY','review',None,
            str(len(unknown_bad))+' Quellen ohne eindeutigen Abgleich zum aktiven Datenpfad: '+
            ', '.join(unknown_bad[:5])+'.',
            'Quellenzuordnung und originale Zeitstempel prüfen; Status nicht als gesund interpretieren.')
    sim = areas.get('simulationAndPush') or {}
    if sim.get('status') == 'unavailable':
        add('SIMULATION_OBSERVATION_MISSING','review',None,
            'Simulationsdiagnose derzeit nicht lesbar.',
            'Fokus simulation prüfen; fehlende Ausgabe bedeutet nicht, dass Tests laufen.')
    else:
        # Expose bounded *recorded* event causes rather than guessing why a
        # model trade is inconclusive. These events are not trading results.
        cases = [c for a in (sim.get('accounts') or []) if isinstance(a,dict)
                 for c in ((a.get('recentCases') or {}).get('items') or [])
                 if isinstance(c,dict) and c.get('status') == 'inconclusive'
                 and (c.get('administrativeReview') or {}).get('status') != paper_case_review.STATUS]
        if cases:
            gaps = sum(any(isinstance(e,dict) and e.get('kind')=='data-gap'
                           for e in (c.get('events') or [])) for c in cases)
            deferred = sum(any(isinstance(e,dict) and e.get('kind')=='deferred-sale'
                               for e in (c.get('events') or [])) for c in cases)
            explanation = (str(len(cases))+
                ' gespeicherte Simulationsfälle ohne bestätigtes Ergebnis. '+
                str(gaps)+' mit protokollierter Datenlücke, '+
                str(deferred)+' mit verschobenem Modellverkauf.')
            add('SIMULATION_OUTCOMES_UNKNOWN','review',None, explanation,
                'Zeitgleiche Originalkurse nachweisen; nur echte Datenlücken '
                'reparieren, Modellverkauf nicht als echten Fill werten.')
    # Investigate independent source samples without equating them to inputs
    # seen by the paper worker, a product quote or a known exit.
    review = ((areas.get('simulationEvidence') or {}).get('gapReview') or {})
    counts = review.get('counts') or {}
    candidates = counts.get('reviewableInputHandoffCandidates')
    if type(candidates) is int and candidates > 0:
        add('PAPER_INPUT_HANDOFF_REVIEW','review',None,
            str(candidates)+' unterschiedliche Lückenzeitpunkte mit früher/zeitnah '
            'archiviertem Gold-API-Originalkurs, aber ohne nachgewiesene '
            'passende frische 15m-Analyse. Dies ist nur ein Prüfhinweis, '
            'keine bestätigte Ursache oder belegter Paper-Ausstieg.',
            'Die Originaluhrzeit von Kurs, Analyse und tatsächlich vom '
            'Paper-Worker empfangenem Datensatz vergleichen; einen '
            'späteren Kurs niemals rückdatieren.')
    feature = (areas.get('newFeatures') or {}).get('researchSelfReview') or {}
    if feature.get('status') == 'unavailable':
        add('RESEARCH_SELF_REVIEW_PENDING','info',feature.get('sourceReportAt'),
            'Noch kein vollständiges gespeichertes Ergebnis der neuen Forschungs-Selbstprüfung.',
            'Nächsten gespeicherten Forschungszyklus abwarten; keine Live-Regeln übernehmen.')
    return {'status':'observed','readOnly':True,
            'scope':'ranked-observations-not-automatic-repair',
            'items':findings,
            'note':'Prioritäten sind technische Sichtungsreihenfolge; keine Fehlerbehebung, Handelsfreigabe oder Renditeprognose.'}


def bounded_report(report, max_bytes):
    """Omit oversized diagnostic areas explicitly, retaining small status areas."""
    import json
    def size(value):
        return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
    if not isinstance(report, dict) or size(report) <= max_bytes:
        return report
    result = dict(report)
    areas = dict(result.get('areas') or {})
    result.update(areas=areas, status='partial', truncated=True, omittedAreas=[])
    # Keep heartbeat, account balances, costs and evaluator observations even if
    # the optional historical journal dwarfs the entire response budget.
    simulation = areas.get('simulationAndPush')
    if isinstance(simulation, dict):
        compact = dict(simulation)
        areas['simulationAndPush'] = compact
        removed = []
        for key in ('history', 'signalHistory', 'details', 'analysis'):
            if size(result) <= max_bytes:
                break
            if key in compact:
                compact.pop(key)
                removed.append(key)
                compact.update(truncated=True, omittedSections=removed)
        # Keep account heartbeats and cost summaries even if per-trade cases
        # exceed the authorized response budget. Do not manufacture outcomes.
        if size(result) > max_bytes and isinstance(compact.get('accounts'), list):
            smaller = []
            omitted_cases = False
            for account in compact['accounts']:
                if isinstance(account, dict) and 'recentCases' in account:
                    entry = dict(account)
                    original_cases = account['recentCases']
                    source_status = (original_cases.get('status')
                                     if isinstance(original_cases, dict) else None)
                    # Preserve the source observation, not raw cases. A size
                    # omission must neither invent an outage nor clear one.
                    if source_status not in ('observed', 'unavailable', 'partial', 'failed'):
                        source_status = 'unknown'
                    entry['recentCases'] = {'status':'unavailable',
                                            'sourceStatus':source_status,
                                            'reason':'omitted-response-size-limit'}
                    smaller.append(entry)
                    omitted_cases = True
                else:
                    smaller.append(account)
            if omitted_cases:
                compact['accounts'] = smaller
                compact.update(truncated=True,
                               omittedSections=removed + ['accounts.recentCases'])
    result['summary'] = summary(areas)
    for name in sorted(areas, key=lambda key: size(areas[key]), reverse=True):
        if size(result) <= max_bytes:
            break
        areas[name] = {'status':'unavailable', 'reason':'omitted-response-size-limit'}
        result['omittedAreas'].append(name)
    return result


