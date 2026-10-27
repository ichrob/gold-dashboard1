"""Prospective alternatives using Bob's actual paper exit engine, never orders."""
import copy
import json
import time

VERSION='ranking-exits-v1'
CAPITAL=100.
NOTE=('Virtueller Ausstiegsvergleich mit Bobs gemeinsamer Simulationslogik: Teilgewinn, '
      'Stoppnachzug, Zielverlängerung, Richtungswechsel, KO-Schutz und maximal vier Stunden '
      'bis spätestens 21:45 Zürich. Je Produkt 100 EUR einschließlich ungenutztem Restgeld; '
      'CHF nur mit bestätigter Umrechnung. Keine echten Verkäufe oder Nettogewinne. '
      'Diese Auswertung verändert noch keine Lernregel.')


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_ranking_lifecycles (
      currency TEXT NOT NULL,slot BIGINT NOT NULL,payload JSONB NOT NULL,
      state JSONB NOT NULL,result JSONB NOT NULL,complete BOOLEAN NOT NULL DEFAULT FALSE,
      checked_at BIGINT NOT NULL,PRIMARY KEY(currency,slot))''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_ranking_lifecycle_pending ON bob_ranking_lifecycles(checked_at) WHERE complete=FALSE')


def active_isins(conn):
    return sorted({c['product']['isin'] for (state,) in conn.execute(
        'SELECT state FROM bob_ranking_lifecycles WHERE complete=FALSE').fetchall()
        for c in [*state['cases'].values(),*state.get('fixedCases',{}).values()] if c['status']=='open'})


def capture(conn,row,market,choices,quotes,now):
    import paper_simulation as sim
    import paper_ko_guard
    cases={};missing=list(row['missing'])
    for candidate in row['candidates']:
        isin=candidate['isin'];choice=next((c for c in choices if c['isin']==isin),None)
        quote=quotes.get(isin);q=sim.fresh_quote(quote,now,isin)
        error,guard=paper_ko_guard.entry_reason(choice or {},quote,market,now)
        if not choice or not q or not guard or error:
            missing.append(isin);continue
        try:c=sim.new_case(market,dict(choice,koGuardRequired=True),quote,now,cash=CAPITAL)
        except ValueError:missing.append(isin);continue
        if not c['productReturnKnown'] or c['endsAt']<=now:missing.append(isin);continue
        c['comparisonLastQuoteAt']=min(sim.stamp(q.get(k) or q.get('quoteAt')) for k in ('bidAt','askAt'))
        cases[isin]=c
    fixed=copy.deepcopy(cases)
    for c in fixed.values():c['comparisonFixedPlan']=True
    state=dict(version=VERSION,cases=cases,fixedCases=fixed,missing=missing)
    result=summarize(row,state)
    conn.execute('''INSERT INTO bob_ranking_lifecycles VALUES(%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)
        ON CONFLICT DO NOTHING''',(row['currency'],row['slot'],json.dumps(row),json.dumps(state),json.dumps(result),not cases,now))


def advance_state(state,market,quotes,now):
    import paper_simulation as sim
    out=copy.deepcopy(state)
    for isin,c in out['cases'].items():
        if c['status']!='open':continue
        quote=quotes.get(isin);q=sim.fresh_quote(quote,now,isin)
        reason=None
        if not q or q['bid']<=0 or q['ask']<=0:reason='Passender frischer Produktkurs fehlt'
        elif q['source']!=c['entryQuote']['source'] or q['currency']!=c['entryQuote']['currency']:
            reason='Produktkursquelle oder Währung gewechselt'
        else:
            at=min(sim.stamp(q.get(k) or q.get('quoteAt')) for k in ('bidAt','askAt'))
            if at<c['comparisonLastQuoteAt'] or at-c['comparisonLastQuoteAt']>90000:
                reason='Produktkurslücke oder rückläufige Quellenzeit'
            elif not sim.finite(market.get('dataAt')) or abs(at-market['dataAt'])>30000:
                reason='Gold- und Produktkurs nicht zeitlich passend'
            else:c['comparisonLastQuoteAt']=at
        if reason:
            c.update(status='inconclusive',closedAt=now,productReturnKnown=False,productGrossPct=None)
            c['events'].append(dict(kind='comparison-unavailable',recordedAt=now,reason=reason));continue
        observed=(c['cashReleased']+c['remainingUnits']*q['bid']-c['allocated'])/CAPITAL*100
        c['observedPeakPct']=max(c.get('observedPeakPct',observed),observed)
        c=sim.advance_case(c,market,quote,now)
        # A source/KO/gap failure is final for the comparison, even if a price
        # arrives later. Never replace an uncertain exit by a favorable quote.
        if c.get('pendingUnits') or c.get('koWatchStatus')=='unverified':
            c.update(status='inconclusive',closedAt=now,productReturnKnown=False,productGrossPct=None)
        out['cases'][isin]=c
    if 'fixedCases' in out:
        fixed=advance_state(dict(cases=out['fixedCases'],missing=out['missing']),market,quotes,now)
        out['fixedCases']=fixed['cases']
    return out


def summarize(row,state):
    returns={};missing=list(state['missing']);pending=[];details={}
    for isin,c in state['cases'].items():
        details[isin]=dict(status=c['status'],exitReason=c.get('exitReason'),closedAt=c.get('closedAt'),
            quantity=c.get('quantity'),entryAsk=c.get('entryAsk'),allocated=c.get('allocated'),
            finalStop=c['engine']['trade']['stop'],finalTarget=c['engine']['trade']['target'],
            events=c['events'],paperOnly=c['product'].get('paperOnly') is True)
        if c['status']=='open':pending.append(isin)
        elif c['status']=='closed' and c['productReturnKnown'] and not c.get('pendingUnits'):
            returns[isin]=dict(grossPct=(c['cashReleased']-c['allocated'])/CAPITAL*100,
                peakPct=c.get('observedPeakPct'),profitEur=c['cashReleased']-c['allocated'],exitReason=c.get('exitReason'),exitAt=c['closedAt'])
        else:missing.append(isin)
    valid=bool(len(row['candidates'])>=2 and not missing and not pending and len(returns)==len(row['candidates']))
    result=dict(version=VERSION,complete=valid,pending=pending,missing=missing,returns=returns,
        details=details,capitalEur=CAPITAL,actualExecution=False,status='pending' if pending else 'complete' if valid else 'incomplete')
    if valid:
        best=max(v['grossPct'] for v in returns.values());chosen=row['chosen']
        alternative=max((i for i in returns if i!=chosen),key=lambda i:(returns[i]['grossPct'],i))
        result.update(bestIsins=sorted(i for i,v in returns.items() if abs(v['grossPct']-best)<1e-9),
            chosenIsin=chosen,chosenPct=returns[chosen]['grossPct'],bestPct=best,alternativeIsin=alternative,
            alternativeAdvantagePct=returns[alternative]['grossPct']-returns[chosen]['grossPct'])
    if 'fixedCases' in state:
        fixed=summarize(row,dict(cases=state['fixedCases'],missing=state['missing']))
        result['stopComparison']=dict(complete=valid and fixed['complete'],
            fixedReturns=fixed['returns'],bobReturns=returns,
            pending=fixed['pending'],missing=fixed['missing'])
    return result


def tick(conn,market,quotes,now):
    rows=conn.execute('''SELECT currency,slot,payload,state FROM bob_ranking_lifecycles
        WHERE complete=FALSE ORDER BY checked_at LIMIT 8 FOR UPDATE SKIP LOCKED''').fetchall()
    for currency,slot,row,state in rows:
        state=advance_state(state,market,quotes,now);result=summarize(row,state)
        conn.execute('''UPDATE bob_ranking_lifecycles SET state=%s::jsonb,result=%s::jsonb,complete=%s,checked_at=%s
            WHERE currency=%s AND slot=%s''',(json.dumps(state),json.dumps(result),not result['pending'] and not result.get('stopComparison',{}).get('pending'),now,currency,slot))
    # Preserve study cases and outcomes for reproducible historical evaluation.


def report(conn):
    rows=conn.execute('SELECT currency,slot,result FROM bob_ranking_lifecycles ORDER BY slot DESC,currency LIMIT 100').fetchall()
    comparisons=[]
    for index,(currency,slot,result) in enumerate(rows):
        result=copy.deepcopy(result)
        result['detailsOmitted']=index>=20
        if index>=20:result['details']={}
        else:
            for detail in result['details'].values():
                detail['eventCount']=len(detail['events']);detail['eventsTruncated']=len(detail['events'])>20
                detail['events']=detail['events'][-20:]
        comparisons.append(dict(currency=currency,slot=slot,**result))
    return dict(version=VERSION,note=NOTE,limit=100,detailsLimit=20,eventLimit=20,comparisons=comparisons)
