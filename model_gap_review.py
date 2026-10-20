"""Separate retrospective interpolation; never original evidence or training truth."""
import json
import math

VERSION = 'gap-model-v1'
STREAM = 'gold-api-xau-usd-v1'
MAX_GAP = 300000
NOTE = ('Nachträgliches Gold-Modell, keine Produktrendite oder Ausführung. '
        'Keine Aussage über Stop-/KO-Treffer zwischen den Messpunkten. '
        'Originalnachweise und Lernstatistik bleiben unverändert.')


def positive(x):
    return type(x) in (int, float) and math.isfinite(x) and x > 0


def interpolate(at, points):
    """Only bracketed gaps <=5 min. No extrapolation or invented error bounds."""
    if not positive(at):return None
    unique={}
    for t,p in points:
        t,p=float(t),float(p)
        if not positive(t) or not positive(p):continue
        if t in unique and unique[t]!=p:return None
        unique[t]=p
    before=[t for t in unique if t<=at];after=[t for t in unique if t>=at]
    if not before or not after:return None
    left,right=max(before),min(after)
    if right-left>MAX_GAP:return None
    price=unique[left] if left==right else unique[left]+(unique[right]-unique[left])*(at-left)/(right-left)
    return dict(at=at,price=price,kind='archived-point' if left==right else 'interpolated',
        source=STREAM,method='linear-bracket',inputs=[dict(at=t,price=unique[t]) for t in sorted({left,right})],
        gapMs=right-left,endpointRange=abs(unique[right]-unique[left]),
        uncertainty='unknown-between-observations',uncertaintyBound=None)


def estimate(record,horizon,start,end,now):
    if not start or not end:return dict(version=VERSION,status='unavailable',reason='Historische Stützpunkte fehlen oder Abstand über fünf Minuten.',calculatedAt=now)
    move=(end['price']/start['price']-1)*100
    direction=record.get('direction')
    return dict(version=VERSION,status='modelled',calculatedAt=now,horizon=horizon,
        direction=direction,start=start,end=end,goldMovePct=move,
        directionalMovePct=move if direction=='LONG' else -move if direction=='SHORT' else None,
        retrospectivelyCalculated=True,originalEvidenceComplete=False,usedForLearning=False,
        productReturnPct=None,actualExecution=False,stopOutcome='unknown',
        targetOutcome='unknown',koOutcome='unknown',pathComplete=False,note=NOTE)


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_gap_models (
        id TEXT PRIMARY KEY,checked_at BIGINT NOT NULL,payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_gap_models_checked ON bob_gap_models(checked_at)')


def point(conn,at):
    # Two bounded indexed lookups, never a full historical scan.
    rows=conn.execute('''(SELECT extract(epoch from quote_at)*1000,price FROM bob_spot_observations
        WHERE stream=%s AND quote_at BETWEEN to_timestamp(%s/1000.0) AND to_timestamp(%s/1000.0)
        ORDER BY quote_at DESC LIMIT 1)
        UNION ALL
        (SELECT extract(epoch from quote_at)*1000,price FROM bob_spot_observations
        WHERE stream=%s AND quote_at BETWEEN to_timestamp(%s/1000.0) AND to_timestamp(%s/1000.0)
        ORDER BY quote_at LIMIT 1)''',(STREAM,at-MAX_GAP,at,STREAM,at,at+MAX_GAP)).fetchall()
    return interpolate(at,rows)


def validate(conn,model):
    checks={}
    for key in ('start','end'):
        p=model[key]
        if p['kind']!='interpolated':continue
        row=conn.execute('''SELECT price FROM bob_spot_observations WHERE stream=%s
            AND quote_at=to_timestamp(%s/1000.0)''',(STREAM,p['at'])).fetchone()
        if row and positive(float(row[0])):
            actual=float(row[0]);checks[key]=dict(at=p['at'],original=actual,estimated=p['price'],
                error=p['price']-actual,absoluteErrorPct=abs(p['price']/actual-1)*100)
    return checks


def tick(conn,now):
    rows=conn.execute('''SELECT r.id,r.ref,a.payload,m.payload FROM bob_test_repairs r
        JOIN bob_decision_audit a ON a.id=r.ref->>'decision'
        LEFT JOIN bob_gap_models m ON m.id=r.id
        WHERE r.kind='signal' AND (r.status<>'recovered' OR m.payload->>'status'='modelled')
        AND (m.checked_at IS NULL OR m.checked_at<%s)
        ORDER BY m.checked_at NULLS FIRST,r.id LIMIT 24''',(now-3600000,)).fetchall()
    for key,ref,record,saved in rows:
        if saved and saved.get('status')=='modelled':
            # Freeze the initial model; compare later exact-time originals separately.
            result=dict(saved,validation=validate(conn,saved),lastComparedAt=now)
        else:
            at=record.get('recordedAt');horizon=ref.get('horizon')
            if not positive(at) or horizon not in (15,60,240) or at+horizon*60000>now:continue
            result=estimate(record,horizon,point(conn,at),point(conn,at+horizon*60000),now)
        conn.execute('''INSERT INTO bob_gap_models VALUES(%s,%s,%s::jsonb)
            ON CONFLICT(id) DO UPDATE SET checked_at=EXCLUDED.checked_at,payload=EXCLUDED.payload''',
            (key,now,json.dumps(result)))
    # Keep the same bounded retention as the source archive for repeated checks;
    # completed retrospective results remain attached to their unresolved cases.
    conn.execute('DELETE FROM bob_gap_models m WHERE NOT EXISTS(SELECT 1 FROM bob_test_repairs r WHERE r.id=m.id)')


def evidence_state(original_status, model_status):
    # A later verified original supersedes the retrospective model in the tally.
    if original_status == 'recovered':return 'original'
    if model_status == 'modelled':return 'estimated'
    if model_status == 'unavailable':return 'unavailable'
    return 'pending'


def evidence_summary(conn):
    rows=conn.execute("""SELECT r.status,m.payload->>'status',count(*)
        FROM bob_test_repairs r LEFT JOIN bob_gap_models m ON m.id=r.id
        WHERE r.kind='signal' GROUP BY 1,2""").fetchall()
    counts=dict(original=0,estimated=0,unavailable=0,pending=0)
    for original,model,count in rows:
        counts[evidence_state(original,model)]+=int(count)
    return dict(counts=counts,total=sum(counts.values()),
        scope='signal-repair-archive-only',
        note='Nur Signalprüfungen mit erfasster Datenlücke, je Zeithorizont ein Fall. '
             'Keine Gesamtbilanz aller Simulationen. Schätzungen zählen nicht als Originalreparatur.',
        labels=dict(original='Mit Originaldaten bestätigt',estimated='Mit Schätzdaten ausgewertet',
                    unavailable='Nicht auswertbar',pending='Nachprüfung ausstehend'))


def report(conn):
    counts=dict(conn.execute("SELECT payload->>'status',count(*) FROM bob_gap_models GROUP BY 1").fetchall())
    rows=conn.execute("SELECT payload FROM bob_gap_models WHERE payload->>'status'='modelled' ORDER BY checked_at DESC LIMIT 20").fetchall()
    return dict(version=VERSION,counts=counts,evidenceSummary=evidence_summary(conn),items=[r[0] for r in rows],limit=20,note=NOTE,
                maxGapSeconds=MAX_GAP//1000,originalEvidenceUnchanged=True)
