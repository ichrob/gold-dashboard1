"""Bounded automatic recovery of saved test evidence; no orders or invented history."""
import json
import time

INTERVAL=120000
MAX_ATTEMPTS=3


def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS bob_test_repair_control (id INTEGER PRIMARY KEY,last_at BIGINT)')
    conn.execute('INSERT INTO bob_test_repair_control VALUES(1,NULL) ON CONFLICT DO NOTHING')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_test_repairs (
      id TEXT PRIMARY KEY,kind TEXT NOT NULL,ref JSONB NOT NULL,
      status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
      next_at BIGINT NOT NULL,payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_test_repairs_due ON bob_test_repairs(next_at) WHERE status=\'trying\'')


def enqueue(conn,key,kind,ref,payload,now):
    payload=dict(payload,firstSeen=now,history=[])
    conn.execute('''INSERT INTO bob_test_repairs VALUES(%s,%s,%s::jsonb,'trying',0,%s,%s::jsonb)
        ON CONFLICT DO NOTHING''',(key,kind,json.dumps(ref),now,json.dumps(payload)))


def discover(conn,now):
    # Excluding known cases advances the bounded discovery cursor on every cycle.
    rows=conn.execute('''SELECT currency,slot,payload,outcome FROM bob_ranking_samples s
      WHERE outcome IS NOT NULL AND NOT (outcome->>'complete')::boolean
      AND NOT EXISTS(SELECT 1 FROM bob_test_repairs r WHERE r.id='title:'||s.currency||':'||s.slot)
      ORDER BY slot DESC LIMIT 24''').fetchall()
    for currency,slot,row,outcome in rows:
        enqueue(conn,'title:'+currency+':'+str(slot),'title',dict(currency=currency,slot=slot),
            dict(type='Titelvergleich · 60 Minuten',at=row['at'],currency=currency,
                 reasons=list(dict.fromkeys(row.get('missing',[])+outcome.get('missing',[])))),now)
    rows=conn.execute('''SELECT currency,slot,result FROM bob_ranking_lifecycles s
      WHERE complete=TRUE AND (NOT (result->>'complete')::boolean
        OR result->'stopComparison'->>'complete'='false')
      AND NOT EXISTS(SELECT 1 FROM bob_test_repairs r WHERE r.id='exit:'||s.currency||':'||s.slot)
      ORDER BY slot DESC LIMIT 24''').fetchall()
    for currency,slot,result in rows:
        enqueue(conn,'exit:'+currency+':'+str(slot),'exit',dict(currency=currency,slot=slot),
            dict(type='Ausstiegs-/Stoppvergleich',at=slot,currency=currency,
                 reasons=list(dict.fromkeys(result.get('missing',[])+(result.get('stopComparison') or {}).get('missing',[])))),now)
    rows=conn.execute('''SELECT a.id,a.payload,h.minutes FROM bob_decision_audit a
      CROSS JOIN (VALUES(15),(60),(240)) h(minutes)
      LEFT JOIN bob_decision_outcomes o ON o.decision_id=a.id AND o.horizon=h.minutes
      WHERE a.recorded_at < to_timestamp(%s/1000.0)-(h.minutes+1)*interval '1 minute'
      AND (o.truth IS NULL OR a.payload->>'marketEvaluable'='false')
      AND NOT EXISTS(SELECT 1 FROM bob_test_repairs r WHERE r.id='signal:'||a.id||':'||h.minutes)
      ORDER BY a.recorded_at DESC LIMIT 48''',(now,)).fetchall()
    for key,row,horizon in rows:
        enqueue(conn,'signal:'+key+':'+str(horizon),'signal',dict(decision=key,horizon=horizon),
            dict(type='Signalprüfung · '+str(horizon)+' Minuten',at=row.get('recordedAt'),currency='',
                 reasons=['invalidStart' if not row.get('marketEvaluable') else 'missingFollowup']),now)


def retry_signal(conn,ref):
    import decision_audit as audit
    row=conn.execute('SELECT payload FROM bob_decision_audit WHERE id=%s',(ref['decision'],)).fetchone()
    if not row:return False,True,'Originalprüfung ist nicht mehr im Archiv vorhanden.'
    record=row[0];horizon=ref['horizon']
    if not record.get('marketEvaluable'):
        return False,True,'Der unveränderliche Startnachweis ist ungültig; ein heutiger Kurs darf ihn nicht ersetzen.'
    target=record['recordedAt']+horizon*60000
    stored=conn.execute('SELECT truth FROM bob_decision_outcomes WHERE decision_id=%s AND horizon=%s',
                        (ref['decision'],horizon)).fetchone()
    if stored and audit.outcome(record,stored[0],horizon):return True,False,'Passender Original-Folgekurs vorhanden; Ergebnis erneut bestätigt.'
    quote=conn.execute('''SELECT extract(epoch from quote_at)*1000,price FROM bob_spot_observations
      WHERE stream='gold-api-xau-usd-v1' AND quote_at>=to_timestamp(%s/1000.0)
      AND quote_at<=to_timestamp(%s/1000.0) ORDER BY quote_at LIMIT 1''',(target,target+60000)).fetchone()
    if not quote:return False,False,'Im ursprünglichen Zeitfenster fehlt weiterhin ein bestätigter Original-Folgekurs.'
    truth=dict(at=float(quote[0]),price=quote[1])
    if not audit.outcome(record,truth,horizon):return False,True,'Archivwert passt nicht zum ursprünglichen Kurs- und Zeitnachweis.'
    extent=conn.execute('''SELECT min(price),max(price) FROM bob_spot_observations
      WHERE stream='gold-api-xau-usd-v1' AND quote_at>=to_timestamp(%s/1000.0)
      AND quote_at<=to_timestamp(%s/1000.0)''',(record['recordedAt'],truth['at'])).fetchone()
    truth.update(minPrice=extent[0],maxPrice=extent[1])
    conn.execute('''INSERT INTO bob_decision_outcomes VALUES(%s,%s,%s::jsonb)
        ON CONFLICT DO NOTHING''',(ref['decision'],horizon,json.dumps(truth)))
    actual=conn.execute('SELECT truth FROM bob_decision_outcomes WHERE decision_id=%s AND horizon=%s',
                        (ref['decision'],horizon)).fetchone()
    valid=bool(actual and audit.outcome(record,actual[0],horizon))
    return valid,not valid,('Original-Folgekurs aus dem Archiv nachgeladen, Ergebnis nachberechnet und geprüft.' if valid
        else 'Gespeicherter Widerspruch verhindert eine sichere automatische Korrektur.')


def retry_title(conn,ref):
    import ranking_learning as rank
    row=conn.execute('SELECT payload,outcome FROM bob_ranking_samples WHERE currency=%s AND slot=%s',
                     (ref['currency'],ref['slot'])).fetchone()
    if not row:return False,True,'Originalvergleich nicht mehr im Archiv.'
    payload,outcome=row
    if (outcome or {}).get('complete'):return True,False,'Originalvergleich ist inzwischen vollständig bestätigt.'
    observations={}
    for c in payload['candidates']:
        observations[c['isin']]=[r[0] for r in conn.execute('''SELECT payload FROM bob_precision_quotes
          WHERE isin=%s AND source=%s AND currency=%s AND at>%s AND at<=%s ORDER BY at''',
          (c['isin'],c['quote']['source'],ref['currency'],payload['at'],payload['at']+3660000)).fetchall()]
    reviewed=rank.evaluate(payload,observations)
    if reviewed['complete']:
        # Frozen learning outcomes may already have been consumed. Never silently
        # rewrite a past experiment from newly arriving evidence.
        return False,True,'Später eingetroffene Originalnachweise gefunden. Der abgeschlossene Lernvergleich bleibt unverändert; getrennte fachliche Nachprüfung erforderlich.'
    if payload.get('missing') or len(payload['candidates'])<2:
        return False,True,'Originalplan und Archiv geprüft: beim Einstieg fehlende Produktnachweise lassen sich nicht rückdatieren.'
    return False,False,'Originalquellen erneut geprüft; gleichzeitige Geld-/Briefnachweise bleiben unvollständig.'


def retry_exit(conn,ref):
    row=conn.execute('SELECT result,state FROM bob_ranking_lifecycles WHERE currency=%s AND slot=%s',
                     (ref['currency'],ref['slot'])).fetchone()
    if not row:return False,True,'Original-Ausstiegsvergleich nicht mehr im Archiv.'
    result,state=row
    if result.get('complete') and (result.get('stopComparison') or {}).get('complete',True):
        return True,False,'Beide gespeicherten Ausstiegswege sind vollständig bestätigt.'
    # Saved exit events and terminal cases are checked, not resumed with a
    # present-day quote that would erase their historical gap.
    failed=[c for c in [*state.get('cases',{}).values(),*state.get('fixedCases',{}).values()]
            if c.get('status')=='inconclusive' or not c.get('productReturnKnown') or c.get('pendingUnits')]
    return False,True,('Originalzustand und Ausstiegsereignisse erneut geprüft: historische Kurs-/KO-Lücke; die damalige Reihenfolge lässt sich nicht sicher rekonstruieren.'
        if failed else 'Eingefrorene Produktgruppe unvollständig; fehlende ursprüngliche Einstiegsnachweise dürfen nicht nachträglich erzeugt werden.')


ACTIONS={'signal':'Archiv-Folgekurs nachladen, Ergebnis nachberechnen und verifizieren',
         'title':'Originalplan und archivierte Produktkurse erneut auswerten',
         'exit':'Gespeicherte Ausstiegswege, Kurslücken und Nachweise erneut prüfen'}


def reconcile(conn,now):
    """A later normal backfill can resolve an escalated signal; absence cannot."""
    import decision_audit as audit
    rows=conn.execute('''SELECT r.id,r.payload,a.payload,o.truth,(r.ref->>'horizon')::integer
      FROM bob_test_repairs r
      JOIN bob_decision_audit a ON a.id=r.ref->>'decision'
      JOIN bob_decision_outcomes o ON o.decision_id=a.id AND o.horizon=(r.ref->>'horizon')::integer
      WHERE r.kind='signal' AND r.status='escalated' AND a.payload->>'marketEvaluable'='true'
      ORDER BY r.next_at LIMIT 48''').fetchall()
    for key,payload,record,truth,horizon in rows:
        if audit.outcome(record,truth,horizon):
            reason='Späterer regulärer Archivabruf hat den Original-Folgekurs geliefert; Ergebnis unabhängig erneut geprüft.'
            payload.update(reason=reason,lastAttemptAt=now)
            payload['history'].append(dict(at=now,action='Spätere erfolgreiche Nachlieferung verifizieren',result=reason))
            conn.execute("UPDATE bob_test_repairs SET status='recovered',next_at=%s,payload=%s::jsonb WHERE id=%s",
                         (now,json.dumps(payload),key))
        else:
            conn.execute('UPDATE bob_test_repairs SET next_at=%s WHERE id=%s',(now,key))


def tick(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    reconcile(conn,now)
    discover(conn,now)
    rows=conn.execute('''SELECT id,kind,ref,attempts,payload FROM bob_test_repairs
        WHERE status='trying' AND next_at<=%s ORDER BY next_at,id LIMIT 48 FOR UPDATE SKIP LOCKED''',(now,)).fetchall()
    for key,kind,ref,attempts,payload in rows:
        try:
            with conn.transaction():ok,permanent,reason={'signal':retry_signal,'title':retry_title,'exit':retry_exit}[kind](conn,ref)
        except Exception:
            ok,permanent,reason=False,False,'Automatische Archivprüfung technisch fehlgeschlagen; keine Reparatur bestätigt.'
        attempts+=1
        status='recovered' if ok else 'escalated' if permanent or attempts>=MAX_ATTEMPTS else 'trying'
        payload.update(lastAttemptAt=now,reason=reason)
        payload.setdefault('history',[]).append(dict(at=now,action=ACTIONS[kind],result=reason))
        conn.execute('''UPDATE bob_test_repairs SET status=%s,attempts=%s,next_at=%s,payload=%s::jsonb WHERE id=%s''',
                     (status,attempts,now+INTERVAL,json.dumps(payload),key))
    conn.execute('UPDATE bob_test_repair_control SET last_at=%s WHERE id=1',(now,))
    # Preserve unresolved history even when the source report rolls out.
    conn.execute("DELETE FROM bob_test_repairs WHERE status='recovered' AND next_at<%s",(now-90*86400000,))
    return dict(processed=len(rows))


def report(conn):
    counts=dict(conn.execute('SELECT status,count(*) FROM bob_test_repairs GROUP BY status').fetchall())
    rows=conn.execute('''SELECT id,status,attempts,payload FROM bob_test_repairs
      WHERE status<>'recovered' ORDER BY (status='escalated') DESC,next_at DESC LIMIT 300''').fetchall()
    checked=conn.execute('SELECT last_at FROM bob_test_repair_control WHERE id=1').fetchone()
    return dict(available=True,workerCheckedAt=checked[0] if checked else None,generatedAt=int(time.time()*1000),maxAttempts=MAX_ATTEMPTS,intervalMs=INTERVAL,
        counts=counts,limit=300,truncated=sum(v for k,v in counts.items() if k!='recovered')>len(rows),
        items=[dict(p,id=key,status=status,attempts=attempts) for key,status,attempts,p in rows],
        note='Automatische Nachprüfung im Hintergrund etwa alle zwei Minuten, maximal drei Versuche. Nicht rekonstruierbare Originaldaten werden nach bestätigter Prüfung direkt weitergegeben. Keine erfundenen historischen Kurse; abgeschlossene Lernexperimente werden nicht überschrieben.')
