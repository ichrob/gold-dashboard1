"""Bounded, per-delivery, signed browser receipt claims.

A resolved showNotification() Promise proves only browser API acceptance,
never Android display. A notificationclick proves browser user interaction.
The proof is valid only for a single random delivery id, never a push endpoint,
account, order or trade; it is never persisted in diagnostics.
"""
import hashlib
import hmac
import re
import secrets
import time

MAX_AGE = 7 * 24 * 3600
STATES = frozenset(("show-resolved", "clicked"))


def issue(secret, *, now=None):
    if not isinstance(secret, str) or not secret:
        return None
    at = int(time.time() if now is None else now)
    delivery_id = secrets.token_hex(16)
    expires = at + MAX_AGE
    msg = f"v1|{delivery_id}|{expires}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {"receiptId": delivery_id, "receiptExpiry": expires,
            "receiptProof": signature}


def verify(value, secret, *, now=None):
    if not isinstance(value, dict) or set(value) != {
            "receiptId", "receiptExpiry", "receiptProof", "receiptState"}:
        raise ValueError("Invalid receipt payload")
    if not isinstance(secret, str) or not secret:
        raise ValueError("Receipt verification unavailable")
    delivery_id = value["receiptId"]
    expires = value["receiptExpiry"]
    signature = value["receiptProof"]
    state = value["receiptState"]
    if (not isinstance(delivery_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", delivery_id) is None
            or type(expires) is not int
            or not isinstance(signature, str)
            or re.fullmatch(r"[0-9a-f]{64}", signature) is None
            or not isinstance(state, str) or state not in STATES):
        raise ValueError("Invalid receipt")
    at = int(time.time() if now is None else now)
    if not at <= expires <= at + MAX_AGE:
        raise ValueError("Expired receipt")
    msg = f"v1|{delivery_id}|{expires}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid receipt proof")
    return delivery_id, state


def event_id(delivery_id, state):
    """Stable id: duplicate browser retries do not inflate persisted evidence."""
    return hashlib.sha256(f"push-receipt|{delivery_id}|{state}".encode("ascii")).hexdigest()[:32]
