"""Manual one-row rollback of a cold decision product reference to full inline JSON.

Never scheduled, never exposed as an HTTP route and never deletes Drive objects.
The original product array is freshly re-downloaded and SHA-verified before a
short compare-and-swap transaction, so original decision clocks, identity and
all non-product fields remain unchanged. No physical disk saving is claimed.
"""
import os
import re
import time

import cold_decision_products as reader
import cold_metrics as codec

_ID = re.compile(r"[A-Za-z0-9_:.-]{1,128}\Z")
_MAX_AGE_SECONDS = 15 * 60


def _approved(approval, now):
    return (os.environ.get("BOB_DECISION_PRODUCT_ROLLBACK_ENABLED") == "1" and
            type(approval) is dict and set(approval) == {"confirmed", "observedAt"} and
            approval.get("confirmed") is True and
            type(approval.get("observedAt")) in (int, float) and
            0 <= now - approval["observedAt"] <= _MAX_AGE_SECONDS)


def restore_one(conn, decision_id, *, approval=None, drive=None, now=None):
    """Explicit operator-only compensation of at most one historical pointer."""
    timestamp = time.time() if now is None else now
    if not _approved(approval, timestamp):
        return {"status": "disabled", "restoredRows": 0, "diskBytesFreed": None}
    if type(decision_id) is not str or not _ID.fullmatch(decision_id):
        return {"status": "invalid-id", "restoredRows": 0, "diskBytesFreed": None}
    if conn.autocommit is not True:
        raise ValueError("Rollback requires a dedicated autocommit connection")

    snapshot = conn.execute(
        "SELECT recorded_at,payload FROM bob_decision_audit WHERE id=%s",
        (decision_id,)).fetchone()
    if snapshot is None or type(snapshot[1]) is not dict or reader.TAG not in snapshot[1]:
        return {"status": "not-a-pointer", "restoredRows": 0, "diskBytesFreed": None}
    at, pointer = snapshot
    content_hash = pointer[reader.TAG]
    if (type(content_hash) is not str or len(content_hash) != 64 or
            "products" in pointer):
        return {"status": "invalid-pointer", "restoredRows": 0, "diskBytesFreed": None}

    if drive is None:
        drive = codec.runtime_drive(conn)
    try:
        # Read from private Drive without a cache, then exercise the same
        # identity-bound reader used by Bob's historical decision reports.
        location = conn.execute(
            "SELECT file_id,sha256,row_index FROM bob_cold_decision_product_objects "
            "WHERE content_hash=%s", (content_hash,)).fetchone()
        if (not location or type(location[2]) is not int or
                not 0 <= location[2] < codec.MAX_ROWS):
            raise codec.ColdArchiveUnavailable("Missing original archive location")
        rows = codec.read_chunk(drive, location[0], location[1],
                                cached=False, conn=conn)
        entry = rows[location[2]]
        products = entry[4]["products"]
        original = reader.resolve(conn, decision_id, pointer,
                                  verified={content_hash: products})
        if codec.digest(codec.encoded(original["products"])) != content_hash:
            raise codec.ColdArchiveUnavailable("Original array differs")
    except Exception:
        # Never repair a missing archive with an empty/reconstructed product.
        return {"status": "original-unavailable", "restoredRows": 0,
                "diskBytesFreed": None}

    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='5s'")
        conn.execute("SET LOCAL lock_timeout='250ms'")
        current = conn.execute(
            "SELECT recorded_at,payload FROM bob_decision_audit "
            "WHERE id=%s FOR UPDATE", (decision_id,)).fetchone()
        if (not current or current[0] != at or
                codec.encoded(current[1]) != codec.encoded(pointer)):
            return {"status": "concurrent-change", "restoredRows": 0,
                    "diskBytesFreed": None}
        updated = conn.execute(
            "UPDATE bob_decision_audit SET payload=%s::jsonb "
            "WHERE id=%s AND recorded_at=%s AND payload=%s::jsonb "
            "AND EXISTS (SELECT 1 FROM bob_cold_decision_product_refs "
            "WHERE decision_id=%s AND content_hash=%s) RETURNING payload",
            (codec.encoded(original).decode("utf-8"), decision_id, at,
             codec.encoded(pointer).decode("utf-8"), decision_id,
             content_hash)).fetchone()
        if not updated or codec.encoded(updated[0]) != codec.encoded(original):
            raise codec.ColdArchiveUnavailable("Original compare-and-swap failed")
        deleted = conn.execute(
            "DELETE FROM bob_cold_decision_product_refs "
            "WHERE decision_id=%s AND content_hash=%s RETURNING decision_id",
            (decision_id, content_hash)).fetchone()
        if not deleted or deleted[0] != decision_id:
            raise codec.ColdArchiveUnavailable("Pointer ledger rollback failed")
        restored = conn.execute(
            "SELECT recorded_at,payload FROM bob_decision_audit WHERE id=%s",
            (decision_id,)).fetchone()
        if (not restored or restored[0] != at or
                codec.encoded(restored[1]) != codec.encoded(original)):
            raise codec.ColdArchiveUnavailable("Restored original mismatch")
    return {"status": "restored-original-inline", "restoredRows": 1,
            "archiveObjectsDeleted": 0, "diskBytesFreed": None}
