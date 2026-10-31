import gzip
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

import cold_metrics as cold
import metric_quality


class Drive:
    def __init__(self):
        self.files = {}
        self.corrupt = False
        self.on_upload = None
        self.downloads = 0

    def upload(self, path, checksum):
        blob = Path(path).read_bytes()
        assert cold.digest(blob) == checksum
        file_id = 'file-' + uuid.uuid4().hex
        self.files[file_id] = blob
        if self.on_upload:
            self.on_upload()
        return file_id

    def download(self, file_id, destination, max_bytes=None):
        self.downloads += 1
        blob = b'corrupted' if self.corrupt else self.files[file_id]
        if len(blob) > max_bytes:
            raise ValueError('too large')
        Path(destination).write_bytes(blob)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        cold._CACHE.clear()
        cold._INDEX_CACHE.clear()
        self.drive = Drive()
        self.row = ['v', 'scope', 123, 456, {'unicode': 'äöß', 'nested': [None, True, 1.25, 9007199254740993]}]
        blob = gzip.compress(cold.encoded({'format': cold.FORMAT, 'rows': [self.row]}), mtime=0)
        self.drive.files['file-1'] = blob
        self.pointer = {cold.TAG: {'file': 'file-1', 'sha256': cold.digest(blob), 'index': 0,
                                  'rowSha256': cold.digest(cold.encoded(self.row))}}

    def test_restart_download_is_exact_and_callers_cannot_mutate_cache(self):
        result = cold.resolve(None, self.pointer, 'scope', drive=self.drive)
        self.assertEqual(result, self.row[4])
        result['nested'].append('changed')
        self.assertEqual(cold.resolve(None, self.pointer, 'scope', drive=self.drive), self.row[4])
        self.assertEqual(self.drive.downloads, 1)
        cold._CACHE.clear()
        self.assertEqual(cold.resolve(None, self.pointer, 'scope', drive=self.drive), self.row[4])
        self.assertEqual(self.drive.downloads, 2)

    def test_corrupt_missing_and_wrong_row_fail_closed(self):
        self.drive.corrupt = True
        with self.assertRaises(cold.ColdArchiveUnavailable):
            cold.resolve(None, self.pointer, drive=self.drive)
        self.drive.corrupt = False
        with self.assertRaises(cold.ColdArchiveUnavailable):
            cold.resolve(None, self.pointer, 'wrong-scope', drive=self.drive)
        self.pointer[cold.TAG]['rowSha256'] = '0' * 64
        with self.assertRaises(cold.ColdArchiveUnavailable):
            cold.resolve(None, self.pointer, drive=self.drive)
        cold._CACHE.clear()
        self.drive.files.clear()
        with self.assertRaises(cold.ColdArchiveUnavailable):
            cold.resolve(None, self.pointer, drive=self.drive)

    def test_decompression_is_bounded(self):
        blob = gzip.compress(b' ' * (cold.MAX_RAW + 1))
        self.drive.files['bomb'] = blob
        with self.assertRaises(cold.ColdArchiveUnavailable):
            cold.read_chunk(self.drive, 'bomb', cold.digest(blob))

    def test_hot_payload_needs_no_credentials(self):
        with patch.object(cold, 'runtime_drive', side_effect=AssertionError('no network')):
            self.assertEqual(cold.resolve(None, self.row[4]), self.row[4])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        cold._CACHE.clear()
        self.conn = psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'], autocommit=True)
        self.schema = 'cold_metrics_' + uuid.uuid4().hex
        self.conn.execute('CREATE SCHEMA ' + self.schema)
        self.conn.execute('SET search_path TO ' + self.schema)
        metric_quality.init(self.conn)
        cold.init(self.conn)
        self.now = 1_800_000_000_000
        self.old = self.now - 8 * 86400000
        self.drive = Drive()
        self.payload = {'checkedAt': self.old, 'at': self.old, 'metrics': {
            'e20': {'absoluteError': 0.0, 'status': 'matched'}},
            'original': [uuid.uuid4().hex for _ in range(80)]}
        self.conn.execute('INSERT INTO bob_metric_checks VALUES (%s,%s,%s,%s,%s::jsonb)',
            (metric_quality.VERSION, 'display:1m', self.old, self.old, cold.encoded(self.payload).decode()))
        self.conn.execute('INSERT INTO bob_metric_checks VALUES (%s,%s,%s,%s,%s::jsonb)',
            (metric_quality.VERSION, 'display:1m', self.now, self.now, cold.encoded(self.payload).decode()))

    def tearDown(self):
        self.conn.execute('DROP SCHEMA ' + self.schema + ' CASCADE')
        self.conn.close()

    def stored(self):
        return self.conn.execute('SELECT payload FROM bob_metric_checks WHERE bar_at=%s', (self.old,)).fetchone()[0]

    def test_report_lookups_and_original_values_equal_after_offload_and_restart(self):
        before = metric_quality.report(self.conn, self.now)
        result = cold.offload_batch(self.conn, self.drive, self.now)
        self.assertEqual(result['movedRows'], 1)
        self.assertTrue(result['readThroughVerified'])
        self.assertGreater(result['originalJsonBytes'], result['referenceJsonBytes'])
        self.assertIn(cold.COMPACT_TAG, self.stored())
        cold._CACHE.clear()
        cold._INDEX_CACHE.clear()
        with patch.object(cold, 'runtime_drive', return_value=self.drive):
            self.assertEqual(metric_quality.report(self.conn, self.now), before)
            self.assertEqual(cold.get(self.conn, metric_quality.VERSION, 'display:1m', self.old), self.payload)
        # A producer replay cannot recreate a full duplicate of an archived row.
        self.conn.execute('''INSERT INTO bob_metric_checks VALUES (%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT DO NOTHING''', (metric_quality.VERSION, 'display:1m', self.old, self.old, '{}'))
        self.assertIn(cold.COMPACT_TAG, self.stored())
        self.assertEqual(cold.offload_batch(self.conn, self.drive, self.now)['movedRows'], 0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM bob_metric_checks').fetchone()[0], 2)
        # Neither payloads nor references expire when outside the report window.
        metric_quality._prune_expired_checks(self.conn, self.now + 100 * 86400000)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM bob_metric_checks').fetchone()[0], 2)

    def test_corrupt_download_keeps_original_and_creates_no_receipt(self):
        self.drive.corrupt = True
        with self.assertRaises(cold.ColdArchiveUnavailable):
            cold.offload_batch(self.conn, self.drive, self.now)
        self.assertEqual(self.stored(), self.payload)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM bob_cold_metric_batches').fetchone()[0], 0)

    def test_concurrent_update_is_not_overwritten(self):
        def update():
            self.conn.execute("UPDATE bob_metric_checks SET payload='{}'::jsonb WHERE bar_at=%s", (self.old,))
        self.drive.on_upload = update
        self.assertEqual(cold.offload_batch(self.conn, self.drive, self.now)['movedRows'], 0)
        self.assertEqual(self.stored(), {})

    def test_failed_readthrough_rolls_back_replacement(self):
        with patch.object(cold, 'resolve', side_effect=cold.ColdArchiveUnavailable('test')):
            with self.assertRaises(cold.ColdArchiveUnavailable):
                cold.offload_batch(self.conn, self.drive, self.now)
        self.assertEqual(self.stored(), self.payload)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM bob_cold_metric_batches').fetchone()[0], 0)

    def test_no_silent_partial_report_when_drive_is_unavailable(self):
        cold.offload_batch(self.conn, self.drive, self.now)
        cold._CACHE.clear()
        self.drive.files.clear()
        with patch.object(cold, 'runtime_drive', return_value=self.drive):
            with self.assertRaises(cold.ColdArchiveUnavailable):
                metric_quality.report(self.conn, self.now)

    def test_small_payloads_save_real_jsonb_space_with_compact_reference(self):
        payload = {'checkedAt': self.old, 'metrics': {}, 'original': uuid.uuid4().hex * 4}
        self.conn.execute('UPDATE bob_metric_checks SET payload=%s::jsonb WHERE bar_at=%s',
                          (cold.encoded(payload).decode(), self.old))
        before = self.conn.execute('SELECT pg_column_size(payload) FROM bob_metric_checks WHERE bar_at=%s', (self.old,)).fetchone()[0]
        self.assertGreater(before, 192)
        self.assertLessEqual(before, 512)
        self.assertEqual(cold.offload_batch(self.conn, self.drive, self.now)['movedRows'], 1)
        after = self.conn.execute('SELECT pg_column_size(payload) FROM bob_metric_checks WHERE bar_at=%s', (self.old,)).fetchone()[0]
        self.assertLess(after, before)
        cold._CACHE.clear()
        cold._INDEX_CACHE.clear()
        with patch.object(cold, 'runtime_drive', return_value=self.drive):
            self.assertEqual(cold.get(self.conn, metric_quality.VERSION, 'display:1m', self.old), payload)

    def test_compact_reference_cannot_be_rebound_to_a_different_sql_identity(self):
        cold.offload_batch(self.conn, self.drive, self.now)
        self.conn.execute('UPDATE bob_metric_checks SET bar_at=bar_at+1 WHERE bar_at=%s', (self.old,))
        cold._CACHE.clear()
        cold._INDEX_CACHE.clear()
        with patch.object(cold, 'runtime_drive', return_value=self.drive):
            with self.assertRaises(cold.ColdArchiveUnavailable):
                cold.get(self.conn, metric_quality.VERSION, 'display:1m', self.old+1)

    def test_missing_compact_index_fails_closed_after_restart(self):
        cold.offload_batch(self.conn, self.drive, self.now)
        self.conn.execute('DELETE FROM bob_cold_metric_batches')
        cold._CACHE.clear()
        cold._INDEX_CACHE.clear()
        with patch.object(cold, 'runtime_drive', return_value=self.drive):
            with self.assertRaises(cold.ColdArchiveUnavailable):
                metric_quality.report(self.conn, self.now)


if __name__ == '__main__':
    unittest.main()
