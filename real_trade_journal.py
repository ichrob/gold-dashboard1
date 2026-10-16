"""Append-only real trade observations. Never executes orders or infers fills."""
import json,time,hashlib,math,re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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

def record_purchase(conn,t):
    """Persist a confirmed purchase independently of the monitoring model."""
    if t.get('active') or t.get('test'):raise ValueError('Kauferfassung aktiviert keine Überwachung')
    p=t.get('product') or {};e=t.get('purchase') or {}
    currency=p.get('currency','EUR')
    if currency not in ('EUR','CHF'):raise ValueError('Produktwährung muss EUR oder CHF sein')
    isin=str(p.get('isin','')).upper()
    if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]',isin):raise ValueError('ISIN fehlt')
    if t.get('dir') not in ('LONG','SHORT'):raise ValueError('Richtung fehlt')
    for k in ('entry','quantity'):
        v=p.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:raise ValueError('Kaufkurs und Stückzahl fehlen')
    if not float(p['quantity']).is_integer():raise ValueError('Ganzzahlige Stückzahl erforderlich')
    tx=str(e.get('transactionId',''))
    if not re.fullmatch(r'[A-Za-z0-9-]{1,80}',tx):raise ValueError('Transaktions-ID fehlt')
    at=datetime.fromisoformat(str(e.get('at','')).replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('Kaufzeit benötigt Zeitzone')
    for k in ('feesCHF','totalCHF'):
        v=e.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:raise ValueError('CHF-Beträge fehlen')
    tid='degiro-purchase-'+tx
    snapshot={'tradeId':tid,'active':False,'recordOnly':True,'dir':t['dir'],
      'product':{'isin':isin,'currency':currency,'entry':p['entry'],'quantity':p['quantity']},
      'purchase':{'transactionId':tx,'at':at.isoformat(),'feesCHF':e['feesCHF'],'totalCHF':e['totalCHF'],
      'source':'Vom Nutzer bestätigte DEGIRO-Ausführung'},'monitoringStatus':'pending-evidence'}
    previous=conn.execute('SELECT active,snapshot FROM bob_real_trades WHERE id=%s FOR UPDATE',(tid,)).fetchone()
    if previous:
        if previous[1]!=snapshot:raise ValueError('Transaktion bereits gespeichert; abweichende Daten nicht überschrieben')
        return {'ok':True,'tradeId':tid,'recordOnly':True,'duplicate':True}
    inserted=conn.execute("""INSERT INTO bob_real_trades(id,active,snapshot,settings)
      VALUES(%s,FALSE,%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING RETURNING id""",
      (tid,json.dumps(snapshot),json.dumps({'timeframe':'15m','trade':None}))).fetchone()
    if not inserted:raise ValueError('Transaktion wurde gleichzeitig gespeichert; bitte neu laden')
    event(conn,tid,'purchase-recorded',snapshot)
    return {'ok':True,'tradeId':tid,'recordOnly':True}


def validate_settlement(raw, execution):
    """Actual broker receipt values; observations remain separate and immutable."""
    if not isinstance(raw,dict) or not execution:raise ValueError('Abrechnung benötigt Ausführungswerte')
    out={}
    for k in ('purchaseTransactionId','saleTransactionId'):
        v=str(raw.get(k,''))
        if not re.fullmatch(r'[A-Za-z0-9-]{1,80}',v):raise ValueError('Transaktions-ID fehlt')
        out[k]=v
    for k in ('purchasedAt','soldAt'):
        dt=datetime.fromisoformat(str(raw.get(k,'')).replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError('Ausführungszeit benötigt Zeitzone')
        out[k]=dt.isoformat()
    if datetime.fromisoformat(out['soldAt'])<datetime.fromisoformat(out['purchasedAt']):raise ValueError('Verkauf vor Kauf')
    for k in ('purchaseTotalCHF','saleTotalCHF','purchaseFeesCHF','saleFeesCHF','purchaseFX','saleFX'):
        v=raw.get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or (k.endswith('FX') and v==0):raise ValueError('Ungültige CHF-Abrechnung')
        out[k]=v
    if raw.get('exitReason') not in ('stop-loss-user-confirmed','manual','other'):raise ValueError('Ausstiegsgrund fehlt')
    out['exitReason']=raw['exitReason']
    out['source']='DEGIRO-Bestätigungen, vom Nutzer zur Dokumentation freigegeben'
    out['netCHF']=round(out['saleTotalCHF']-out['purchaseTotalCHF'],2)
    out['holdingSeconds']=(datetime.fromisoformat(out['soldAt'])-datetime.fromisoformat(out['purchasedAt'])).total_seconds()
    out['feesEURMethod']='CHF-Kosten je Abrechnung mit deren EUR/CHF-Kurs umgerechnet'
    expected=out['purchaseFeesCHF']*out['purchaseFX']+out['saleFeesCHF']*out['saleFX']
    if abs(expected-execution['feesEUR'])>0.0001:raise ValueError('EUR-Kosten passen nicht zur CHF-Abrechnung')
    return out

def settled_purchase(purchase, closed):
    """DEGIRO execution IDs and order IDs differ; require exact receipt values."""
    receipt=closed.get('settlement') or {}
    buy=purchase.get('purchase') or {}
    if buy.get('transactionId')==receipt.get('purchaseTransactionId'):return True
    product=purchase.get('product') or {};sold=closed.get('product') or {}
    return bool(receipt) and all(product.get(k)==sold.get(k) for k in ('isin','entry','quantity')) and buy.get('at')==receipt.get('purchasedAt') and buy.get('feesCHF')==receipt.get('purchaseFeesCHF') and buy.get('totalCHF')==receipt.get('purchaseTotalCHF')

def handle(conn,action,payload):
    if action=='write' and payload.get('emailReceiptId'):
        from trade_workflow import import_purchase
        return import_purchase(conn,payload)
    if action=='write':
        t=payload.get('trade') or {}
        if t.get('recordOnly') is True:return record_purchase(conn,t)
        if t.get('test'):raise ValueError('Probelauf ist kein echter Trade')
        tid=t.get('tradeId')
        if not isinstance(tid,str) or not 1<=len(tid)<=100:raise ValueError('Trade-ID fehlt')
        active=t.get('active') is True
        execution=t.get('actualExecution')
        if execution is not None:
            if not isinstance(execution,dict) or active:raise ValueError('Ausführung erst nach Beendigung erfassen')
            currency=(t.get('product') or {}).get('currency','EUR')
            if currency not in ('EUR','CHF'):raise ValueError('Produktwährung fehlt')
            keys=('entry'+currency,'exit'+currency,'quantity','fees'+currency)
            for k in keys:
                v=execution.get(k)
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or (v<0 if k.startswith('fees') else v<=0):raise ValueError('Ungültige Ausführungswerte in Produktwährung')
            execution={k:execution[k] for k in keys}
            execution['net'+currency]=(execution['exit'+currency]-execution['entry'+currency])*execution['quantity']-execution['fees'+currency]
            execution['source']='Vom Nutzer erfasst, nicht mit DEGIRO abgeglichen'
            t={**t,'actualExecution':execution}
        snapshot={k:t.get(k) for k in ('tradeId','active','dir','entry','stop','target','initialRisk','product','monitorStartedAt','closedAt','closeGoldReference','actualExecution','purchase','settlement')}
        settings=background_push.config({'timeframe':payload.get('timeframe','15m'),'trade':{**snapshot,'active':True,'instrument':'XAU/USD'} if active else None})
        previous=conn.execute('SELECT active,snapshot FROM bob_real_trades WHERE id=%s FOR UPDATE',(tid,)).fetchone()
        if previous and previous[1].get('product') and (previous[1]['product'].get('currency','EUR')!=(snapshot.get('product') or {}).get('currency','EUR')):
            raise ValueError('Produktwährung eines gespeicherten Trades darf nicht geändert werden')
        if t.get('settlement') is not None:
            if active:raise ValueError('Abrechnung nur für geschlossenen Trade')
            if (snapshot.get('product') or {}).get('currency','EUR')!='EUR':raise ValueError('Für CHF-Produkte die native CHF-Ausführung erfassen')
            snapshot['settlement']=validate_settlement(t['settlement'],snapshot.get('actualExecution'))
        elif previous and previous[1].get('settlement'):
            snapshot['settlement']=previous[1]['settlement']
        if previous and previous[1].get('actualExecution') and not snapshot.get('actualExecution'):snapshot['actualExecution']=previous[1]['actualExecution']
        if previous and not previous[0] and active:
            old=previous[1]
            if not old.get('recordOnly'):raise ValueError('Geschlossener Trade darf nicht erneut geöffnet werden')
            closed=conn.execute("SELECT snapshot FROM bob_real_trades WHERE active=FALSE AND snapshot->'settlement' IS NOT NULL").fetchall()
            if any(settled_purchase(old,row[0]) for row in closed):
                raise ValueError('Dieser Kauf ist bereits durch einen bestätigten Verkauf abgeschlossen')
            if (old.get('product') or {}).get('currency','EUR')!=(t.get('product') or {}).get('currency','EUR') or old.get('dir')!=t.get('dir') or any((old.get('product') or {}).get(k)!=(t.get('product') or {}).get(k) for k in ('isin','entry','quantity')):
                raise ValueError('Überwachung passt nicht zum gespeicherten Kauf')
            snapshot['purchase']=old.get('purchase')
        if previous and previous[1].get('purchase'):snapshot['purchase']=previous[1]['purchase']
        if previous and previous[1].get('exitReceipt'):
            snapshot['exitReceipt']=previous[1]['exitReceipt']
            snapshot['closedAt']=previous[1].get('closedAt')
        if previous and previous[0] and active and previous[1].get('dir')==snapshot['dir']:
            old_stop=previous[1].get('stop')
            if background_push.positive(old_stop):snapshot['stop']=(max if snapshot['dir']=='LONG' else min)(old_stop,snapshot['stop'])
        if active:settings['trade']['stop']=snapshot['stop']
        conn.execute('''INSERT INTO bob_real_trades(id,active,snapshot,settings) VALUES(%s,%s,%s::jsonb,%s::jsonb)
          ON CONFLICT(id) DO UPDATE SET active=excluded.active,snapshot=excluded.snapshot,settings=excluded.settings,updated_at=now()''',
          (tid,active,json.dumps(snapshot),json.dumps(settings)))
        event(conn,tid,'trade-opened' if not previous else 'trade-closed-in-bob' if previous[0] and not active else 'trade-updated',snapshot)
        if isinstance(payload.get('event'),dict):event(conn,tid,'browser-event',payload['event'])
        if not active:sync_devices(conn)
        return {'ok':True,'tradeId':tid}
    if action=='read':
        tid=payload.get('tradeId');before=payload.get('before')
        trades=conn.execute('SELECT id,opened_at,updated_at,active,snapshot FROM bob_real_trades ORDER BY opened_at DESC LIMIT 100').fetchall()
        result={'trades':[dict(id=i,openedAt=o.isoformat(),updatedAt=u.isoformat(),active=a,snapshot=s) for i,o,u,a,s in trades]}
        settled=[item['snapshot'] for item in result['trades'] if not item['active'] and item['snapshot'].get('settlement')]
        for item in result['trades']:
            if item['snapshot'].get('recordOnly') and any(settled_purchase(item['snapshot'],closed) for closed in settled):
                item['snapshot']={**item['snapshot'],'consumed':True}
        states={i:s for i,s in conn.execute('SELECT id,state FROM bob_real_trades WHERE active=TRUE').fetchall()}
        for item in result['trades']:
            if item['active']:
                selected=device_plan({},False,{item['id']:({'trade':item['snapshot']},states.get(item['id']) or {})})
                if selected:item['snapshot']=selected[0]['trade']
        devices=conn.execute("SELECT trade_enabled,active_trade,background_config FROM subscriptions").fetchall()
        for item in result['trades']:
            item['pushDevices']=sum(1 for enabled,active,cfg in devices if enabled and active and
                ((cfg or {}).get('trade') or {}).get('tradeId')==item['id'])
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
            evidence={k:market.get(k) for k in ('baseDirection','learningPolicy','direction','ready','priceFresh','price','dataAt','analysisBarAt','decisionReason','score','context','trendContext','plan','suggestedStop','suggestedTarget','ruleVersion')}
            evidence['planAfter']=next_state.get('trade');evidence['recommendations']=events
            evidence['delivery']='Nur protokolliert; tatsächlicher Push-Versand wird separat erfasst'
            event(conn,tid,'observation',evidence,str(now))
            next_state['journalCheckedAt']=now
            conn.execute('UPDATE bob_real_trades SET state=%s::jsonb,updated_at=now() WHERE id=%s',(json.dumps(next_state),tid))
        except Exception as exc:
            event(conn,tid,'observation-error',{'error':type(exc).__name__,'at':now},str(now))


def sale_matches(snapshot, receipt):
    """Full sale only. Source clock stays local when the receipt has no zone."""
    if receipt.get('status')!='pending-review' or receipt.get('side')!='SELL':return False
    if not isinstance(receipt.get('orderIdDigest'),str) or not re.fullmatch(r'[0-9a-f]{64}',receipt['orderIdDigest']):return False
    product=snapshot.get('product') or {}
    if product.get('currency','EUR')!='EUR':return False  # EUR receipt prices must not close a native CHF position.
    if product.get('isin')!=receipt.get('isin') or product.get('quantity')!=receipt.get('quantity'):return False
    if not background_push.positive(receipt.get('priceEur')):return False
    try:
        if not snapshot['purchase'].get('at'):
            from trade_workflow import receipt_clock
            bought_local=receipt_clock({'executedLocal':snapshot['purchase']['executedLocal']})
            sold_local=receipt_clock(receipt)
            return bought_local<sold_local<=datetime.now(ZoneInfo('Europe/Zurich')).replace(tzinfo=None)
        bought=datetime.fromisoformat(snapshot['purchase']['at'].replace('Z','+00:00'))
        if bought.tzinfo is None:return False
        if receipt.get('executedAt'):
            sold=datetime.fromisoformat(receipt['executedAt'].replace('Z','+00:00'))
            return sold.tzinfo is not None and bought<sold<=datetime.now(timezone.utc)
        # DEGIRO CH receipts print a local wall clock; use it only for ordering,
        # never manufacture an execution UTC timestamp or a quote timestamp.
        sold=datetime.strptime(receipt['executedLocal'],'%d.%m.%Y %H:%M:%S')
        return bought.astimezone(ZoneInfo('Europe/Zurich')).replace(tzinfo=None)<sold<=datetime.now(ZoneInfo('Europe/Zurich')).replace(tzinfo=None)
    except (KeyError,TypeError,ValueError):return False


def reconcile_sales(conn):
    """Authenticated mailbox evidence ends monitoring; never submits an order."""
    rows=conn.execute('SELECT id,snapshot FROM bob_real_trades WHERE active=TRUE FOR UPDATE').fetchall()
    if not rows:return 0
    receipts=conn.execute('SELECT message_id,payload FROM bob_trade_email_import ORDER BY imported_at DESC LIMIT 100').fetchall()
    count=0
    for mid,payload in receipts:
        receipt=payload.get('result') or {}
        candidates=[row for row in rows if (row[1].get('product') or {}).get('isin')==receipt.get('isin')]
        if len(candidates)!=1:continue
        matches=[(tid,snap) for tid,snap in candidates if sale_matches(snap,receipt)]
        if len(matches)!=1:continue
        # One broker sale may not consume two Bob positions, including on retry.
        prior=conn.execute("SELECT id FROM bob_real_trades WHERE snapshot->'exitReceipt'->>'orderIdDigest'=%s LIMIT 1",(receipt['orderIdDigest'],)).fetchone()
        if prior:continue
        tid,snapshot=matches[0]
        snapshot={**snapshot,'active':False,'closedAt':datetime.now(timezone.utc).isoformat(),
          'exitReceipt':{**receipt,'messageId':mid,'source':'Automatisch zugeordnete weitergeleitete DEGIRO-Verkaufsbestätigung'},
          'closureSource':'sale-email','monitoringStatus':'closed'}
        conn.execute('''UPDATE bob_real_trades SET active=FALSE,snapshot=%s::jsonb,
          settings=jsonb_set(settings,'{trade}','null'::jsonb),
          state=state-'trade',updated_at=now() WHERE id=%s''',(json.dumps(snapshot),tid))
        event(conn,tid,'sale-email-monitoring-closed',snapshot['exitReceipt'],receipt['orderIdDigest'])
        rows=[row for row in rows if row[0]!=tid];count+=1
    if count:sync_devices(conn)
    return count


def device_plan(settings, active, journals, closed=()):
    """Private single-owner Bob: attach only opted-in idle devices, never replace another trade."""
    settings=dict(settings or {'timeframe':'15m','trailAtr':1.5})
    linked=settings.get('journalTradeId')
    current=(settings.get('trade') or {}).get('tradeId')
    if current in closed:
        settings.pop('journalTradeId',None)
        settings['trade']=None
        return settings,False
    if linked and current==linked and linked not in journals:
        settings.pop('journalTradeId',None)
        settings['trade']=None
        return settings,False
    if linked and current!=linked:
        # A device has selected another trade; leave its plan untouched.
        return None
    if active and current and not linked:
        return None
    if len(journals)!=1 and not linked:
        return None
    tid=linked or next(iter(journals),None)
    if tid not in journals:
        return None
    saved,state=journals[tid]
    plan=dict(saved.get('trade') or {})
    if not plan.get('active') or plan.get('tradeId')!=tid:
        return None
    # Preserve gains in the central monitor when attaching a new device.
    watched=state.get('trade') or {}
    if watched.get('tradeId')==tid and background_push.positive(watched.get('stop')):
        plan['stop']=(max if plan['dir']=='LONG' else min)(plan['stop'],watched['stop'])
    settings.update(trade=plan,journalTradeId=tid)
    return settings,True


def sync_devices(conn):
    # Same authenticated private application scope as the journal. Opt-outs are never changed.
    journals={tid:(settings,state) for tid,settings,state in conn.execute(
        'SELECT id,settings,state FROM bob_real_trades WHERE active=TRUE').fetchall()}
    closed={tid for tid, in conn.execute("SELECT id FROM bob_real_trades WHERE active=FALSE AND COALESCE((snapshot->>'recordOnly')::boolean,FALSE)=FALSE").fetchall()}
    if closed:
        conn.execute('''UPDATE subscriptions SET trade_monitor=NULL,active_trade=FALSE,updated_at=now()
          WHERE trade_monitor->>'tradeId'=ANY(%s)
          AND (background_config->'trade'->>'tradeId' IS NULL
               OR background_config->'trade'->>'tradeId'=trade_monitor->>'tradeId')''',(list(closed),))
    rows=conn.execute('SELECT id,active_trade,background_config,trade_enabled FROM subscriptions FOR UPDATE').fetchall()
    for sid,active,settings,enabled in rows:
        if not enabled and ((settings or {}).get('trade') or {}).get('tradeId') not in closed:continue
        selected=device_plan(settings,active,journals,closed)
        if selected is None:continue
        updated,new_active=selected
        if updated==settings and active==new_active:continue
        conn.execute('''UPDATE subscriptions SET background_config=%s::jsonb,active_trade=%s,
          background_state=CASE WHEN %s THEN background_state ELSE background_state-'trade'-'journalConnected' END,
          trade_monitor=CASE WHEN %s THEN trade_monitor ELSE NULL END,updated_at=now() WHERE id=%s''',
                     (json.dumps(updated),new_active,new_active,new_active,sid))
