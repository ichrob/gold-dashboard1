"""Compact read-only view of existing virtual account controls.

This is *not* a historical trade replay and never certifies a profitable strategy.
No SQL, product IDs, raw case payloads, broker records or new market assumptions.
"""
import math

PROFILES = ('conservative', 'balanced', 'offensive', 'early100', 'trend800',
            'early1000oct', 'normal1000oct', 'trend800nov', 'normal1000nov', 'ema3000nov', 'noema5000nov',
            'trend1000dec', 'normal1000dec', 'early1000dec', 'early5m1000nov')
STATUSES = ('scheduled', 'running', 'completed', 'ending-pending-quotes',
            'night-paused', 'market-closed', 'preparing', 'stopped', 'unavailable')


def number(value, *, positive=False, timestamp=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    if timestamp:
        if not 0 < value <= 1e15:
            return None
    elif abs(value) > 1e12 or (positive and value < 0.01):
        return None
    return float(value)


def entry_block_code(value):
    """Classify the latest saved gate without exposing raw product or private data.

    A reason is a current-control observation only. No historical blocker
    counts, missed-profit estimate or assumption that a trade was possible.
    """
    if not isinstance(value,str) or not value.strip():
        return 'not-observed'
    reason=value.lower()
    if reason.startswith('zwei-5m-test:'):
        return 'two-candle-wait'
    # These two timing gates are the dominant actual November no-entry
    # observations. Reuse the fixed codes from the 15-minute paper buckets.
    # Never expose the original free-text reason or change entry approval.
    ema_stretch = 'preis über 1,5 atr von ema20' in reason
    signal_age = 'älter als 15 minuten' in reason
    if ema_stretch and signal_age:
        return 'ema-stretch-and-signal-age'
    if ema_stretch:
        return 'ema-stretch'
    if signal_age:
        return 'signal-age'
    if any(word in reason for word in ('goldkurs nicht aktuell','quellenzeit','marktdaten',
                                      'daten fehlen','quellenlücke','5m-daten veraltet')):
        return 'source-not-fresh'
    if any(word in reason for word in ('außerhalb','nachtmodus','markt geschlossen',
                                      'börsenpause','einstiegszeit')):
        return 'session-paused'
    # In the paper evaluator this exact generic ABWARTEN text is emitted only
    # for a NEUTRAL market direction, not for a failed paper stop/target model.
    # Do not report yesterday's fixed plan fallback as missing in this case.
    if reason.strip() == 'abwarten: kein bestätigter gültiger goldplan':
        return 'no-direction'
    if any(word in reason for word in ('kein bestätigter gültiger goldplan',
                                      'stopp-/zielplan','risikoplan','kein gültiger goldplan',
                                      'kein bestätigter stopp')):
        return 'plan-not-ready'
    if any(word in reason for word in ('geld-/brief','geldkurs','briefkurs','kursart',
                                      'ausführungskurs','quote')):
        return 'product-quote-missing'
    if any(word in reason for word in ('ko-schutz','knock-out','ko-barriere',
                                      'ko-schwelle')):
        return 'knockout-protection'
    if any(word in reason for word in ('kein passendes belegtes produkt','kein geeigneter',
                                      'produkteeinstieg','produktfreigabe','nicht freigegeben')):
        return 'product-not-approved'
    if any(word in reason for word in ('kollektivrichtungswert','score zu schwach')):
        return 'signal-score-weak'
    if any(word in reason for word in ('tagesrisiko','risikolimit','risikobudget','verlustgrenze','tagesverlustgrenze')):
        return 'risk-limit'
    # The main signal may stay NEUTRAL while SHORT/LONG context is visible:
    # weak trend, incompatible 5m/15m confirmation and a missing second
    # close are observed market-wait reasons, not unknown system faults.
    if any(word in reason for word in (
            'haupttrend geschwächt', '5m-kursindikatoren neutral oder widersprüchlich',
            'zeitebenen bestätigen die richtung nicht',
            'trendstärke schwach: zweite schlusskerze',
            'erst 1 von 2 geschlossenen 5m-kerzen bestätigt',
            'kleine ema-/macd-distanz: zweite schlusskerze')):
        return 'no-direction'
    if 'kurzfristiger rücksetzer; einstieg abwarten' in reason:
        return 'plan-not-ready'
    if any(word in reason for word in ('abwarten','keine bestätigte richtung',
                                      'keine einstiegsrichtung','signal neutral')):
        return 'no-direction'
    return 'other-or-unclassified'


ENTRY_BLOCK_CODES = frozenset((
    'not-observed','source-not-fresh','session-paused','plan-not-ready',
    'product-quote-missing','knockout-protection','product-not-approved',
    'signal-score-weak','risk-limit','no-direction','other-or-unclassified',
    'ema-stretch-and-signal-age','ema-stretch','signal-age',
    'two-candle-wait'))


FORWARD_VERSION = 'prospective-paper-v1'
MIN_HOLDOUT_CASES = 30
PROOF_REASONS = (
    'actual-broker-fees-and-executability-not-observed',
    'full-original-product-history-not-audited',
    'paired-out-of-sample-strategy-comparison-not-established',
)


def safe_forward_evidence(value):
    """Copy only bounded, numeric forward-run evidence from a saved control.

    A prospective model-only sample is not a certificate of real-world costs,
    a comparable winner, a broker execution, or a fully read trade history.
    """
    result = {'status':'not-observed', 'readOnly':True,
              'actualNetVerified':False, 'winnerConfirmed':False}
    if not isinstance(value, dict) or value.get('version') != FORWARD_VERSION:
        return result
    started = number(value.get('startedAt'), timestamp=True)
    validated = number(value.get('validationAt'), timestamp=True)
    if started is None or validated is None or validated <= started:
        return result
    phases = {}
    for name in ('calibration', 'validation'):
        row = value.get(name)
        row = row if isinstance(row, dict) else {}
        count = row.get('cases')
        net = number(row.get('netEur'))
        gross = number(row.get('grossEur'))
        if type(count) is not int or not 0 <= count <= 100000 or (
                count > 0 and (net is None or gross is None)):
            phases[name] = {'status':'unavailable', 'cases':None}
        else:
            phases[name] = {'status':'observed' if count else 'not-yet-observed',
                            'cases':count,
                            'modelNetEur':round(net,4) if net is not None and count else None,
                            'modelGrossEur':round(gross,4) if gross is not None and count else None}
    excluded = value.get('excluded')
    excluded = excluded if type(excluded) is int and 0 <= excluded <= 100000 else None
    sufficient = (excluded == 0 and
                  all(phases[k]['status']=='observed'
                      and phases[k]['cases'] >= MIN_HOLDOUT_CASES
                      for k in phases))
    return {'status':'sample-observed' if any(
                x['status']=='observed' for x in phases.values()) else 'collecting',
            'startedAt':started, 'validationAt':validated,
            'excluded':excluded, **phases,
            'sufficientModelHoldoutCases':sufficient,
            'readOnly':True, 'actualNetVerified':False,
            'winnerConfirmed':False}


def safe_forward_projected(value):
    """Revalidate the already sanitized in-process forward projection."""
    if not isinstance(value, dict) or value.get('readOnly') is not True:
        return safe_forward_evidence(None)
    result = {'status':'not-observed', 'readOnly':True,
              'actualNetVerified':False, 'winnerConfirmed':False}
    if value.get('status') not in ('sample-observed','collecting'):
        return result
    start = number(value.get('startedAt'),timestamp=True)
    validation = number(value.get('validationAt'),timestamp=True)
    if start is None or validation is None or validation <= start:
        return result
    result.update(status=value['status'],startedAt=start,validationAt=validation)
    excluded=value.get('excluded')
    result['excluded']=excluded if type(excluded) is int and 0 <= excluded <= 100000 else None
    for name in ('calibration','validation'):
        original=value.get(name)
        original=original if isinstance(original,dict) else {}
        count=original.get('cases')
        if type(count) is int and 0 <= count <= 100000:
            status=('observed' if count else 'not-yet-observed')
            net=number(original.get('modelNetEur'))
            gross=number(original.get('modelGrossEur'))
            if count and (net is None or gross is None):
                result[name]={'status':'unavailable','cases':None}
            else:
                result[name]={'status':status,'cases':count,
                              'modelNetEur':net if count else None,
                              'modelGrossEur':gross if count else None}
        else:
            result[name]={'status':'unavailable','cases':None}
    result['sufficientModelHoldoutCases'] = (
        result['excluded']==0 and
        all(result[k]['status']=='observed'
            and result[k]['cases'] >= MIN_HOLDOUT_CASES
            for k in ('calibration','validation')))
    return result


def safe_net_sample(value):
    """No arbitrary case text/ISIN/quote/secret fields in compact diagnostics."""
    if not isinstance(value,dict) or value.get('status') not in (
            'observed', 'not-yet-observed', 'partial', 'unavailable'):
        return {'status':'unavailable','fullHistoryRead':False,'brokerNetVerified':False}
    out = {'status':value['status'],'fullHistoryRead':False,
           'brokerNetVerified':False}
    for key in ('sampled','modelEvidenceEligible','excluded',
                'positiveSampleModelCases'):
        v=value.get(key)
        if type(v) is int and 0 <= v <= 5:
            out[key]=v
    net=number(value.get('sampleModelNetEur'))
    if net is not None and out.get('modelEvidenceEligible',0)>0:
        out['sampleModelNetEur']=net
    raw=value.get('excludedReasonCounts')
    if isinstance(raw,dict):
        import paper_net_evidence
        out['excludedReasonCounts']={k:v for k,v in raw.items()
            if k in paper_net_evidence.REASONS and type(v) is int
            and 0 <= v <= 5}
    return out



# Fixed, code-owned exit categories; never forward raw case/issuer data.
LOSS_REVIEW_PROFILES = frozenset(('ema3000nov','noema5000nov',
                                  'early1000dec','early5m1000nov'))
MODEL_EXIT_REASONS = frozenset(('stop','time-exit','target-exit',
    'reversal-exit','ko-safety-exit','profit-weak','trend-exit',
    'partial-profit','stop-follow','other'))


def saved_exit_review(reflection):
    """Read a control's already-stored paper reflections; no trade or SQL reads.

    The cumulative counts are stored by the normal ledger at settlement.
    The most recent 20 reviewed cases are a bounded descriptive SAMPLE, not
    necessarily the entire history, nor verified DEGIRO net returns.
    """
    unknown = dict(status='not-yet-observed', readOnly=True, realOrders=False,
        brokerNetVerified=False, fullHistoryRead=False,
        sampleScope='last-twenty-saved-reflections-not-full-trade-history')
    if not isinstance(reflection, dict) or reflection.get('version') != 'paper-reflection-v1':
        return unknown
    def count(key):
        v=reflection.get(key)
        return v if type(v) is int and 0 <= v <= 1000000 else None
    reviewed=count('reviewed'); evaluated=count('evaluated')
    losses=count('modelLosses'); unpriced=count('unpriced')
    if (None in (reviewed,evaluated,losses,unpriced) or
            evaluated+unpriced > reviewed or losses > evaluated):
        return dict(unknown,status='invalid-stored-summary')
    recent=reflection.get('recent')
    if not isinstance(recent,list):
        recent=[]
    reasons={}
    sample=dict(reviewed=0,modeledWins=0,modeledLosses=0,
                modeledFlat=0,unpriced=0,grossPositiveButNetNonPositive=0)
    for x in recent[-20:]:
        if not isinstance(x,dict) or x.get('version')!='paper-reflection-v1':
            continue
        sample['reviewed']+=1
        reason=x.get('exitReason')
        reason=reason if reason in MODEL_EXIT_REASONS else 'other'
        reasons[reason]=reasons.get(reason,0)+1
        cost=x.get('costModel')
        net=number(cost.get('modelNetEur')) if isinstance(cost,dict) else None
        gross=number(cost.get('grossEur')) if isinstance(cost,dict) else None
        if net is None:
            sample['unpriced']+=1
        else:
            sample['modeledWins' if net>0 else
                   'modeledLosses' if net<0 else 'modeledFlat']+=1
            if gross is not None and gross>0 and net<=0:
                sample['grossPositiveButNetNonPositive']+=1
    return {**unknown,'status':'observed',
        'cumulative':{'reviewed':reviewed,'modeledEvaluated':evaluated,
                      'modeledLosses':losses,'unpriced':unpriced,
                      'modelNetEur':number(reflection.get('modelNetEur'))},
        'recentSample':sample,'recentExitReasons':reasons,
        'lastAt':number(reflection.get('lastAt'),timestamp=True)}


def safe_exit_review_projection(value):
    """Allowlist an already sanitized report for paperProfitEvidence rows."""
    if not isinstance(value,dict) or value.get('status') not in (
            'observed','not-yet-observed','invalid-stored-summary'):
        return {'status':'unavailable','readOnly':True,'brokerNetVerified':False,
                'fullHistoryRead':False}
    out={'status':value['status'],'readOnly':True,'realOrders':False,
         'brokerNetVerified':False,'fullHistoryRead':False,
         'sampleScope':'last-twenty-saved-reflections-not-full-trade-history'}
    def validated_counts(obj,fields):
        return {k:obj[k] for k in fields if type(obj.get(k)) is int
                and 0<=obj[k]<=1000000} if isinstance(obj,dict) else {}
    if out['status']=='observed':
        cumul=value.get('cumulative')
        out['cumulative']=validated_counts(cumul,
            ('reviewed','modeledEvaluated','modeledLosses','unpriced'))
        if isinstance(cumul,dict):
            out['cumulative']['modelNetEur']=number(cumul.get('modelNetEur'))
        out['recentSample']=validated_counts(value.get('recentSample'),
            ('reviewed','modeledWins','modeledLosses','modeledFlat',
             'unpriced','grossPositiveButNetNonPositive'))
        reasons=value.get('recentExitReasons')
        out['recentExitReasons']={
            k:v for k,v in reasons.items() if k in MODEL_EXIT_REASONS
            and type(v) is int and 0<=v<=20} if isinstance(reasons,dict) else {}
        out['lastAt']=number(value.get('lastAt'),timestamp=True)
    return out


def snapshot(accounts):
    """Project only explicitly allowlisted account-control numbers already read."""
    unavailable = dict(status='unavailable', readOnly=True, realOrders=False,
                       strategyWinnerConfirmed=False, netProductReturnsVerified=False,
                       fullHistoryRead=False,
                       scope='existing-paper-account-controls-not-trade-outcome-proof')
    if not isinstance(accounts, list):
        return dict(unavailable, reason='paper-account-controls-not-observed')
    by_profile = {a.get('profile'): a for a in accounts[:20]
                  if isinstance(a, dict) and a.get('profile') in PROFILES}
    rows = []
    for profile in PROFILES:
        a = by_profile.get(profile)
        if a is None:
            rows.append(dict(profile=profile, source='missing-account-control',
                             initialCapitalEur=None, equityEur=None,
                             modelProfitEur=None, modelReturnPct=None))
            continue
        initial = number(a.get('initialCapital'), positive=True)
        equity = number(a.get('equity'))
        total = number(a.get('totalProfit'))
        model_pct = (round((equity / initial - 1) * 100, 4)
                     if initial is not None and equity is not None else None)
        status = a.get('status') if a.get('status') in STATUSES else 'unavailable'
        # The night pause overwrites the displayed reason. Prefer the last
        # trading-window code saved by the virtual ledger, never the raw text.
        control = a.get('control') if isinstance(a.get('control'),dict) else {}
        last_code, last_at = None, None
        if profile in ('trend800nov','normal1000nov','ema3000nov', 'noema5000nov',
                       'trend1000dec','normal1000dec','early1000dec',
                       'early5m1000nov'):
            stored = a.get('lastTradingEntryBlockCode',
                           control.get('lastTradingEntryBlockCode'))
            stored_valid = isinstance(stored, str) and stored in ENTRY_BLOCK_CODES
            if stored_valid:
                last_code = stored
                last_at = number(a.get('lastTradingEntryBlockAt',
                                       control.get('lastTradingEntryBlockAt')),
                                 timestamp=True)
            elif status in ('night-paused', 'market-closed', 'preparing',
                            'scheduled', 'completed'):
                # A current after-hours reason is not evidence of an actual
                # trading-window entry blocker. Never invent its time.
                last_code = 'not-observed'
            else:
                last_code = entry_block_code(a.get('reason') or control.get('reason'))
        rows.append(dict(
            profile=profile, source='saved-virtual-control',
            status=status,
            checkedAt=number(a.get('checkedAt'), timestamp=True),
            startAt=number(a.get('startAt'), timestamp=True),
            endAt=number(a.get('endAt'), timestamp=True),
            initialCapitalEur=initial,
            cashEur=number(a.get('cash')),
            equityEur=equity,
            modelProfitEur=total,
            modelReturnPct=model_pct,
            realizedModelProfitEur=number(a.get('realizedProfit')),
            exampleCostsDebitedEur=number(a.get('costsDebitedEur')),
            tradeOutcomeVerified=False,
            latestEntryBlockCode=last_code,
            latestEntryBlockAt=last_at,
            forwardEvidence=(safe_forward_projected(a['forwardEvidence'])
                             if a.get('forwardEvidence') is not None
                             else safe_forward_evidence(a.get('forwardValidation'))),
            recentModelNetSample=safe_net_sample(a.get('netEvidenceSample')),
            modelExitReview=(safe_exit_review_projection(a.get('modelExitReview'))
                             if profile in LOSS_REVIEW_PROFILES else None)))
    complete = all(r.get('source') == 'saved-virtual-control'
                   and r.get('initialCapitalEur') is not None
                   and r.get('equityEur') is not None for r in rows)
    return dict(
        status='observed' if complete else 'partial',
        readOnly=True, realOrders=False,
        strategyWinnerConfirmed=False, netProductReturnsVerified=False,
        fullHistoryRead=False, rows=rows,
        proofReasons=list(PROOF_REASONS),
        modelNetAuditAvailable=any(row.get('recentModelNetSample',{}).get(
            'modelEvidenceEligible',0)>0 for row in rows),
        comparableStrategyHoldoutVerified=False,
        brokerExecutionVerified=False,
        scope='existing-paper-account-controls-plus-last-five-sampled-cases-not-broker-proof',
        note='Nur gespeicherte virtuelle Kontostände und angenommene Kosten, '
             'keine geprüften historischen Trade-Abschlüsse oder ausführbaren '
             'Produktkurse. Eine höhere Modellrendite beweist keinen '
             'profitablen Strategievorteil. Fehlende Werte bleiben unbekannt.')
