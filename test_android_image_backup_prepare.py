"""No-production-write tests for one-batch image backup preparation and AEAD."""
import copy
import hashlib
import os
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone

import android_image_backup_prepare as prep
import android_image_recovery_bundle as recovery
from test_android_image_recovery_bundle import original, A, B


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class ReadOnlyConnection:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        if sql.lstrip().startswith('SELECT'):
            return Result(self.row)
        if sql.startswith('SET LOCAL'):
            return Result(None)
        raise AssertionError("Unexpected query: write attempted")


class BackupPreparationTests(unittest.TestCase):
    def fixture(self):
        batch = original('1' * 32)
        now = datetime.now(timezone.utc)
        row = (now, batch, {'stage': 'synced', 'count': 10},
               [{'isin': 'test-only'}], now, 2)
        return batch, ReadOnlyConnection(row)

    def test_complete_original_and_derived_references_without_writing(self):
        batch, conn = self.fixture()
        unchanged = copy.deepcopy(batch)
        blob, sha = prep.pack_active_source_readonly(conn, batch['batchId'], A)
        manifest = recovery.validate_recovery_bundle(blob, sha)
        self.assertEqual(manifest['original'], unchanged)
        self.assertEqual(manifest['sourceMetadata']['parsedItems'], [{'isin': 'test-only'}])
        self.assertEqual(manifest['sourceMetadata']['processingAttempts'], 2)
        self.assertEqual(manifest['batchId'], batch['batchId'])
        self.assertEqual(len(manifest['objects']), len(batch['images']))
        self.assertEqual(batch, unchanged)
        queries = [q[0] for q in conn.queries]
        self.assertEqual(sum(q.lstrip().startswith('SELECT') for q in queries), 1)
        self.assertTrue(all(q.startswith('SET LOCAL') or q.lstrip().startswith('SELECT')
                            for q in queries))
        self.assertIn('NOT d.revoked', queries[-1])
        self.assertIn("24 hours", queries[-1])

    def test_missing_or_wrong_scope_fails_without_leaking_private_details(self):
        batch, conn = self.fixture()
        conn.row = None
        with self.assertRaisesRegex(ValueError, 'Private image source backup unavailable'):
            prep.pack_active_source_readonly(conn, batch['batchId'], A)
        with self.assertRaises(ValueError):
            prep.pack_active_source_readonly(conn, batch['batchId'], 'bad-scope')

    def test_source_mutation_or_invalid_metadata_fails_closed(self):
        batch, conn = self.fixture()
        now = datetime.now(timezone.utc)
        conn.row = (now, batch, None, None, now, -1)
        with self.assertRaisesRegex(ValueError, 'Private image source backup unavailable'):
            prep.pack_active_source_readonly(conn, batch['batchId'], A)


class SealingTests(unittest.TestCase):
    def fixture(self):
        from test_android_image_recovery_bundle import BundleUnitTests
        unit = BundleUnitTests()
        return unit.make_bundle(unit.manifest())

    def test_encrypted_bytes_roundtrip_and_random_nonces(self):
        blob, sha = self.fixture()
        key = b'Q' * 32  # CI fixture only; never a production credential.
        sealed, digest = prep.seal_bundle(blob, sha, key)
        another, other_digest = prep.seal_bundle(blob, sha, key)
        self.assertNotEqual(sealed, another)
        self.assertNotEqual(digest, other_digest)
        self.assertEqual(prep.open_sealed_bundle(sealed, digest, sha, key), blob)
        self.assertNotIn(b'private trading app text', sealed)

    def test_wrong_key_and_tamper_even_with_rehashed_ciphertext_rejected(self):
        blob, sha = self.fixture()
        sealed, digest = prep.seal_bundle(blob, sha, b'K' * 32)
        with self.assertRaises(ValueError):
            prep.open_sealed_bundle(sealed, digest, sha, b'Z' * 32)
        altered = bytearray(sealed)
        altered[-1] ^= 1
        altered = bytes(altered)
        forged_hash = hashlib.sha256(altered).hexdigest()
        with self.assertRaises(ValueError):
            prep.open_sealed_bundle(altered, forged_hash, sha, b'K' * 32)
        with self.assertRaises(ValueError):
            prep.open_sealed_bundle(sealed, '0' * 64, sha, b'K' * 32)

    def test_missing_key_and_original_checksum_rejected(self):
        blob, sha = self.fixture()
        with self.assertRaises(ValueError):
            prep.seal_bundle(blob, sha, b'weak')
        sealed, digest = prep.seal_bundle(blob, sha, b'K' * 32)
        with self.assertRaises(ValueError):
            prep.open_sealed_bundle(sealed, digest, '0' * 64, b'K' * 32)


if __name__ == '__main__':
    unittest.main()
