"""Bounded read-only operational observations; never invoke repair or trading."""
from datetime import datetime, timezone
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
    gap_evidence = (areas.get('simulationAndPush') or {}).get('gapEvidence')
    if isinstance(gap_evidence, dict):
        areas['gapEvidence'] = gap_evidence
        areas['simulationAndPush'] = dict(areas['simulationAndPush'])
        areas['simulationAndPush'].pop('gapEvidence', None)
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
        'causeScope':'overlap-possible-recorded-events-only-not-ground-truth',
        'observedCases':len(stored),
        'closed':sum(c.get('status') == 'closed' for c in stored),
        'open':sum(c.get('status') == 'open' for c in stored),
        'inconclusive':sum(c.get('status') == 'inconclusive' for c in stored),
        'accountsUnavailable':sum(g.get('status') != 'observed' for g in groups),
        'realOrders':False,'missingResultsAreLosses':False,
        'note':'Unbestätigte Simulationen sind weder realisierte Verluste '
               'noch automatisch behobene Datenlücken.'}


def push_snapshot(conn, evaluator, paper_health, portfolios, extended=False):
    """Only SELECT statements; fixed tables and explicit private diagnostic projections."""
    accounts = []
    for profile in portfolios.POLICIES:
        table = portfolios.names(profile)['bob_paper_control']
        row = conn.execute(f'SELECT payload FROM {table} WHERE id=1').fetchone()
        accounts.append({'profile':profile, **fields(row[0] if row else {},
            ('enabled','status','checkedAt','startAt','reason','currency','initialCapital','cash','equity','dayProfit','totalProfit','realizedProfit','costsDebitedEur','costPeriodProfit','costsStartedAt','costsNote'))})
    row = conn.execute('SELECT count(*) FROM subscriptions WHERE general_enabled=TRUE OR (trade_enabled=TRUE AND active_trade=TRUE)').fetchone()
    result = {'status':'observed', 'paper':paper_health.snapshot(conn), 'accounts':accounts,
            'push': {'activeMonitors':row[0], 'deliveryStatus':'not-verified',
                     # Subscription eligibility is not proof of a delivered Android
                     # notification, and no subscriptions is not a push transport failure.
                     'monitorState':('none-enabled' if row[0] == 0 else 'subscriptions-observed'),
                     'deliveryNote':('Keine aktiven Push-Monitore/Subscriptions nach Datenbankfilter; '
                         'Geräteberechtigung und tatsächliche Zustellung sind nicht geprüft.'
                         if row[0] == 0 else
                         'Empfangsberechtigte Subscriptions vorhanden; tatsächlicher '
                         'Geräteempfang noch nicht nachgewiesen.'),
                     'evaluator':fields(evaluator.status(), ('completed','failed','queueTimeouts','shared','busy','waiting','inFlight','lastDurationMs','lastWaitMs'))}}
    if extended:
        for account in accounts:
            table = portfolios.names(account['profile'])['bob_paper_cases']
            try:
                with conn.transaction():
                    cases = conn.execute(f'SELECT payload FROM {table} ORDER BY started_at DESC LIMIT 5').fetchall()
                account['recentCases'] = {'status':'observed','items':[project(row[0], CASE) for row in cases]}
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


CASE = shape('status','startedAt','closedAt','lastAt','direction','modelOnly','netReturnKnown','productReturnKnown','productGrossPct','goldR','capitalMode','ledgerCostsDebited','ledgerFeesEur','ledgerSlippageEur','ledgerModelNetEur',
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
        data_gaps=deferred=terminal=0
        for c in cases:
            if not isinstance(c,dict):
                kinds['other']+=1
                continue
            status=c.get('status')
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
            'gapReview':__import__('paper_gap_triage').assess(
                {'recentRecordedGapInstants':clusters[-10:]},
                simulation.get('spotGapArchive'),simulation.get('analysisGapArchive')),
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
            leverageObservation=shape('value','leverage','source','at','current','calculated','method'),
            sourceObservations=[shape('source','at','bidAt','askAt','bid','ask','currency','kind','priceKind','isExecutableQuote')],
            fieldRecovery=shape('status','state','source','checkedAt','reason',conflicts=[None]))]))


def summary(areas):
    findings=[]
    def walk(value,path):
        if isinstance(value,list):
            for i,item in enumerate(value[:20]):walk(item,path+'.'+str(i))
            return
        if not isinstance(value,dict):return
        state=value.get('status',value.get('state'))
        if state in ('unavailable','stale','degraded','failed','retry','partial','wrong-basis','invalid-ohlc','recent-gap','missing','insufficient','incomplete','conflict','inconclusive','recurred'):
            findings.append({'area':path,'state':state})
        if path.endswith('.dmi') and value.get('available') is False:
            findings.append({'area':path,'state':'incomplete'})
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
    return {'attention':findings[:40], 'assessment':'needs-attention' if findings else 'observed-only',
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
    'simulation': ('simulationEvidence', 'simulationAndPush', 'background', 'collection', 'gapEvidence'),
    'sources': ('market', 'sourceReliability', 'collection', 'background', 'analysis'),
    'research': ('research', 'strategyResearch', 'strategyReport', 'newFeatures'),
    'mobile': ('newFeatures', 'runtime', 'degiroSync', 'products'),
    'products': ('products', 'degiroSync', 'gapEvidence'),
    'repairs': ('selfHealing', 'problems', 'background', 'diagnosticTriage'),
    'trades': ('background', 'diagnosticTriage'),
    'signals': ('analysis', 'background', 'diagnosticTriage', 'pushDeliveries'),
}


def read_access_coverage(manifest):
    """Bounded, non-operational inventory of 100 *unverified* feature objectives.

    This is documentation coverage, not evidence that a feature works.
    Never exposes raw repository text, credentials or individual user data.
    """
    try:
        rows = manifest['tasks']
        ids = [row['id'] for row in rows]
        allowed = {'partial', 'planned', 'blocked-client', 'requires-device'}
        if (manifest.get('schemaVersion') != 1 or manifest.get('total') != 100
                or len(rows) != 100 or sorted(ids) != list(range(1,101))
                or any(row.get('state') not in allowed or
                       row.get('verified') is not False for row in rows)):
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
        return {'status':'inventory-only','total':100,'verified':0,
                'unverified':100,'counts':counts,'recordedAt':manifest.get('asOf'),
                'codeFilesMapped':len(unique_paths),'codeFilesPresent':present,
                'codeFilesMissing':len(unique_paths)-present,
                'codeFileScope':'existence-only-not-test-or-live-proof',
                'note':'Repository worklist only. File presence is not a functional test. No feature is live-proven by inclusion.'}
    except (KeyError, TypeError, ValueError, AttributeError):
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
    reduced.update(focus=focus, status='observed', areas=areas,
                   summary=summary(areas))
    # Absence in a focused area is not proof of health.
    if not areas or any(isinstance(v,dict) and v.get('status') == 'unavailable'
                        for v in areas.values()):
        reduced['status'] = 'partial'
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
                 if isinstance(c,dict) and c.get('status') == 'inconclusive']
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
                    entry['recentCases'] = {'status':'unavailable',
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

