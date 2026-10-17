"""One bounded price-bias candidate, frozen before forward validation.

Only model display correction; original quotes and trading safeguards are immutable.
The identity includes ISIN, currency, bid side, source and all product terms.
"""
import copy
import hashlib
import json
import math
import random
from statistics import median

VERSION='price-bias-v1'
MINUTE=60000


def identity(product,source):
    return hashlib.sha256(json.dumps([VERSION,'bid',source,product.get('_precisionScope','list')]+[product.get(k) for k in
        ('isin','currency','direction','ratio','strike','ko')],sort_keys=True).encode()).hexdigest()


def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS bob_precision_control (id INTEGER PRIMARY KEY,paused BOOLEAN NOT NULL)')
    conn.execute('INSERT INTO bob_precision_control VALUES(1,FALSE) ON CONFLICT DO NOTHING')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_precision_learning (
        id TEXT PRIMARY KEY,state JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_precision_events (
        seq BIGSERIAL PRIMARY KEY,id TEXT NOT NULL,at BIGINT NOT NULL,payload JSONB NOT NULL)''')


def initial():return dict(version=VERSION,phase='training',factor=0.,rows=[],lastAt=0,events=[])


def errors(rows,factor):
    raw=[abs(r['quoted']/r['estimated']-1) for r in rows]
    fixed=[abs(r['quoted']/r['estimated']-1-factor) for r in rows]
    n=len(raw)
    return dict(count=n,rawMaePct=100*sum(raw)/n if n else None,
        correctedMaePct=100*sum(fixed)/n if n else None,
        rawMaxPct=100*max(raw) if n else None,correctedMaxPct=100*max(fixed) if n else None)


def improves(m):return bool(m['count'] and m['rawMaePct']>1e-6 and
    m['correctedMaePct']<=m['rawMaePct']*.9 and m['correctedMaxPct']<=m['rawMaxPct'])


def lower_bound(rows,factor):
    # Resample time blocks, not adjacent 30-second measurements as independent.
    blocks={}
    for r in rows:
        error=r['quoted']/r['estimated']-1
        blocks.setdefault(int(r['at']//(5*MINUTE)),[]).append(abs(error)-abs(error-factor))
    values=[sum(v)/len(v) for v in blocks.values()]
    if len(values)<12:return None
    rng=random.Random(73019)
    means=sorted(sum(rng.choices(values,k=len(values)))/len(values) for _ in range(2000))
    return means[19]*100


def transition(state,row):
    s=copy.deepcopy(state);at=row['at']
    if s.get('version')!=VERSION:return initial()
    if at<=s['lastAt'] or at-s['lastAt']<MINUTE:return s
    # Breaks prevent collecting a cherry-picked sparse validation window.
    if s['lastAt'] and at-s['lastAt']>120000:
        s['events'].append(dict(at=at,event='reset',reason='Datenlücke; Korrektur deaktiviert, neue Auswahl.'))
        s.update(phase='training',rows=[],factor=0.)
    s['lastAt']=at
    if s['phase']=='cooldown':
        if at<s['restartAt']:return s
        s.update(phase='training',rows=[],factor=0.)
    s['rows'].append({k:row[k] for k in ('at','quoted','estimated')})
    rows=s['rows'];span=rows[-1]['at']-rows[0]['at']
    if s['phase']=='training' and len(rows)>=30 and span>=29*MINUTE:
        factor=median(r['quoted']/r['estimated']-1 for r in rows)
        if abs(factor)>.03 or not improves(errors(rows,factor)):
            s.update(phase='cooldown',factor=0.,rows=[],restartAt=at+30*MINUTE)
            s['events'].append(dict(at=at,event='rejected',reason='Auswahl ohne stabilen Vorteil innerhalb ±3 %.'))
        else:
            s.update(phase='validation',candidate=factor,frozenAt=at,rows=[])
            s['events'].append(dict(at=at,event='frozen',factor=factor))
    elif s['phase']=='validation' and len(rows)>=60 and span>=59*MINUTE:
        m=errors(rows,s['candidate']);bound=lower_bound(rows,s['candidate'])
        passed=improves(m) and bound is not None and bound>0
        s.update(evidence=m,lowerBound99Pct=bound,rows=[],factor=s['candidate'] if passed else 0.,
                 phase='monitoring' if passed else 'cooldown',restartAt=at+30*MINUTE)
        s['events'].append(dict(at=at,event='adopted' if passed else 'rejected',evidence=m,lowerBound99Pct=bound))
    elif s['phase']=='monitoring' and len(rows)>=20:
        m=errors(rows,s['factor']);s['monitoring']=m;s['rows']=[]
        if not improves(m):
            s.update(phase='cooldown',factor=0.,restartAt=at+30*MINUTE)
            s['events'].append(dict(at=at,event='rollback',reason='Neue Kontrollwerte bestätigen den Vorteil nicht.',evidence=m))
    return s


def observe(conn,product,row):
    if any(type(row.get(k)) not in (float,int) or not math.isfinite(row[k]) or row[k]<=0 for k in ('at','quoted','estimated')):return
    if conn.execute('SELECT paused FROM bob_precision_control WHERE id=1 FOR SHARE').fetchone()[0]:return
    identity_key=identity(product,row['source'])
    conn.execute('INSERT INTO bob_precision_learning VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',(identity_key,json.dumps(initial())))
    state=conn.execute('SELECT state FROM bob_precision_learning WHERE id=%s FOR UPDATE',(identity_key,)).fetchone()[0]
    if row['at']<=state['lastAt'] or row['at']-state['lastAt']<MINUTE:return
    n=len(state['events']);s=transition(state,row)
    # Freeze the displayed candidate before observing this new price. Never fit
    # a correction to the same sample that is used to draw its apparent benefit.
    factor=(state.get('candidate') if state.get('phase')=='validation' else
            state.get('factor') if policy(state,row['at'])['usable'] else None)
    if row['at']-state.get('lastAt',0)>120000:factor=None
    point=dict(at=row['at'],raw=row['estimated'],original=row['quoted'],
        corrected=row['estimated']*(1+factor) if factor is not None else None,
        phase=state.get('phase'),source=row['source'],side='bid')
    s['chartHistory']=(state.get('chartHistory',[])+[point])[-720:]
    for event in s['events'][n:]:
        conn.execute('INSERT INTO bob_precision_events(id,at,payload) VALUES(%s,%s,%s::jsonb)',(identity_key,event['at'],json.dumps(event)))
    s['events']=s['events'][-30:];s['isin']=product['isin'];s['currency']=product['currency']
    s['source']=row['source'];s['lastRaw']=row['estimated'];s['lastQuoted']=row['quoted']
    conn.execute('UPDATE bob_precision_learning SET state=%s::jsonb WHERE id=%s',(json.dumps(s),identity_key))


def policy(state,now):
    usable=state.get('version')==VERSION and state.get('phase')=='monitoring' and 0<=now-state.get('lastAt',0)<=120000
    return dict(usable=usable,factor=state.get('factor',0.) if usable else 0.,phase=state.get('phase','training'),
        lastAt=state.get('lastAt'),count=(state.get('evidence') or {}).get('count',len(state.get('rows',[]))),
        evidence=state.get('evidence'),events=state.get('events',[]),source=state.get('source'),
        latestRaw=state.get('lastRaw') if 0<=now-state.get('lastAt',0)<=120000 else None,
        latestCorrected=state['lastRaw']*(1+state['factor']) if usable and state.get('lastRaw') else None,
        reason='Spätere Prüfwerte und laufende Kontrolle' if usable else 'Noch kein aktueller, unabhängig bestätigter Korrekturvorteil')


def for_product(conn,product,now):
    if conn.execute('SELECT paused FROM bob_precision_control WHERE id=1').fetchone()[0]:
        return dict(policy(initial(),now),phase='paused',reason='Automatische Kurskorrektur vom Nutzer pausiert')
    # Source is part of the identity; multiple sources never get pooled.
    rows=conn.execute("SELECT id,state FROM bob_precision_learning WHERE state->>'isin'=%s ORDER BY (state->>'lastAt')::bigint DESC LIMIT 48",(product.get('isin'),)).fetchall()
    compatible=[state for stored_id,state in rows if stored_id==identity(product,state.get('source'))]
    return policy(max(compatible,key=lambda s:s['lastAt']) if compatible else initial(),now)


def control(conn,enabled,now):
    if type(enabled) is not bool:raise ValueError('enabled muss true oder false sein')
    conn.execute('UPDATE bob_precision_control SET paused=%s WHERE id=1',(not enabled,))
    # Resume starts fresh evidence; it never resurrects a previously active fit.
    for identity_key,state in conn.execute('SELECT id,state FROM bob_precision_learning FOR UPDATE').fetchall():
        state.update(phase='training' if enabled else 'paused',factor=0.,rows=[],lastAt=0)
        conn.execute('UPDATE bob_precision_learning SET state=%s::jsonb WHERE id=%s',(json.dumps(state),identity_key))
    conn.execute('INSERT INTO bob_precision_events(id,at,payload) VALUES(%s,%s,%s::jsonb)',
        ('control',now,json.dumps(dict(event='resumed' if enabled else 'paused',at=now))))
    return dict(enabled=enabled)


def report(conn,now):
    paused=conn.execute('SELECT paused FROM bob_precision_control WHERE id=1').fetchone()[0]
    states=conn.execute('SELECT state FROM bob_precision_learning ORDER BY (state->>\'lastAt\')::bigint DESC LIMIT 24').fetchall()
    events=conn.execute('SELECT payload FROM bob_precision_events ORDER BY seq DESC LIMIT 20').fetchall()
    return dict(enabled=not paused,states=[dict(policy(s,now),isin=s.get('isin'),currency=s.get('currency'),chartHistory=s.get('chartHistory',[])[-240:]) for s, in states],
        events=[r[0] for r in events],note='Maximal ±3 % reine Modellkorrektur; 30 Auswahlwerte, 60 spätere Prüfwerte und mindestens 12 Zeitblöcke; danach jeweils 20 neue Kontrollwerte. Datenlücke oder Verschlechterung deaktiviert die Korrektur.')
