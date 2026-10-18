"""Isolated fault drills and evidence-prioritized research; no rule activation."""
import hashlib,json,os,subprocess,sys,time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

DRILLS=[('quotes','Kursausfall und Wiederanlauf','test_resilience_drills.Drills.test_quote_recovery'),
        ('transport','Verbindungsabbruch und erneuter Versuch','test_resilience_drills.Drills.test_transport_recovery'),
        ('restart','Neustart mit gespeichertem Überwachungsstand','test_resilience_drills.Drills.test_restart')]

def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS bob_resilience_runs (day TEXT NOT NULL,build TEXT NOT NULL,payload JSONB NOT NULL,PRIMARY KEY(day,build))')
    conn.execute('CREATE TABLE IF NOT EXISTS bob_hint_audit (id TEXT PRIMARY KEY,at BIGINT NOT NULL,payload JSONB NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_hint_audit_at ON bob_hint_audit(at)')
    conn.execute('CREATE TABLE IF NOT EXISTS bob_research_priorities (day TEXT PRIMARY KEY,at BIGINT NOT NULL,payload JSONB NOT NULL)')

def run_drills(database,now=None):
    now=int(time.time()*1000) if now is None else now
    day=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
    build=os.environ.get('RENDER_GIT_COMMIT','local')
    with database() as conn:
        if conn.execute('SELECT 1 FROM bob_resilience_runs WHERE day=%s AND build=%s',(day,build)).fetchone():return
    rows=[]
    # Strip service credentials. Only fixed, local unittest targets; no live fault injection.
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','PYTHONPATH')}
    for key,label,target in DRILLS:
        try:
            result=subprocess.run([sys.executable,'-m','unittest',target],cwd=Path(__file__).parent,env=env,timeout=20,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            status='passed' if result.returncode==0 else 'failed'
        except subprocess.TimeoutExpired:status='timeout'
        rows.append(dict(key=key,label=label,status=status))
    payload=dict(at=now,build=build,items=rows,scope='Isolierte Proben mit echten Überwachungsfunktionen und simulierten Ausfällen. Kein Beweis einer störungsfreien Liveverbindung.')
    with database() as conn:
        conn.execute('INSERT INTO bob_resilience_runs VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',(day,build,json.dumps(payload)))
        conn.commit()
    print('BOB_RESILIENCE persisted=true build='+build+' '+','.join(row['key']+':'+row['status'] for row in rows),flush=True)

def hint_record(sid,event,accepted,at):
    data=event.get('data') or {}
    if data.get('test'):return None
    generated=data.get('generatedAt');source=data.get('dataAt')
    valid=lambda x:type(x) in (int,float) and 0<x<=at
    lag=at-generated if valid(generated) else None
    source_age=at-source if valid(source) else None
    fingerprint=hashlib.sha256(json.dumps([str(sid),data.get('tradeId'),data.get('eventKind'),event.get('body')],sort_keys=True).encode()).hexdigest()
    return dict(at=at,kind=data.get('eventKind','unknown'),fingerprint=fingerprint,accepted=bool(accepted),
        latencyMs=lag,sourceAgeMs=source_age,
        timing='unknown' if lag is None else 'delayed' if lag>30000 else 'prompt',
        usefulness='unknown',receipt='unconfirmed')

def capture(conn,sid,events,accepted,at):
    for index,event in enumerate(events):
        row=hint_record(sid,event,accepted,at)
        if row:
            key=hashlib.sha256((str(time.time_ns())+str(index)+row['fingerprint']).encode()).hexdigest()
            conn.execute('INSERT INTO bob_hint_audit VALUES(%s,%s,%s::jsonb)',(key,at,json.dumps(row,allow_nan=False)))
    conn.execute('DELETE FROM bob_hint_audit WHERE at<%s',(at-30*86400000,))

def hint_summary(rows):
    seen={};repeats=0
    for row in sorted(rows,key=lambda r:r['at']):
        # Only accepted identical messages to the same device/trade count as repeat candidates.
        if row['accepted']:
            last=seen.get(row['fingerprint'])
            if last is not None and 0<=row['at']-last<=300000:repeats+=1
            seen[row['fingerprint']]=row['at']
    return dict(attempts=len(rows),accepted=sum(r['accepted'] for r in rows),failed=sum(not r['accepted'] for r in rows),
        prompt=sum(r['accepted'] and r['timing']=='prompt' for r in rows),delayed=sum(r['accepted'] and r['timing']=='delayed' for r in rows),
        unknown=sum(r['accepted'] and r['timing']=='unknown' for r in rows),repeats=repeats,
        note='Letzte 30 Tage, höchstens 10.000 Versuche. Rechtzeitig bedeutet technisch: Push-Dienst akzeptiert innerhalb 30 Sekunden nach Erzeugung. Kein Empfangsnachweis am Handy. Wiederholungen sind Prüfkandidaten, nicht automatisch Fehlalarme. Fachlicher Nutzen und verpasste Warnungen bleiben ohne unabhängigen Ereignisnachweis offen.')

def prioritize(report,drills,hints):
    items=[]
    def add(key,label,count,priority,experiment,measure):
        if count:items.append(dict(key=key,label=label,cases=count,priority=priority,experiment=experiment,measure=measure,status='Getrennter Test vorgeschlagen; keine automatische Regeländerung'))
    add('resilience','Ausfallsicherheit',sum(r['status']!='passed' for r in drills.get('items',[])),100,'Fehlgeschlagene Ausfallprobe reproduzieren und Wiederanlauf prüfen','Alle betroffenen Proben erfolgreich; keine verlorenen Warnungen')
    days=report.get('dailyReview',[]);today=days[-1] if days else {}
    add('data','Datenlücken',today.get('missingSlots',0)+today.get('invalidSlots',0),90,'Ursachen fehlender und ungültiger Messfenster getrennt prüfen','Mindestens 95 % gültige geplante Messfenster')
    add('delivery','Hinweisversand',hints.get('failed',0)+hints.get('delayed',0),80,'Versandfehler und Verzögerungen im isolierten Transporttest nachstellen','Weniger Fehler/Verzögerungen bei unveränderten kritischen Warnungen')
    add('duplicates','Wiederholte Hinweise',hints.get('repeats',0),60,'Identische Meldungen prüfen; Schutzwarnungen getrennt bewerten','Weniger unnötige Wiederholungen ohne fehlende Schutzwarnungen')
    add('costs','Fehlende Abrechnungsbelege',report.get('costEvidence',{}).get('missing',0),50,'Vorhandene Abschlüsse vervollständigen; keine zusätzlichen Trades','Vollständige Kosten-/Zeit-/Ausführungsbelege')
    add('missed','Verpasste positive Testfälle',report.get('assessment',{}).get('missedWinners',0),40,'Gesperrte positive Fälle nach Marktphase vergleichen; Variante separat prüfen','Weniger verpasste Fälle ohne mehr negative Fälle unter Stresskosten')
    return dict(items=sorted(items,key=lambda r:(-r['priority'],r['key'])),note='Eine Aufgabe pro Problemklasse, automatisch nach Sicherheit und Nachweislücken geordnet. Prioritätszahlen sind feste Arbeitsreihenfolge, keine gemessene finanzielle Schadenshöhe. Bestehende Versuche bleiben getrennt; neue Varianten werden nur vorgeschlagen.')

def read(conn,report,now):
    row=conn.execute('SELECT payload FROM bob_resilience_runs ORDER BY day DESC,payload->>\'at\' DESC LIMIT 1').fetchone()
    drills=row[0] if row else dict(items=[],scope='Noch keine gespeicherte Ausfallprobe.')
    drills['currentBuild']=drills.get('build')==os.environ.get('RENDER_GIT_COMMIT','local')
    drills['recent']=bool(drills.get('at') and 0<=now-drills['at']<=26*3600000)
    records=conn.execute('SELECT payload FROM bob_hint_audit WHERE at BETWEEN %s AND %s ORDER BY at DESC LIMIT 10001',(now-30*86400000,now)).fetchall()
    hints=hint_summary([r[0] for r in records[:10000]]);hints['truncated']=len(records)>10000
    return dict(drills=drills,hints=hints,priorities=prioritize(report,drills,hints))
