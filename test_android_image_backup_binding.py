"""Synthetic only: encrypted PNG proof must bind to CURRENT exact source."""
import copy
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone

import android_image_backup_binding as binding
import android_image_backup_prepare as prep
from test_android_image_backup_prepare import ReadOnlyConnection
from test_android_image_recovery_bundle import original, A, B


class ExactArchiveBindingTests(unittest.TestCase):
    def fixture(self):
        now = datetime.now(timezone.utc)
        batch = original('1' * 32)
        connection = ReadOnlyConnection((
            now, batch, {'stage':'synced','count':10},
            [{'isin':'synthetic-only'}], now, 2))
        blob, digest = prep.pack_active_source_readonly(
            connection,batch['batchId'],A)
        sealed, cipher_sha = prep.seal_bundle(blob,digest,b'Q'*32)
        receipt = {
            'version':'bob-private-image-recovery-receipt-v1',
            'status':'independent-encrypted-original-verified',
            'verifiedAt':now.isoformat(),
            'archiveDriveFileId':'A'*24,
            'encryptedSha256':cipher_sha,
            'encryptedBytes':len(sealed),
            'originalBundleSha256':digest,
            'encryptionVerified':True,
            'remoteDownloadVerified':True,
            'independentServerVerified':True,
            'fullBatchRoundTripVerified':True,
            'allReferencesVerified':True,
            'sourcePreserved':True,
            'restoredImages':len(batch['images']),
            'sourceModified':False,
            'imageMigrationAuthorized':False,
            'deletionAuthorized':False,
            'diskBytesFreed':None,
        }
        return connection, batch, sealed, receipt, now

    def payload(self,receipt):
        return json.dumps(receipt,sort_keys=True,separators=(',',':'),
                          ensure_ascii=False).encode()

    def prove(self,c,batch,sealed,receipt,now,**updates):
        args=dict(conn=c,receipt_bytes=self.payload(receipt),ciphertext=sealed,
                  key=b'Q'*32,archive_file_id='A'*24,
                  batch_id=batch['batchId'],device_scope=A,now=now)
        args.update(updates)
        return binding.verify_current_source_binding(**args)

    def test_exact_original_binding_and_no_writes_or_production_authorization(self):
        c,batch,sealed,receipt,now=self.fixture()
        result=self.prove(c,batch,sealed,receipt,now)
        self.assertEqual(result['status'],'exact-active-original-binding-verified')
        self.assertEqual(result['imageCount'],1)
        self.assertTrue(result['originalAndMetadataUnchanged'])
        self.assertTrue(result['readOnly'])
        self.assertFalse(result['independentServerRestoreReverifiedHere'])
        self.assertFalse(result['keyEscrowVerified'])
        self.assertFalse(result['productionMigrationAuthorized'])
        self.assertFalse(result['originalDeletionAuthorized'])
        self.assertIsNone(result['diskBytesFreed'])
        self.assertEqual(sum(x[0].lstrip().startswith('SELECT')
                             for x in c.queries),2)
        self.assertTrue(all(x[0].lstrip().startswith('SELECT') or
                            x[0].startswith('SET LOCAL') for x in c.queries))
        serialized=json.dumps(result)
        for secret in ('synthetic-only','Q'*32,'A'*24,batch['batchId'],
                       receipt['originalBundleSha256']):
            self.assertNotIn(secret,serialized)

    def test_different_batch_device_and_file_id_fail(self):
        c,batch,sealed,receipt,now=self.fixture()
        for changes in ({'batch_id':'2'*32},
                        {'device_scope':B},
                        {'archive_file_id':'Z'*24}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.prove(c,batch,sealed,receipt,now,**changes)

    def test_modified_receipt_and_original_fail_closed(self):
        for field,value in (('restoredImages',2),('encryptionVerified',False),
                            ('remoteDownloadVerified',False),
                            ('sourceModified',True),('diskBytesFreed',1000),
                            ('imageMigrationAuthorized',True)):
            c,batch,sealed,receipt,now=self.fixture()
            receipt[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(
                    ValueError,"Private original image binding not verified"):
                self.prove(c,batch,sealed,receipt,now)
        c,batch,sealed,receipt,now=self.fixture()
        row=list(c.row)
        row[-1]=row[-1]+1
        c.row=tuple(row)
        with self.assertRaises(ValueError):
            self.prove(c,batch,sealed,receipt,now)

    def test_wrong_key_tampered_ciphertext_and_expired_attestation_rejected(self):
        c,batch,sealed,receipt,now=self.fixture()
        with self.assertRaises(ValueError):
            self.prove(c,batch,sealed,receipt,now,key=b'X'*32)
        forged=bytearray(sealed)
        forged[-1] ^= 1
        with self.assertRaises(ValueError):
            self.prove(c,batch,bytes(forged),receipt,now)
        with self.assertRaises(ValueError):
            self.prove(c,batch,sealed,receipt,now=now+timedelta(days=2))

    def test_lost_or_revoked_source_cannot_be_approved(self):
        c,batch,sealed,receipt,now=self.fixture()
        c.row=None
        with self.assertRaises(ValueError):
            self.prove(c,batch,sealed,receipt,now)

    def test_receipt_must_be_canonical_small_and_private(self):
        c,batch,sealed,receipt,now=self.fixture()
        payload=json.dumps(receipt).encode()
        with self.assertRaises(ValueError):
            self.prove(c,batch,sealed,receipt,now,receipt_bytes=payload)
        with self.assertRaises(ValueError):
            self.prove(c,batch,sealed,receipt,now,receipt_bytes=b'{'*5000)
        with self.assertRaises(ValueError):
            self.prove(c,batch,sealed,receipt,now,
                       receipt_bytes=self.payload({**receipt,'extra':'no'}))


if __name__=='__main__':
    unittest.main()
