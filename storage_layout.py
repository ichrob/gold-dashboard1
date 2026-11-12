"""Read-only relation layout and explicitly sampled payload sizes; no free-space claims."""

import json
import threading

_DECISION_LOG_LOCK = threading.Lock()
_DECISION_LOGGED = False


def _log_decision_sample_once(sample):
    """Publish one sanitized size summary per process for private Render diagnostics.

    Bob's read-only MCP connection may project away newly added optional fields.
    Never print raw JSON values, identifiers, dates, credentials, or exceptions.
    """
    global _DECISION_LOGGED
    if not isinstance(sample, dict) or sample.get('status') != 'sampled':
        return
    with _DECISION_LOG_LOCK:
        if _DECISION_LOGGED:
            return
        allowed = set(_DECISION_FIELD_KEYS) | {'other-fields'}
        groups = []
        for item in sample.get('fields', []):
            if not isinstance(item,dict) or item.get('fieldGroup') not in allowed:
                return
            numbers = (item.get('observedFieldValues'),
                       item.get('summedNestedBytes'),item.get('maximumNestedBytes'))
            if any(type(n) is not int or n < 0 for n in numbers):
                return
            groups.append(dict(field=item['fieldGroup'],rows=numbers[0],
                               nestedBytes=numbers[1],maximumBytes=numbers[2]))
        count = sample.get('sampledRecords')
        if type(count) is not int or not 1 <= count <= 8 or len(groups)>len(allowed):
            return
        _DECISION_LOGGED = True
        print('BOB_DECISION_FOOTPRINT ' +
              json.dumps({'status':'sampled','sampledRecords':count,
                          'fields':groups,'diskBytesFreed':None},
                         sort_keys=True,separators=(',',':')),flush=True)


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
                'diagnosticRecentStageSample':recent_diagnostic_stages(conn),
                'diagnosticPayloadEqualitySample':diagnostic_payload_equality_sample(conn),
                'diagnosticPayloadByteSample':diagnostic_payload_byte_sample(conn),
                'decisionPayloadSample':decision_payload_sample(conn),
                'decisionProductsCohorts':decision_products_cohorts(conn),
                'reclaimableBytes':None,
                'note':'Allocated relation sizes include live and reusable space; not a bloat measurement.'}
    except Exception:
        return {'status':'not-observed','readOnly':True,'reclaimableBytes':None}


# Only persisted-stage metadata, not payloads, trace IDs, timings or source rows.
# Index-backed newest-record sample; a full day of INSERT operations is never inferred.
_DIAGNOSTIC_STAGE_SAMPLE_CAP = 512
_DIAGNOSTIC_STAGE_NAMES = frozenset((
    'input', 'analysis', 'analysis-failed', 'push', 'push-delivery',
    'paper-input', 'health', 'transport',
))


def recent_diagnostic_stages(conn):
    """Bounded stage mix for the latest persisted events, not write counters.

    The index on recorded_at DESC makes the small selection independent of the
    lifetime size of the diagnostic journal. Retention may already have removed
    older rows. Neither matching stages nor matching payloads mean duplicate
    events, so this observation must never drive retention or event skipping.
    """
    try:
        with conn.transaction():
            rows = conn.execute("""SELECT stage,count(*) FROM (
                SELECT stage FROM bob_diagnostic_history
                ORDER BY recorded_at DESC LIMIT %s
                ) AS newest GROUP BY stage ORDER BY stage""",
                (_DIAGNOSTIC_STAGE_SAMPLE_CAP,)).fetchall()
        if any(stage not in _DIAGNOSTIC_STAGE_NAMES
               or type(count) is not int or count <= 0
               for stage, count in rows):
            return {'status': 'not-observed', 'readOnly': True}
        total = sum(count for _, count in rows)
        if total > _DIAGNOSTIC_STAGE_SAMPLE_CAP:
            return {'status': 'not-observed', 'readOnly': True}
        return {
            'status': 'observed' if rows else 'observed-empty',
            'readOnly': True,
            'method': 'indexed-latest-persisted-events',
            'sampleCap': _DIAGNOSTIC_STAGE_SAMPLE_CAP,
            'sampledRows': total,
            'moreOlderEventsMayExist': total == _DIAGNOSTIC_STAGE_SAMPLE_CAP,
            'stages': [{'stage': stage, 'persistedSampleRows': count}
                       for stage, count in rows],
            'note': 'Newest persisted records only; stage counts are neither '
                    '24h INSERT counters nor a representative population ratio. '
                    'Original IDs, times and payloads are not returned. '
                    'No duplicate event, removable data or freed disk is proven.',
        }
    except Exception:
        return {'status': 'not-observed', 'readOnly': True}


# This is evidence of equal *stored JSONB values*, not of removable events.
# Event identities, source times and trace IDs remain distinct and are never returned.
_DIAGNOSTIC_EQUALITY_SAMPLE_CAP = 256
_DIAGNOSTIC_EQUALITY_STAGES = ('input', 'analysis')


def diagnostic_payload_byte_sample(conn):
    """Bounded SQL aggregate of actual JSONB payload bytes, never raw data."""
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='1500ms'")
            rows = conn.execute("""WITH recent AS MATERIALIZED (
                SELECT stage,payload FROM bob_diagnostic_history
                ORDER BY recorded_at DESC LIMIT 256
            ), eligible AS MATERIALIZED (
                SELECT payload FROM recent WHERE stage='input'
            ), grouped AS (
                SELECT payload,count(*) AS copies,
                       octet_length(payload::text) AS bytes
                FROM eligible GROUP BY payload
            )
            SELECT coalesce(sum(copies),0)::bigint,
                   coalesce(count(*),0)::bigint,
                   coalesce(sum(copies*bytes),0)::bigint,
                   coalesce(sum(bytes),0)::bigint
            FROM grouped""").fetchone()
        if not rows or any(type(v) is not int or v < 0 for v in rows):
            return {'status': 'not-observed', 'readOnly': True}
        total, distinct, original, shared = rows
        if total > 256 or distinct > total or shared > original:
            return {'status': 'not-observed', 'readOnly': True}
        return {'status': 'sampled', 'readOnly': True,
                'sampledInputRows': total, 'distinctPayloads': distinct,
                'originalPayloadJsonBytes': original,
                'sharedPayloadJsonBytes': shared,
                'payloadOnlyLogicalDifferenceBytes': original-shared,
                'physicalBytesFreed': None,
                'scope': 'bounded-input-json-aggregate-excludes-reference-overhead'}
    except Exception:
        return {'status': 'not-observed', 'readOnly': True}


def diagnostic_payload_equality_sample(conn):
    """Exact JSONB equality within the newest 256 persisted event rows only.

    Grouping is performed privately in PostgreSQL on a strictly bounded indexed
    selection. The returned aggregate contains no payload, hash, trace, ID or
    timestamp. Rows equal by JSONB alone are not duplicate source events;
    source-time/trace equality is measured separately but is STILL no permission
    to skip, delete, rewrite or coalesce an original event.
    """
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='1500ms'")
            rows = conn.execute("""WITH recent AS MATERIALIZED (
                    SELECT stage,payload,trace_id,observed_at
                    FROM bob_diagnostic_history
                    ORDER BY recorded_at DESC LIMIT %s
                ), eligible AS MATERIALIZED (
                    SELECT stage,payload,trace_id,observed_at FROM recent
                    WHERE stage=ANY(%s::text[])
                ), by_payload AS (
                    SELECT stage,payload,count(*) AS n FROM eligible
                    GROUP BY stage,payload
                ), by_context AS (
                    SELECT stage,payload,trace_id,observed_at,count(*) AS n
                    FROM eligible GROUP BY stage,payload,trace_id,observed_at
                ), payload_totals AS (
                    SELECT stage,sum(n)::bigint AS sampled,
                        count(*)::bigint AS distinct_payloads,
                        sum(n-1)::bigint AS repeated_payload_rows
                    FROM by_payload GROUP BY stage
                ), context_totals AS (
                    SELECT stage,sum(n-1)::bigint AS matching_context_rows
                    FROM by_context GROUP BY stage
                )
                SELECT p.stage,p.sampled,p.distinct_payloads,
                    p.repeated_payload_rows,
                    coalesce(c.matching_context_rows,0)::bigint
                FROM payload_totals p LEFT JOIN context_totals c
                    ON p.stage=c.stage ORDER BY p.stage""",
                (_DIAGNOSTIC_EQUALITY_SAMPLE_CAP,
                 list(_DIAGNOSTIC_EQUALITY_STAGES))).fetchall()
        stages = []
        overall = 0
        for stage, sampled, distinct, repeats, same_context in rows:
            numbers = (sampled, distinct, repeats, same_context)
            if (stage not in _DIAGNOSTIC_EQUALITY_STAGES
                    or any(type(v) is not int or v < 0 for v in numbers)
                    or not 1 <= distinct <= sampled
                    or repeats != sampled-distinct
                    or same_context > repeats):
                return {'status': 'not-observed', 'readOnly': True}
            overall += sampled
            stages.append({'stage': stage, 'sampledRows': sampled,
                           'distinctStoredJsonbPayloads': distinct,
                           'repeatedStoredJsonbRows': repeats,
                           'sameTraceTimeAndJsonbExtraRows': same_context})
        if overall > _DIAGNOSTIC_EQUALITY_SAMPLE_CAP or len(stages) > 2:
            return {'status': 'not-observed', 'readOnly': True}
        return {
            'status': 'sampled' if stages else 'observed-empty',
            'readOnly': True, 'sampleCapAllStages': _DIAGNOSTIC_EQUALITY_SAMPLE_CAP,
            'eligibleSampledRows': overall,
            'selection': 'newest-indexed-persisted-rows-before-stage-filter',
            'stages': stages, 'diskBytesFreed': None,
            'reclaimableBytes': None, 'migrationAuthorized': False,
            'note': 'Exactly equal stored JSONB is not evidence that distinct '
                    'events are redundant or removable. The smaller same-trace/'
                    'observed-time count is not proof of safe coalescing either. '
                    'Sample is neither a full 24h history nor a savings estimate. '
                    'No payload, trace, event ID, timestamp or hash is returned.',
        }
    except Exception:
        return {'status': 'not-observed', 'readOnly': True}


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
        result = {'status':'sampled' if rows else 'empty', 'readOnly':True,
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
        _log_decision_sample_once(result)
        return result
    except Exception:
        return {'status':'not-observed','readOnly':True,'reclaimableBytes':None}


def decision_products_cohorts(conn):
    """Read-only, index-bounded age cohorts of immutable decision products.

    Six ordered index windows each select no more than eight ids; overlapping
    rows across cohorts are explicitly counted. A separate cap-limited count reads
    only heap keys, never original JSON. No original JSON leaves SQL.
    Serialized JSON size describes the sample, never physical TOAST usage.
    """
    try:
        with conn.transaction():
            rows = conn.execute("""WITH picked AS MATERIALIZED (
                  SELECT 'oldest'::text cohort,id FROM (
                    SELECT id FROM bob_decision_audit
                    ORDER BY recorded_at,id LIMIT 8
                  ) old
                  UNION ALL
                  SELECT 'newest'::text cohort,id FROM (
                    SELECT id FROM bob_decision_audit
                    ORDER BY recorded_at DESC,id DESC LIMIT 8
                  ) recent
                  UNION ALL
                  SELECT 'before-24h'::text cohort,id FROM (
                    SELECT id FROM bob_decision_audit
                    WHERE recorded_at < now()-interval '24 hours'
                    ORDER BY recorded_at DESC,id DESC LIMIT 8
                  ) day_old
                  UNION ALL
                  SELECT 'before-7d'::text cohort,id FROM (
                    SELECT id FROM bob_decision_audit
                    WHERE recorded_at < now()-interval '7 days'
                    ORDER BY recorded_at DESC,id DESC LIMIT 8
                  ) week_old
                  UNION ALL
                  SELECT 'before-14d'::text cohort,id FROM (
                    SELECT id FROM bob_decision_audit
                    WHERE recorded_at < now()-interval '14 days'
                    ORDER BY recorded_at DESC,id DESC LIMIT 8
                  ) two_weeks
                  UNION ALL
                  SELECT 'before-30d'::text cohort,id FROM (
                    SELECT id FROM bob_decision_audit
                    WHERE recorded_at < now()-interval '30 days'
                    ORDER BY recorded_at DESC,id DESC LIMIT 8
                  ) month_old
                ), sized AS MATERIALIZED (
                  SELECT p.cohort,p.id,
                    octet_length(a.payload::text) AS whole_bytes,
                    CASE WHEN jsonb_typeof(a.payload->'products')='array'
                      THEN octet_length((a.payload->'products')::text)
                      ELSE 0 END AS product_bytes,
                    CASE WHEN jsonb_typeof(a.payload->'products')='array'
                      THEN jsonb_array_length(a.payload->'products')
                      ELSE 0 END AS product_count,
                    CASE WHEN jsonb_typeof(a.payload->'products')='array'
                      THEN a.payload->'products'
                      ELSE NULL END AS product_array
                  FROM picked p JOIN bob_decision_audit a ON a.id=p.id
                )
                SELECT cohort,count(*),coalesce(sum(whole_bytes),0),
                  coalesce(sum(product_bytes),0),coalesce(max(product_bytes),0),
                  count(*) FILTER (WHERE product_count>0),
                  coalesce(sum(product_count),0),
                  count(DISTINCT product_array) FILTER (WHERE product_count>0),
                  (SELECT count(DISTINCT id) FROM picked)
                FROM sized GROUP BY cohort ORDER BY cohort""").fetchall()
        # A bounded heap-only count distinguishes a stale pg_stat estimate
        # from thousands of live decisions, without reading their TOAST JSON.
        # Failure is isolated; the cohort sample remains available.
        try:
            with conn.transaction():
                observed_count = conn.execute("""SELECT count(*) FROM (
                    SELECT 1 FROM bob_decision_audit LIMIT 10001
                ) bounded""").fetchone()[0]
            if type(observed_count) is not int or observed_count < 0:
                observed_count = None
        except Exception:
            observed_count = None
        return dict(
            status='sampled' if rows else 'empty',
            readOnly=True,
            method='indexed-six-age-windows-max-eight-rows-each',
            maxSelectedRows=48,
            boundedRecordCount=observed_count,
            boundedRecordCountCap=10001,
            recordCountIsLowerBound=(observed_count == 10001) if observed_count is not None else None,
            uniqueSampledRecords=int(rows[0][8]) if rows else 0,
            cohorts=[
                dict(ageWindow=cohort,selectedRows=int(count),
                     totalJsonTextBytes=int(whole),
                     productsJsonTextBytes=int(products),
                     maximumProductsJsonTextBytes=int(maximum),
                     nonEmptyProductRows=int(nonempty),
                     numberOfProducts=int(items),
                     distinctNonEmptyArrays=int(unique))
                for cohort,count,whole,products,maximum,nonempty,items,unique,_ in rows
            ],
            reclaimableBytes=None,
            note='Overlapping age cohorts are not independent or a representative '
                 'population estimate. Serialized JSON text sizes are not live '
                 'TOAST storage, database free space, or an offload permission.'
        )
    except Exception:
        return {'status':'not-observed','readOnly':True,'reclaimableBytes':None}
