"""Isolated PostgreSQL exercise for one image pointer CAS and exact rollback.

TEST-ONLY: never loaded by Bob startup, HTTP, storage worker, CLI or
background tasks. Requires a fresh png_restore_<uuid> schema populated
from a separately validated original/references recovery package.
No production writer, scheduled migration, source deletion or disk claim.
"""
import re
import time

import android_image_readthrough as reader
import android_image_persistent_shadow as shadow
import android_image_recovery_bundle as recovery
import android_list

_TEST_SCHEMA = re.compile(r'png_restore_[a-f0-9]{32}\Z')


def rehearse_test_schema(conn, blob, checksum):
    """Exercise exactly one CAS pointer transition then CAS restore in tests.

    The source schema must already contain a byte-exact restored original
    and staged device-scoped reference/object ledger, as supplied by the
    existing independent restoration format. It never initializes any
    schema and cannot operate against the normal public schema.
    """
    try:
        schema = conn.execute("SELECT current_schema()").fetchone()
        if (not schema or len(schema) != 1 or type(schema[0]) is not str
                or not _TEST_SCHEMA.fullmatch(schema[0])):
            raise ValueError("Isolated test schema required")
        manifest = recovery.validate_recovery_bundle(blob, checksum)
        bid, scope = manifest['batchId'], manifest['deviceScope']
        original = manifest['original']
        pointer = manifest['reference']
        metadata = manifest['sourceMetadata']
        from psycopg.types.json import Jsonb
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='8s'")
            conn.execute("SET LOCAL lock_timeout='500ms'")
            row = conn.execute("""SELECT i.created_at,i.payload,i.import_receipt,
                    i.parsed_items,i.processing_at,i.processing_attempts
                FROM bob_android_list_images i
                JOIN bob_android_diagnostic_devices d USING(token_hash)
                WHERE i.batch_id=%s AND i.token_hash=%s
                  AND NOT d.revoked AND d.expires_at>now()
                  AND i.created_at>now()-interval '24 hours'
                  AND i.created_at<=now()
                FOR UPDATE OF i""", (bid,scope)).fetchone()
            if not row or len(row)!=6:
                raise ValueError("No eligible source")
            uploaded, source, receipt, items, processed, attempts = row
            if (uploaded.isoformat()!=manifest['uploadedAt']
                    or source!=original
                    or receipt!=metadata['importReceipt']
                    or items!=metadata['parsedItems']
                    or (processed.isoformat() if processed else None)
                       !=metadata['processingAt']
                    or attempts!=metadata['processingAttempts']):
                raise ValueError("Original source changed")
            # The recovered objects and pointer ledger must be complete
            # before any temporary source pointer can be installed.
            if shadow._resolve(conn,bid,scope,original=(uploaded,original))!=original:
                raise ValueError("Recovered ledger differs")
            swapped = conn.execute("""UPDATE bob_android_list_images
                 SET payload=%s
                 WHERE batch_id=%s AND token_hash=%s
                   AND created_at=%s AND payload=%s
                 RETURNING payload""",
                (Jsonb(pointer),bid,scope,uploaded,Jsonb(original))).fetchone()
            if not swapped or swapped[0]!=pointer:
                raise ValueError("One-batch CAS transition failed")
            if reader.materialize(conn,bid,pointer)!=original:
                raise ValueError("Exact reference read-through failed")
            response=android_list.handle(conn,{'action':'list-get','batchId':bid},
                                         time.time())
            if (response['batch']!=original or response['items']!=items
                    or response['import']!=receipt):
                raise ValueError("Browser result changed")
            reverted = conn.execute("""UPDATE bob_android_list_images
                 SET payload=%s
                 WHERE batch_id=%s AND token_hash=%s
                   AND created_at=%s AND payload=%s
                 RETURNING payload""",
                 (Jsonb(original),bid,scope,uploaded,Jsonb(pointer))).fetchone()
            if not reverted or reverted[0]!=original:
                raise ValueError("Original CAS restoration failed")
            after = conn.execute("""SELECT created_at,payload,import_receipt,
                    parsed_items,processing_at,processing_attempts
                 FROM bob_android_list_images WHERE batch_id=%s
                   AND token_hash=%s""",(bid,scope)).fetchone()
            if after!=row:
                raise ValueError("Original image and metadata not recovered")
        return {
            'status':'isolated-cas-rollback-rehearsal-verified',
            'sourceRestored':True,
            'fullOriginalReadThroughVerified':True,
            'browserReaderVerified':True,
            'metadataPreserved':True,
            'rehearsedImages':len(original['images']),
            'productionWriterInstalled':False,
            'independentRemoteBackupVerifiedByThisTest':False,
            'migrationAuthorized':False,
            'deletionAuthorized':False,
            'diskBytesFreed':None,
        }
    except Exception:
        # Never disclose recovered PNGs, device identity or SQL arguments.
        raise ValueError("Isolated image CAS rehearsal invalid") from None
