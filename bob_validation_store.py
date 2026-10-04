"""Durable frozen GCZ26 predictions; asynchronous, server-token-only archive."""
import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, build_opener
from bob_auth import NoRedirect

KEY='future:GCZ26:gold-api-spot-ratio-v1'
_lock=threading.Lock()
_queue=[]
_thread=None
_last_truth=None
_active_until=0
_status='Genauigkeitsmessung noch nicht dauerhaft gesichert'


def stamp(raw):
    if not isinstance(raw,str):raise ValueError('Kurszeit fehlt oder ist ungültig')
    at=datetime.fromisoformat(raw.replace('Z','+00:00'))
    if at.tzinfo is None:raise ValueError('Messzeit ohne Zeitzone')
    return at.astimezone(timezone.utc)


def bucket(age):
    if not 0<age<=1800:raise ValueError('Ungültiger Referenzabstand')
    return '0–60s' if age<=60 else '61–300s' if age<=300 else '301–900s' if age<=900 else '901–1800s'


def event(payload, now=None):
    now=now or datetime.now(timezone.utc)
    if payload.get('key')!=KEY or payload.get('type') not in ('prediction','truth'):
        raise ValueError('Messidentität nicht bestätigt')
    value=payload.get('value')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
        raise ValueError('Ungültiger Messkurs')
    at=stamp(payload['at'])
    if not 0<=(now-at).total_seconds()<=(90 if payload['type']=='prediction' else 3600):
        raise ValueError('Messzeit nicht verwendbar')
    ref=stamp(payload['referenceAt']) if payload['type']=='prediction' else None
    horizon=bucket((at-ref).total_seconds()) if ref else ''
    return payload['type'],at,float(value),ref,horizon


def init(conn):
    import comparison_store
    comparison_store.init(conn)
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_future_predictions (
        bucket TEXT NOT NULL, quote_at TIMESTAMPTZ NOT NULL, price DOUBLE PRECISION NOT NULL,
        reference_at TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        truth_at TIMESTAMPTZ, PRIMARY KEY(bucket,quote_at))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_future_truths (
        quote_at TIMESTAMPTZ PRIMARY KEY, price DOUBLE PRECISION NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp())''')

    conn.execute('CREATE INDEX IF NOT EXISTS bob_prediction_truth_idx ON bob_future_predictions(bucket,truth_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_prediction_quote_idx ON bob_future_predictions(quote_at DESC)')


def handle(conn, action, payload):
    if action not in ('read','write'):raise ValueError('Unbekannte Messaktion')
    if payload.get('key') == 'future:GCZ26:spot-cfd-comparison-v1':
        import comparison_store
        return comparison_store.handle(conn, action, payload)
    # Serialize pairing and writes across scanner instances. Caller commits.
    conn.execute('SELECT pg_advisory_xact_lock(68431026)')
    if action=='write':
        events=payload.get('events')
        if not isinstance(events,list) or len(events)>40:raise ValueError('Ungültiges Messpaket')
        checked=[event(e) for e in events]
        conn.execute("DELETE FROM bob_future_predictions WHERE received_at<now()-interval '7 days'")
        conn.execute("DELETE FROM bob_future_truths WHERE received_at<now()-interval '7 days'")
        for kind,at,value,ref,horizon in checked:
            if kind=='prediction':
                # First server receipt is immutable, even after recalculation.
                conn.execute('''INSERT INTO bob_future_predictions(bucket,quote_at,price,reference_at)
                    VALUES(%s,%s,%s,%s) ON CONFLICT(bucket,quote_at) DO NOTHING''',(horizon,at,value,ref))
            else:
                conn.execute('''INSERT INTO bob_future_truths(quote_at,price) VALUES(%s,%s)
                    ON CONFLICT(quote_at) DO NOTHING''',(at,value))
                actual=conn.execute('SELECT price FROM bob_future_truths WHERE quote_at=%s',(at,)).fetchone()
                if not actual or actual[0]!=value:raise ValueError('Widersprüchlicher Future-Zeitstempel')
        # Compare only predictions archived before the first receipt of truth.
        truth_times=list({at for kind,at,*_ in checked if kind=='truth'})
        truths=(conn.execute('SELECT quote_at,received_at FROM bob_future_truths WHERE quote_at=ANY(%s) ORDER BY received_at,quote_at',(truth_times,)).fetchall() if truth_times else [])
        for at,received in truths:
            for horizon in ('0–60s','61–300s','301–900s','901–1800s'):
                used=conn.execute('SELECT 1 FROM bob_future_predictions WHERE bucket=%s AND truth_at=%s',(horizon,at)).fetchone()
                if used:continue
                row=conn.execute('''SELECT quote_at FROM bob_future_predictions WHERE bucket=%s AND truth_at IS NULL
                    AND received_at<=%s AND quote_at BETWEEN %s-interval '5 seconds' AND %s+interval '5 seconds'
                    ORDER BY abs(extract(epoch FROM quote_at-%s)),quote_at LIMIT 1''',(horizon,received,at,at,at)).fetchone()
                if row:conn.execute('UPDATE bob_future_predictions SET truth_at=%s WHERE bucket=%s AND quote_at=%s',(at,horizon,row[0]))
    rows=conn.execute('''SELECT p.bucket,p.quote_at,p.price,p.reference_at,p.received_at,t.quote_at,t.price,t.received_at
        FROM bob_future_predictions p JOIN bob_future_truths t ON p.truth_at=t.quote_at
        WHERE t.received_at>=now()-interval '7 days' ORDER BY t.received_at DESC LIMIT 40320''').fetchall()
    pairs=[dict(bucket=b,predictionAt=a.isoformat(),prediction=value,referenceAt=ref.isoformat(),
                predictionReceivedAt=created.isoformat(),truthAt=ta.isoformat(),truth=tv,truthReceivedAt=received.isoformat())
           for b,a,value,ref,created,ta,tv,received in reversed(rows)]
    prediction_count=conn.execute("SELECT count(*) FROM bob_future_predictions WHERE received_at>=now()-interval '7 days'").fetchone()[0]
    truth_count=conn.execute("SELECT count(*) FROM bob_future_truths WHERE received_at>=now()-interval '7 days'").fetchone()[0]
    latest=conn.execute('''SELECT t.quote_at,
        (SELECT min(abs(extract(epoch FROM p.quote_at-t.quote_at))) FROM bob_future_predictions p
         WHERE p.received_at<=t.received_at) FROM bob_future_truths t WHERE t.received_at>=now()-interval '7 days' ORDER BY t.quote_at DESC LIMIT 1''').fetchone()
    diagnostics=dict(predictionCount=prediction_count,truthCount=truth_count,pairCount=len(pairs),
                     lastTruthAt=latest[0].isoformat() if latest else None,
                     nearestPredictionSeconds=float(latest[1]) if latest and latest[1] is not None else None)
    # Display the latest frozen prediction, even if it has no matching truth
    # yet. Original quote time is never replaced with the archive read time.
    last_prediction=conn.execute("""SELECT quote_at,price,received_at,reference_at
        FROM bob_future_predictions WHERE quote_at>=now()-interval '7 days' AND quote_at<=now()
        ORDER BY quote_at DESC,received_at DESC LIMIT 1""").fetchone()
    diagnostics['latestEstimate']=(dict(contract='GCZ26',priceAt=last_prediction[0].isoformat(),
        priceUsd=last_prediction[1],savedAt=last_prediction[2].isoformat(),
        referenceAt=last_prediction[3].isoformat()) if last_prediction else None)
    return dict(ok=True,key=KEY,pairs=pairs,diagnostics=diagnostics)


def request(action, payload, key=KEY):
    base=os.environ.get('PUSH_SERVICE_URL','').rstrip('/');token=os.environ.get('PUSH_SERVICE_TOKEN','')
    if not base or not token:raise OSError('Messspeicher nicht konfiguriert')
    if not base.startswith(('http://','https://')):base='http://'+base
    req=Request(base+'/market-validations/'+action,data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-Bob-Push-Token':token},method='POST')
    with build_opener(NoRedirect()).open(req,timeout=12) as response:body=response.read(20971521)
    if len(body)>20971520:raise ValueError('Messantwort zu groß')
    result=json.loads(body)
    if not isinstance(result,dict) or result.get('key')!=key or result.get('ok') is not True:
        raise ValueError('Messantwort nicht verwendbar')
    return result


def status():
    with _lock:return _status


def enqueue(key, kind, value, at, reference_at=None):
    global _thread,_last_truth,_active_until
    if key!=KEY or not os.environ.get('PUSH_SERVICE_URL') or not os.environ.get('PUSH_SERVICE_TOKEN'):return
    e=dict(key=key,type=kind,value=value,at=at)
    if reference_at is not None:e['referenceAt']=reference_at
    with _lock:
        _active_until=time.monotonic()+120
        if kind=='truth':
            if _last_truth==(at,value):return
            _last_truth=(at,value)
        _queue.append(e);_queue[:]=_queue[-120:]
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=_sync,name='bob-future-validation',daemon=True)
            _thread.start()


def _sync():
    global _status
    import estimate_quality
    while True:
        with _lock:
            batch=list(_queue[:40])
            if not batch and time.monotonic()>_active_until:return
        # Do not retry old predictions as fresh ones after an outage.
        now=datetime.now(timezone.utc)
        usable=[]
        for e in batch:
            try:event(e,now);usable.append(e)
            except (ValueError,TypeError,KeyError):pass
        try:
            result=request('write' if usable else 'read',{'events':usable} if usable else {})
            estimate_quality.restore_durable(result['pairs'],datetime.now(timezone.utc))
            with _lock:
                del _queue[:len(batch)]
                _status='Genauigkeitsmessung dauerhaft gesichert; eingefrorene Schätzungen bleiben über Neustarts erhalten'
                d=result.get('diagnostics',{})
                if all(isinstance(d.get(k),int) and not isinstance(d[k],bool) and d[k]>=0 for k in ('predictionCount','truthCount','pairCount')):
                    _status+=' · Messarchiv: '+str(d['predictionCount'])+' eingefrorene Schätzungen, '+str(d['truthCount'])+' datierte GCZ26-Kurse, '+str(d['pairCount'])+' passende Paare insgesamt'
                    if d.get('lastTruthAt'):
                        last=stamp(d['lastTruthAt']).astimezone(timezone.utc)
                        _status+=' · jüngster echter Vergleichskurs '+last.strftime('%d.%m.%Y %H:%M:%S UTC')
                    distance=d.get('nearestPredictionSeconds')
                    if isinstance(distance,(int,float)) and not isinstance(distance,bool) and math.isfinite(distance) and distance>=0:
                        _status+=' · nächster vorher gespeicherter Schätzzeitpunkt: '+str(round(distance,2))+' s Abstand (höchstens 5 s)'
        except (OSError,ValueError,TypeError,KeyError):
            with _lock:_status='Dauerhafter Messspeicher momentan nicht erreichbar; lokale Messung läuft weiter'
        threading.Event().wait(30)
