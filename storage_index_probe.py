"""Read-only source, disposable key-only index sizing on isolated restore DB."""
import hashlib
import json
import os
from pathlib import Path
import resource
import psycopg
from psycopg import sql
from drive_evidence_archive import verify_restore_isolation

INDEXES = [
 ('bob_decision_outcomes_pkey','bob_decision_outcomes', [('decision_id','text'),('horizon','integer')],True),
 ('bob_metric_checks_pkey','bob_metric_checks',[('version','text'),('scope','text'),('bar_at','bigint')],True),
 ('bob_diagnostic_history_trace','bob_diagnostic_history',[('trace_id','text'),('recorded_at','timestamp with time zone')],False),
 ('bob_diagnostic_history_pkey','bob_diagnostic_history',[('id','text')],True),
 ('bob_candle_evidence_pkey','bob_candle_evidence',[('source_key','text'),('open_time','bigint'),('fingerprint','text')],True),
]

def guard():
    if int(Path('/sys/fs/cgroup/memory.current').read_text()) > 420*1024*1024:
        raise MemoryError('Service reserve')

def digest(row):
    raw=json.dumps(row,default=str,separators=(',',':')).encode()
    if len(raw)>16384: raise ValueError('Oversized key')
    return int.from_bytes(hashlib.sha256(raw).digest(),'big')

def run():
    resource.setrlimit(resource.RLIMIT_AS,(192*1024*1024,192*1024*1024))
    source=os.environ['DATABASE_URL']; target=os.environ['BOB_ARCHIVE_RESTORE_DATABASE_URL']
    verify_restore_isolation(source,target)
    for index,table,cols,unique in INDEXES:
        guard()
        with psycopg.connect(source,options='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=500') as src, psycopg.connect(target,autocommit=True,options='-c statement_timeout=60000 -c work_mem=4096 -c maintenance_work_mem=16384 -c max_parallel_maintenance_workers=0') as dst:
            src.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            src.execute("SET LOCAL timezone='UTC'"); dst.execute("SET timezone='UTC'")
            if dst.execute('SELECT pg_database_size(current_database())').fetchone()[0]>50000000: raise ValueError('Target not empty')
            if not dst.execute("SELECT pg_try_advisory_lock(hashtext('bob_isolated_sizing_v1'))").fetchone()[0]: raise ValueError('Busy')
            settings='SELECT datcollate,datctype,datlocprovider,datlocale FROM pg_database WHERE datname=current_database()'
            if src.execute(settings).fetchone()!=dst.execute(settings).fetchone(): raise ValueError('Collation mismatch')
            expected='CREATE '+('UNIQUE ' if unique else '')+'INDEX '+index+' ON public.'+table+' USING btree ('+', '.join(n for n,t in cols)+')'
            metadata=src.execute('SELECT pg_get_indexdef(indexrelid),indisvalid,indisready,pg_relation_size(indexrelid) FROM pg_index WHERE indexrelid=%s::regclass',('public.'+index,)).fetchone()
            if metadata[:3]!=(expected,True,True) or metadata[3]>16000000: raise ValueError('Index changed or exceeds budget')
            names=sql.SQL(',').join(sql.Identifier(n) for n,t in cols)
            dst.execute(sql.SQL('CREATE TEMP TABLE probe_keys ({})').format(sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(n),sql.SQL(t)) for n,t in cols)))
            count=total=0
            with src.cursor(name='keys') as cur:
                cur.execute(sql.SQL('SELECT {} FROM {}').format(names,sql.Identifier('public',table)))
                while True:
                    guard(); rows=cur.fetchmany(256)
                    if not rows: break
                    with dst.cursor().copy('COPY probe_keys FROM STDIN') as copy:
                        for row in rows:
                            total=(total+digest(row))%(1<<256); count+=1; copy.write_row(row)
                    if count>250000: raise ValueError('Row budget')
            src.rollback()
            actual=seen=0
            with dst.transaction(),dst.cursor(name='verify') as cur:
                cur.execute(sql.SQL('SELECT {} FROM probe_keys').format(names))
                while True:
                    guard(); rows=cur.fetchmany(256)
                    if not rows: break
                    for row in rows: actual=(actual+digest(row))%(1<<256); seen+=1
            if (count,total)!=(seen,actual): raise ValueError('Keys differ')
            dst.execute(sql.SQL('CREATE {} INDEX probe_index ON probe_keys ({})').format(sql.SQL('UNIQUE' if unique else ''),names))
            size=dst.execute("SELECT pg_relation_size('pg_temp.probe_index')").fetchone()[0]
            print(json.dumps(dict(index=index,rows=count,sourceBytes=metadata[3],rebuiltBytes=size,potentialSavingBytes=metadata[3]-size,keysVerified=True,productionRowsModified=False)),flush=True)

if __name__=='__main__':
    try: run()
    except Exception as e:
        print(json.dumps({'status':'stopped','errorType':type(e).__name__}),flush=True)
        raise SystemExit(1)
