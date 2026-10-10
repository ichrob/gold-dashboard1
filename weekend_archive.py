"""Durable display-only market quote/candle archive; never a signal input."""
import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

FRAMES = {'1m':60000,'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'4h':14400000}
CARD_KEYS = ('spot','cfd','future','estimate')
CFD_CHART_KEYS = tuple('cfd-chart:'+tf for tf in FRAMES)
MAX_AGE = 7 * 86400
_worker = None
_lock = threading.Lock()


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_weekend_archive (
        data_key TEXT PRIMARY KEY,
        quote_at TIMESTAMPTZ NOT NULL,
        payload JSONB NOT NULL
    )""")


def positive(n):
    return isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) and n>0


def valid(key, item, now=None):
    now = time.time() if now is None else now
    if key not in CARD_KEYS and key not in ('chart:'+x for x in FRAMES) and key not in CFD_CHART_KEYS:
        return None
    if not isinstance(item,dict):
        return None
    try:
        at = datetime.fromisoformat(item['at'].replace('Z','+00:00'))
        if at.tzinfo is None or not 0 <= now-at.timestamp() <= MAX_AGE:
            return None
        if key in CARD_KEYS:
            if not positive(item.get('price')):
                return None
            if key=='spot' and item.get('symbol')!='XAU/USD':
                return None
            if key=='cfd' and item.get('kind')!='cfd':
                return None
        else:
            is_cfd=key.startswith('cfd-chart:')
            tf=key[10:] if is_cfd else key[6:]
            bars=item.get('bars')
            if not isinstance(bars,list) or not 2<=len(bars)<=180:
                return None
            previous=-1
            for b in bars:
                if not isinstance(b,dict) or b.get('instrument')!=('GOLD-CFD' if is_cfd else 'XAU/USD') or b.get('isOpen') is not False:
                    return None
                stamp=b.get('openTime')
                if not isinstance(stamp,(int,float)) or isinstance(stamp,bool) or stamp<=previous or stamp>now*1000:
                    return None
                if not all(positive(b.get(k)) for k in ('open','high','low','close')):
                    return None
                if b['low']>min(b['open'],b['close']) or b['high']<max(b['open'],b['close']):
                    return None
                previous=stamp
            if abs(at.timestamp()*1000-(previous+FRAMES[tf]))>1500:
                return None
        return at.astimezone(timezone.utc)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return None



def observation_bars(rows, frames=None, now=None):
    """Sparse real Spot ticks grouped without filling gaps or inventing highs/lows."""
    now=time.time() if now is None else now
    grouped={tf:{} for tf in (frames if frames is not None else FRAMES)}
    for timestamp,price in rows:
        if timestamp.tzinfo is None or not positive(price):
            continue
        epoch=timestamp.timestamp()*1000
        if not 0 <= now*1000-epoch <= MAX_AGE*1000:
            continue
        for tf,bytime in grouped.items():
            step=FRAMES[tf]
            bucket=int(epoch//step)*step
            # Only confirmed complete intervals are suitable as chart points.
            if bucket+step>now*1000:
                continue
            bar=bytime.get(bucket)
            if bar is None:
                bytime[bucket]=dict(openTime=bucket,open=price,high=price,
                    low=price,close=price,isOpen=False,instrument='XAU/USD',
                    source='Gold API · gespeicherte Spot-Messpunkte',
                    observedOnly=True,samples=1)
            else:
                bar['high']=max(bar['high'],price)
                bar['low']=min(bar['low'],price)
                bar['close']=price
                bar['samples']+=1
    return {tf:list(sorted(bars.values(),key=lambda b:b['openTime']))[-180:]
            for tf,bars in grouped.items() if len(bars)>=2}



def merge_chart_history(old, new):
    """Keep earlier measured closed candles after a scanner restart.

    A later, partial in-memory collector must not erase Friday's stored history.
    Identical timestamps retain the better-sampled version; no missing bars are filled.
    """
    combined={}
    for row in old.get('bars',[]):
        combined[row['openTime']]=dict(row)
    for row in new['bars']:
        earlier=combined.get(row['openTime'])
        if earlier is None or row.get('samples',0)>=earlier.get('samples',0):
            combined[row['openTime']]=dict(row)
    return dict(new,bars=[combined[t] for t in sorted(combined)][-180:])


def handle(conn, action, payload):
    if action=='write':
        items=payload.get('items')
        if not isinstance(items,dict) or len(items)>2*len(FRAMES)+len(CARD_KEYS):
            raise ValueError('Ungültige Wochenendarchivdaten')
        count=0
        for key,item in items.items():
            stamp=valid(key,item)
            if stamp is None:
                continue
            if key.startswith(('chart:', 'cfd-chart:')):
                old=conn.execute("SELECT payload FROM bob_weekend_archive WHERE data_key=%s FOR UPDATE",(key,)).fetchone()
                if old:
                    prior=old[0] if isinstance(old[0],dict) else json.loads(old[0])
                    previous_at=valid(key,prior)
                    if previous_at is not None and stamp>previous_at:
                        merged=merge_chart_history(prior,item)
                        if valid(key,merged) is not None:
                            item=merged
            conn.execute("""INSERT INTO bob_weekend_archive(data_key,quote_at,payload)
                VALUES(%s,%s,%s::jsonb)
                ON CONFLICT(data_key) DO UPDATE
                SET quote_at=excluded.quote_at, payload=excluded.payload
                WHERE bob_weekend_archive.quote_at<excluded.quote_at""",
                (key,stamp,json.dumps(item,allow_nan=False)))
            count+=1
        conn.execute("DELETE FROM bob_weekend_archive WHERE quote_at < now() - interval '7 days'")
        return {'ok':True,'accepted':count}
    if action=='read':
        rows=conn.execute("""SELECT data_key,payload FROM bob_weekend_archive
            WHERE quote_at >= now()-interval '7 days'""").fetchall()
        result={'displayOnly':True,'cards':{},'history':{}}
        for key,item in rows:
            if isinstance(item,str):
                item=json.loads(item)
            if valid(key,item) is None:
                continue
            if key in CARD_KEYS:
                result['cards'][key]=dict(item,marketClosed=True,historical=True,
                                           realtimeCfd=False,isExchangeRealtime=False)
            elif key.startswith('cfd-chart:'):
                result.setdefault('cfdHistory',{})[key[10:]]=item['bars']
            else:
                result['history'][key[6:]]=item['bars']

        # Fallback for a previously deployed Friday: reconstruct only from
        # original persisted XAU/USD Spot observations. These are SAMPLE-derived
        # bars, not complete exchange OHLC. They never enter signal generation.
        missing=[tf for tf in FRAMES if tf not in result['history']]
        if missing:
            try:
                import bob_market_store
                rows=conn.execute("""SELECT quote_at,price FROM bob_spot_observations
                    WHERE stream=%s AND quote_at >= now()-interval '7 days'
                    ORDER BY quote_at DESC LIMIT 12000""",
                    (bob_market_store.STREAM,)).fetchall()
                rebuilt=observation_bars(reversed(rows),missing)
                for tf,bars in rebuilt.items():
                    if bars:
                        result['history'][tf]=bars
                if rebuilt:
                    result['spotHistoryNote']='Nur beobachtete Gold-Spot-Messpunkte; keine vollständigen OHLC-Kerzen'
            except Exception:
                pass
        # Recover genuine Spot observations that were archived by Bob before
        # deployment of this new table, without manufacturing a fresh quote.
        if 'spot' not in result['cards']:
            try:
                import bob_market_store
                row=conn.execute("""SELECT quote_at,price FROM bob_spot_observations
                    WHERE stream=%s AND quote_at>=now()-interval '7 days'
                    ORDER BY quote_at DESC LIMIT 1""",(bob_market_store.STREAM,)).fetchone()
                if row:
                    result['cards']['spot']=dict(price=row[1],at=row[0].isoformat(),
                        kind='spot',symbol='XAU/USD',source='Gold API · gespeicherter Spot',
                        historical=True,marketClosed=True,realtimeCfd=False,isExchangeRealtime=False)
            except Exception:
                pass
        return result
    raise ValueError('Unbekannte Archivaktion')


def request(action, payload):
    base=os.environ.get('PUSH_SERVICE_URL','').rstrip('/')
    token=os.environ.get('PUSH_SERVICE_TOKEN','')
    if not base or not token:
        raise OSError('Archivanbindung fehlt')
    if not base.startswith(('https://','http://')):
        base='http://'+base
    data=json.dumps(payload,allow_nan=False).encode()
    req=Request(base+'/weekend-archive/'+action,data=data,method='POST',
                headers={'Content-Type':'application/json','X-Bob-Push-Token':token})
    with urlopen(req,timeout=18) as response:
        body=response.read(1000001)
    if len(body)>1000000:
        raise ValueError('Archivantwort zu gross')
    result=json.loads(body)
    if not isinstance(result,dict):
        raise ValueError('Ungueltige Archivantwort')
    return result


def collect_items(bundle,cards,now=None):
    now=time.time() if now is None else now
    items={}
    for key in ('cfd','future','estimate'):
        q=cards.get(key) if isinstance(cards,dict) else None
        if valid(key,q,now) is not None:
            items[key]=q
    spots=bundle.get('spots',{}) if isinstance(bundle,dict) else {}
    if isinstance(spots,dict) and positive(spots.get('xaus')):
        q=dict(price=spots['xaus'],at=spots.get('spot_price_as_of'),
               symbol='XAU/USD',kind='spot',source=spots.get('primary') or 'Gold API',
               changePct=(spots.get('dailyChange') or {}).get('changePct'))
        if valid('spot',q,now) is not None:
            items['spot']=q
    frames=bundle.get('history',{}).get('bars_by_tf',{}) if isinstance(bundle,dict) else {}
    for tf,step in FRAMES.items():
        bars=frames.get(tf,[]) if isinstance(frames,dict) else []
        if not isinstance(bars,list):
            continue
        closed=[dict(b) for b in bars if isinstance(b,dict) and b.get('instrument')=='XAU/USD' and b.get('isOpen') is False][-180:]
        if len(closed)<2:
            continue
        at=datetime.fromtimestamp((closed[-1]['openTime']+step)/1000,timezone.utc).isoformat()
        q=dict(at=at,bars=closed)
        if valid('chart:'+tf,q,now) is not None:
            items['chart:'+tf]=q

    # Investing.com CFD candles are explicitly sampled from Bob's observations;
    # never backfill with Spot, Yahoo futures or a synthetic price.
    try:
        import investing_card
        for tf,step in FRAMES.items():
            if tf == '30m':
                continue
            bars=investing_card.chart_snapshot(tf).get('bars') or []
            closed=[dict(b) for b in bars if isinstance(b,dict)
                and b.get('instrument')=='GOLD-CFD'
                and b.get('isOpen') is False and b.get('openTime',0)+step<=now*1000][-180:]
            if len(closed)<2:
                continue
            q=dict(at=datetime.fromtimestamp((closed[-1]['openTime']+step)/1000,
                timezone.utc).isoformat(),bars=closed)
            if valid('cfd-chart:'+tf,q,now) is not None:
                items['cfd-chart:'+tf]=q
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        print('BOB_WEEKEND_ARCHIVE cfd_chart_error='+type(exc).__name__,flush=True)
    return items


def save_once(get_bundle,get_cards):
    bundle,cards={},{}
    try:
        bundle=get_bundle()
    except Exception as exc:
        print('BOB_WEEKEND_ARCHIVE bundle_error='+type(exc).__name__,flush=True)
    try:
        cards=get_cards()
    except Exception as exc:
        print('BOB_WEEKEND_ARCHIVE cards_error='+type(exc).__name__,flush=True)
    items=collect_items(bundle,cards)
    if items:
        result=request('write',{'items':items})
        print('BOB_WEEKEND_ARCHIVE saved='+str(result.get('accepted',0)),flush=True)


def start(get_bundle,get_cards):
    global _worker
    with _lock:
        if _worker and _worker.is_alive():
            return
        def run():
            import background_push
            while True:
                if not background_push.gold_weekend_seconds_remaining():
                    try:
                        save_once(get_bundle,get_cards)
                    except Exception as exc:
                        print('BOB_WEEKEND_ARCHIVE error='+type(exc).__name__,flush=True)
                time.sleep(300)
        _worker=threading.Thread(target=run,daemon=True,name='bob-weekend-archive')
        _worker.start()
