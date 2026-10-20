"""Bounded read-only operational observations; never invoke repair or trading."""
from datetime import datetime, timezone
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
    return {'status': 'unavailable' if not live else 'stale' if age is None or not 0 <= age <= 120 else live.get('status', 'observed'),
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
    return {'readOnly':True, 'realOrders':False,
            'observedAt':datetime.now(timezone.utc).isoformat(),
            'status':'partial' if any(a.get('status') == 'unavailable' for a in areas.values()) else 'observed',
            'schemaVersion':2, 'summary':summary(areas),
            'scope':'operational-observations-not-complete-feature-validation', 'areas':areas}


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
        result['history'] = collect({'journal':lambda:__import__('diagnostic_history').report(conn)})
        result['details'] = stored_details(conn)
        result['analysis'] = analysis_snapshot()
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
ANALYSIS = shape('ready','priceFresh','dataAt','analysisBarAt','price','direction','baseDirection','mtf','score','atr','macd','signal','decisionReason','ruleVersion','suggestedStop','suggestedTarget',
    analysisSnapshot=INDICATORS, trendContext=shape('available','direction','intact','reason'),
    entryTimingGate=shape('allowed','reason','status'),session=shape('phase','entryAllowed','reason'),
    dmi=shape('available','adx','plusDI','minusDI','direction','reason'),continuedPlan=PLAN)
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
    return collect({
        'gapModels':gap_models,
        'decisionArchive':lambda:rows("SELECT payload FROM bob_decision_audit ORDER BY recorded_at DESC LIMIT 20",
            shape('recordedAt','barAt','priceAt','price','direction','baseDirection','shadowDirection','reason','score','ruleVersion','build','origin','marketEvaluable',
                indicators=INDICATORS,gateReasons=[None],plan=shape('kind','direction','entry','stop','target','unit','at'))),
        'tradeMonitoring':lambda:rows("SELECT jsonb_build_object('updatedAt',updated_at,'active',active,'direction',snapshot->'dir','product',snapshot->'product','state',state) FROM bob_real_trades ORDER BY updated_at DESC LIMIT 10",
            shape('updatedAt','active','direction',product=shape('isin','currency','entry'),state=STATE)),
        'tradeEvents':lambda:rows("SELECT jsonb_build_object('at',recorded_at,'kind',kind,'evidence',payload) FROM bob_real_trade_events ORDER BY seq DESC LIMIT 20",
            shape('at','kind',evidence=shape('at','outcome','error','delivery','dataAt','price','direction','decisionReason','suggestedStop','suggestedTarget',analysisSnapshot=INDICATORS))),
        'pushObservations':lambda:rows("SELECT jsonb_build_object('updatedAt',updated_at,'generalEnabled',general_enabled,'tradeEnabled',trade_enabled,'activeTrade',active_trade,'state',background_state) FROM subscriptions ORDER BY updated_at DESC LIMIT 10",
            shape('updatedAt','generalEnabled','tradeEnabled','activeTrade',state=STATE)),
        'learning':lambda:rows("SELECT jsonb_build_object('day',run_day,'calculatedAt',calculated_at,'lastBarAt',last_bar_at,'status',status,'report',report) FROM bob_strategy_lab_daily ORDER BY run_day DESC LIMIT 3",
            shape('day','calculatedAt','lastBarAt','status',report=shape('version','mode','closedBars','approved','affectsLiveSignals','orderExecutionEnabled',
                evidence=shape('folds','trades','reason'),learningCycle=shape('status','reason','liveRuleChanged','productNetValidated',
                    prospective=shape('sessions','trades','baselineTrades','candidateIndex','baselineIndex','lastEvaluatedBarAt'),
                    completedStrategies=[None],rejectedStrategies=[None])))),
        'researchMedia':lambda:rows("SELECT jsonb_build_object('video',video_id,'updatedAt',updated_at,'frameAttempt',frame_attempt,'summaryAttempt',summary_attempt,'frameStatus',frame_status,'summaryError',summary_error,'summaryFailures',summary_failures,'frames',frames,'summary',summary) FROM bob_research_enhancements ORDER BY updated_at DESC LIMIT 10",
            shape('video','updatedAt','frameAttempt','summaryAttempt','frameStatus','summaryError','summaryFailures',
                frames=[shape('at','requestedAt','isCover','userProvided','width','height')],
                summary=shape('kind','model','partial',visualNotes=[shape('at','kind','reason')]))),
        'repairs':lambda:rows("SELECT jsonb_build_object('at',event_at,'recordedAt',recorded_at,'kind',kind,'code',code) FROM bob_self_heal_events ORDER BY recorded_at DESC LIMIT 20",
            shape('at','recordedAt','kind','code')),
    })


def research_snapshot(value):
    return project(value,shape('checkedAt','fresh','successfulFeeds','intervalSeconds','videosFound','videosAnalyzed','mcoOutlook','mcoReason',
        sources=[shape('id','status','checkedAt','scanned','relevant','error')],
        items=[shape('title','publishedAt','outlook','current','coverage','transcriptAnalyzed','trustedTranscript','transcriptAccess','transcriptProvider','transcriptLanguage','transcriptWords','analysisStatus','error',
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
        if state in ('unavailable','stale','degraded','failed','retry','partial','wrong-basis','invalid-ohlc','recent-gap','missing','insufficient','recurred'):
            findings.append({'area':path,'state':state})
        for key,item in value.items():
            if isinstance(item,(dict,list)):walk(item,path+'.'+key)
    for name,area in areas.items():walk(area,name)
    return {'attention':findings[:40], 'assessment':'needs-attention' if findings else 'observed-only',
            'note':'No finding does not prove feature health. Source timestamps remain authoritative; report time is collection time.'}
