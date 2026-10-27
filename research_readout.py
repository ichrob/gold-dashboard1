"""Fixed SELECT-only projection of the stored research report, without account data."""
from bob_diagnostics import project, shape

STRATEGIES = ('baseline', 'trend-strict', 'trend-tight', 'breakout',
              'breakout-confirmed', 'mean-revert', 'learned-linear')
SCORE = shape('trades','skippedGap','avgNetPct','netReturnPct','maxDrawdownPct','minEquityIndex',
              'maxEquityIndex','winRatePct','profitFactor','grossWinsPct','grossLossesPct')
AGGREGATE = shape('trades','meanFoldNetPct','worstFoldNetPct','maxFoldDrawdownPct')
STATS = shape('index','peak','maxDrawdownPct','trades')
COST = shape('costBpsPerSide',candidate=STATS,baseline=STATS)
PROTOCOL = shape('version','engineVersion','horizonBars','baseline','minSessions',
                 'minTradesEach','costKind','productNetValidated',
                 costBpsPerSide=shape('standard','stress'))
SELF_REVIEW = shape('mode','status','confidence','reason','sessions','trades',
    'baselineTrades','liveRuleChanged','automaticOrder','productNetValidated',
    'actionable',
    comparedScenarios={name:shape(
        'candidateTrades','baselineTrades','candidateNetIndex','baselineNetIndex',
        'relativeDifferencePct','candidateMaxDrawdownPct','baselineMaxDrawdownPct',
        'advantage') for name in ('standard','stress')},
    recentWindows=shape('comparedIntervals','outperformingIntervals',
                        'underperformingOrEqualIntervals','note'))

PROGRESS = shape('sessions','trades','baselineTrades','candidateIndex','baselineIndex',
                 'lastEvaluatedBarAt', costScenarios=shape(standard=COST,stress=COST),
                 lastObservation=shape('day','newBars',candidate=SCORE,baseline=SCORE))
REPORT = shape('version','mode','status','brokerConnected','orderExecutionEnabled',
    'affectsLiveSignals','historicalInstrument','barInterval','closedBars',
    'costBpsPerSide','horizonBars','approved','description','note',rangeMs=[None],strategies=[None],
    replay=shape('available','id'),
    folds=[shape('trainEndMs','validationStartMs','testStartMs','testEndMs',
                 'selectedOnValidation','learningFittedOnTrain','selectionUsesTest',
                 validation={k:SCORE for k in STRATEGIES},outOfSample={k:SCORE for k in STRATEGIES})],
    outOfSampleByStrategy={k:AGGREGATE for k in STRATEGIES},
    validationSelected=AGGREGATE,samePeriodBaseline=AGGREGATE,
    evidence=shape('folds','selectedTrades','sufficientForResearch','statisticallyConfirmed',
                   'productNetValidated','liveForwardValidated'),
    learningCycle=shape('version','status','reason','day','checkpoint','liveRuleChanged',
        'productNetValidated','automaticOrder',experiments=[None],completedStrategies=[None],
        rejectedStrategies=[None],prospective=PROGRESS,
        proposal=shape('strategy','state','proposedOn','frozenAtBar','mode','source','note',protocol=PROTOCOL),
        completed=[shape('strategy','proposedOn','finishedOn','result',prospective=PROGRESS)],
        selfReview=SELF_REVIEW))


def read(conn):
    # No initialization, collection, fitting, repair or write call on this path.
    rows=conn.execute('''SELECT jsonb_build_object('day',run_day,'calculatedAt',calculated_at,
        'lastBarAt',last_bar_at,'status',status,'report',report)
        FROM bob_strategy_lab_daily ORDER BY run_day DESC LIMIT 1''').fetchall()
    return dict(status='observed' if rows else 'empty',readOnly=True,
        scope='latest-stored-reference-research-not-product-execution',limit=1,
        emptyMeans='no-stored-observations',items=[project(row[0],shape(
            'day','calculatedAt','lastBarAt','status',report=REPORT)) for row in rows])
