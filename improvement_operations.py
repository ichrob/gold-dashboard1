"""Private daily evidence, repair episodes and review-only release dossiers."""
import json
import math
import os
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

ZONE=ZoneInfo('Europe/Zurich')


def finite(v):return type(v) in (int,float) and math.isfinite(v)
def nonnegative(v):return finite(v) and v>=0


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_improvement_daily
        (campaign TEXT NOT NULL,day TEXT NOT NULL,at BIGINT NOT NULL,payload JSONB NOT NULL,
         PRIMARY KEY(campaign,day))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_improvement_release_dossiers
        (campaign TEXT NOT NULL,day TEXT NOT NULL,at BIGINT NOT NULL,payload JSONB NOT NULL,
         PRIMARY KEY(campaign,day))''')


def cost_review(snapshots,start):
    import trade_learning_review as learning
    import trade_risk_review as risk
    items=[]
    for s in snapshots:
        if s.get('active') or s.get('test') or s.get('recordOnly'):continue
        bounds=learning.window(s)
        if bounds and bounds[0].timestamp()*1000<start:continue
        p=s.get('product') or {};e=s.get('actualExecution') or {};buy=s.get('purchase') or {}
        sale=s.get('exitReceipt') or {};settlement=s.get('settlement') or {};currency=p.get('currency','EUR')
        entry=e.get('entry'+currency,p.get('entry'));exit_price=e.get('exit'+currency,sale.get('price'))
        qty=e.get('quantity',p.get('quantity'));native_fee=e.get('fees'+currency)
        buy_fee=settlement.get('purchaseFeesCHF',buy.get('feesCHF'))
        sale_fee=settlement.get('saleFeesCHF',sale.get('feesCHF'))
        fee_chf=buy_fee+sale_fee if nonnegative(buy_fee) and nonnegative(sale_fee) else None
        evaluation=risk.evaluation(s)
        net=evaluation['realizedNetCHF']
        if net is None and currency=='CHF':net=evaluation['realizedNetProduct']
        net=net if finite(net) else None
        missing=[]
        if not bounds or bounds[2]:missing.append('Bestätigte Kauf-/Verkaufszeiten mit Zeitzone')
        if not finite(entry) or entry<=0:missing.append('Tatsächlicher Kaufkurs')
        if not finite(exit_price) or exit_price<=0:missing.append('Tatsächlicher Verkaufskurs')
        if not finite(qty) or qty<=0 or int(qty)!=qty:missing.append('Stückzahl')
        if currency not in ('EUR','CHF'):missing.append('Produktwährung')
        if fee_chf is None and not nonnegative(native_fee):missing.append('Tatsächliche Kauf- und Verkaufsgebühren')
        if net is None:missing.append('Vollständige CHF-Nettoabrechnung')
        items.append(dict(tradeId=s.get('tradeId'),currency=currency,entry=entry if finite(entry) else None,exit=exit_price if finite(exit_price) else None,
            feesCHF=fee_chf,feesNative=native_fee if nonnegative(native_fee) else None,
            netCHF=net,complete=not missing,missing=missing,
            source=sale.get('source') or settlement.get('source') or e.get('source') or 'Vom Nutzer erfasste Belege',
            brokerVerified=False))
    return dict(total=len(items),complete=sum(x['complete'] for x in items),
        missing=sum(not x['complete'] for x in items),items=items[-30:],truncated=len(items)>30,
        note='Tatsächliche, gespeicherte Belegwerte; Nutzerbestätigung ist kein unabhängiger Brokerabgleich. Keine Gebühren als null ergänzen. Unvollständige Belege sperren die Freigabeprüfung. Modellkurse und Kostenannahmen bleiben getrennt; Slippage ohne zeitgleichen Ordernachweis unbekannt.')


def repair_episodes(events):
    active={};episodes=[];duplicates=0;orphaned=0
    order={'detected':0,'repair-attempt':1,'repair-failed':2,'repair-verified':3,'recovered':4}
    for at,kind,code in sorted(events,key=lambda e:(e[0],order.get(e[1],5))):
        if kind=='detected':
            if code in active:duplicates+=1;continue
            item=dict(code=code,at=at,end=None,verified=False,attempts=0)
            active[code]=item;episodes.append(item)
        elif code in active:
            if kind=='repair-attempt':active[code]['attempts']+=1
            elif kind in ('repair-verified','recovered'):
                active[code]['end']=at;active[code]['verified']=kind=='repair-verified';del active[code]
        elif kind=='repair-verified':orphaned+=1
    verified=[x for x in episodes if x['verified']]
    durations=[(x['end']-x['at']).total_seconds() for x in verified if x['end']>=x['at']]
    types={x['code'] for x in episodes}
    return dict(episodes=len(episodes),types=len(types),verified=len(verified),open=len(active),
        recoveredWithoutVerifiedRepair=sum(x['end'] is not None and not x['verified'] for x in episodes),
        repeatedDetections=duplicates,recurrences=len(episodes)-len(types),orphanedVerifications=orphaned,
        verifiedPct=100*len(verified)/len(episodes) if episodes else None,
        meanRepairSeconds=sum(durations)/len(durations) if durations else None)


def repairs(conn,now):
    events=conn.execute('''SELECT event_at,kind,code FROM bob_self_heal_events
        WHERE event_at>=to_timestamp(%s/1000.0)-interval '30 days' AND event_at<=to_timestamp(%s/1000.0)
        ORDER BY event_at DESC,event_id DESC LIMIT 10001''',(now,now)).fetchall()
    result=repair_episodes(list(reversed(events[:10000])))
    import training_handoff
    groups=training_handoff.problem_groups(conn)
    recurring=conn.execute('''SELECT count(*) FILTER (WHERE episode>1),COALESCE(sum(greatest(episode-1,0)),0)
        FROM bob_training_problem_groups''').fetchone()
    counts=dict(conn.execute('SELECT status,count(*) FROM bob_test_repairs GROUP BY status').fetchall())
    result.update(status='ok',truncated=len(events)>10000,testProblemTypes=len(groups),
        testCases=sum(g['cases'] for g in groups),recoveredTestCases=counts.get('recovered',0),
        recurringTestTypes=recurring[0],testRecurrences=int(recurring[1]),
        note='Betriebsfehler: letzte 30 Tage, maximal 10.000 Ereignisse, nach Fehlercode und Episode zusammengefasst. Wiederholte Meldungen derselben offenen Episode zählen nicht erneut. Verifiziert bedeutet protokollierter Reparaturnachweis, keine Garantie dauerhaft beseitigter Ursachen. Testfall-Reparaturen und Fehlerarten werden getrennt gezählt; behobene Testfälle bleiben höchstens 90 Tage gespeichert.')
    return result


def daily(conn,campaign,now,start,trial_rows):
    today=datetime.fromtimestamp(now/1000,ZONE).date();first=max(datetime.fromtimestamp(start/1000,ZONE).date(),today-timedelta(days=6))
    stats={day:(observed,valid,last,source) for day,observed,valid,last,source in conn.execute('''
        SELECT day,count(*),count(*) FILTER (WHERE valid),max(slot),
        max((payload->>'priceAt')::double precision) FILTER (WHERE valid)
        FROM bob_improvement_observations WHERE campaign=%s AND day>=%s AND slot<%s GROUP BY day''',
        (campaign,first.isoformat(),now//30000*30000)).fetchall()}
    result=[];day=first
    while day<=today:
        if day.weekday()<5:
            a=int(datetime(day.year,day.month,day.day,8,tzinfo=ZONE).timestamp()*1000)
            b=int(datetime(day.year,day.month,day.day,22,tzinfo=ZONE).timestamp()*1000)
            expected=max(0,(min(now//30000*30000,b)-a)//30000)
            observed,valid,last,source=stats.get(day.isoformat(),(0,0,None,None))
            cases=[r for r in trial_rows if r[0]==day.isoformat()]
            completed=[r for r in cases if r[3]]
            missing=sum(bool(p.get('valid') and p.get('ready') and finite(p.get('adx')) and p.get('at',now)+3780000<now and not o) for d,phase,p,o in cases)
            result.append(dict(day=day.isoformat(),closed=now>=b,expected=expected,observed=observed,valid=valid,
                coveragePct=round(min(100,100*valid/expected),2) if expected else None,
                missingSlots=max(0,expected-observed),invalidSlots=observed-valid,lastSlot=last,lastValidSourceAt=source,
                trials=len(cases),completed=len(completed),missingOutcomes=missing,
                positive=sum(o['scenarios'][0]['baseline']>0 for d,phase,p,o in completed),
                negative=sum(o['scenarios'][0]['baseline']<0 for d,phase,p,o in completed),
                note='Signal-Fälle nach angenommenen Standardkosten, keine echten Trade-Gewinne. Verschiedene Regelstände werden hier nur gezählt, nicht als gemeinsamer Vorteil bewertet.'))
        day+=timedelta(days=1)
    return result


def release_dossier(report,costs):
    a=report['assessment'];r=report['real'];coverage=report['reliability'].get('coveragePct')
    regimes=a.get('regimes',[])
    regime_ok=all(any(x['key']==key and x['cases']>=30 and x['days']>=5 and
        x.get('difference') is not None and x['difference']>=0 and x.get('stressDifference') is not None and x['stressDifference']>=0
        for x in regimes) for key in ('rising','falling','sideways'))
    checks=[dict(key='data',label='Datenabdeckung mindestens 95 %',met=finite(coverage) and coverage>=95),
        dict(key='independent',label='Unabhängiger Vergleich vollständig und Vorteil unter beiden Kostenannahmen',met=report['progress'][2]==100 and a['code']=='benefit'),
        dict(key='real',label='Mindestens 20 zugeordnete Nettovergleiche an 10 Tagen mit positivem Unterschied',met=r['pairedCount']>=20 and r['pairedDays']>=10 and finite(a.get('netDifferenceCHF')) and a['netDifferenceCHF']>0),
        dict(key='costs',label='Kosten- und Ausführungsbelege vollständig',met=costs['complete']>=20 and costs['missing']==0),
        dict(key='regimes',label='Kein beobachteter Nachteil in drei ausreichend belegten Marktphasen',met=regime_ok)]
    return dict(status='Fachliche Freigabeprüfung möglich' if all(c['met'] for c in checks) else 'Nachweise noch unvollständig',checks=checks,
        evidenceReady=all(c['met'] for c in checks),approvalRequired=True,approved=False,automaticRuleChange=False,
        baselineBuild=os.environ.get('RENDER_GIT_COMMIT','local-unverified'),baselineCohort=report['comparison']['cohort'],
        candidate=report['protocol']['candidate'],rollbackStatus='Verfahren vorbereitet; kein Regelwechsel ausgeführt',
        rollbackSteps=['Vor jeder Freigabe tatsächlich aktive Regelversion, Parameter und Build als unveränderlichen Ausgangsstand sichern.',
          'Änderung nur in eigener geprüfter Version nach gesonderter Freigabe übernehmen; offene Trades und ihre Risiko-/Stoppregeln unverändert lassen.',
          'Bei fehlender Aktualität, Regelkonflikten oder bestätigtem Rückschritt neue Variante sperren; vorhandene Trade-Überwachung weiterführen.',
          'Gesicherten Ausgangsstand über geprüften Revert wiederherstellen; Tests, laufenden Build und Datenfluss kontrollieren. Bei Risiko-/Orderänderungen gesonderte Freigabe erforderlich.'],
        note='Dies ist ein prüfbares Freigabedossier, keine Handelsfreigabe und kein automatischer Umschalter. Tagesstände werden gespeichert; der angezeigte Build ist der Berichtsersteller, nicht pauschal eine garantierte sichere Rücksetzversion.')


def attach(conn,report,trial_rows,snapshots,now,start):
    costs=cost_review(snapshots,start)
    report['dailyReview']=daily(conn,report['protocol']['version'],now,start,trial_rows)
    report['costEvidence']=costs
    report['releaseDossier']=release_dossier(report,costs)
    try:
        with conn.transaction():report['repairQuality']=repairs(conn,now)
    except Exception:
        report['repairQuality']=dict(status='unavailable',note='Reparaturbilanz derzeit nicht abrufbar; keine Erfolgsquote bestätigt.')


def archive(conn,report,now):
    campaign=report['protocol']['version']
    for row in report['dailyReview']:
        conn.execute('''INSERT INTO bob_improvement_daily VALUES(%s,%s,%s,%s::jsonb)
            ON CONFLICT(campaign,day) DO UPDATE SET at=excluded.at,payload=excluded.payload''',
            (campaign,row['day'],now,json.dumps(row)))
    day=datetime.fromtimestamp(now/1000,ZONE).date().isoformat()
    conn.execute('''INSERT INTO bob_improvement_release_dossiers VALUES(%s,%s,%s,%s::jsonb)
        ON CONFLICT(campaign,day) DO UPDATE SET at=excluded.at,payload=excluded.payload''',
        (campaign,day,now,json.dumps(report['releaseDossier'])))
    latest=next((r for r in report['dailyReview'] if r['day']==day),None)
    return dict(version=campaign,at=now,persisted=True,day=day,
        **{k:latest[k] if latest else None for k in ('observed','valid','expected','lastSlot','lastValidSourceAt','coveragePct')})
