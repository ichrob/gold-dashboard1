"""Frozen research inputs and source: no provider refetch, no archived-code execution."""
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import zlib
import strategy_lab
import research_learning

VERSION = 'bob-research-replay-v1'
FILES = ('strategy_lab.py','research_learning.py','research_self_review.py')
MAX_RAW = 8_000_000
MAX_COMPRESSED = 500_000


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sources():
    return {name:Path(__file__).with_name(name).read_text() for name in FILES}


def make(rows, previous, day, checkpoint, report):
    package=dict(version=VERSION,scope='historical-and-forward-reference-research',
        day=day,checkpoint=checkpoint,rows=rows,previous=previous,expected={k:v for k,v in report.items() if k!='replay'},
        sources=sources(),python=platform.python_version(),build=os.environ.get('RENDER_GIT_COMMIT','unknown'),
        costBpsPerSide=report.get('costBpsPerSide',strategy_lab.COST_BPS_PER_SIDE))
    raw=canonical(package);compressed=zlib.compress(raw,9)
    if len(raw)>MAX_RAW or len(compressed)>MAX_COMPRESSED:raise ValueError('Replay package too large')
    return dict(id=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(compressed).decode(),encoding='zlib-base64')


def unpack(envelope):
    if not isinstance(envelope,dict) or envelope.get('encoding')!='zlib-base64':raise ValueError('Invalid replay package')
    data=envelope.get('data')
    if not isinstance(data,str) or len(data)>4*((MAX_COMPRESSED+2)//3):raise ValueError('Replay package too large')
    compressed=base64.b64decode(data,validate=True)
    if len(compressed)>MAX_COMPRESSED:raise ValueError('Replay package too large')
    decoder=zlib.decompressobj();raw=decoder.decompress(compressed,MAX_RAW+1)
    if len(raw)>MAX_RAW or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise ValueError('Invalid compressed replay')
    if hashlib.sha256(raw).hexdigest()!=envelope.get('id'):raise ValueError('Replay checksum mismatch')
    package=json.loads(raw)
    if package.get('version')!=VERSION or set(package.get('sources',{}))!=set(FILES):raise ValueError('Invalid replay schema')
    return package,compressed


def replay(envelope):
    package,_=unpack(envelope)
    # Never execute code delivered by a request or loaded from the database.
    # For an older engine, use the matching reviewed Git revision offline.
    if package['sources']!=sources():raise ValueError('Matching reviewed engine required')
    report=strategy_lab.run(package['rows'],cost_bps=package['costBpsPerSide'])
    report=research_learning.enrich(report,package['rows'],package['previous'],day=package['day'])
    report['learningCycle']['checkpoint']=package['checkpoint']
    return dict(matches=canonical(report)==canonical(package['expected']),report=report)


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_research_replays (
        id TEXT PRIMARY KEY, day DATE NOT NULL, recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        package BYTEA NOT NULL, row_count INTEGER NOT NULL, engine_version TEXT NOT NULL,
        scope TEXT NOT NULL)""")
    conn.execute('CREATE INDEX IF NOT EXISTS bob_research_replays_day ON bob_research_replays(day DESC,recorded_at DESC)')


def save(conn,envelope,day,report):
    package,compressed=unpack(envelope)
    expected={k:v for k,v in report.items() if k!='replay'}
    if package['day']!=str(day) or canonical(package['expected'])!=canonical(expected):raise ValueError('Replay/report mismatch')
    if package['sources']!=sources():raise ValueError('Replay engine mismatch')
    if replay(envelope)['matches'] is not True:raise ValueError('Replay result mismatch')
    conn.execute("""INSERT INTO bob_research_replays(id,day,package,row_count,engine_version,scope)
        VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
        (envelope['id'],day,compressed,len(package['rows']),report['version'],package['scope']))


def read(conn,identity):
    if not isinstance(identity,str) or len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('Invalid replay ID')
    row=conn.execute('SELECT package FROM bob_research_replays WHERE id=%s',(identity,)).fetchone()
    if not row:return dict(status='not-found',readOnly=True)
    envelope=dict(id=identity,data=base64.b64encode(bytes(row[0])).decode(),encoding='zlib-base64')
    unpack(envelope)
    return dict(status='observed',readOnly=True,replay=envelope)


def diagnostics(conn):
    rows=conn.execute('SELECT id,day,recorded_at,row_count,engine_version,scope FROM bob_research_replays ORDER BY day DESC,recorded_at DESC LIMIT 5').fetchall()
    size=conn.execute('SELECT pg_total_relation_size(%s::regclass),pg_database_size(current_database())',
                      ('bob_research_replays',)).fetchone()
    return dict(status='observed' if rows else 'no-records',readOnly=True,automaticExpiry=False,
        archiveBytes=size[0],databaseBytes=size[1],
        items=[dict(id=i,day=str(d),recordedAt=str(at),candles=n,engineVersion=v,scope=s) for i,d,at,n,v,s in rows])


if __name__ == '__main__':
    import sys
    envelope=json.loads(Path(sys.argv[1]).read_text())
    result=replay(envelope.get('replay',envelope))
    print(json.dumps(dict(matches=result['matches'],version=result['report']['version'])))
    raise SystemExit(0 if result['matches'] else 1)
