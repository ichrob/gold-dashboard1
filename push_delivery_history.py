"""Private, bounded history of push-provider attempts (not device receipts).

Only diagnostic_history's fixed, redacted projection is returned. A TEST
message can never be counted as a verified live market signal, and accepting
a Web Push request never proves it appeared on an Android device.
"""
from datetime import datetime, timedelta, timezone
from bob_diagnostics import shape, project

PAGE_SIZE = 100
MAX_OFFSET = 9900
FIELDS = shape("outcome", "httpStatus", "direction", "signalBarAt", "dataAt",
               "test", "synthetic", "eventKinds")


def arguments(value=None, now=None):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {"start", "end", "offset"}:
        raise ValueError("Only start, end and offset are supported")
    now = now or datetime.now(timezone.utc)

    def timestamp(key, default):
        raw = value.get(key)
        if raw is None:
            if key in value:
                raise ValueError("A timestamp cannot be null")
            return default
        if not isinstance(raw, str) or len(raw) > 40:
            raise ValueError("Invalid timestamp")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Explicit timezone required")
            return parsed.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError("Invalid timezone-aware timestamp") from None

    end = timestamp("end", now)
    start = timestamp("start", end - timedelta(hours=24))
    offset = value.get("offset", 0)
    if type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
        raise ValueError("Invalid offset")
    if not timedelta(0) < end - start <= timedelta(hours=24):
        raise ValueError("Window must be greater than zero and at most 24 hours")
    return {"start": start.isoformat(), "end": end.isoformat(), "offset": offset}


def report(conn, value=None):
    args = arguments(value)
    rows = conn.execute(
        """SELECT id, recorded_at, payload
           FROM bob_diagnostic_history
           WHERE stage = 'push-delivery' AND recorded_at >= %s AND recorded_at < %s
           ORDER BY recorded_at, id LIMIT %s OFFSET %s""",
        (args["start"], args["end"], PAGE_SIZE + 1, args["offset"]),
    ).fetchall()
    has_more = len(rows) > PAGE_SIZE
    records = []
    for row_id, recorded_at, stored in rows[:PAGE_SIZE]:
        fields = project(stored, FIELDS)
        test = (fields.get("test") is True or fields.get("synthetic") is True)
        records.append({
            "id": str(row_id),
            "attemptedAt": recorded_at.isoformat(),
            **fields,
            "classification": "synthetic-test" if test else "not-marked-test",
            "handsetReceipt": "not-verified",
            "marketEventVerified": False,
        })
    return {
        "status": "observed" if records else "empty",
        "readOnly": True,
        "realOrders": False,
        "timezone": "Europe/Zurich",
        "window": args,
        "retentionDays": 7,
        "records": records,
        "nextOffset": args["offset"] + PAGE_SIZE if has_more else None,
        "scope": "observed-provider-attempts-only",
        "limitations": [
            "Test messages are synthetic, never evidence of a live market event.",
            "Not marked TEST does not establish a real market trigger; correlate original decision times separately.",
            "Provider acceptance does not establish Android display or user acknowledgement.",
            "Earlier attempts before deployment are not backfilled.",
            "This is a seven-day best-effort asynchronous journal; missing rows are not proof no push was sent.",
        ],
    }
