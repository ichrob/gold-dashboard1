"""Forward-only paper decision evidence. Never grant a product or broker release."""
import copy
import math
import decision_evidence
import stop_target_audit
import paper_costs

VERSION='paper-entry-review-v1'

def number(v):
    return type(v) in (int,float) and math.isfinite(v)

def capture(market,choice,quote,now,entered,reason,control=None,policy=None):
    control=control or {};policy=policy or {};plan=market.get('plan')
    direction=market.get('direction')
    at=market.get('dataAt')
    from paper_simulation import fresh_quote
    q=fresh_quote(quote,now,choice['isin']) if choice else None
    checks=[]
    def add(key,label,value,required=True):
        checks.append(dict(key=key,label=label,required=required,
            state='pass' if value is True else 'fail' if value is False else 'unknown'))
    add('fresh','Goldkurs und ursprüngliche Quellenzeit',market.get('priceFresh') is True and number(at) and 0<=now-at<=60000)
    add('analysis','Marktanalyse bereit',market.get('ready') is True)
    add('plan','Bestätigte Richtung mit gültigem Stopp/Ziel',direction in ('LONG','SHORT') and stop_target_audit.valid_plan(plan) and plan['direction']==direction)
    add('session','Einstiegszeit', (market.get('session') or {}).get('entryAllowed'))
    trend=(market.get('trendContext') or {})
    add('trend','Haupttrend passt zur Richtung',trend.get('direction')==direction and trend.get('intact') is True if trend.get('available') else None,policy.get('require_trend') is True)
    add('timing','Separate Einstiegsbestätigung',(market.get('entryTimingGate') or {}).get('allowed'),False)
    add('product','Ausgewähltes belegtes Produkt',bool(choice) and not choice.get('indicative') and not choice.get('estimated'))
    add('quote','Gültiges Geld/Brief-Paar für die Simulation',bool(q))
    if choice and choice.get('koGuardRequired'):
        import paper_ko_guard
        ko_reason,_=paper_ko_guard.entry_reason(choice,quote,market,now)
        add('ko','Bestehender KO-Schutz',ko_reason is None)
    day_loss=control.get('dayProfit');opening=control.get('dayOpeningEquity')
    add('dailyRisk','Bestehende Tagesverlustgrenze',day_loss>-(policy.get('daily_loss_fraction',.03)*opening) if number(day_loss) and number(opening) and opening>0 else None,False)
    return dict(version=VERSION,capturedAt=now,sourceAt=at,decision='entry' if entered else 'wait',
        reason=str(reason)[:500],direction=direction,isin=choice.get('isin') if choice else None,
        plan={k:plan.get(k) for k in ('entry','stop','target','unit')} if isinstance(plan,dict) else None,
        riskUsd=abs(plan['entry']-plan['stop']) if stop_target_audit.valid_plan(plan) else None,
        riskPct=abs(plan['entry']-plan['stop'])/plan['entry']*100 if stop_target_audit.valid_plan(plan) else None,
        ruleVersion=market.get('ruleVersion'),checks=checks,requiredFailures=[c['key'] for c in checks if c['required'] and c['state']=='fail'],
        unknownChecks=[c['key'] for c in checks if c['state']=='unknown'],
        context=decision_evidence.capture(market),affectsApproval=False)

def daily(cases,stats,day):
    rows=[c for c in cases if not c.get('demonstration')]
    checked=[c for c in rows if (c.get('entryChecklist') or {}).get('version')==VERSION]
    violations=[c for c in checked if c['entryChecklist']['requiredFailures']]
    unknown=[c for c in checked if c['entryChecklist']['unknownChecks']]
    settled=[c for c in rows if c.get('status')!='open' and not c.get('pendingUnits')]
    priced=[v for c in settled if (v:=paper_costs.evaluate(c,c.get('ledgerCostModel') or paper_costs.SCENARIOS[0])) is not None]
    return dict(version=VERSION,day=day,entries=len(rows),checkedEntries=len(checked),
        legacyEntries=len(rows)-len(checked),ruleConsistent=sum(all(x['state']=='pass' for x in c['entryChecklist']['checks'] if x['required']) for c in checked),
        entriesWithUnknownChecks=len(unknown),requiredViolations=len(violations),
        reviewCandidates=[dict(at=c.get('startedAt'),failures=[x['label'] for x in c['entryChecklist']['checks'] if x['required'] and x['state']=='fail']) for c in violations[:20]],
        closed=len(settled),pricedClosed=len(priced),unpricedClosed=len(settled)-len(priced),
        modelNetEur=sum(v['modelNetEur'] for v in priced) if priced else None,
        waitChecks=stats.get('waitChecks',0),lastChecklist=copy.deepcopy(stats.get('lastEntryChecklist')),
        entryChecks=copy.deepcopy(stats.get('entryCheckCounts',{})),
        note='Auswertung der gespeicherten Tagesfälle (maximal 100), keine rückwirkenden Checklisten. '
             'Regelgerecht bedeutet nach den erfassten Pflichtprüfungen; unbekannte Angaben separat. '
             'Ein Verlust allein ist kein vermeidbarer Fehler. Dieser Tagesbericht allein belegt keinen Optimierungsvorteil; keine automatische Regeländerung.')
