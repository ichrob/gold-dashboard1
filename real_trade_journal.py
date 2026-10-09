"""Append-only real trade observations. Never executes orders or infers fills."""
import json,time,hashlib,math
import background_push

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_real_trades (
      id TEXT PRIMARY KEY, opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), active BOOLEAN NOT NULL,
      snapshot JSONB NOT NULL, settings JSONB NOT NULL, state JSONB NOT NULL DEFAULT '{}')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_real_trade_events (
      seq BIGSERIAL PRIMARY KEY, trade_id TEXT NOT NULL REFERENCES bob_real_trades(id),
      recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(), kind TEXT NOT NULL,
      dedup TEXT UNIQUE NOT NULL, payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_real_trade_events_trade ON bob_real_trade_events(trade_id,seq)')

def event(conn,trade_id,kind,payload,key=None):
    if not trade_id:return
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False)
    dedup=hashlib.sha256((trade_id+'|'+kind+'|'+(key or raw)).encode()).hexdigest()
    conn.execute('''INSERT INTO bob_real_trade_events(trade_id,kind,dedup,payload)
      SELECT id,%s,%s,%s::jsonb FROM bob_real_trades WHERE id=%s ON CONFLICT(dedup) DO NOTHING''',
      (kind,dedup,raw,trade_id))

def handle(conn,action,payload):
    if action=='write':
        t=payload.get('trade') or {}
        if t.get('test'):raise ValueError('Probelauf ist kein echter Trade')
        tid=t.get('tradeId')
        if not isinstance(tid,str) or not 1<=len(tid)<=100:raise ValueError('Trade-ID fehlt')
        active=t.get('active') is True
        execution=t.get('actualExecution')
        if execution is not None:
            if not isinstance(execution,dict) or active:raise ValueError('Ausführung erst nach Beendigung erfassen')
            for k in ('entryEUR','exitEUR','quantity','feesEUR'):
                v=execution.get(k)
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or (v<0 if k=='feesEUR' else v<=0):raise ValueError('Ungültige Ausführungswerte')
            execution={k:execution[k] for k in ('entryEUR','exitEUR','quantity','feesEUR')}
            execution['netEUR']=(execution['exitEUR']-execution['entryEUR'])*execution['quantity']-execution['feesEUR']
            execution['source']='Vom Nutzer erfasst, nicht mit DEGIRO abgeglichen'
            t={**t,'actualExecution':execution}
        snapshot={k:t.get(k) for k in ('tradeId','active','dir','entry','stop','target','initialRisk','product','monitorStartedAt','closedAt','closeGoldReference','actualExecution')}
        settings=background_push.config({'timeframe':payload.get('timeframe','15m'),'trade':{**snapshot,'active':True,'instrument':'XAU/USD'}})
        previous=conn.execute('SELECT active,snapshot FROM bob_real_trades WHERE id=%s FOR UPDATE',(tid,)).fetchone()
        if previous and previous[1].get('actualExecution') and not snapshot.get('actualExecution'):snapshot['actualExecution']=previous[1]['actualExecution']
        if previous and not previous[0] and active:raise ValueError('Geschlossener Trade darf nicht erneut geöffnet werden')
        conn.execute('''INSERT INTO bob_real_trades(id,active,snapshot,settings) VALUES(%s,%s,%s::jsonb,%s::jsonb)
          ON CONFLICT(id) DO UPDATE SET active=excluded.active,snapshot=excluded.snapshot,settings=excluded.settings,updated_at=now()''',
          (tid,active,json.dumps(snapshot),json.dumps(settings)))
        event(conn,tid,'trade-opened' if not previous else 'trade-closed-in-bob' if previous[0] and not active else 'trade-updated',snapshot)
        if isinstance(payload.get('event'),dict):event(conn,tid,'browser-event',payload['event'])
        return {'ok':True,'tradeId':tid}
    if action=='read':
        tid=payload.get('tradeId');before=payload.get('before')
        trades=conn.execute('SELECT id,opened_at,updated_at,active,snapshot FROM bob_real_trades ORDER BY opened_at DESC LIMIT 100').fetchall()
        result={'trades':[dict(id=i,openedAt=o.isoformat(),updatedAt=u.isoformat(),active=a,snapshot=s) for i,o,u,a,s in trades]}
        if tid:
            rows=conn.execute('''SELECT seq,recorded_at,kind,payload FROM bob_real_trade_events
              WHERE trade_id=%s AND (%s::bigint IS NULL OR seq<%s::bigint) ORDER BY seq DESC LIMIT 501''',(tid,before,before)).fetchall()
            result['more']=len(rows)>500;rows=rows[:500]
            result['events']=[dict(seq=s,at=a.isoformat(),kind=k,payload=p) for s,a,k,p in rows]
            result['nextBefore']=rows[-1][0] if rows else None
        return result
    raise ValueError('Unbekannte Journalaktion')

def observe(conn,bundle):
    # Runs independently of notification permission, including with the app closed.
    for tid,settings,state in conn.execute('SELECT id,settings,state FROM bob_real_trades WHERE active=TRUE FOR UPDATE').fetchall():
        now=int(time.time()*1000)
        if now-state.get('journalCheckedAt',0)<25000:continue
        try:
            market=background_push.analyze(bundle,settings)
            next_state,events=background_push.advance(state,settings,market,False,True)
            evidence={k:market.get(k) for k in ('direction','ready','priceFresh','price','dataAt','analysisBarAt','decisionReason','score','context','trendContext','plan','suggestedStop','suggestedTarget','ruleVersion')}
            evidence['planAfter']=next_state.get('trade');evidence['recommendations']=events
            evidence['delivery']='Nur protokolliert; tatsächlicher Push-Versand wird separat erfasst'
            event(conn,tid,'observation',evidence,str(now))
            next_state['journalCheckedAt']=now
            conn.execute('UPDATE bob_real_trades SET state=%s::jsonb,updated_at=now() WHERE id=%s',(json.dumps(next_state),tid))
        except Exception as exc:
            event(conn,tid,'observation-error',{'error':type(exc).__name__,'at':now},str(now))
