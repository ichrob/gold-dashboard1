"""Bounded, opt-in Aiven service host metrics read through the official API.

No startup hook, schema write, Aiven credential disclosure, or auto-promotion.
Aiven metrics REST is POST but read-only: /v1/project/{project}/service/{service}/metrics.
All result statuses are secret-free. Unknown chart schemas fail closed.
"""
import json
import math
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from aiven_host_capacity_review import HOST_MAX_AGE_SECONDS

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
DATE = re.compile(r"^Date\((\d{4}),(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2})\)$")
MAX_RESPONSE = 512 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _instant(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Chart epochs are only accepted as milliseconds; seconds are ambiguous.
        if 1e12 < value < 5e12:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return None
    if isinstance(value, str):
        found = DATE.fullmatch(value)
        if found:
            y, m, d, hh, mm, ss = map(int, found.groups())
            try:
                return datetime(y, m+1, d, hh, mm, ss, tzinfo=timezone.utc)
            except ValueError:
                return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
        except ValueError:
            return None
    return None


def _percent(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    # Fractional 0.27 values might be 27%, not 0.27%; never guess units.
    if 0 < value < 1:
        return None
    return float(value)


def _chart_pairs(chart):
    if not isinstance(chart, dict) or not isinstance(chart.get("cols"), list):
        return []
    cols = chart["cols"]
    if len(cols) != 2 or len(chart.get("rows", [])) > 500:
        return []
    result = []
    for row in chart.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("c"), list) or len(row["c"]) != 2:
            return []
        cells = row["c"]
        if any(not isinstance(cell, dict) for cell in cells):
            return []
        stamp = _instant(cells[0].get("v"))
        value = _percent(cells[1].get("v"))
        if stamp and value is not None:
            result.append((stamp, value))
    return result


def _metrics_pairs(payload, name):
    if not isinstance(payload, dict) or not isinstance(payload.get("metrics"), dict):
        return []
    metric = payload["metrics"].get(name)
    return _chart_pairs(metric)


def _request_once(url, headers, body):
    opener = build_opener(NoRedirect())
    req = Request(url, data=body, headers=headers, method="POST")
    with opener.open(req, timeout=5) as response:
        if response.status != 200 or not response.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise ValueError("provider response invalid")
        data = response.read(MAX_RESPONSE+1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("provider response too large")
        return json.loads(data.decode("utf-8"))


def read(environ=None, request_once=None, now=None):
    env = os.environ if environ is None else environ
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Timezone is required")
    now = now.astimezone(timezone.utc)
    if env.get("BOB_AIVEN_METRICS_ONCE") != "1":
        return {"status": "disabled"}
    token = env.get("BOB_AIVEN_METRICS_TOKEN", "")
    project = env.get("BOB_AIVEN_METRICS_PROJECT", "")
    service = env.get("BOB_AIVEN_METRICS_SERVICE", "")
    if not token or not NAME.fullmatch(project) or not NAME.fullmatch(service):
        return {"status": "not-configured"}
    if len(token) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        return {"status": "invalid-authentication"}
    url = ("https://api.aiven.io/v1/project/" + quote(project, safe="") +
           "/service/" + quote(service, safe="") + "/metrics")
    body = b'{"period":"hour"}'
    headers = {"Authorization": "aivenv1 " + token,
               "Content-Type": "application/json",
               "Accept": "application/json"}
    try:
        payload = (_request_once if request_once is None else request_once)(url, headers, body)
        ram = _metrics_pairs(payload, "mem_usage")
        disk = _metrics_pairs(payload, "disk_usage")
        candidates = [(t, m, d) for t, m in ram for td, d in disk
                      if abs((t-td).total_seconds()) <= 60]
        if not candidates:
            return {"status": "schema-or-metrics-unverified"}
        timestamp, mem_pct, disk_pct = max(candidates, key=lambda x: x[0])
        age = (now-timestamp).total_seconds()
        if not 0 <= age <= HOST_MAX_AGE_SECONDS:
            return {"status": "metrics-stale-or-future"}
        return {"status": "observed",
                "host": {"source": "aiven-service-metrics-api",
                         "project": project, "service": service,
                         "node": "service-wide",
                         "observedAt": timestamp.isoformat(),
                         "memoryUsedPct": mem_pct, "diskUsedPct": disk_pct}}
    except Exception:
        return {"status": "provider-metrics-unavailable"}


def main():
    result = read()
    print(json.dumps({"status": result["status"], "hostMetricObserved": result["status"] == "observed"}, sort_keys=True))
    return 0 if result["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
