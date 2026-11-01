"""Lossless, read-only evidence export. No deletion or production restore API.

COPY text retains PostgreSQL values (including bytea, numeric and JSON). An
isolated PostgreSQL restore must reproduce every byte of each sorted COPY file.
Credentials are environment-only; archives must stay in the private Drive folder.
"""
import argparse
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

VERSION = 'bob-evidence-archive-v3'
# Reviewed evidence only: never OAuth, passkeys, sessions, subscriptions or settings.
TABLES = frozenset('''bob_spot_observations bob_candle_evidence bob_candle_checkpoints
bob_comparison_predictions bob_comparison_truths bob_decision_audit bob_decision_outcomes
bob_future_predictions bob_future_truths bob_product_predictions bob_product_truths
bob_paper_cases bob_paper_control bob_paper_days bob_paper_products bob_paper_stop_studies
bob_precision_cases bob_precision_cohorts bob_precision_quotes bob_precision_events
bob_precision_learning bob_intraday_comparison bob_list_price_anchors bob_list_price_pairs
bob_manual_paper_observations bob_manual_paper_watch bob_research_replays
bob_strategy_lab_daily bob_strategy_lab_revisions bob_weekend_archive bob_zukunft_observations
bob_trade_comparisons bob_real_trade_price_curve bob_stop_target_tests bob_risk_paper_cases
bob_risk_paper bob_exit_quality_cases bob_exit_quality_protocol bob_adaptive_events
bob_improvement_daily bob_improvement_observations bob_improvement_protocol
bob_improvement_release_dossiers bob_improvement_reviews bob_improvement_state
bob_improvement_trials bob_hint_audit bob_resilience_runs bob_test_repairs
bob_rule_learning bob_rule_learning_samples bob_ranking_events bob_ranking_lifecycles
bob_ranking_samples bob_ranking_state bob_gap_models bob_source_reliability
bob_broker_venue_evidence bob_broker_venue_history bob_degiro_candidate_proofs
bob_degiro_product_audit bob_storage_samples bob_metric_checks
bob_diagnostic_history bob_real_trades bob_real_trade_events bob_research_enhancements
bob_research_transcripts bob_research_priorities bob_youtube_feed_archive bob_video_ocr'''.split())
TYPE = re.compile(r'^(?:text|boolean|smallint|integer|bigint|real|double precision|bytea|json|jsonb|date|uuid|numeric(?:\(\d+(?:,\d+)?\))?|character varying(?:\(\d+\))?|character(?:\(\d+\))?|timestamp(?:\(\d+\))? (?:with|without) time zone|time(?:\(\d+\))? (?:with|without) time zone|interval)(?:\[\])?$')
MAX_BYTES = 512 * 1024 * 1024  # compressed archive / remote download
MAX_RAW_BYTES = 4 * 1024 * 1024 * 1024  # streamed, never held together
SEGMENT_BYTES = 32 * 1024 * 1024


def selected_tables():
    from paper_portfolios import POLICIES, names
    # Keep an archived decision's exact content address and per-decision link
    # in the *same* reviewed evidence snapshot as bob_decision_audit.
    # These tables are optional before the first explicitly approved pilot.
    # A restored pointer without its ledger would be unresolvable history.
    cold_ledgers = {
        'bob_cold_metric_batches', 'bob_cold_analysis_batches',
        'bob_cold_observation_objects', 'bob_cold_observation_scan',
        'bob_cold_decision_product_objects', 'bob_cold_decision_product_refs',
        'bob_cold_decision_product_scan', 'bob_cold_decision_pilot_attempts',
    }
    return TABLES | cold_ledgers | {table for profile in POLICIES for table in names(profile).values()}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def copy_query(schema, table, columns):
    from psycopg import sql
    cols = sql.SQL(',').join(map(sql.Identifier, columns))
    # No production-server sort or temp spill. Canonicalize on worker scratch.
    return sql.SQL('COPY (SELECT {cols} FROM {table}) TO STDOUT').format(
        cols=cols, table=sql.Identifier(schema, table))


def settings(conn):
    conn.execute("SET LOCAL timezone='UTC'")
    conn.execute("SET LOCAL datestyle='ISO, YMD'")
    conn.execute("SET LOCAL intervalstyle='postgres'")
    conn.execute("SET LOCAL extra_float_digits=3")
    conn.execute("SET LOCAL bytea_output='hex'")
    conn.execute("SET LOCAL statement_timeout='120s'")
    conn.execute("SET LOCAL lock_timeout='3s'")


SORT_CHUNK_BYTES = 2 * 1024 * 1024
MAX_ROW_BYTES = 16 * 1024 * 1024


class ArchiveByteBudgetExceeded(ValueError):
    pass


class ArchiveRowBudgetExceeded(ValueError):
    pass


class ArchiveScratchSpaceInsufficient(ValueError):
    pass


def canonical_copy(blocks, output, limit):
    """Canonical COPY bytes with bounded worker-side merge sort, never DB sort."""
    size = rows = 0
    h = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix='bob-copy-sort-') as directory:
        if shutil.disk_usage(directory).free < 2 * limit + 32 * 1024 * 1024:
            raise ArchiveScratchSpaceInsufficient('Insufficient worker sort space')
        chunks = []; batch = []; batch_bytes = 0; pending = b''
        def flush():
            nonlocal batch, batch_bytes
            path = Path(directory) / str(len(chunks))
            with open(path, 'xb') as part:
                os.chmod(path, 0o600)
                part.writelines(sorted(batch))
            chunks.append(path); batch = []; batch_bytes = 0
        for block in blocks:
            block = bytes(block); size += len(block)
            if size > limit:
                raise ArchiveByteBudgetExceeded('Archive byte budget exceeded; no deletion allowed')
            data = pending + block
            lines = data.split(b'\n'); pending = lines.pop()
            if len(pending) > MAX_ROW_BYTES:
                raise ArchiveRowBudgetExceeded('COPY row exceeds bounded memory budget')
            for line in lines:
                if len(line) > MAX_ROW_BYTES:
                    raise ArchiveRowBudgetExceeded('COPY row exceeds bounded memory budget')
                line += b'\n'; rows += 1
                batch.append(line); batch_bytes += len(line)
                if batch_bytes >= SORT_CHUNK_BYTES: flush()
        if pending:
            raise ValueError('Incomplete COPY record')
        if batch: flush()
        # Each merge head can be a large row. Pairwise merge bounds open files
        # and memory, including when many COPY rows approach the row limit.
        serial = len(chunks)
        while len(chunks) > 1:
            merged = []
            for offset in range(0, len(chunks), 2):
                pair = chunks[offset:offset+2]
                if len(pair) == 1:
                    merged.append(pair[0]); continue
                path = Path(directory) / str(serial); serial += 1
                with open(pair[0], 'rb') as left, open(pair[1], 'rb') as right, open(path, 'xb') as dest:
                    os.chmod(path, 0o600)
                    dest.writelines(heapq.merge(left, right))
                for part in pair: part.unlink()
                merged.append(path)
            chunks = merged
        if chunks:
            with open(chunks[0], 'rb') as canonical:
                for block in iter(lambda: canonical.read(1024*1024), b''):
                    h.update(block); output.write(block)
    return dict(bytes=size, rows=rows, sha256=h.hexdigest())


def copy_out(conn, query, output, limit):
    with conn.cursor().copy(query) as copy:
        return canonical_copy(copy, output, limit)


def copy_segments(blocks, limit):
    """Yield one bounded on-disk segment at a time; never split a COPY row."""
    total = size = 0
    pending = b''
    with tempfile.TemporaryFile() as part:
        for block in blocks:
            block = bytes(block)
            total += len(block)
            if total > limit:
                raise ArchiveByteBudgetExceeded('Raw snapshot budget exceeded')
            lines = (pending + block).split(b'\n')
            pending = lines.pop()
            if len(pending) > MAX_ROW_BYTES:
                raise ArchiveRowBudgetExceeded('COPY row exceeds bounded memory budget')
            for line in lines:
                if len(line) > MAX_ROW_BYTES:
                    raise ArchiveRowBudgetExceeded('COPY row exceeds bounded memory budget')
                row = line + b'\n'
                if len(row) > SEGMENT_BYTES:
                    raise ArchiveRowBudgetExceeded('COPY row exceeds segment budget')
                if size and size + len(row) > SEGMENT_BYTES:
                    part.seek(0)
                    yield part
                    part.seek(0); part.truncate(0); size = 0
                part.write(row); size += len(row)
        if pending:
            raise ValueError('Incomplete COPY record')
        # Empty tables still have an explicit zero-row member in the manifest.
        if size or total == 0:
            part.seek(0)
            yield part


def export(dsn, destination, tables=None, schema='public', progress=None):
    import psycopg
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Never overwrite an existing archive')
    tables = selected_tables() if tables is None else set(tables)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < MAX_BYTES * 2:
        raise ValueError('Insufficient scratch space for bounded export')
    with tempfile.TemporaryDirectory(dir=destination.parent) as work:
        stage = Path(work) / 'archive.zip'
        manifest = dict(version=VERSION, createdAt=datetime.now(timezone.utc).isoformat(),
                        build=os.environ.get('RENDER_GIT_COMMIT', 'unknown'),
                        scope='reviewed-evidence-tables-not-full-database-backup',
                        sourceSchema=schema, tables=[], absentTables=[], evidenceDeleted=False,
                        deletionPermitted=False, restoreVerified=False)
        with psycopg.connect(dsn) as conn, zipfile.ZipFile(stage, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            settings(conn)
            manifest['sourceDatabase'] = conn.info.dbname
            manifest['postgresVersion'] = conn.info.server_version
            manifest['databaseBytes'] = conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
            existing = {r[0] for r in conn.execute('SELECT tablename FROM pg_tables WHERE schemaname=%s', (schema,))}
            manifest['absentTables'] = sorted(tables-existing)
            manifest['excludedTables'] = sorted(existing-tables)
            if not tables & existing:
                raise ValueError('No evidence tables found')
            remaining = MAX_RAW_BYTES
            for table in sorted(tables & existing):
                columns = conn.execute('''SELECT a.attname,format_type(a.atttypid,a.atttypmod)
                    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped
                    ORDER BY a.attnum''', (schema, table)).fetchall()
                if not columns or any(not TYPE.fullmatch(t) for _,t in columns):
                    raise ValueError('Unsupported column type; export stopped without deleting data')
                query = copy_query(schema, table, [c[0] for c in columns])
                with conn.cursor().copy(query) as copy:
                    for segment, part in enumerate(copy_segments(copy, remaining)):
                        filename = str(len(manifest['tables'])) + '.copy'
                        with z.open(filename, 'w') as out:
                            proof = canonical_copy(iter(lambda: part.read(1024*1024), b''), out, SEGMENT_BYTES)
                        remaining -= proof['bytes']
                        manifest['tables'].append(dict(name=table, segment=segment, columns=columns, file=filename, **proof))
                        if stage.stat().st_size > MAX_BYTES:
                            raise ArchiveByteBudgetExceeded('Compressed archive budget exceeded')
                        if progress:
                            progress('export-' + str((MAX_RAW_BYTES-remaining)//(1024*1024)) + '-MiB')
            z.writestr('manifest.json', json.dumps(manifest, sort_keys=True))
        if stage.stat().st_size > MAX_BYTES:
            raise ArchiveByteBudgetExceeded('Compressed archive budget exceeded')
        # Hard link is atomic and fails if another process created destination.
        os.chmod(stage, 0o600)
        os.link(stage, destination)
    return dict(sha256=digest(destination), **manifest)


def restore_check(archive, expected_sha256, restore_dsn, *, temporary_session=False):
    import psycopg
    from psycopg import sql
    if digest(archive) != expected_sha256:
        raise ValueError('Archive checksum mismatch')
    if Path(archive).stat().st_size > MAX_BYTES:
        raise ArchiveByteBudgetExceeded('Compressed archive budget exceeded')
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('Duplicate archive members')
        if sum(i.file_size for i in z.infolist()) > MAX_RAW_BYTES + 2*1024*1024:
            raise ValueError('Archive expands beyond byte budget')
        if z.getinfo('manifest.json').file_size > 2*1024*1024:
            raise ValueError('Manifest too large')
        manifest = json.loads(z.read('manifest.json'))
        if manifest.get('version') != VERSION or not manifest.get('tables'):
            raise ValueError('Invalid archive manifest')
        with psycopg.connect(restore_dsn) as conn:
            if conn.info.server_version // 10000 != manifest['postgresVersion'] // 10000:
                raise ValueError('Matching PostgreSQL major version required')
            if conn.info.dbname == manifest['sourceDatabase'] and not temporary_session:
                raise ValueError('Restore requires a separately named isolated test database')
            # Roll back each bounded segment to release its temporary relation
            # before the next, including PostgreSQL pending-delete disk files.
            for i, item in enumerate(manifest['tables']):
                settings(conn)
                conn.execute("SET LOCAL search_path = pg_temp, pg_catalog")
                if z.getinfo(item['file']).file_size > SEGMENT_BYTES:
                    raise ArchiveByteBudgetExceeded('Restore segment too large')
                if item['file'] != f'{i}.copy' or any(not TYPE.fullmatch(t) for _, t in item['columns']):
                    raise ValueError('Unsafe archive schema')
                name = 'bob_archive_restore_' + str(i)
                fields = sql.SQL(',').join(sql.SQL('{} {}').format(sql.Identifier(n), sql.SQL(t)) for n,t in item['columns'])
                conn.execute(sql.SQL('CREATE TEMP TABLE {} ({}) ON COMMIT DROP').format(sql.Identifier(name), fields))
                h = hashlib.sha256(); size = rows = 0
                with z.open(item['file']) as data, conn.cursor().copy(sql.SQL('COPY {} FROM STDIN').format(sql.Identifier(name))) as copy:
                    for block in iter(lambda: data.read(1024*1024), b''):
                        h.update(block); size += len(block); rows += block.count(b'\n'); copy.write(block)
                if (size, rows, h.hexdigest()) != (item['bytes'], item['rows'], item['sha256']):
                    raise ValueError('Table checksum or count mismatch')
                with open(os.devnull, 'wb') as sink:
                    restored = copy_out(conn, copy_query('pg_temp', name, [c[0] for c in item['columns']]), sink, SEGMENT_BYTES)
                if restored != {k:item[k] for k in ('bytes','rows','sha256')}:
                    raise ValueError('Restored PostgreSQL values differ from original export')
                conn.rollback()  # Release all objects and disk for this segment.
    return dict(version=VERSION, archiveSha256=expected_sha256, restoreVerified=True,
                verifiedAt=datetime.now(timezone.utc).isoformat(), tables=len({t['name'] for t in manifest['tables']}), segments=len(manifest['tables']),
                restoreIsolation='session-temporary-tables' if temporary_session else 'separate-database',
                rows=sum(t['rows'] for t in manifest['tables']), evidenceDeleted=False,
                deletionPermitted=False, scope=manifest['scope'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'verify'])
    parser.add_argument('path')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.action == 'export':
        result = export(os.environ['DATABASE_URL'], args.path)
    else:
        result = restore_check(args.path, args.sha256, os.environ['BOB_ARCHIVE_RESTORE_DATABASE_URL'])
    print(json.dumps(result, sort_keys=True))
