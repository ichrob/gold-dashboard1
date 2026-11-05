"""Safe, bounded expiry for unneeded handset list-image uploads.

Only an *unparsed*, expired attempt with a separate, newer, fully verified
ten-row list from the SAME device and SAME Zurich day can be removed.
Successfully imported/list-linked images, current OCR retries, unmatched
images, foreign devices and durable archive proofs remain untouched.

An expired source is not itself a verified archive. This garbage collector
does not authorize deletion or compression of evidence-bearing images.
"""
_MAX_ROWS = 8

def sweep_once(connect):
    """Run one small transaction; return aggregate counters, never source IDs.

    No background credentials, remote archive access, broad DELETE, or VACUUM
    FULL. A row locked by another worker is skipped, not waited on.
    """
    with connect() as conn:
        if not conn.execute(
                "SELECT to_regclass('bob_android_list_images')"
        ).fetchone()[0]:
            return dict(status='no-image-table', removed=0,
                        logicalPayloadBytes=0, physicalBytesFreed=None)
        rows=conn.execute("""
            WITH eligible AS (
                SELECT i.batch_id
                FROM bob_android_list_images AS i
                WHERE i.created_at < now() - interval '48 hours'
                  AND i.parsed_items IS NULL
                  AND i.import_receipt->>'stage' IN
                      ('waiting-memory','read-failed','fetch-failed','store-failed')
                  AND (i.processing_at IS NULL
                       OR i.processing_at < now() - interval '24 hours')
                  AND jsonb_typeof(i.payload->'images') = 'array'
                  AND NOT jsonb_path_exists(i.payload,
                         '$.images[*]."_bobPrivateImageRefV1"')
                  AND EXISTS (
                      SELECT 1 FROM bob_android_list_images AS replacement
                      WHERE replacement.token_hash=i.token_hash
                        AND replacement.batch_id<>i.batch_id
                        AND replacement.created_at>i.created_at
                        AND replacement.import_receipt->>'stage'='synced'
                        AND CASE WHEN jsonb_typeof(replacement.parsed_items)='array'
                            THEN jsonb_array_length(replacement.parsed_items)=10
                            ELSE false END
                        AND (replacement.created_at AT TIME ZONE 'Europe/Zurich')::date =
                            (i.created_at AT TIME ZONE 'Europe/Zurich')::date
                        -- A later ten-item list is not necessarily an exact
                        -- replacement for an unparsed earlier screenshot.
                        -- Permit deletion ONLY for bit-identical PNG data
                        -- in the same order, on the same authenticated device.
                        AND jsonb_typeof(replacement.payload->'images')='array'
                        AND jsonb_array_length(replacement.payload->'images')=
                            jsonb_array_length(i.payload->'images')
                        AND jsonb_array_length(i.payload->'images') BETWEEN 1 AND 4
                        AND jsonb_array_length(jsonb_path_query_array(
                            i.payload,'$.images[*].png'))=
                            jsonb_array_length(i.payload->'images')
                        AND jsonb_path_query_array(
                            replacement.payload,'$.images[*].png')=
                            jsonb_path_query_array(i.payload,'$.images[*].png')
                  )
                ORDER BY i.created_at, i.batch_id
                LIMIT %s
                FOR UPDATE OF i SKIP LOCKED
            )
            DELETE FROM bob_android_list_images AS i USING eligible
            WHERE i.batch_id=eligible.batch_id
            RETURNING pg_column_size(i.payload)
        """,(_MAX_ROWS,)).fetchall()
        conn.commit()
    # Logical payload lengths are not physically reclaimed Render volume.
    return dict(status='expired-obsolete-only',removed=len(rows),
                logicalPayloadBytes=sum(max(0,int(row[0])) for row in rows),
                physicalBytesFreed=None)
