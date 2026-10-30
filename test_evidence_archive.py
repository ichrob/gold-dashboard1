import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zipfile

import evidence_archive as archive


class ArchiveSafety(unittest.TestCase):
    def test_segments_preserve_every_record_and_do_not_split_rows(self):
        raw = b'bbb\na\ncc\ncc\n\n'
        with patch.object(archive, 'SEGMENT_BYTES', 6):
            parts = [part.read() for part in archive.copy_segments(
                [raw[i:i+1] for i in range(len(raw))], len(raw))]
        self.assertEqual(b''.join(parts), raw)
        self.assertTrue(all(len(part) <= 6 and part.endswith(b'\n') for part in parts))
        self.assertEqual([p.read() for p in archive.copy_segments([], 0)], [b''])
        with self.assertRaises(archive.ArchiveByteBudgetExceeded):
            list(archive.copy_segments([raw], len(raw)-1))
        with patch.object(archive, 'SEGMENT_BYTES', 2):
            with self.assertRaises(archive.ArchiveRowBudgetExceeded):
                list(archive.copy_segments([b'big\n'], 4))

    def copied(self, blocks, limit=10000):
        class Copy:
            def __enter__(self): return iter(blocks)
            def __exit__(self, *args): pass
        class Connection:
            def cursor(self): return self
            def copy(self, query): return Copy()
        out = io.BytesIO()
        result = archive.copy_out(Connection(), 'query', out, limit)
        return out.getvalue(), result

    def test_external_sort_preserves_duplicates_across_blocks_and_merge_rounds(self):
        raw = b'z\\ntext\nb\na\nb\nc\n\\N\n\n'
        expected = b''.join(sorted(raw.splitlines(keepends=True)))
        # One-byte blocks exercise separators and escaped newline boundaries;
        # tiny chunks force multiple pairwise merge rounds and odd chunk counts.
        with patch.object(archive, 'SORT_CHUNK_BYTES', 2):
            data, proof = self.copied([raw[i:i+1] for i in range(len(raw))])
        self.assertEqual(data, expected)
        self.assertEqual(proof, dict(bytes=len(raw), rows=7,
                                    sha256=hashlib.sha256(expected).hexdigest()))

    def test_empty_copy_and_invalid_records(self):
        self.assertEqual(self.copied([])[0], b'')
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            self.copied([b'partial'])
        with patch.object(archive, 'MAX_ROW_BYTES', 3):
            for blocks in ([b'long\n'], [b'lo', b'ng']):
                with self.assertRaisesRegex(ValueError, 'memory budget'):
                    self.copied(blocks)

    def test_source_copy_does_not_sort_on_database(self):
        query = archive.copy_query('public', 'evidence', ['x', 'payload']).as_string()
        self.assertEqual(query, 'COPY (SELECT "x","payload" FROM "public"."evidence") TO STDOUT')

    def test_type_validation_rejects_executable_sql(self):
        for kind in ['jsonb','numeric(30,12)','timestamp with time zone','bytea','text[]']:
            self.assertTrue(archive.TYPE.fullmatch(kind))
        for kind in ['text); DROP TABLE x;--','public.secret','text DEFAULT 4','text\n']:
            self.assertFalse(archive.TYPE.fullmatch(kind))

    def test_secrets_are_not_selected_and_all_portfolios_are(self):
        tables = archive.selected_tables()
        self.assertFalse({'bob_oauth','subscriptions','bob_passkeys','bob_settings','bob_browser_sessions'} & tables)
        from paper_portfolios import POLICIES, names
        for profile in POLICIES:
            self.assertTrue(set(names(profile).values()) <= tables)

    def test_corruption_rejected_before_connect(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'bad.zip'; path.write_bytes(b'bad')
            with patch('psycopg.connect') as connect:
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    archive.restore_check(path, '0'*64, 'unused')
                connect.assert_not_called()

    def test_copy_budget_aborts(self):
        class Copy:
            def __enter__(self): return iter([b'one\n',b'two\n'])
            def __exit__(self,*args): pass
        class Connection:
            def cursor(self): return self
            def copy(self, query): return Copy()
        with self.assertRaisesRegex(ValueError,'budget'):
            archive.copy_out(Connection(), 'query', io.BytesIO(), 4)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'requires isolated PostgreSQL')
class ArchivePostgres(unittest.TestCase):
    def test_exact_roundtrip_and_source_unchanged(self):
        import psycopg
        from psycopg import sql
        dsn = os.environ['BOB_TEST_DATABASE_URL']
        schema = 'archive_test_' + uuid.uuid4().hex
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('CREATE TABLE {}.original (n numeric(30,12), raw bytea, payload jsonb, at timestamptz, note text, x double precision)').format(sql.Identifier(schema)))
            for note in ['line\nnext\t\\N', None, '', 'Gold € 中文', 'duplicate', 'duplicate']:
                conn.execute(sql.SQL('INSERT INTO {}.original VALUES (%s,%s,%s,%s,%s,%s)').format(sql.Identifier(schema)),
                    ('123456789012345678.123456789012', b'\x00\xff', '{"exact":12345678901234567890}', '2026-10-30 08:00:00.123456+01', note, float('inf')))
        try:
            with tempfile.TemporaryDirectory() as d:
                path = Path(d)/'original.zip'
                proof = archive.export(dsn, path, {'original','absent'}, schema)
                self.assertEqual(proof['tables'][0]['rows'], 6)
                self.assertEqual(proof['absentTables'], ['absent'])
                with self.assertRaisesRegex(ValueError,'isolated'):
                    archive.restore_check(path, proof['sha256'], dsn)
                temporary_receipt = archive.restore_check(path, proof['sha256'], dsn, temporary_session=True)
                self.assertTrue(temporary_receipt['restoreVerified'])
                self.assertEqual(temporary_receipt['restoreIsolation'], 'session-temporary-tables')
                # CI itself is isolated. Change ONLY the manifest's source label
                # to exercise the temp-table restore in this CI database.
                downloaded = Path(d)/'downloaded.zip'
                with zipfile.ZipFile(path) as src, zipfile.ZipFile(downloaded,'w') as dst:
                    for name in src.namelist():
                        data = src.read(name)
                        if name == 'manifest.json':
                            manifest = json.loads(data); manifest['sourceDatabase'] = 'production-source'
                            data = json.dumps(manifest).encode()
                        dst.writestr(name, data)
                receipt = archive.restore_check(downloaded, archive.digest(downloaded), dsn)
                self.assertTrue(receipt['restoreVerified'])
                self.assertFalse(receipt['deletionPermitted'])
                # Force the real COPY/restore path through several segments.
                segmented = Path(d)/'segmented.zip'
                with patch.object(archive, 'SEGMENT_BYTES', 256):
                    split_proof = archive.export(dsn, segmented, {'original'}, schema)
                    self.assertGreater(len(split_proof['tables']), 1)
                    self.assertEqual(sum(t['rows'] for t in split_proof['tables']), 6)
                    split_receipt = archive.restore_check(segmented, split_proof['sha256'], dsn, temporary_session=True)
                    self.assertEqual(split_receipt['tables'], 1)
                    self.assertEqual(split_receipt['rows'], 6)
                    self.assertEqual(split_receipt['segments'], len(split_proof['tables']))
                with psycopg.connect(dsn) as conn:
                    self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {}.original').format(sql.Identifier(schema))).fetchone()[0], 6)
                with self.assertRaisesRegex(ValueError,'overwrite'):
                    archive.export(dsn, path, {'original'}, schema)
                # A changed data stream with a valid outer hash still fails.
                bad = Path(d)/'bad.zip'
                with zipfile.ZipFile(downloaded) as src, zipfile.ZipFile(bad,'w') as dst:
                    for name in src.namelist():
                        data = src.read(name)
                        if name == '0.copy': data += data.splitlines(keepends=True)[0]
                        dst.writestr(name,data)
                with self.assertRaisesRegex(ValueError,'checksum or count'):
                    archive.restore_check(bad, archive.digest(bad), dsn)
        finally:
            with psycopg.connect(dsn) as conn:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__': unittest.main()
