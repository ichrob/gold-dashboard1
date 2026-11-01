"""Privacy-preserving bounded Android screenshot duplication evidence.

Only aggregate lengths and candidate equality groups leave PostgreSQL.
No raw PNG/base64, hashes, account, device, batch or product identifiers
are returned. This is read-only diagnostics, never a deduplication writer.
"""
import base64
import hashlib
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
    ORDER BY created_at DESC,batch_id DESC LIMIT 8
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


# The second, more expensive pass runs only after a positive candidate result
# and only while the encoded sample is strictly bounded. It returns no images,
# SHA-256 strings or even single-image lengths; all are discarded in-process.
_MAX_EXACT_ENCODED = 12_000_000
_EXACT_SQL = """WITH newest AS MATERIALIZED (
    SELECT payload FROM bob_android_list_images
    WHERE created_at >= now()-interval '24 hours'
    ORDER BY created_at DESC,batch_id DESC LIMIT 8
)
SELECT img.image->>'png'
FROM newest n CROSS JOIN LATERAL
  jsonb_array_elements(
    CASE WHEN jsonb_typeof(n.payload->'images')='array'
         THEN n.payload->'images' ELSE '[]'::jsonb END
  ) AS img(image)
WHERE jsonb_typeof(img.image)='object'
  AND jsonb_typeof(img.image->'png')='string'
  AND octet_length(img.image->>'png') BETWEEN 1 AND 2000000
"""


def _verify_exact(conn, summary):
    """SHA-256 + full raw PNG byte equality; no content leaves this function."""
    if summary['candidateRepeatedImages'] <= 0:
        return {'exactVerificationStatus':'not-required',
                'exactDuplicateProven':False}
    if summary['totalEncodedImageCharacters'] > _MAX_EXACT_ENCODED:
        return {'exactVerificationStatus':'sample-too-large',
                'exactDuplicateProven':False}
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='2000ms'")
            conn.execute("SET LOCAL lock_timeout='500ms'")
            rows=conn.execute(_EXACT_SQL).fetchall()
        if type(rows) is not list or len(rows)!=summary['sampledImages']:
            return {'exactVerificationStatus':'cohort-changed',
                    'exactDuplicateProven':False}
        # Verify the fingerprint-only pass and exact pass saw the same
        # cohort; a concurrent new batch must not become a false proof.
        encoded_total = 0
        candidates = {}
        raw_seen = {}
        candidate_repeats = candidate_chars = 0
        exact_repeats = exact_encoded_chars = exact_png_bytes = 0
        for row in rows:
            if (not isinstance(row,(tuple,list)) or len(row)!=1
                    or type(row[0]) is not str):
                return {'exactVerificationStatus':'not-observed',
                        'exactDuplicateProven':False}
            encoded=row[0]
            n=len(encoded.encode('utf8'))
            encoded_total+=n
            if not 1 <= n <= 2_000_000 or encoded_total > _MAX_EXACT_ENCODED:
                return {'exactVerificationStatus':'sample-too-large',
                        'exactDuplicateProven':False}
            coarse=(n,hashlib.md5(encoded.encode('utf8')).digest())
            if coarse in candidates:
                candidate_repeats+=1
                candidate_chars+=n
            else:
                candidates[coarse]=True
            raw=base64.b64decode(encoded,validate=True)
            if raw[:8] != b'\\x89PNG\\r\\n\\x1a\\n':
                return {'exactVerificationStatus':'not-observed',
                        'exactDuplicateProven':False}
            digest=hashlib.sha256(raw).digest()
            group=raw_seen.setdefault(digest, [])
            if any(original == raw for original in group):
                exact_repeats+=1
                exact_encoded_chars+=n
                exact_png_bytes+=len(raw)
            else:
                group.append(raw)
        if (encoded_total!=summary['totalEncodedImageCharacters']
                or candidate_repeats!=summary['candidateRepeatedImages']
                or candidate_chars!=summary['candidateRepeatedEncodedCharacters']):
            return {'exactVerificationStatus':'cohort-changed',
                    'exactDuplicateProven':False}
        return {'exactVerificationStatus':'verified',
                'exactDuplicateProven':exact_repeats > 0,
                'exactDuplicateImages':exact_repeats,
                'exactRepeatedEncodedCharacters':exact_encoded_chars,
                'exactRepeatedPngBytes':exact_png_bytes}
    except Exception:
        # Never disclose SQL errors, raw images or filesystem/credential text.
        return {'exactVerificationStatus':'not-observed',
                'exactDuplicateProven':False}


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
            if result.get('status')=='sampled':
                result.update(_verify_exact(conn,result))
        except Exception:
            result={'status':'not-observed','readOnly':True,
                    'reclaimableBytes':None,'diskBytesFreed':None}
        _cache=dict(result)
        _cached_at=at
        return result
    finally:
        _lock.release()
