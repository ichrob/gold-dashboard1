"""Public aggregate PAPER heartbeat, intentionally without ISINs or account details.

A successful HTTP request is NOT proof that paper observations advanced.
This reports all five durable account check timestamps from PostgreSQL.
"""
import math
import time

import background_push
import paper_portfolios


def snapshot(conn, now_ms=None):
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    phase = background_push.degiro_session(now_ms)
    checked = 0
    ages = []
    # All SQL identifiers are built from code-owned allowlisted profile names.
    for profile in paper_portfolios.POLICIES:
        table = paper_portfolios.names(profile)["bob_paper_control"]
        row = conn.execute(f"SELECT payload FROM {table} WHERE id=1").fetchone()
        payload = row[0] if row and isinstance(row[0], dict) else {}
        value = payload.get("checkedAt")
        if type(value) in (int, float) and math.isfinite(value) and 0 < value <= now_ms:
            checked += 1
            ages.append((now_ms-value)/1000)
    # Initial market opening is allowed time to complete first fetch / cold-start.
    # At other times, a status of "ok" requires ALL four durable ledgers to advance.
    if phase != "trading":
        state = "paused"
    elif checked == len(paper_portfolios.POLICIES) and max(ages) <= 300:
        state = "ok"
    else:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        local = datetime.fromtimestamp(now_ms/1000, ZoneInfo("Europe/Zurich"))
        minutes = local.hour*60+local.minute
        state = "warming" if minutes < 8*60+10 else "degraded"
    return {"state": state, "sessionMode": phase,
            "pauseReason": "outside-user-trading-window-not-broker-market-closed" if state == "paused" else None,
            "accountsTotal": len(paper_portfolios.POLICIES),
            "accountsChecked": checked,
            "maxCheckAgeSeconds": round(max(ages)) if ages else None,
            "realOrders": False,
            "scope": "paper-account-heartbeat-not-quote-quality"}
