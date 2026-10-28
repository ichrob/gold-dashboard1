"""Independent forward paper study. No orders; costs are explicit assumptions."""
import copy
import json
import math
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import evaluator_runtime
import paper_ko_guard

VERSION = 'risk-paper-2000-v1'
FEE = 5.0  # Assumed EUR per side, NOT a verified broker tariff.
DELAYS = (0, 30, 60)


def seed(now):
    return dict(version=VERSION, startedAt=now, checkedAt=None, realOrders=False,
                costAssumptionPerSide=FEE, accounts={str(d): dict(delaySeconds=d,
                cash=2000., realized=0., closed=0, wins=0, incomplete=0,
                peak=2000., maxDrawdown=0., equity=2000., position=None,
                pending=None, lastSignal=None, recent=[]) for d in DELAYS})


def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS bob_risk_paper (id INTEGER PRIMARY KEY CHECK(id=1), payload JSONB NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS bob_risk_paper_cases (id TEXT PRIMARY KEY, payload JSONB NOT NULL)')
    conn.execute('INSERT INTO bob_risk_paper VALUES(1,%s::jsonb) ON CONFLICT DO NOTHING', (json.dumps(seed(time.time()*1000)),))


def active_isins(conn):
    row=conn.execute('SELECT payload FROM bob_risk_paper WHERE id=1').fetchone()
    return [a['position']['isin'] for a in (row[0]['accounts'].values() if row else []) if a.get('position')]


def quote_at(q, side):
    from paper_simulation import stamp
    return stamp(q.get(side+'At') or q.get('quoteAt'))


def usable(raw, isin, now, due):
    from paper_simulation import fresh_quote
    # Chart interpolation/FX model prices are not observed EUR transaction pairs.
    if not isinstance(raw,dict) or raw.get('paperFxConversion') or raw.get('priceKind') in ('calculated','issuer-chart'):
        return None
    q=fresh_quote(raw,now,isin)
    if not q or any(quote_at(q,k) is None or quote_at(q,k)<due for k in ('bid','ask')):
        return None
    return q


def advance(old, result, quotes, now, entry_allowed=True):
    state=copy.deepcopy(old); state['checkedAt']=now
    signal=result.get('signal') or {}
    ready=(signal.get('ready') is True and isinstance(signal.get('at'),(int,float))
           and 0<=now-signal['at']<=60000)
    state['signal']=signal
    market=dict(price=signal.get('spot'),priceFresh=ready,dataAt=signal.get('at'),
                direction=signal.get('direction'),atr=signal.get('atr'),
                plan={'unit':'USD/oz','direction':signal.get('direction')})
    closed=[]
    for key,a in state['accounts'].items():
        delay=a['delaySeconds']*1000; p=a.get('position')
        a['reason']='Warte auf bestätigtes Risiko-Signal'
        if ready and a.get('lastDataAt') and signal['at']<a['lastDataAt']:
            a['reason']='Rückläufige Kurszeit: keine Auswertung';a['equity']=None
            if p:p['dataGap']=True
            continue
        if p:
            raw=quotes.get(p['isin']) or {}; q=usable(raw,p['isin'],now,p['entryAt'])
            if not ready or (a.get('lastDataAt') and signal['at']-a['lastDataAt']>90000):
                p['dataGap']=True
            watch=(result.get('watches') or {}).get(key) or p.get('watch',{})
            p['watch']=watch
            guard,blocked=paper_ko_guard.assess(p,raw,market,now)
            terminal=paper_ko_guard.terminal(raw,p['isin'])
            if terminal or (guard and guard['crossed']):
                p['settlementUnknown']=True
            local=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'))
            action=watch.get('action')
            if not p.get('exitDue') and (action in ('AUSSTIEG PRÜFEN','ZEITGRENZE PRÜFEN','GEGENBEWEGUNG') or (guard and guard['danger']) or (local.hour,local.minute)>=(21,45) or now-p['entryAt']>=4*3600000):
                p.update(exitDue=now+delay,exitSignalAt=now,exitReason=action or 'Sitzungs-/Zeitgrenze')
            if p.get('settlementUnknown'):
                a['reason']='KO/Produktende beobachtet: Abrechnung ungeklärt; kein Verkauf erfunden'
                a['equity']=None
            elif p.get('exitDue') and now>=p['exitDue']:
                exitq=usable(raw,p['isin'],now,p['exitDue'])
                if exitq and not blocked and guard and not guard['crossed']:
                    proceeds=p['units']*exitq['bid']-FEE
                    pnl=proceeds-p['debit']
                    case={**p,'exitAt':now,'exitQuote':exitq,'modelNet':pnl,'gross':p['units']*(exitq['bid']-p['entryQuote']['ask']),
                          'costsAssumed':2*FEE,'brokerExecutionVerified':False}
                    a['cash']+=proceeds;a['realized']+=pnl;a['closed']+=1
                    a['wins']+=int(pnl>0);a['incomplete']+=int(bool(p.get('dataGap')))
                    a['recent']=[case,*a['recent']][:20];closed.append(case)
                    a['position']=None;a['reason']='Simulierter Verkauf zum beobachteten Geldkurs'
                else:
                    a['reason']='Ausstieg fällig; passender neuer Geldkurs/KO-Nachweis fehlt'
                    a['equity']=None
            if a.get('position') and not p.get('settlementUnknown'):
                a['equity']=a['cash']+p['units']*q['bid']-FEE if q else None
            elif not a.get('position'):a['equity']=a['cash']
        else:
            a['equity']=a['cash']
            confirmed=ready and signal.get('stage')=='BESTÄTIGT' and signal.get('direction') in ('LONG','SHORT')
            episode=signal.get('direction') if confirmed else None
            if not confirmed or not entry_allowed:
                a['pending']=None
                if ready:a['lastSignal']=None
            elif a.get('lastSignal')!=episode and not a.get('pending'):
                choices=result.get('choices') or []
                if choices:
                    # Freeze product choice at signal observation; never pick a later winner.
                    a['pending']=dict(choice=choices[0],due=now+delay,signalAt=now,signal=signal)
                    a['lastSignal']=episode
                else:a['reason']='Keine geeigneten Top-2-Produkte mit Nachweisen'
            pending=a.get('pending')
            if pending:
                a['reason']='Virtueller Einstieg wartet auf Reaktionszeit und neuen Briefkurs'
                choice=pending['choice'];raw=quotes.get(choice['isin']) or {}
                if now-pending['due']>90000:
                    a['pending']=None;a['reason']='Einstieg verfallen: keine rechtzeitigen Kursnachweise'
                elif now>=pending['due']:
                    q=usable(raw,choice['isin'],now,pending['due'])
                    blocker,_=paper_ko_guard.entry_reason(choice,raw,market,now)
                    still_selected=any(c['isin']==choice['isin'] for c in result.get('choices',[]))
                    if q and not blocker and still_selected:
                        units=math.floor((min(1000.,a['cash'])-FEE)/q['ask'])
                        if units>0:
                            debit=units*q['ask']+FEE; sign=1 if choice['direction']=='LONG' else -1
                            p=dict(**choice,id=f"risk-{key}-{int(now)}",entryAt=now,entryQuote=q,
                                   signal=pending['signal'],signalAt=pending['signalAt'],delaySeconds=a['delaySeconds'],
                                   units=units,debit=debit,goldEntry=signal['spot'],goldStop=signal['spot']-sign*1.5*signal['atr'],watch={})
                            a['position']=p;a['cash']-=debit;a['pending']=None
                            a['equity']=a['cash']+units*q['bid']-FEE;a['reason']='Virtuelle Position offen'
                    elif blocker:a['reason']=blocker
        if ready:a['lastDataAt']=signal['at']
        if a.get('equity') is not None:
            a['peak']=max(a['peak'],a['equity']);a['maxDrawdown']=max(a['maxDrawdown'],a['peak']-a['equity'])
        a['reviewReady']=a['closed']-a['incomplete']>=100
    return state,closed


def tick(conn,bundle,evidence,quotes,now):
    import background_push
    row=conn.execute('SELECT payload FROM bob_risk_paper WHERE id=1 FOR UPDATE').fetchone()
    if not row:return
    state=row[0]
    request={**evidence,'bundle':bundle,'quotes':quotes,'riskOnly':True,
             'market':{},'positions':{k:a['position'] for k,a in state['accounts'].items() if a.get('position')}}
    p=evaluator_runtime.run(['node',str(Path(__file__).with_name('paper_selection.js'))],
        input=json.dumps(request),text=True,capture_output=True,check=True,timeout=8,priority=2)
    state,cases=advance(state,json.loads(p.stdout),quotes,time.time()*1000,background_push.degiro_entry_allowed())
    for c in cases:
        conn.execute('INSERT INTO bob_risk_paper_cases VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',(c['id'],json.dumps(c)))
    conn.execute('UPDATE bob_risk_paper SET payload=%s::jsonb WHERE id=1',(json.dumps(state),))


def report(conn):
    row=conn.execute('SELECT payload FROM bob_risk_paper WHERE id=1').fetchone()
    return row[0] if row else {'status':'not-started','realOrders':False}
