"""Private, durable operational counters for Bob's verified self-healing.

Postgres lives on the existing push service. Only fixed code/kind values are
accepted. Never store diagnostics, API bodies, usernames, trades or secrets.
The Bob-side event queue avoids slowing live analysis on DB/network problems.
"""
from collections import deque
from datetime import datetime, timezone
import json
import os
import re
import threading
import time
import uuid
from urllib.request import Request, build_opener

EVENT_KINDS = frozenset(("detected", "repair-attempt", "repair-failed",
                         "repair-verified", "recovered"))
EVENT_CODES = frozenset((
    "cfd-worker-stopped", "spot-change-worker-stopped", "comparison-worker-stopped",
    "market-feed-not-current", "background-not-current",
    "market-worker-stopped", "background-worker-stopped",
    "research-worker-stopped", "unknown-service-failure",
    "trade-setup-stalled", "screenshot-import-failed",
    "training-audit-unavailable", "training-portfolios-unavailable",
    "training-repairs-unavailable", "training-improve-unavailable",
))
_TODO = deque(maxlen=512)
_QUEUE_LOCK = threading.Lock()
_SENDER_RUNNING = False
_STATS_LOCK = threading.Lock()
_STATS_CACHE = None
_STATS_AT = 0.0
_STATS_TTL = 60


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_self_heal_events (
        event_id TEXT PRIMARY KEY,
        event_at TIMESTAMPTZ NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        kind TEXT NOT NULL,
        code TEXT NOT NULL
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS bob_self_heal_events_latest
        ON bob_self_heal_events(recorded_at DESC)""")


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")
    return str(value)


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid event")
    event_id = payload.get("id")
    kind = payload.get("kind")
    code = payload.get("code")
    when = payload.get("at")
    if not isinstance(event_id, str) or not re.fullmatch(r"[a-f0-9]{32}", event_id):
        raise ValueError("Invalid event id")
    if kind not in EVENT_KINDS or code not in EVENT_CODES:
        raise ValueError("Unknown event kind or code")
    if not isinstance(when, str) or len(when) > 40:
        raise ValueError("Invalid event time")
    try:
        dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid event time") from exc
    if dt.tzinfo is None:
        raise ValueError("Time zone required")
    return event_id, kind, code, dt.astimezone(timezone.utc).isoformat()


def handle(conn, action, payload):
    if action == "write":
        event_id, kind, code, when = validate(payload)
        inserted = conn.execute("""INSERT INTO bob_self_heal_events
            (event_id, event_at, kind, code) VALUES (%s,%s,%s,%s)
            ON CONFLICT (event_id) DO NOTHING RETURNING event_id""",
            (event_id, when, kind, code)).fetchone()
        return {"ok": True, "stored": bool(inserted)}
    if action == "read":
        rows = conn.execute("""SELECT kind, count(*) FROM bob_self_heal_events
            GROUP BY kind""").fetchall()
        totals = {kind: int(count) for kind, count in rows}
        last = conn.execute("""SELECT kind, code, event_at
            FROM bob_self_heal_events
            ORDER BY recorded_at DESC, event_id DESC LIMIT 12""").fetchall()
        total = totals.get("detected", 0)
        verified = totals.get("repair-verified", 0)
        normalized = totals.get("recovered", 0)
        return {
            "status": "ok",
            "since": "ab Aktivierung des dauerhaften Fehlerzählers",
            "detected": total,
            "verifiedRepairs": verified,
            "normalizedWithoutVerifiedRepair": max(0, normalized - verified),
            "recoveryEvents": normalized,
            "repairAttempts": totals.get("repair-attempt", 0),
            "failedAttempts": totals.get("repair-failed", 0),
            "lastEventAt": _iso(last[0][2]) if last else None,
            "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "events": [{"kind": k, "code": c, "at": _iso(t)} for k, c, t in last],
        }
    raise ValueError("Unknown self-healing action")


def request(action, payload):
    from bob_auth import NoRedirect
    base = os.environ.get("PUSH_SERVICE_URL", "").rstrip("/")
    token = os.environ.get("PUSH_SERVICE_TOKEN", "")
    if not base or not token:
        raise OSError("Private problem counter not configured")
    if not base.startswith(("https://", "http://")):
        base = "http://" + base
    req = Request(base + "/self-heal-events/" + action,
                  data=json.dumps(payload, separators=(",", ":")).encode(),
                  method="POST", headers={
                      "Content-Type": "application/json",
                      "X-Bob-Push-Token": token,
                  })
    with build_opener(NoRedirect()).open(req, timeout=8) as response:
        raw = response.read(32769)
    if len(raw) > 32768:
        raise ValueError("Counter response too large")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid counter response")
    return data


def queue_event(kind, code):
    """Best-effort enqueue, no external I/O in Bob's monitoring code path."""
    global _SENDER_RUNNING
    if kind not in EVENT_KINDS or code not in EVENT_CODES:
        raise ValueError("Unrecognized self-healing event")
    event = {
        "id": uuid.uuid4().hex, "kind": kind, "code": code,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _QUEUE_LOCK:
        _TODO.append(event)
        if not _SENDER_RUNNING and os.environ.get("PUSH_SERVICE_URL") and os.environ.get("PUSH_SERVICE_TOKEN"):
            _SENDER_RUNNING = True
            threading.Thread(target=_sender, daemon=True, name="bob-repair-event-store").start()
    return event["id"]


def _sender():
    global _SENDER_RUNNING
    while True:
        with _QUEUE_LOCK:
            if not _TODO:
                _SENDER_RUNNING = False
                return
            event = _TODO[0]
        try:
            ack = request("write", event)
            if ack.get("ok") is not True:
                raise OSError("Private counter not acknowledged")
        except Exception as exc:
            print("BOB_REPAIR_AUDIT delivery=" + type(exc).__name__, flush=True)
            time.sleep(20)
            continue
        with _QUEUE_LOCK:
            if _TODO and _TODO[0]["id"] == event["id"]:
                _TODO.popleft()


def statistics(*, read=request, clock=time.monotonic):
    """Cached private DB summary; show unknown/stale rather than inventing zeros."""
    global _STATS_CACHE, _STATS_AT
    now = clock()
    with _STATS_LOCK:
        if _STATS_CACHE is not None and now - _STATS_AT < _STATS_TTL:
            return dict(_STATS_CACHE)
        try:
            data = read("read", {})
            if data.get("status") != "ok" or not all(
                isinstance(data.get(key), int) and not isinstance(data.get(key), bool)
                for key in ("detected", "verifiedRepairs", "normalizedWithoutVerifiedRepair", "repairAttempts")
            ):
                raise ValueError("Invalid private counter summary")
        except Exception as exc:
            print("BOB_REPAIR_AUDIT summary=" + type(exc).__name__, flush=True)
            data = (dict(_STATS_CACHE, status="stale") if _STATS_CACHE is not None
                    and _STATS_CACHE.get("detected") is not None else
                    {"status": "unavailable", "detected": None, "verifiedRepairs": None,
                     "normalizedWithoutVerifiedRepair": None, "repairAttempts": None,
                     "checkedAt": None, "events": []})
        _STATS_CACHE = data
        _STATS_AT = now
        return dict(data)
