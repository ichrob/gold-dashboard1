"""Bounded prospective paper evaluation; no orders or automatic strategy tuning."""
import hashlib
import json
import math
import paper_costs
import paper_evidence_chain

VERSION='prospective-paper-v1'
DAY=86400000


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def signature(market):
    policy=market.get('learningPolicy')
    frozen={'ruleVersion':market.get('ruleVersion')}
    frozen['learningPolicy']=({k:policy.get(k) for k in ('version','variant','base')}
        if isinstance(policy,dict) else policy if isinstance(policy,str) else None)
    return hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()


def start(control, market, now):
    if ('forwardValidation' not in control and finite(now) and market.get('ready') is True
            and market.get('priceFresh') is True and finite(market.get('dataAt'))
            and 0<=now-market['dataAt']<=60000 and market.get('ruleVersion')
            and market.get('learningPolicy')!='unavailable'):
        control['forwardValidation']=dict(version=VERSION,startedAt=now,validationAt=now+DAY,
            signature=signature(market),excluded=0,calibration={},validation={},
            actualNetKnown=False,strategyWinnerConfirmed=False,automaticPolicyChanges=False)


def record(control, case, now):
    state=control.get('forwardValidation')
    if not state or state.get('version')!=VERSION:return
    if case.get('forwardValidationRecorded') is True:return
    # No historical reconstruction: new entry instrumentation is mandatory.
    timing=case.get('entryTiming') or {}
    costs=paper_costs.evaluate(case,case.get('ledgerCostModel') or paper_costs.SCENARIOS[0])
    evidence=paper_costs.evidence_report([case])['cases']
    eligible=(finite(case.get('startedAt')) and case['startedAt']>=state['startedAt']
        and timing.get('version')==1 and finite(timing.get('sourceAt'))
        and finite(timing.get('decisionAt')) and 0<=timing['decisionAt']-timing['sourceAt']<=60000
        and signature(case.get('analysis') or {})==state['signature']
        and evidence and evidence[0]['performanceEligible'] and costs is not None
        and paper_evidence_chain.review(case)['complete'] is True
        and not any(e.get('kind') in ('data-gap','deferred-sale') for e in case.get('events',[])))
    case['forwardValidationRecorded']=True
    if not eligible:
        state['excluded']+=1
        return
    phase='validation' if case['startedAt']>=state['validationAt'] else 'calibration'
    row=state[phase]
    row.setdefault('cases',0);row.setdefault('netEur',0.);row.setdefault('grossEur',0.)
    row.setdefault('wins',0);row.setdefault('positiveNetEur',0.);row.setdefault('negativeNetEur',0.)
    row.setdefault('sourceAgeSumMs',0.)
    row['cases']+=1;row['netEur']+=costs['modelNetEur'];row['grossEur']+=costs['grossEur']
    row['wins']+=int(costs['modelNetEur']>0)
    row['positiveNetEur']+=max(0,costs['modelNetEur'])
    row['negativeNetEur']+=min(0,costs['modelNetEur'])
    row['sourceAgeSumMs']+=timing['decisionAt']-timing['sourceAt']
    row['expectancyEur']=row['netEur']/row['cases']
    row['profitFactor']=row['positiveNetEur']/-row['negativeNetEur'] if row['negativeNetEur']<0 else None
    row['meanSourceAgeMs']=row['sourceAgeSumMs']/row['cases']
    row['lastAt']=now
