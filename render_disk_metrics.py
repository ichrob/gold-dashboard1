"""Optional read-only Render volume observation; credentials never leave this module."""
import datetime
import json
import math
import os
import threading
import time
import urllib.request

RESOURCE = 'dpg-datjno1srm7s738vv500-a'
URL = 'https://api.render.com/v1/metrics/disk-usage?resource=' + RESOURCE + '&resolutionSeconds=60'
_lock = threading.Lock()
_cache = None
_cached_at = 0


def parse(payload, now):
    points = []
    if not isinstance(payload, list):
        return {'status': 'invalid-response'}
    for series in payload:
        if not isinstance(series, dict):
            continue
        labels = series.get('labels', [])
        if not any(isinstance(x, dict) and x.get('field') in ('resource', 'service', 'database')
                   and x.get('value') == RESOURCE for x in labels):
            continue
        for point in series.get('values', []):
            try:
                stamp = datetime.datetime.fromisoformat(point['timestamp'].replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    continue
                at = stamp.timestamp()
                value = point['value']
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                    continue
                if 0 <= now - at <= 300:
                    points.append((at, value, series.get('unit')))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
    if not points:
        return {'status': 'no-fresh-observation'}
    # Keep API units explicit. Do not turn unverified units into a rewrite budget.
    at, value, unit = max(points, key=lambda p: p[0])
    return {'status': 'observed', 'resource': RESOURCE, 'observedAt': at,
            'diskUsage': value, 'unit': unit, 'source': 'render-metrics-api',
            'scope': 'volume-usage', 'maintenanceBudgetApproved': False}


def report():
    global _cache, _cached_at
    key = os.environ.get('BOB_RENDER_METRICS_API_KEY', '').strip()
    if not key:
        return {'status': 'configuration-required', 'requiredSecret': 'BOB_RENDER_METRICS_API_KEY'}
    now = time.time()
    with _lock:
        if _cache is not None and now - _cached_at < 60:
            result = dict(_cache)
            if result.get('status') == 'observed' and now - result['observedAt'] > 300:
                return {'status': 'no-fresh-observation'}
            return result
        try:
            req = urllib.request.Request(URL, headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
            # Never follow redirects with the bearer credential.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            with urllib.request.build_opener(NoRedirect).open(req, timeout=5) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ValueError('response-too-large')
                result = parse(json.loads(raw), now)
        except Exception:
            result = {'status': 'unavailable'}
        _cache, _cached_at = result, now
        return dict(result)
