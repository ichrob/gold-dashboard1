"""Manual-only remote encrypted PNG backup and independent recovery proof.

NO application import, public endpoint, schedule, startup hook, environmental
flag, production source writer, data deletion or mass migration. An approved
operator must separately run this inside a protected Bob runtime with source
read access, independent restore server and private Drive runtime credentials.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

import android_image_backup_prepare as prep
import android_image_recovery_bundle as recovery
from drive_evidence_archive import verify_restore_isolation

_SOURCE_OPTIONS = '-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'
_MAX_SCRATCH = prep._MAX_CIPHER * 2 + 16 * 1024 * 1024


def _file_sha256(path, limit):
    digest = hashlib.sha256()
    size = 0
    with open(path, 'rb') as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b''):
            size += len(chunk)
            if size > limit:
                raise ValueError('Encrypted image download too large')
            digest.update(chunk)
    return digest.hexdigest(), size


def _restore_once(restore_dsn, blob, digest):
    """Different server verified upstream. CREATE/RESTORE then ROLLBACK test.

    One fresh schema exists only inside an uncommitted transaction on the
    separately verified restore instance. No production schema is targeted,
    and not even the test server retains private image rows after proof.
    """
    import psycopg
    schema = 'png_restore_' + uuid.uuid4().hex
    conn = psycopg.connect(restore_dsn, connect_timeout=10,
                           application_name='bob_png_isolated_restore')
    try:
        conn.execute('SET LOCAL statement_timeout=10000')
        conn.execute('SET LOCAL lock_timeout=1000')
        conn.execute('CREATE SCHEMA ' + schema)
        conn.execute('SET LOCAL search_path TO ' + schema)
        conn.execute("""CREATE TABLE bob_android_list_images (
            batch_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            payload JSONB NOT NULL,
            import_receipt JSONB,
            parsed_items JSONB,
            processing_at TIMESTAMPTZ,
            processing_attempts INTEGER NOT NULL)""")
        result = recovery.restore_to_isolated_test_schema(conn, blob, digest)
        if (result.get('fullBatchRoundTripVerified') is not True or
                result.get('sourcePreserved') is not True):
            raise ValueError('Exact original recovery not verified')
        # The isolated data never becomes permanent on this restore server.
        conn.rollback()
        missing = conn.execute('SELECT to_regnamespace(%s)', (schema,)).fetchone()
        if missing is None or missing[0] is not None:
            raise ValueError('Test restore schema was not rolled back')
        return result['restoredImages']
    finally:
        conn.rollback()
        conn.close()


def run_once(source_dsn, restore_dsn, drive, key, batch_id, device_scope,
             *, work_directory='/tmp/bob-png-private-backup'):
    """Explicit manual run of ONE unexpired batch, no source mutation.

    Drive adapter must be the established private GoogleDrive object with
    preflight/upload/download verification, never a public URL adapter.
    Only opaque aggregate flags may appear in a caller's status or receipt.
    """
    import psycopg

    if (type(source_dsn) is not str or not source_dsn or
            type(restore_dsn) is not str or not restore_dsn or
            type(key) is not bytes or len(key) != 32):
        raise ValueError('Private image backup configuration missing')
    # Both independent host identity probes and source auth must succeed
    # BEFORE exporting any private PNG or issuing an external Drive upload.
    if verify_restore_isolation(source_dsn, restore_dsn) != 'separate-database-instance':
        raise ValueError('Independent restore server not proven')
    if not all(callable(getattr(drive, name, None))
               for name in ('preflight', 'upload', 'download')):
        raise ValueError('Private verified Drive adapter required')
    # Private folder and 256 MiB reserve from the existing Drive preflight.
    drive.preflight(prep._MAX_CIPHER)
    with psycopg.connect(source_dsn, connect_timeout=10,
                         application_name='bob_png_source_readonly',
                         options=_SOURCE_OPTIONS) as conn:
        blob, source_sha = prep.pack_active_source_readonly(conn,batch_id,device_scope)
    encrypted, cipher_sha = prep.seal_bundle(blob,source_sha,key)

    directory = Path(work_directory)
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError('Private image scratch directory required')
    if shutil.disk_usage(directory).free < _MAX_SCRATCH:
        raise ValueError('Insufficient safe image backup scratch')
    with tempfile.TemporaryDirectory(prefix='bob-png-',dir=directory) as root:
        uploaded_path = Path(root) / 'image-recovery.aead'
        downloaded_path = Path(root) / 'image-recovery-remote.aead'
        with open(uploaded_path,'xb') as writer:
            os.chmod(uploaded_path,0o600)
            writer.write(encrypted)
        del encrypted
        file_id = drive.upload(uploaded_path,cipher_sha)
        if type(file_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', file_id):
            raise ValueError('Encrypted Drive receipt invalid')
        drive.download(file_id,downloaded_path,max_bytes=prep._MAX_CIPHER)
        downloaded_sha, downloaded_size = _file_sha256(downloaded_path,prep._MAX_CIPHER)
        if downloaded_sha!=cipher_sha:
            raise ValueError('Remote encrypted image mismatch')
        # Read ciphertext only; plaintext remains in protected memory.
        downloaded = downloaded_path.read_bytes()
        if len(downloaded)!=downloaded_size:
            raise ValueError('Remote encrypted image length differs')
        restored_blob = prep.open_sealed_bundle(downloaded,cipher_sha,source_sha,key)
        if restored_blob!=blob:
            raise ValueError('Original compressed backup bytes differ')
        restored_images = _restore_once(restore_dsn,restored_blob,source_sha)

        # The live batch and all mutable processing metadata must still match
        # the original snapshot before we may emit a full success receipt.
        with psycopg.connect(source_dsn,connect_timeout=10,
                             application_name='bob_png_source_recheck_readonly',
                             options=_SOURCE_OPTIONS) as conn:
            _, current_sha = prep.pack_active_source_readonly(conn,batch_id,device_scope)
        if current_sha!=source_sha:
            raise ValueError('Original image record changed since backup')
        receipt = {
            'version':'bob-private-image-recovery-receipt-v1',
            'status':'independent-encrypted-original-verified',
            'verifiedAt':datetime.now(timezone.utc).isoformat(),
            'archiveDriveFileId':file_id,
            'encryptedSha256':cipher_sha,
            'encryptedBytes':downloaded_size,
            'originalBundleSha256':source_sha,
            'encryptionVerified':True,
            'remoteDownloadVerified':True,
            'independentServerVerified':True,
            'fullBatchRoundTripVerified':True,
            'allReferencesVerified':True,
            'sourcePreserved':True,
            'restoredImages':restored_images,
            'sourceModified':False,
            'imageMigrationAuthorized':False,
            'deletionAuthorized':False,
            'diskBytesFreed':None,
        }
        # A success receipt is only published after ALL checks pass. It
        # contains no PNG, app text, device scope, session ID or account.
        receipt_path=Path(root)/'image-recovery-verified.json'
        receipt_data=json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()
        if len(receipt_data)>4096:
            raise ValueError('Private image receipt exceeds limit')
        with open(receipt_path,'xb') as writer:
            os.chmod(receipt_path,0o600)
            writer.write(receipt_data)
        receipt_sha=hashlib.sha256(receipt_data).hexdigest()
        receipt_id=drive.upload(receipt_path,receipt_sha)
        if type(receipt_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', receipt_id):
            raise ValueError('Private image verification receipt invalid')
        fetched_receipt=Path(root)/'image-recovery-verified-remote.json'
        drive.download(receipt_id,fetched_receipt,max_bytes=4096)
        receipt_check,size=_file_sha256(fetched_receipt,4096)
        if receipt_check!=receipt_sha or size!=len(receipt_data):
            raise ValueError('Private image verification receipt changed')
    # Return only sanitized proof flags; archive/receipt IDs and private
    # checksums remain in the verified private Drive receipt.
    return {k:v for k,v in receipt.items() if k not in
            ('archiveDriveFileId','encryptedSha256','originalBundleSha256',
             'encryptedBytes')}
