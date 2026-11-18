"""No-order, quiet-hours and owner-consent regression checks."""
from datetime import datetime
from zoneinfo import ZoneInfo

import phone_access_handoff as access


TZ = ZoneInfo("Europe/Zurich")


def instant(year, month, day, hour, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=TZ).timestamp())


def test_zurich_window_and_weekend():
    assert not access.allowed(instant(2026, 11, 18, 7, 59))
    assert access.allowed(instant(2026, 11, 18, 8))
    assert access.allowed(instant(2026, 11, 18, 21, 59))
    assert not access.allowed(instant(2026, 11, 18, 22))
    assert not access.allowed(instant(2026, 11, 21, 12))
    assert access.allowed(instant(2027, 3, 29, 8))  # Zurich summer time
    assert access.allowed(instant(2027, 10, 29, 8))  # Zurich winter time


def test_once_a_day_when_ignored():
    now = instant(2026, 11, 18, 8)
    first = access.new_request({}, "morning-list", now)
    assert first["status"] == "pending"
    assert first["expiresAt"] == now + 600
    assert first["attempts"] == 1
    assert access.new_request(first, "morning-list", now + 60) is None
    assert access.new_request(first, "morning-list", now + 1000) is None
    assert access.new_request(first, "morning-list", instant(2026, 11, 19, 8))


def test_snooze_and_daily_cap():
    now = instant(2026, 11, 18, 10)
    state = access.new_request({}, "manual", now)
    state.update(status="snoozed", notBefore=now + 1200)
    assert access.new_request(state, "manual", now + 1199) is None
    again = access.new_request(state, "manual", now + 1200)
    assert again["requestId"] != state["requestId"]
    assert again["attempts"] == 2
    again.update(status="snoozed", notBefore=now + 2400)
    third = access.new_request(again, "manual", now + 2400)
    assert third["attempts"] == 3
    third.update(status="snoozed", notBefore=now + 3600)
    assert access.new_request(third, "manual", now + 3600) is None


def test_no_message_on_weekend_or_unknown_reason():
    now = instant(2026, 11, 21, 10)
    assert access.new_request({}, "morning-list", now) is None
    assert access.new_request({}, "unlock-phone", instant(2026, 11, 18, 10)) is None


def test_approval_does_not_grant_android_read_or_order():
    now = instant(2026, 11, 18, 10)
    state = access.new_request({}, "broker-read", now)
    shown = access.public_state(state, now)
    assert shown["readAuthorized"] is False
    assert shown["ordersAuthorized"] is False
    msg = access.notification(state)
    assert msg["data"]["kind"] == "device-access"
    assert msg["data"]["url"] == "/handy/access"
    assert "PIN" not in str(msg)
    assert "isin" not in str(msg).lower()


class FakeDB:
    def __init__(self, state):
        self.state = state
        self.query = ""

    def execute(self, query, parameters=()):
        self.query = query
        if query.startswith("UPDATE"):
            import json
            self.state = json.loads(parameters[0])
        return self

    def fetchone(self):
        return (self.state,)


def test_browser_approval_cannot_authorize_a_read():
    now = instant(2026, 11, 18, 10)
    state = access.new_request({}, "manual", now)
    db = FakeDB(state)
    choice = access.decide(db, state["requestId"], "approve", now)
    assert choice["status"] == "approved"
    assert choice["readAuthorized"] is False
    assert choice["ordersAuthorized"] is False
    assert access.decide(db, state["requestId"], "approve", now + 1)["ok"] is False


def test_only_approved_actual_receipt_can_finish():
    now = instant(2026, 11, 18, 10)
    state = access.new_request({}, "manual", now)
    db = FakeDB(state)
    assert access.completed(db, now) is False
    state["status"] = "approved"
    assert access.completed(db, now)
    assert db.state["status"] == "completed"
    assert access.completed(db, now) is False
