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
    if key not in CARD_KEYS and key not in ('chart:'+x for x in FRAMES):
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
            tf=key[6:]
            bars=item.get('bars')
            if not isinstance(bars,list) or not 2<=len(bars)<=180:
                return None
            previous=-1
            for b in bars:
                if not isinstance(b,dict) or b.get('instrument')!='XAU/USD' or b.get('isOpen') is not False:
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


def handle(conn, action, payload):
    if action=='write':
        items=payload.get('items')
        if not isinstance(items,dict) or len(items)>len(FRAMES)+len(CARD_KEYS):
            raise ValueError('Ungültige Wochenendarchivdaten')
        count=0
        for key,item in items.items():
            stamp=valid(key,item)
            if stamp is None:
                continue
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
            else:
                result['history'][key[6:]]=item['bars']
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
