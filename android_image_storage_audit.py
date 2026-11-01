"""Privacy-preserving bounded Android screenshot duplication evidence.

Only aggregate lengths and candidate equality groups leave PostgreSQL.
No raw PNG/base64, hashes, account, device, batch or product identifiers
are returned. This is read-only diagnostics, never a deduplication writer.
"""
import threading
import time

_SAMPLE_BATCHES = 8
_CACHE_SECONDS = 900
_lock = threading.Lock()
_cache = None
_cached_at = 0

# A fixed, small indexed recent-batch sample. Every eligible PNG candidate
# was previously limited to two million encoded characters by android_list.
# MD5 grouping is an exploratory candidate, NOT an exact-identical-image
# proof suitable for rewriting rows or changing retention. Collision-safe
# deduplication would require cryptographic checks AND bytewise read-through.
_SQL = """WITH newest AS MATERIALIZED (
    SELECT payload FROM bob_android_list_images
    WHERE created_at >= now()-interval '24 hours'
    ORDER BY created_at DESC LIMIT 8
), selected AS MATERIALIZED (
    SELECT octet_length(img.image->>'png')::bigint encoded_bytes,
           md5(img.image->>'png') fingerprint
    FROM newest n CROSS JOIN LATERAL
      jsonb_array_elements(
        CASE WHEN jsonb_typeof(n.payload->'images')='array'
             THEN n.payload->'images' ELSE '[]'::jsonb END
      ) AS img(image)
    WHERE jsonb_typeof(img.image)='object'
      AND jsonb_typeof(img.image->'png')='string'
      AND octet_length(img.image->>'png') BETWEEN 1 AND 2000000
), groups AS MATERIALIZED (
    SELECT fingerprint,encoded_bytes,count(*)::bigint copies
    FROM selected GROUP BY fingerprint,encoded_bytes
)
SELECT
    (SELECT count(*)::bigint FROM newest),
    (SELECT count(*)::bigint FROM selected),
    (SELECT coalesce(sum(encoded_bytes),0)::bigint FROM selected),
    (SELECT coalesce(sum(copies-1),0)::bigint FROM groups WHERE copies>1),
    (SELECT coalesce(sum((copies-1)*encoded_bytes),0)::bigint
       FROM groups WHERE copies>1)
"""


def _counts(result, observed_at):
    if not isinstance(result,(tuple,list)) or len(result)!=5:
        return {'status':'not-observed','readOnly':True}
    if any(type(v) is not int or v < 0 for v in result):
        return {'status':'not-observed','readOnly':True}
    batches, images, chars, repeated, repeated_chars = result
    if (batches > _SAMPLE_BATCHES or images > batches*4
            or repeated > images or repeated_chars > chars):
        return {'status':'not-observed','readOnly':True}
    return {
        'status':'sampled' if batches else 'empty',
        'readOnly':True,
        'observedAt':observed_at,
        'method':'latest-eight-batches-md5-candidate-groups-no-raw-images',
        'sampledBatches':batches, 'sampleCapBatches':_SAMPLE_BATCHES,
        'additionalBatchesMayExist':batches == _SAMPLE_BATCHES,
        'sampledImages':images,
        'totalEncodedImageCharacters':chars,
        'candidateRepeatedImages':repeated,
        'candidateRepeatedEncodedCharacters':repeated_chars,
        'exactDuplicateProven':False,
        'reclaimableBytes':None,
        'diskBytesFreed':None,
        'note':'Only hashed base64 text groups within bounded recent batches. '
               'MD5 collision handling and exact PNG bytewise verification are '
               'required before any deduplication. Character counts are not '
               'PostgreSQL storage allocation, Render free space, or verified savings.'
    }


def report(conn, now=None):
    """Bounded read-only, 15-minute-cached sample, fail closed on DB errors."""
    global _cache, _cached_at
    at=time.time() if now is None else now
    if _cache is not None and 0 <= at-_cached_at < _CACHE_SECONDS:
        return dict(_cache)
    if not _lock.acquire(blocking=False):
        return {'status':'busy','readOnly':True,
                'reclaimableBytes':None,'diskBytesFreed':None}
    try:
        if _cache is not None and 0 <= at-_cached_at < _CACHE_SECONDS:
            return dict(_cache)
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='1500ms'")
                conn.execute("SET LOCAL lock_timeout='500ms'")
                row=conn.execute(_SQL).fetchone()
            result=_counts(row, at)
        except Exception:
            result={'status':'not-observed','readOnly':True,
                    'reclaimableBytes':None,'diskBytesFreed':None}
        _cache=dict(result)
        _cached_at=at
        return result
    finally:
        _lock.release()
