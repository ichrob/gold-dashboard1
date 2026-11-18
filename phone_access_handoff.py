"""Opt-in, no-order DEGIRO screen handoff for the owner's Samsung.

An access request is a notification, NOT a remote phone capability. Only a
fresh, local tap in Bob Handy can start the existing bounded product reader.
No PIN, Android unlock, broker order or hidden screen navigation is possible.
"""
import json
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
REASONS = frozenset(("morning-list", "manual", "broker-read"))
MAX_NOTICES_PER_DAY = 3
SNOOZE_SECONDS = 20 * 60
REQUEST_SECONDS = 10 * 60


def day_start(now):
    local = datetime.fromtimestamp(now, ZURICH)
    return int(local.replace(hour=8, minute=0, second=0, microsecond=0).timestamp())


def allowed(now):
    local = datetime.fromtimestamp(now, ZURICH)
    return local.weekday() < 5 and 8 <= local.hour < 22


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_phone_access_handoff (
        id SMALLINT PRIMARY KEY CHECK (id=1),
        state JSONB NOT NULL
    )""")
    conn.execute("""INSERT INTO bob_phone_access_handoff(id,state)
        VALUES(1,'{}'::jsonb) ON CONFLICT (id) DO NOTHING""")


def read(conn, lock=False):
    row = conn.execute(
        "SELECT state FROM bob_phone_access_handoff WHERE id=1" +
        (" FOR UPDATE" if lock else "")
    ).fetchone()
    return dict(row[0] or {}) if row else {}


def save(conn, state):
    conn.execute("UPDATE bob_phone_access_handoff SET state=%s::jsonb WHERE id=1",
                 (json.dumps(state, separators=(',', ':')),))


def public_state(state, now):
    if not state:
        return {"ok": True, "status": "none", "hours": "08:00-22:00 Europe/Zurich"}
    status = state.get("status", "none")
    if status == "pending" and state.get("expiresAt", 0) <= now:
        status = "expired"
    return {"ok": True, "status": status, "requestId": state.get("requestId"),
            "reason": state.get("reason"), "expiresAt": state.get("expiresAt"),
            "notBefore": state.get("notBefore"), "sentCount": state.get("sentCount", 0),
            "hours": "08:00-22:00 Europe/Zurich",
            "readAuthorized": False, "ordersAuthorized": False}


def decide(conn, request_id, choice, now=None):
    now = int(time.time()) if now is None else now
    if not isinstance(request_id, str) or len(request_id) != 32 or any(c not in "0123456789abcdef" for c in request_id):
        raise ValueError("Invalid access-request identity")
    if choice not in ("approve", "later"):
        raise ValueError("Invalid access-request decision")
    state = read(conn, lock=True)
    if (state.get("requestId") != request_id or state.get("status") != "pending" or
            state.get("expiresAt", 0) <= now or not allowed(now)):
        return {"ok": False, "status": "expired-or-unavailable", "readAuthorized": False}
    state["status"] = "approved" if choice == "approve" else "snoozed"
    state["respondedAt"] = now
    if choice == "later":
        state["notBefore"] = now + SNOOZE_SECONDS
    save(conn, state)
    # Approving this browser handoff NEVER creates an Android read lease.
    return {"ok": True, "status": state["status"], "readAuthorized": False,
            "openBobHandy": choice == "approve", "ordersAuthorized": False}


def completed(conn, now=None):
    """Only call after a verified, successfully synced real list receipt."""
    now = int(time.time()) if now is None else now
    state = read(conn, lock=True)
    if state.get("status") != "approved" or state.get("day") != day_start(now):
        return False
    state["status"] = "completed"
    state["completedAt"] = now
    save(conn, state)
    return True


def new_request(state, reason, now):
    if reason not in REASONS or not allowed(now):
        return None
    day = day_start(now)
    attempts = int(state.get("attempts", 0)) if state.get("day") == day else 0
    if attempts >= MAX_NOTICES_PER_DAY:
        return None
    if state.get("day") == day:
        if state.get("status") in ("approved", "completed"):
            return None
        if state.get("status") == "pending" and state.get("expiresAt", 0) > now:
            return None
        if state.get("status") == "snoozed" and state.get("notBefore", 0) > now:
            return None
        # No unrequested repeated reminders; user must choose 'Später'.
        if state.get("status") in ("expired", "pending"):
            return None
    return {"requestId": uuid.uuid4().hex, "day": day, "reason": reason,
            "status": "pending", "createdAt": now, "expiresAt": now + REQUEST_SECONDS,
            "notBefore": now, "attempts": attempts + 1, "sentCount": 0}


def notification(state):
    reason = state.get("reason")
    return {"title": "Bob Handy · DEGIRO-Zugriff benötigt",
            "body": "Bob möchte " + ("die aktuelle Goldproduktliste" if reason == "morning-list" else "Produktdaten") +
                    " lesen. Jetzt freigeben oder später entscheiden.",
            "tag": "bob-device-access",
            "data": {"kind": "device-access", "url": "/handy/access",
                     "expiresAt": state["expiresAt"] * 1000},
            "requireInteraction": False}


def request(conn, reason, sender, now=None):
    """Sender is a callback(subscription, message, ttl) -> bool.

    A provider acceptance is NOT confirmation that a notification appeared.
    """
    now = int(time.time()) if now is None else now
    state = read(conn, lock=True)
    updated = new_request(state, reason, now)
    if updated is None:
        return public_state(state, now)
    save(conn, updated)
    delivered = 0
    rows = conn.execute(
        "SELECT subscription FROM subscriptions WHERE general_enabled=TRUE LIMIT 10"
    ).fetchall()
    message = notification(updated)
    for (subscription,) in rows:
        try:
            if sender(subscription, message, REQUEST_SECONDS):
                delivered += 1
        except Exception:
            # A rejected push cannot authorize a phone read or claim delivery.
            pass
    updated["sentCount"] = delivered
    save(conn, updated)
    return public_state(updated, now)


def morning_list_missing(conn, now):
    """A daily prompt only when there is no confirmed imported morning list."""
    if not allowed(now):
        return False
    # A currently open reader is already using the display, so do not interrupt.
    if conn.execute("""SELECT 1 FROM bob_android_remote
        WHERE state->>'active'='true'
          AND (state->>'seenAt')::bigint >= %s
          AND (state->>'expiresAt')::bigint > %s LIMIT 1""",
                    (now-30, now)).fetchone():
        return False
    if not conn.execute("SELECT to_regclass('bob_android_list_images')").fetchone()[0]:
        return False
    return not bool(conn.execute("""SELECT 1 FROM bob_android_list_images
        WHERE import_receipt->>'stage'='synced' AND created_at >= to_timestamp(%s)
        LIMIT 1""", (day_start(now),)).fetchone())
