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
                'decisionPayloadSample':decision_payload_sample(conn),
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


# Strictly bounded exploratory accounting. Audit JSON is part of several SQL
# predicates and direct readers, so it must NOT be replaced by cold pointers
# until every dependency can resolve the exact original.
_DECISION_FIELD_KEYS = (
    'decisionContext', 'reviewVariants', 'products', 'indicators',
    'marketOptimization', 'entryQuality', 'minuteEntry', 'earlyWarning',
    'analysisSnapshot', 'intraday', 'plan',
)


def decision_payload_sample(conn):
    """Aggregate child JSONB sizes for up to 8 immutable decisions, no raw values.

    Oldest and newest indexed keys are sampled separately. Child JSONB sizes
    are exploratory logical measures, NOT reclaimable TOAST or disk bytes.
    """
    try:
        with conn.transaction():
            rows = conn.execute("""WITH picked AS MATERIALIZED (
                  SELECT id FROM (
                    SELECT id FROM bob_decision_audit
                    ORDER BY recorded_at ASC,id ASC LIMIT 4
                  ) oldest
                  UNION
                  SELECT id FROM (
                    SELECT id FROM bob_decision_audit
                    ORDER BY recorded_at DESC,id DESC LIMIT 4
                  ) newest
                ), selected AS MATERIALIZED (
                  SELECT a.id,a.payload FROM bob_decision_audit a
                  JOIN picked p ON a.id=p.id
                )
                SELECT CASE WHEN e.key=ANY(%s::text[]) THEN e.key
                            ELSE 'other-fields' END AS field_group,
                       count(*),coalesce(sum(pg_column_size(e.value)),0),
                       max(pg_column_size(e.value)),
                       (SELECT count(*) FROM selected)
                FROM selected s CROSS JOIN LATERAL jsonb_each(s.payload) e
                GROUP BY 1 ORDER BY 3 DESC,1""",
                (list(_DECISION_FIELD_KEYS),)).fetchall()
        return {'status':'sampled' if rows else 'empty', 'readOnly':True,
                'method':'indexed-oldest-four-and-newest-four-max-eight-unique-rows',
                'sampledRecords':int(rows[0][4]) if rows else 0,
                'fields':[{'fieldGroup':field,'observedFieldValues':int(count),
                           'summedNestedBytes':int(total),
                           'maximumNestedBytes':int(maximum)}
                          for field,count,total,maximum,_ in rows],
                'reclaimableBytes':None,
                'note':'Only aggregate sizes of up to eight decisions, no payload contents. '
                       'JSONB child sizes are not physical TOAST usage, free space, '
                       'all-row coverage, or a permitted offload budget.'}
    except Exception:
        return {'status':'not-observed','readOnly':True,'reclaimableBytes':None}
