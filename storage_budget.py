"""Bounded storage observations for durable comparison evidence.

No research deletion, downsampling, paid scaling or order side effects.
Database size excludes WAL and other databases; never label it disk free space.
"""
import json
import threading
import time
from contextlib import nullcontext

# Confirmed production capacity; logical-size warnings remain distinct from disk use.
from storage_capacity import ALLOCATION_BYTES, CAUTION_BYTES, ACTION_BYTES
_NEXT=0
_LOCK=threading.Lock()


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_storage_samples (
        slot BIGINT PRIMARY KEY, sampled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        database_bytes BIGINT NOT NULL,
        relation_bytes JSONB NOT NULL DEFAULT '{}'::jsonb,
        writer_stats JSONB NOT NULL DEFAULT '{}'::jsonb)''')
    # Existing installations predate fixed per-relation snapshots.  Keep all
    # historical database-size samples and add only the missing observation
    # column; no evidence table or retention rule is changed.
    conn.execute("ALTER TABLE bob_storage_samples ADD COLUMN IF NOT EXISTS relation_bytes JSONB NOT NULL DEFAULT '{}'::jsonb")
    # Only ten fixed per-table counter tuples per half-hour slot, never raw data.
    conn.execute("ALTER TABLE bob_storage_samples ADD COLUMN IF NOT EXISTS writer_stats JSONB NOT NULL DEFAULT '{}'::jsonb")
    # One fixed, redacted comparison measurement.  This permits a later exact
    # 08:00/22:00 heap/index/TOAST and logical-byte pair without raw evidence.
    conn.execute("ALTER TABLE bob_storage_samples ADD COLUMN IF NOT EXISTS entry_exit_metrics JSONB NOT NULL DEFAULT '{}'::jsonb")
    # Tiny derived daily snapshots for five areas; no evidence or source deletion.
    __import__('storage_knowledge').init(conn)
    __import__('storage_case_results').init(conn)
    __import__('storage_history_evaluations').init(conn)
    __import__('storage_paper_evaluation').init(conn)
    __import__('storage_quality_evaluation').init(conn)
    __import__('storage_improvement_evaluation').init(conn)


def state(size):
    return 'action-required' if size>=ACTION_BYTES else 'caution' if size>=CAUTION_BYTES else 'below-budget-threshold'


def maybe_observe(conn,now=None):
    global _NEXT
    now=time.time() if now is None else now
    if now<_NEXT or not _LOCK.acquire(blocking=False):return
    try:
        _NEXT=now+1800
        # SAVEPOINT protects the diagnostic event if metadata maintenance is unavailable.
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='3s'")
            size=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
            relations=conn.execute('''SELECT relname,pg_total_relation_size(relid)
                FROM pg_stat_user_tables WHERE schemaname=current_schema()''').fetchall()
            relation_bytes={name:value for name,value in relations
                if isinstance(name,str) and isinstance(value,int) and value>=0}
            counters=__import__('storage_forensics').snapshot_counters(conn)
            try:
                # Nested transaction/savepoint keeps an optional aggregate
                # timeout from aborting the core capacity observation.
                with conn.transaction():
                    entry_exit=__import__('entry_exit_storage').sample(conn)
            except Exception:
                # Never lose the core capacity sample when the optional fixed
                # comparison aggregate is temporarily unavailable.
                entry_exit={}
            conn.execute('''INSERT INTO bob_storage_samples(slot,database_bytes,relation_bytes,writer_stats,entry_exit_metrics)
                VALUES(%s,%s,%s::jsonb,%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING''',
                (int(now//1800)*1800,size,json.dumps(relation_bytes,sort_keys=True),
                 json.dumps(counters,sort_keys=True),json.dumps(entry_exit,sort_keys=True)))
            # Only capacity telemetry expires. Never delete test/market evidence.
            conn.execute('DELETE FROM bob_storage_samples WHERE slot<%s',(int(now)-90*86400,))
        # Separate bounded savepoints: failed/slow summaries never undo telemetry,
        # block diagnostic delivery, or alter original market/test evidence.
        try:
            __import__('storage_knowledge').capture(conn, now)
        except Exception:
            pass
    except Exception:
        _NEXT=now+300
    finally:
        _LOCK.release()


def _sanitized_archive_attempt(row):
    """Never expose Drive file identifiers, auth metadata or original receipts."""
    if not row:
        return None
    stored = row[2] if isinstance(row[2], dict) else {}
    proof = stored.get('receipt') if isinstance(stored.get('receipt'), dict) else {}
    return {'status': row[0], 'updatedAt': str(row[1]),
            'phase': stored.get('phase'), 'errorType': stored.get('errorType'),
            'receiptPersistenceErrorType': stored.get('receiptPersistenceErrorType'),
            'encryptionVerified': proof.get('encryptionVerified') is True,
            'encryptionVersion': (proof.get('encryptionVersion') if
                                  proof.get('encryptionVersion') in
                                  ('none','aes-256-gcm-stream-v1') else None),
            'restoreVerified': proof.get('restoreVerified') is True,
            'remoteDownloadVerified': proof.get('remoteDownloadVerified') is True,
            'recoveryKeyVerified': proof.get('recoveryKeyVerified') is True,
            'restoreIsolation': (proof.get('restoreIsolation') if
                                 proof.get('restoreIsolation') ==
                                 'separate-database-instance' else None),
            'scope': (proof.get('scope') if proof.get('scope') ==
                      'reviewed-evidence-tables-not-full-database-backup' else None),
            'deletionPermitted': proof.get('deletionPermitted'),
            'evidenceDeleted': stored.get('evidenceDeleted') is True}


def archive_status(conn):
    """Show latest claim and last verified restore separately, including rollouts.

    Interrupted attempts must remain visible but must not hide an earlier
    verified original or turn that old receipt into fresh permission. No retry,
    ledger mutation, token exposure or external archive read is performed.
    """
    process = __import__('archive_worker').status()
    try:
        with conn.transaction() if hasattr(conn, 'transaction') else nullcontext():
            latest = conn.execute('''SELECT status,updated_at,receipt FROM bob_archive_attempts
                ORDER BY updated_at DESC LIMIT 1''').fetchone()
            verified = conn.execute('''SELECT status,updated_at,receipt FROM bob_archive_attempts
                WHERE status='verified' ORDER BY updated_at DESC LIMIT 1''').fetchone()
    except Exception:
        return process
    if not latest:
        return process
    output = {**process,
              'latestPersistedAttempt':_sanitized_archive_attempt(latest)}
    if verified:
        output['latestVerifiedAttempt'] = _sanitized_archive_attempt(verified)
    if latest[0] == 'running':
        # An old 'running' claim can mean a rolling service deploy interrupted
        # the process. Only mark it as a *review candidate*, not a proven error.
        from datetime import datetime, timezone
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                str(latest[1]).replace('Z','+00:00'))).total_seconds()
        except (ValueError, TypeError, OverflowError):
            age = None
        output['incompleteClaimReview'] = (
            'nonterminal-overdue' if age is not None and age > 600 else
            'running-or-recent' if age is not None else 'unknown')
    return output


def report(conn,now=None):
    now=time.time() if now is None else now
    size=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    # Catalog statistics and size functions, never full COUNT(*) scans of evidence.
    tables=conn.execute('''SELECT relname,pg_total_relation_size(relid),
        n_live_tup,n_dead_tup,last_autovacuum
        FROM pg_stat_user_tables WHERE schemaname=current_schema()
        ORDER BY pg_total_relation_size(relid) DESC LIMIT 12''').fetchall()
    samples=conn.execute('''SELECT slot,database_bytes,relation_bytes,writer_stats,
        entry_exit_metrics,sampled_at
        FROM bob_storage_samples ORDER BY slot DESC LIMIT 336''').fetchall()
    growth=None;days=None
    if len(samples)>1:
        last,first=samples[0],samples[-1]
        elapsed=last[0]-first[0]
        if elapsed>=86400:
            growth=(last[1]-first[1])*86400/elapsed
            if growth>0:days=max(0,(ACTION_BYTES-size)/growth)
    relation_samples=[sample for sample in samples
        if isinstance(sample[2],dict) and sample[2]]
    relation_deltas=[]
    relation_elapsed=None
    relation_first_at=None
    relation_last_at=None
    if len(relation_samples)>1:
        latest,baseline=relation_samples[0],relation_samples[-1]
        relation_last_at,relation_first_at=latest[0],baseline[0]
        relation_elapsed=relation_last_at-relation_first_at
        if relation_elapsed>0:
            names=set(latest[2])|set(baseline[2])
            for name in names:
                before=baseline[2].get(name)
                after=latest[2].get(name)
                if isinstance(before,int) and isinstance(after,int):
                    relation_deltas.append(dict(table=name,bytesBefore=before,
                        bytesAfter=after,bytesDelta=after-before))
            relation_deltas.sort(key=lambda item:(abs(item['bytesDelta']),item['table']),reverse=True)
    persisted_archive = archive_status(conn)
    image_module = __import__('android_image_backup_readiness')
    image_backup_readiness = image_module.report()
    # Boolean only: this SELECT never reads/returns PNGs, app text, ISINs,
    # token hashes or batch IDs, and cannot authorize an actual backup.
    image_backup_readiness['syncedSourceBatchCandidatePresent'] = (
        image_module.synced_source_candidate_present(conn))
    decision_preview = __import__('cold_decision_product_writer').preview(
        conn, now=now, archive_proof=persisted_archive)
    return dict(status='observed',readOnly=True,observedAt=now,
        databaseDiagnostics=__import__('database_diagnostics').report(conn),
        databaseBytes=size,configuredAllocationBytes=ALLOCATION_BYTES,
        budgetState=state(size),cautionBytes=CAUTION_BYTES,actionBytes=ACTION_BYTES,
        scope='logical-database-size-not-total-disk-use-or-free-space',
        estimatedGrowthBytesPerDay=round(growth) if growth is not None else None,
        estimatedDaysToActionThreshold=round(days,1) if days is not None else None,
        growthStatus='observed' if growth is not None else 'needs-at-least-24-hours',
        lastSampleAt=samples[0][0] if samples else None,
        relationGrowthStatus='observed' if relation_deltas else 'needs-two-fixed-snapshots',
        relationBaselineSampleAt=relation_first_at,
        relationLatestSampleAt=relation_last_at,
        relationElapsedSeconds=relation_elapsed,
        largestTableDeltas=relation_deltas[:12],
        featureAllocation=__import__('feature_storage').report(samples, now),
        storageForensics=__import__('storage_forensics').report(conn,samples),
        fixedSlotDaily=__import__('storage_daily_compact').report(samples),
        entryExitStorage=__import__('entry_exit_storage').report(conn,samples,now),
        androidImageDuplication=__import__('android_image_storage_audit').report(conn),
        androidImageAgeReview=__import__('android_image_age_review').report(conn),
        androidImageReferenceShadow=__import__('android_image_reference_shadow').report(conn),
        androidImageBackupReadiness=image_backup_readiness,
        largestTables=[dict(table=name,bytes=n,estimatedRows=live,estimatedDeadRows=dead,
            lastAutovacuum=str(vac) if vac else None) for name,n,live,dead,vac in tables],
        archiveWorker={**persisted_archive, 'originalImageBackupReadiness': image_backup_readiness},
        decisionProductsPreview=decision_preview,
        decisionProductsPilot=__import__('decision_product_pilot').status(conn),
        coldMetrics=__import__('cold_metrics').status(conn),
        layout=__import__('storage_layout').report(conn),
        knowledgeSummaries=__import__('storage_knowledge').report(conn),
        paperFinalReceipts=__import__('storage_case_results').report(conn),
        historyEvaluations=__import__('storage_history_evaluations').report(conn),
        paperDailyEvaluations=__import__('storage_paper_evaluation').report(conn),
        qualityEvaluations=__import__('storage_quality_evaluation').report(conn),
        improvementEvaluations=__import__('storage_improvement_evaluation').report(conn),
        renderVolume=__import__('render_disk_metrics').report(),
        coldAnalysis=__import__('cold_analysis').status(conn),
        coldTests=__import__('cold_test_evidence').status(conn),
        coldObservations=__import__('cold_observations').status(conn),
        offloadPolicy=__import__('storage_pressure').policy(size),
        evidenceDeleted=False,automaticPaidScaling=False,
        note='Cold metric payloads retain their keys and verified private archive references. '
             'Dead-row estimates do not measure reclaimable disk bytes. Capacity forecasts are estimates.')
