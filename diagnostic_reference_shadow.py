"""In-memory reversible diagnostic reference shadow; never writes production data.

This is a model for a future migration, not a storage migration or permission
to remove event payloads. Caller owns its input and output; no persistence.
"""
import hashlib
import json


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def shadow(events):
    """Deduplicate JSON payload values while retaining each event envelope.

    This model intentionally requires an explicit bounded in-memory sequence.
    It never queries the database, uploads data, or modifies original events.
    """
    if type(events) not in (list, tuple) or len(events) > 256:
        raise ValueError("Expected at most 256 events")
    total_size = 0
    blobs = {}
    records = []
    originals = []
    for event in events:
        if type(event) is not dict or "payload" not in event:
            raise ValueError("Event must contain payload")
        original = _canonical(event)
        if len(original) > 1_000_000:
            raise ValueError("Event exceeds safe shadow size")
        total_size += len(original)
        if total_size > 8000000:
            raise ValueError("Shadow batch too large")
        payload = _canonical(event["payload"])
        key = hashlib.sha256(payload).hexdigest()
        if key in blobs and blobs[key] != payload:
            raise ValueError("Digest collision")
        blobs[key] = payload
        envelope = {k: v for k, v in event.items() if k != "payload"}
        records.append({"envelope": envelope, "payloadDigest": key})
        originals.append(original)
    reconstructed = []
    for record in records:
        envelope = dict(record["envelope"])
        envelope["payload"] = json.loads(blobs[record["payloadDigest"]])
        reconstructed.append(_canonical(envelope))
    if reconstructed != originals:
        raise ValueError("Round-trip mismatch")
    original_bytes = sum(len(value) for value in originals)
    reference_bytes = sum(len(blob) for blob in blobs.values()) + sum(
        len(_canonical(record)) for record in records)
    return {"status": "verified-shadow", "readOnly": True,
            "originalLogicalBytes": original_bytes,
            "referenceLogicalBytes": reference_bytes,
            "logicalByteDifference": original_bytes - reference_bytes,
            "originalEvents": len(events), "uniquePayloads": len(blobs),
            "reconstructionVerified": True, "originalRowsChanged": False,
            "physicalBytesFreed": None,
            "scope": "in-memory-logical-round-trip-not-production-disk-savings"}


def preview(events):
    """Expose aggregate counters only, never envelopes, hashes or payloads."""
    return shadow(events)
