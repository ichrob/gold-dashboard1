"""Manual sizing rehearsal on a separate PostgreSQL server; no production writes.

Archives are modeled in session-temporary tables, not uploaded or activated.
Measures rebuilt indexes and heap/TOAST; never claims provider-volume savings.
All test data disappear on session close. No scheduler or HTTP entry point.
"""
import hashlib
import json
import os
import re
import time
import resource
from pathlib import Path
from datetime import datetime, timezone

import psycopg
from psycopg import sql

import evidence_archive as archive
from drive_evidence_archive import verify_restore_isolation

TABLES = {
    'bob_decision_audit': ('recorded_at', 'products'),
    'bob_diagnostic_history': ('recorded_at', None),
    'bob_metric_checks': ('checked_at', None),
    'bob_decision_outcomes': (None, None),
    'bob_shadow_study_events': ('at', None),
}
TAG = '_bobSizingArchiveV1'
MAX_TABLE = 180_000_000
MAX_RAW = 700_000_000
HASH_BYTES = 32_000_000


def memory_guard():
    used=Path('/sys/fs/cgroup/memory.current')
    deadline=time.monotonic()+30
    while used.exists() and int(used.read_text())>420*1024*1024:
        if time.monotonic()>=deadline:
            raise MemoryError('Shared service reserve remained exhausted')
        time.sleep(0.5)


def row_hash(row):
    value=json.dumps(row,ensure_ascii=False,separators=(',',':'),default=str).encode()
    if len(value)>2*1024*1024:
        raise ValueError('Row exceeds isolated memory budget')
    return hashlib.sha256(value).hexdigest().encode()+b'\n'


def column_expression(name, kind, alias=None):
    value=sql.Identifier(alias,name) if alias else sql.Identifier(name)
    # Preserve JSON numeric precision by transferring PostgreSQL's own text.
    return sql.SQL('({})::text').format(value) if kind in ('json','jsonb') else value


def report(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def size(conn):
    return conn.execute("SELECT pg_total_relation_size('pg_temp.sizing_data')").fetchone()[0]


def fingerprint(conn, query):
    def blocks():
        with conn.transaction(), conn.cursor(name='sizing_fingerprint') as cur:
            cur.execute(query)
            while True:
                memory_guard()
                rows=cur.fetchmany(32)
                if not rows: break
                for row in rows: yield row_hash(row)
    with open(os.devnull,'wb') as sink:
        return archive.canonical_copy(blocks(),sink,HASH_BYTES)


def run_table(name, source_dsn, target_dsn):
    clock, field = TABLES[name]
    with psycopg.connect(source_dsn, connect_timeout=10,
            application_name='bob_sizing_source_readonly',
            options='-c default_transaction_read_only=on -c statement_timeout=120000 -c lock_timeout=500') as src, \
         psycopg.connect(target_dsn, autocommit=True, connect_timeout=10,
            application_name='bob_isolated_sizing_only',
            options='-c statement_timeout=120000 -c lock_timeout=1000 -c work_mem=4096 -c maintenance_work_mem=16384 -c max_parallel_maintenance_workers=0') as dst:
        src.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        src.execute("SET LOCAL timezone='UTC'")
        dst.execute("SET timezone='UTC'")
        if dst.execute('SELECT pg_database_size(current_database())').fetchone()[0] > 50_000_000:
            raise ValueError('Restore database is not empty enough for bounded rehearsal')
        if not dst.execute("SELECT pg_try_advisory_lock(hashtext('bob_isolated_sizing_v1'))").fetchone()[0]:
            raise ValueError('Another sizing rehearsal is active')
        total = src.execute('SELECT pg_total_relation_size(%s::regclass)', ('public.'+name,)).fetchone()[0]
        if not 0 < total <= MAX_TABLE:
            raise ValueError('Table exceeds isolated rehearsal budget')
        now = src.execute('SELECT extract(epoch FROM now())').fetchone()[0]
        cols = src.execute("""SELECT a.attname,format_type(a.atttypid,a.atttypmod)
            FROM pg_attribute a WHERE a.attrelid=%s::regclass
            AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""", ('public.'+name,)).fetchall()
        if not cols or any(not archive.TYPE.fullmatch(t) for _, t in cols):
            raise ValueError('Unreviewed column type')
        indexes = src.execute("""SELECT pg_get_indexdef(indexrelid),indisvalid,indisready
            FROM pg_index WHERE indrelid=%s::regclass ORDER BY indexrelid""", ('public.'+name,)).fetchall()
        if any(not valid or not ready for _, valid, ready in indexes):
            raise ValueError('Source contains an incomplete index')
        fields = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(n), sql.SQL(t)) for n,t in cols)
        dst.execute(sql.SQL('CREATE TEMP TABLE sizing_data ({})').format(fields))
        copied = 0
        report({'phase':'copying-readonly-source','table':name,'sourceBytes':total})
        projection=sql.SQL(',').join(column_expression(n,t) for n,t in cols)
        def transfer():
            nonlocal copied
            with src.cursor(name='sizing_source') as reader:
                reader.execute(sql.SQL('SELECT {} FROM {}').format(projection,sql.Identifier('public',name)))
                while True:
                    memory_guard()
                    rows=reader.fetchmany(32)
                    if not rows: break
                    # Each target COPY is bounded to one small batch too.
                    with dst.cursor().copy('COPY sizing_data FROM STDIN') as writer:
                        for row in rows:
                            writer.write_row(row)
                            copied+=1
                            yield row_hash(row)
                    if copied%4096==0: report({'phase':'copy-progress','table':name,'rows':copied})
        with open(os.devnull,'wb') as sink:
            original_hash=archive.canonical_copy(transfer(),sink,HASH_BYTES)
        # Release the source snapshot before any expensive test-only operation.
        src.rollback(); src.close()
        baseline_query=sql.SQL('SELECT {} FROM sizing_data').format(projection)
        baseline=fingerprint(dst,baseline_query)
        if original_hash!=baseline:
            raise ValueError('Copied originals differ')
        for number,(definition,_,_) in enumerate(indexes):
            match = re.fullmatch(r'CREATE (UNIQUE )?INDEX \S+ ON public\.'+name+r' (USING .+)', definition)
            if not match:
                raise ValueError('Unreviewed index definition')
            dst.execute(sql.SQL('CREATE {} INDEX {} ON sizing_data {}').format(
                sql.SQL('UNIQUE' if match[1] else ''),sql.Identifier('sizing_index_'+str(number)),sql.SQL(match[2])))
        dst.execute('VACUUM (ANALYZE, PARALLEL 0) sizing_data')
        rebuilt = size(dst)
        output = {'table':name,'sourceRelationBytes':total,'rebuiltRelationBytes':rebuilt,
                  'rows':baseline['rows'],'copyVerified':True,'scenarios':[]}
        report({'phase':'rebuilt','table':name,'bytes':rebuilt,'sourceBytes':total,'rows':baseline['rows']})
        if clock:
            dst.execute('CREATE TEMP TABLE sizing_archive (hash text PRIMARY KEY, original jsonb NOT NULL)')
            dst.execute('CREATE TEMP TABLE sizing_locations (hash text PRIMARY KEY, file_id text NOT NULL, sha256 text NOT NULL, row_index integer NOT NULL, verified_at timestamptz NOT NULL)')
            payload = "payload->'products'" if field else 'payload'
            hash_expr = "encode(sha256(convert_to(("+payload+")::text,'UTF8')),'hex')"
            for days in (14,7):
                limit = int((float(now)-days*86400)*1000) if clock=='checked_at' else datetime.fromtimestamp(float(now)-days*86400,timezone.utc)
                eligible = sql.SQL('{} < %s AND NOT (payload ? %s) AND octet_length(({} )::text)>512').format(sql.Identifier(clock),sql.SQL(payload))
                if field:
                    eligible += sql.SQL(" AND jsonb_typeof(payload->'products')='array'")
                dst.execute(sql.SQL('INSERT INTO sizing_archive SELECT DISTINCT {},{} FROM sizing_data WHERE {} ON CONFLICT DO NOTHING').format(sql.SQL(hash_expr),sql.SQL(payload),eligible),(limit,TAG))
                dst.execute("INSERT INTO sizing_locations SELECT hash,repeat('f',64),repeat('a',64),0,now() FROM sizing_archive ON CONFLICT DO NOTHING")
                pointer = sql.SQL("(payload-'products') || jsonb_build_object(%s::text,{})" if field else "jsonb_build_object(%s::text,{})").format(sql.SQL(hash_expr))
                dst.execute(sql.SQL('UPDATE sizing_data SET payload={} WHERE {}').format(pointer,eligible),(TAG,limit,TAG))
                before_vacuum = size(dst)
                dst.execute('VACUUM (FULL, ANALYZE) sizing_data')
                # TAG is a fixed developer-owned literal, never external SQL.
                resolved = sql.SQL("CASE WHEN d.payload ? {} THEN {} ELSE d.payload END").format(sql.Literal(TAG),
                    sql.SQL("(d.payload-{})||jsonb_build_object('products',a.original)").format(sql.Literal(TAG)) if field else sql.SQL('a.original'))
                select_cols = sql.SQL(',').join(sql.SQL('({})::text').format(resolved) if n=='payload' else column_expression(n,t,'d') for n,t in cols)
                query = sql.SQL('SELECT {} FROM sizing_data d LEFT JOIN sizing_archive a ON a.hash=d.payload->>{}').format(select_cols,sql.Literal(TAG))
                after = fingerprint(dst,query)
                if after!=baseline:
                    raise ValueError('Full reconstruction differs from original COPY')
                ledger = dst.execute("SELECT pg_total_relation_size('pg_temp.sizing_locations')").fetchone()[0]
                count,unique = dst.execute('SELECT (SELECT count(*) FROM sizing_data WHERE payload ? %s),(SELECT count(*) FROM sizing_archive)',(TAG,)).fetchone()
                result={'ageDays':days,'archivedRows':count,'distinctOriginals':unique,
                    'beforeVacuumBytes':before_vacuum,'compactedRelationBytes':size(dst),
                    'modeledLocationLedgerBytes':ledger,'reconstructionVerified':True,
                    'modelOnly':True,'archiveUploadVerified':False}
                output['scenarios'].append(result); report({'phase':'scenario','table':name,**result})
        return output


def main():
    if os.environ.get('BOB_ISOLATED_SIZING_CONFIRMED')!='1':
        raise ValueError('Explicit isolated rehearsal opt-in required')
    resource.setrlimit(resource.RLIMIT_AS,(192*1024*1024,192*1024*1024))
    memory_guard()
    source=os.environ['DATABASE_URL']; target=os.environ['BOB_ARCHIVE_RESTORE_DATABASE_URL']
    verify_restore_isolation(source,target)
    result={'scope':'isolated-sizing-model','productionRowsModified':False,
            'physicalProductionBytesFreed':0,'tables':[]}
    selected=os.environ.get('BOB_ISOLATED_SIZING_TABLE')
    if selected is not None and selected not in TABLES:
        raise ValueError('Unreviewed rehearsal table')
    for name in ([selected] if selected else TABLES):
        result['tables'].append(run_table(name,source,target))
    report(result)


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        import traceback
        report({'status':'stopped','errorType':type(exc).__name__,
                'codeLines':[frame.lineno for frame in traceback.extract_tb(exc.__traceback__)],
                'productionRowsModified':False})
        raise SystemExit(1)
