"""Seven-day archive of actual Gold-API Spot observations, preserving source time."""
import json
import math
import os
import time
from datetime import datetime,timezone
from urllib.request import Request,build_opener
from bob_auth import NoRedirect

STREAM='gold-api-xau-usd-v1'


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_spot_observations (
        stream TEXT NOT NULL,
        quote_at TIMESTAMPTZ NOT NULL,
        price DOUBLE PRECISION NOT NULL,
        PRIMARY KEY(stream,quote_at)
    )''')


def point(payload, now=None, age=60):
    now=time.time() if now is None else now
    if payload.get('symbol')!='XAU' or payload.get('currency')!='USD':
        raise ValueError('Spot-Identität fehlt')
    price=payload.get('price');raw=payload.get('at')
    if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<=0:
        raise ValueError('Ungültiger Spot-Kurs')
    if not isinstance(raw,str):raise ValueError('Spot-Quellenzeit fehlt')
    at=datetime.fromisoformat(raw.replace('Z','+00:00'))
    if at.tzinfo is None or not 0<=now-at.timestamp()<=age:
        raise ValueError('Spot-Quellenzeit nicht verwendbar')
    return at.astimezone(timezone.utc).isoformat(),float(price)


def handle(conn, action, payload):
    if action=='write':
        at,price=point(payload)
        conn.execute("DELETE FROM bob_spot_observations WHERE quote_at < now()-interval '7 days'")
        conn.execute('''INSERT INTO bob_spot_observations(stream,quote_at,price)
            VALUES(%s,%s,%s) ON CONFLICT(stream,quote_at) DO NOTHING''',(STREAM,at,price))
        row=conn.execute('SELECT price FROM bob_spot_observations WHERE stream=%s AND quote_at=%s',(STREAM,at)).fetchone()
        if not row or row[0]!=price:
            raise ValueError('Widersprüchlicher Spot-Quellenzeitstempel')
        return {'ok':True}
    if action=='read':
        rows=conn.execute('''SELECT quote_at,price FROM bob_spot_observations
            WHERE stream=%s AND quote_at >= now()-interval '1 hour' AND quote_at <= now()
            ORDER BY quote_at DESC LIMIT 240''',(STREAM,)).fetchall()
        summary=conn.execute("SELECT count(*),min(quote_at),max(quote_at) FROM bob_spot_observations WHERE stream=%s AND quote_at>=now()-interval '7 days'",(STREAM,)).fetchone()
        diagnostics=dict(sampleCount=summary[0],firstAt=summary[1].isoformat() if summary[1] else None,lastAt=summary[2].isoformat() if summary[2] else None)
        return {'observations':[dict(at=at.isoformat(),price=price,symbol='XAU',currency='USD') for at,price in reversed(rows)],'diagnostics':diagnostics}
    raise ValueError('Unbekannte Spot-Speicheraktion')


def request(action, payload):
    base=os.environ.get('PUSH_SERVICE_URL','').rstrip('/')
    token=os.environ.get('PUSH_SERVICE_TOKEN','')
    if not base or not token:raise OSError('Spot-Speicher nicht konfiguriert')
    if not base.startswith(('http://','https://')):base='http://'+base
    req=Request(base+'/market-spots/'+action,data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-Bob-Push-Token':token},method='POST')
    with build_opener(NoRedirect()).open(req,timeout=12) as response:data=response.read(65537)
    if len(data)>65536:raise ValueError('Spot-Speicherantwort zu groß')
    result=json.loads(data)
    if not isinstance(result,dict):raise ValueError('Spot-Speicherantwort nicht verwendbar')
    return result

