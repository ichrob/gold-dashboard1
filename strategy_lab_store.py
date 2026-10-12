"""Persist daily read-only Zukunft walk-forward reports in existing Bob PostgreSQL.

Only accessible through push-service's shared secret; no broker, trading or
live decision use. Same-day reruns do not duplicate historical runs.
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import strategy_lab

ZONE = ZoneInfo("Europe/Zurich")
MAX_REPORT_BYTES = 220000


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_strategy_lab_daily (
        run_day DATE PRIMARY KEY,
        calculated_at TIMESTAMPTZ NOT NULL,
        last_bar_at BIGINT,
        status TEXT NOT NULL,
        version TEXT NOT NULL,
        report JSONB NOT NULL
    )""")


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Kein Bericht")
    day = payload.get("day")
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("Ungültiger Berichtstag") from exc
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZONE).date()
    if d > today or (today-d).days > 2 or d.weekday() >= 5:
        raise ValueError("Berichtstag ausserhalb automatischer Handelszeit")
    report = payload.get("report")
    if not isinstance(report, dict) or report.get("mode") != "RESEARCH_ONLY" or report.get("version") != strategy_lab.VERSION:
        raise ValueError("Ungültige Forschungs-Version")
    if report.get("status") not in ("evaluated", "insufficient") or report.get("approved") is not False or report.get("orderExecutionEnabled") is not False or report.get("affectsLiveSignals") is not False:
        raise ValueError("Forschungs-Sperrstatus ungültig")
    if report.get("brokerConnected") is not False or not isinstance(report.get("closedBars"), int):
        raise ValueError("Forschungsnachweis unvollständig")
    last = report.get("rangeMs", [None, None])[-1]
    if last is not None and (type(last) is not int or last > int(now.timestamp()*1000)+3600000):
        raise ValueError("Letzte Kerze ungültig")
    data = json.dumps(report, ensure_ascii=False, allow_nan=False)
    if len(data.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("Forschungsbericht zu gross")
    return d, report, last, data


def handle(conn, action, payload):
    if action == "write":
        day, report, last, data = validate(payload)
        # Lock per date; never regress a validated report to insufficient, or
        # replace with fewer/older bars in a same-day retry.
        conn.execute("""INSERT INTO bob_strategy_lab_daily(run_day, calculated_at,last_bar_at,status,version,report)
            VALUES(%s,now(),%s,%s,%s,%s::jsonb)
            ON CONFLICT(run_day) DO UPDATE SET
              calculated_at=excluded.calculated_at, last_bar_at=excluded.last_bar_at,
              status=excluded.status, version=excluded.version, report=excluded.report
            WHERE (bob_strategy_lab_daily.status != 'evaluated' OR excluded.status = 'evaluated')
              AND COALESCE(excluded.last_bar_at,0) >= COALESCE(bob_strategy_lab_daily.last_bar_at,0)
        """, (day, last, report["status"], strategy_lab.VERSION, data))
        # Research results retained for 90 calendar days; no deletion of other Bob data.
        conn.execute("DELETE FROM bob_strategy_lab_daily WHERE run_day < CURRENT_DATE - 90")
        return dict(saved=True, day=day.isoformat(), mode="RESEARCH_ONLY")
    if action == "read":
        rows = conn.execute("""SELECT run_day, calculated_at,last_bar_at,status,version,report
            FROM bob_strategy_lab_daily ORDER BY run_day DESC LIMIT 14""").fetchall()
        latest = rows[0] if rows else None
        return {
            "mode": "RESEARCH_ONLY",
            "automation": {
                "enabled": True, "frequency": "daily-weekdays",
                "timezone": "Europe/Zurich", "fromHour": 8,
                "lastDay": latest[0].isoformat() if latest else None,
                "lastRunAt": latest[1].isoformat() if latest else None,
                "history": [dict(day=r[0].isoformat(),at=r[1].isoformat(),status=r[3],
                                 version=r[4],closedBars=r[5].get("closedBars"),
                                 lastBarAt=r[2]) for r in rows],
            },
            "latestReport": latest[5] if latest else None,
        }
    raise ValueError("Unbekannte Forschungs-Speicheraktion")
