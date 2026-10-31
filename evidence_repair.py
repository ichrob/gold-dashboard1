"""Bounded automatic recovery of saved test evidence; no orders or invented history."""
import json
import time

INTERVAL=120000
MAX_ATTEMPTS=3


def init(conn):
    import training_handoff, model_gap_review
    model_gap_review.init(conn)
    training_handoff.init(conn)
    conn.execute('CREATE TABLE IF NOT EXISTS bob_test_repair_control (id INTEGER PRIMARY KEY,last_at BIGINT)')
    conn.execute('INSERT INTO bob_test_repair_control(id,last_at) VALUES(1,NULL) ON CONFLICT DO NOTHING')
    conn.execute('ALTER TABLE bob_test_repair_control ADD COLUMN IF NOT EXISTS signal_cursor TEXT')
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
    # Primary-key pagination bounds work before inspecting outcomes. A persistent
    # cursor covers the older archive; recent mature decisions get a fast lane.
    cursor=conn.execute('SELECT signal_cursor FROM bob_test_repair_control WHERE id=1').fetchone()[0]
    page=conn.execute('SELECT id,payload,extract(epoch from recorded_at)*1000 FROM bob_decision_audit WHERE id>%s ORDER BY id LIMIT 128',
                      (cursor or '',)).fetchall()
    conn.execute('UPDATE bob_test_repair_control SET signal_cursor=%s WHERE id=1',
                 (page[-1][0] if len(page)==128 else None,))
    recent=conn.execute("SELECT id,payload,extract(epoch from recorded_at)*1000 FROM bob_decision_audit WHERE recorded_at<to_timestamp(%s/1000.0)-interval '16 minutes' ORDER BY recorded_at DESC LIMIT 32",(now,)).fetchall()
    records={r[0]:r for r in [*page,*recent]}
    import decision_audit as audit
    for key,row,recorded_at in records.values():
        stored=dict(conn.execute('SELECT horizon,truth FROM bob_decision_outcomes WHERE decision_id=%s',(key,)).fetchall())
        for horizon in (15,60,240):
            start=audit.milliseconds(row.get('recordedAt'))
            if start is None:continue
            if start+(horizon+1)*60000>=now:continue
            if audit.outcome(row,stored.get(horizon),horizon) is not None:continue
            enqueue(conn,'signal:'+key+':'+str(horizon),'signal',dict(decision=key,horizon=horizon),
                dict(type='Signalprüfung · '+str(horizon)+' Minuten',at=row.get('recordedAt'),currency='',
                     reasons=['invalidStart' if not row.get('marketEvaluable') else 'missingFollowup']),now)


def journal_truth(conn,target):
    """Recover only original source-time/price pairs from saved input events."""
    import diagnostic_history as history
    import decision_audit as audit
    try:
        with conn.transaction():
            rows=conn.execute('''SELECT payload,observed_at FROM bob_diagnostic_history
                WHERE stage='input' AND observed_at BETWEEN %s AND %s
                ORDER BY observed_at,id LIMIT 128''',(target/1000,(target+120000)/1000)).fetchall()
    except Exception:
        return None  # Optional journal unavailable; absence is not recovery.
    points={}
    for payload,observed_at in rows:
        point=history.original_spot(payload,observed_at)
        if not point:continue
        at=audit.milliseconds(point[0]);price=point[1]
        if at is None or not target<=at<=target+60000:continue
        if at in points and points[at]!=price:return None
        points[at]=price
    if not points:return None
    at=min(points)
    return dict(at=at,price=points[at],source='gold-api-xau-usd-v1',
                evidenceOrigin='diagnostic-input-journal')


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
    truth=dict(at=float(quote[0]),price=quote[1]) if quote else journal_truth(conn,target)
    if truth is None:return False,False,'Im ursprünglichen Zeitfenster fehlt weiterhin ein bestätigter Original-Folgekurs.'
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
    return valid,not valid,('Original-Folgekurs aus '+('dem Diagnosejournal' if truth.get('evidenceOrigin') else 'dem Kursarchiv')+' nachgeladen, Ergebnis nachberechnet und geprüft.' if valid
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


def archive_attempt_state(conn,key,payload,failed,reason,now):
    """Keep technical status current without declaring missing history recovered."""
    previous=payload.get('technicalFailure') is True or payload.get('reason')=='Automatische Archivprüfung technisch fehlgeschlagen; keine Reparatur bestätigt.'
    if previous==failed:return
    payload.update(technicalFailure=failed,reason=reason,lastAttemptAt=now)
    conn.execute('UPDATE bob_test_repairs SET payload=%s::jsonb WHERE id=%s',
                 (json.dumps(payload),key))


def reconcile(conn,now):
    """A later normal backfill can resolve an escalated signal; absence cannot."""
    import decision_audit as audit
    rows=[]
    archive_checks=0
    rotated=[]
    # Bound the queue BEFORE joining the archives. One request replaces 96
    # sequential database round trips without scanning the whole outcome table.
    pending=conn.execute("""WITH pending AS MATERIALIZED (
        SELECT id,payload,ref FROM bob_test_repairs
        WHERE kind='signal' AND status='escalated' ORDER BY next_at,id LIMIT 48)
      SELECT p.id,p.payload,p.ref,a.payload,o.truth FROM pending p
      LEFT JOIN LATERAL (SELECT payload FROM bob_decision_audit
        WHERE id=p.ref->>'decision' LIMIT 1) a ON TRUE
      LEFT JOIN LATERAL (SELECT truth FROM bob_decision_outcomes
        WHERE decision_id=p.ref->>'decision'
          AND horizon=(p.ref->>'horizon')::integer LIMIT 1) o ON TRUE""").fetchall()
    for key,payload,ref,record,truth in pending:
        # A late source observation can arrive after all three initial retries.
        # Previously only a separate bulk harvest could resolve these cases.
        # Limit archive lookups and retain invalid/missing evidence unchanged.
        if record and record.get('marketEvaluable') and not truth:
            if archive_checks>=8:
                # Do not rotate an unexamined case to the back of the queue.
                # Otherwise the same first eight of each 48-case page can be
                # retried forever while the other forty never reach the archive.
                continue
            archive_checks+=1
            try:
                with conn.transaction():
                    recovered,_,reason=retry_signal(conn,ref)
                    archive_attempt_state(conn,key,payload,False,reason,now)
                    if recovered:
                        stored=conn.execute('SELECT truth FROM bob_decision_outcomes WHERE decision_id=%s AND horizon=%s',
                                           (ref['decision'],ref['horizon'])).fetchone()
                        truth=stored[0] if stored else None
            except Exception:
                archive_attempt_state(conn,key,payload,True,
                    'Automatische Archivprüfung technisch fehlgeschlagen; keine Reparatur bestätigt.',now)
        rotated.append(key)
        if record and record.get('marketEvaluable') and truth:
            rows.append((key,payload,record,truth,ref['horizon']))
    if rotated:
        conn.execute('UPDATE bob_test_repairs SET next_at=%s WHERE id=ANY(%s::text[])',
                     (now,rotated))
    for key,payload,record,truth,horizon in rows:
        if audit.outcome(record,truth,horizon):
            reason='Späterer regulärer Archivabruf hat den Original-Folgekurs geliefert; Ergebnis unabhängig erneut geprüft.'
            payload.update(reason=reason,lastAttemptAt=now)
            payload.setdefault('history',[]).append(dict(at=now,action='Spätere erfolgreiche Nachlieferung verifizieren',result=reason))
            conn.execute("UPDATE bob_test_repairs SET status='recovered',next_at=%s,payload=%s::jsonb WHERE id=%s",
                         (now,json.dumps(payload),key))


def tick(conn,now=None):
    # Shared transaction lock permits parallel readers but excludes the bounded
    # storage compactor. Never cancel repairs or advance their queue when busy.
    if not conn.execute('SELECT pg_try_advisory_xact_lock_shared(hashtext(%s))',
                        ('bob_storage_maintenance_v1',)).fetchone()[0]:
        return dict(processed=0,status='maintenance-busy')
    now=int(time.time()*1000) if now is None else now
    reconcile(conn,now)
    discover(conn,now)
    rows=conn.execute('''SELECT id,kind,ref,attempts,payload FROM bob_test_repairs
        WHERE status='trying' AND next_at<=%s ORDER BY next_at,id LIMIT 48 FOR UPDATE SKIP LOCKED''',(now,)).fetchall()
    for key,kind,ref,attempts,payload in rows:
        technical_failure=False
        try:
            with conn.transaction():ok,permanent,reason={'signal':retry_signal,'title':retry_title,'exit':retry_exit}[kind](conn,ref)
        except Exception:
            technical_failure=True
            ok,permanent,reason=False,False,'Automatische Archivprüfung technisch fehlgeschlagen; keine Reparatur bestätigt.'
        attempts+=1
        status='recovered' if ok else 'escalated' if permanent or attempts>=MAX_ATTEMPTS else 'trying'
        payload.update(lastAttemptAt=now,reason=reason,technicalFailure=technical_failure)
        payload.setdefault('history',[]).append(dict(at=now,action=ACTIONS[kind],result=reason))
        conn.execute('''UPDATE bob_test_repairs SET status=%s,attempts=%s,next_at=%s,payload=%s::jsonb WHERE id=%s''',
                     (status,attempts,now+INTERVAL,json.dumps(payload),key))
    # A model failure cannot roll back original-evidence recovery.
    import model_gap_review
    try:
        with conn.transaction():model_gap_review.tick(conn,now)
    except Exception as exc:
        print('BOB_GAP_MODEL error='+type(exc).__name__,flush=True)
    conn.execute('UPDATE bob_test_repair_control SET last_at=%s WHERE id=1',(now,))
    # Preserve unresolved history even when the source report rolls out.
    conn.execute("DELETE FROM bob_test_repairs WHERE status='recovered' AND next_at<%s",(now-90*86400000,))
    return dict(processed=len(rows))


def report(conn):
    counts=dict(conn.execute('SELECT status,count(*) FROM bob_test_repairs GROUP BY status').fetchall())
    rows=conn.execute('''SELECT id,status,attempts,payload FROM bob_test_repairs
      WHERE status<>'recovered' ORDER BY (status='escalated') DESC,next_at DESC LIMIT 300''').fetchall()
    checked=conn.execute('SELECT last_at FROM bob_test_repair_control WHERE id=1').fetchone()
    import training_handoff
    groups=training_handoff.problem_groups(conn)
    import model_gap_review
    model_review=model_gap_review.report(conn)
    return dict(modelReview=model_review,problemGroups=groups,problemCount=len(groups),affectedCases=sum(g['cases'] for g in groups),available=True,workerCheckedAt=checked[0] if checked else None,generatedAt=int(time.time()*1000),maxAttempts=MAX_ATTEMPTS,intervalMs=INTERVAL,
        counts=counts,limit=300,truncated=sum(v for k,v in counts.items() if k!='recovered')>len(rows),
        items=[dict(p,id=key,status=status,attempts=attempts) for key,status,attempts,p in rows],
        note='Automatische Nachprüfung im Hintergrund etwa alle zwei Minuten, maximal drei Versuche. Nicht rekonstruierbare Originaldaten werden nach bestätigter Prüfung direkt weitergegeben. Keine erfundenen historischen Kurse; abgeschlossene Lernexperimente werden nicht überschrieben.')
