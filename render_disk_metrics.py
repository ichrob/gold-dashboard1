"""Optional read-only Render volume observation; credentials never leave this module."""
import datetime
import json
import math
import os
import threading
import time
import urllib.request
import urllib.error

RESOURCE = 'dpg-datjno1srm7s738vv500-a'
# Render's disk-usage API reports a unit per time series (often GB).
# Normalize only explicit known units; unknown units must fail closed.
_UNIT_TO_BYTES = {
    'B': 1, 'bytes': 1, 'KB': 1_000, 'MB': 1_000_000,
    'GB': 1_000_000_000, 'KiB': 1_024,
    'MiB': 1_048_576, 'GiB': 1_073_741_824,
}
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
        unit = series.get('unit')
        scale = _UNIT_TO_BYTES.get(unit) if isinstance(unit, str) else None
        if scale is None:
            # Never guess what an unknown unit means for rewrite headroom.
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
                raw_bytes = value * scale
                if not math.isfinite(raw_bytes) or raw_bytes > 1_000_000_000_000:
                    continue
                if 0 <= now - at <= 300:
                    # Round upward, never understate disk usage before a write.
                    points.append((at, math.ceil(raw_bytes), unit))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
    if not points:
        return {'status': 'no-fresh-observation'}
    at, used_bytes, reported_unit = max(points, key=lambda p: p[0])
    return {'status': 'observed', 'resource': RESOURCE, 'observedAt': at,
            'diskUsage': used_bytes, 'unit': 'bytes', 'reportedUnit': reported_unit,
            'source': 'render-metrics-api', 'scope': 'volume-usage',
            'maintenanceBudgetApproved': False}


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
        except urllib.error.HTTPError as exc:
            # Never emit response bodies, headers, URLs or credentials.
            # Numeric allowlist is enough to distinguish permission and API errors.
            code = exc.code if type(exc.code) is int and exc.code in (
                400, 401, 403, 404, 409, 429, 500, 502, 503) else None
            result = {'status': 'provider-http-error', 'httpStatus': code}
        except urllib.error.URLError:
            result = {'status': 'network-unavailable'}
        except (ValueError, UnicodeError):
            result = {'status': 'invalid-response'}
        except Exception:
            result = {'status': 'unavailable'}
        _cache, _cached_at = result, now
        return dict(result)
