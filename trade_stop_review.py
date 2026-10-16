"""Append-only stop proposals and user-reported broker actions, never broker orders."""
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def stop_of(payload):
    value=(payload.get('planAfter') or {}).get('stop')
    return value if type(value) in (int,float) and math.isfinite(value) and value>0 else None

def read(conn,tid):
    events=conn.execute("""SELECT seq,recorded_at,kind,payload FROM bob_real_trade_events
      WHERE trade_id=%s AND kind IN ('observation','broker-stop-confirmation')
      ORDER BY seq DESC LIMIT 20001""",(tid,)).fetchall()
    snapshot=conn.execute('SELECT snapshot FROM bob_real_trades WHERE id=%s',(tid,)).fetchone()
    from trade_learning_review import window
    bounds=window(snapshot[0]) if snapshot else None
    truncated=len(events)>20000;events=list(reversed(events[:20000]))
    proposals=[];confirmations={};previous=None
    for seq,at,kind,p in events:
        if kind=='broker-stop-confirmation':
            confirmations.setdefault(p.get('recommendationSeq'),[]).append({**p,'recordedAt':at.isoformat()})
            continue
        if bounds and not bounds[0]<=at<=bounds[1]:continue
        stop=stop_of(p)
        if stop is None or stop==previous:continue
        previous=stop
        evidence=p.get('productEvidence') or {}
        proposals.append(dict(seq=seq,at=at.isoformat(),goldStop=stop,
          productStop=evidence.get('stop'),productPrice=evidence.get('price'),
          currency=evidence.get('currency'),sourceAt=evidence.get('spotAt'),
          fxAt=evidence.get('fxAt'),kind='model',brokerVerified=False))
    for row in proposals:
        row['confirmations']=confirmations.get(row['seq'],[])
        for action in row['confirmations']:
            action['reactionSeconds']=round((datetime.fromisoformat(action['at'])-datetime.fromisoformat(row['at'])).total_seconds(),1)
            proposed=row.get('productStop')
            if proposed is not None:action['differenceFromProposal']=round(action['price']-proposed,6)
    return {'rows':proposals[-300:],'truncated':truncated or len(proposals)>300}

def confirm(conn,raw):
    import real_trade_journal as journal
    if not isinstance(raw,dict):raise ValueError('Stopp-Bestätigung fehlt')
    tid=raw.get('tradeId');seq=raw.get('recommendationSeq')
    if not isinstance(tid,str) or type(seq) is not int or raw.get('action') not in ('set','filled'):
        raise ValueError('Trade, Stopp-Vorschlag oder Status ungültig')
    if raw.get('userConfirmed') is not True:raise ValueError('Ausdrückliche Nutzerbestätigung fehlt')
    proposal=conn.execute("""SELECT recorded_at,payload FROM bob_real_trade_events
      WHERE trade_id=%s AND seq=%s AND kind='observation'""",(tid,seq)).fetchone()
    trade=conn.execute('SELECT snapshot FROM bob_real_trades WHERE id=%s',(tid,)).fetchone()
    if not proposal or stop_of(proposal[1]) is None or not trade:raise ValueError('Stopp-Vorschlag nicht gefunden')
    currency=(trade[0].get('product') or {}).get('currency','EUR')
    if raw.get('currency')!=currency:raise ValueError('Produktwährung stimmt nicht')
    price=raw.get('price')
    if type(price) not in (float,int) or not math.isfinite(price) or price<=0:raise ValueError('Tatsächlicher Produktkurs fehlt')
    try:
        if raw.get('localAt') and raw.get('timezone')=='Europe/Zurich':
            local=datetime.fromisoformat(raw['localAt'])
            if local.tzinfo is not None:raise ValueError()
            at=local.replace(tzinfo=ZoneInfo('Europe/Zurich'))
            if at.utcoffset()!=at.replace(fold=1).utcoffset() or at.astimezone(timezone.utc).astimezone(at.tzinfo).replace(tzinfo=None)!=local:
                raise ValueError()
        else:
            at=datetime.fromisoformat(raw.get('at','').replace('Z','+00:00'))
        if at.tzinfo is None or at<proposal[0] or at>datetime.now(timezone.utc):raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('Zeit mit Zeitzone zwischen Vorschlag und jetzt erforderlich')
    data=dict(recommendationSeq=seq,action=raw['action'],price=price,currency=currency,
      at=at.isoformat(),source='Vom Nutzer bestätigt; kein unabhängiger Brokerabgleich',brokerVerified=False)
    journal.event(conn,tid,'broker-stop-confirmation',data)
    return {'ok':True,'brokerVerified':False,'ordersPlaced':False}
