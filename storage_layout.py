"""Read-only relation layout and explicitly sampled payload sizes; no free-space claims."""

def report(conn):
    try:
        with conn.transaction():
            rows = conn.execute('''SELECT c.relname,pg_total_relation_size(c.oid),
                pg_relation_size(c.oid),pg_indexes_size(c.oid),
                CASE WHEN c.reltoastrelid=0 THEN 0 ELSE pg_total_relation_size(c.reltoastrelid) END
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relkind='r' AND c.relname LIKE 'bob_%'
                ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 12''').fetchall()
            indexes = conn.execute('''SELECT t.relname,c.relname,pg_relation_size(c.oid),i.indisvalid
                FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
                JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=current_schema() AND t.relname LIKE 'bob_%'
                ORDER BY pg_relation_size(c.oid) DESC LIMIT 15''').fetchall()
        return {'status':'observed','readOnly':True,
                'tables':[{'table':name,'totalBytes':total,'heapBytes':heap,'indexBytes':idx,
                           'toastBytes':toast,'otherBytes':max(0,total-heap-idx-toast)}
                          for name,total,heap,idx,toast in rows],
                'indexes':[{'table':table,'index':name,'bytes':size,'valid':valid}
                           for table,name,size,valid in indexes],
                'diagnosticPayloadSample':diagnostic_sample(conn),
                'reclaimableBytes':None,
                'note':'Allocated relation sizes include live and reusable space; not a bloat measurement.'}
    except Exception:
        return {'status':'not-observed','readOnly':True,'reclaimableBytes':None}


def diagnostic_sample(conn):
    try:
        with conn.transaction():
            rows=conn.execute('''SELECT stage,count(*),round(avg(bytes)),max(bytes)
                FROM (SELECT stage,pg_column_size(payload) AS bytes
                      FROM bob_diagnostic_history TABLESAMPLE SYSTEM (2) REPEATABLE (42)
                      LIMIT 2000) sampled GROUP BY stage ORDER BY stage''').fetchall()
        return {'status':'sampled','method':'2-percent-block-sample-max-2000-rows',
                'stages':[{'stage':stage,'sampledRows':count,'averageStoredPayloadBytes':int(avg),
                           'maximumStoredPayloadBytes':maximum} for stage,count,avg,maximum in rows],
                'note':'Block sample is not an exact population count or savings estimate.'}
    except Exception:
        return {'status':'not-observed'}
