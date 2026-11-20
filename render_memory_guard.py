"""Fail-closed read-only RAM capacity check for optional PostgreSQL maintenance.

Uses Render's existing authenticated API key. No new service, scheduled job,
database queries, upgrades, secrets in output or maintenance authorization.
A green reading does not replace backup, disk, WAL, lock or operator approval.
"""
import datetime
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request

from render_disk_metrics import RESOURCE, _UNIT_TO_BYTES

_ENDPOINT = 'https://api.render.com/v1/metrics/'
_TYPES = ('memory', 'memory-limit')
_MIN_FREE = 32 * 1024 * 1024
_MAX_RATIO = 0.85
_WINDOW = 900
_FRESH = 300
_SPAN = 600
_MIN_SAMPLES = 8
_MAX_GAP = 180
_CACHE_SECONDS = 60
_lock = threading.Lock()
_cache = None
_cached_at = 0


def _points(payload, now, *, smallest=False):
    """Return only this exact database's recent byte readings."""
    points = {}
    if type(payload) is not list:
        return points
    for series in payload[:30]:
        if type(series) is not dict:
            continue
        labels = series.get('labels')
        if type(labels) is not list or not any(
                type(x) is dict and x.get('field') in
                ('resource', 'service', 'database') and
                x.get('value') == RESOURCE for x in labels):
            continue
        unit = series.get('unit')
        factor = _UNIT_TO_BYTES.get(unit) if type(unit) is str else None
        if factor is None:
            continue
        values = series.get('values')
        if type(values) is not list:
            continue
        for item in values[:120]:
            try:
                stamp = datetime.datetime.fromisoformat(
                    item['timestamp'].replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    continue
                at = stamp.timestamp()
                value = item['value']
                if (type(value) not in (int, float) or
                        not math.isfinite(value) or value < 0 or
                        not 0 <= now-at <= _WINDOW):
                    continue
                converted = value*factor
                if not math.isfinite(converted) or converted > 2**45:
                    continue
                # Do not overstate available headroom when a provider sends
                # duplicate readings: maximum usage, MINIMUM memory limit.
                rounded = math.ceil(converted) if not smallest else math.floor(converted)
                points[at] = (min(points[at], rounded) if smallest and at in points
                              else max(points.get(at, 0), rounded))
            except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
                continue
    return points


def assess(usage, limits, now):
    """Dense aligned provider history with no high-RAM excursions."""
    denied = {'status':'memory-proof-unavailable', 'readOnly':True,
              'maintenanceAuthorized':False, 'physicalBytesFreed':None}
    if type(now) not in (int, float) or not math.isfinite(now):
        return denied
    used = _points(usage, now)
    maximum = _points(limits, now, smallest=True)
    # Never ignore an unmatched RAM spike merely because its matching
    # plan-limit timestamp is missing from an otherwise good time series.
    # Missing usage samples also cannot establish an all-clear trend.
    if set(used) != set(maximum):
        return denied
    at = sorted(used)
    if (len(at) < _MIN_SAMPLES or now-at[-1] > _FRESH or
            at[-1]-at[0] < _SPAN or
            any(later-earlier > _MAX_GAP
                for earlier,later in zip(at,at[1:]))):
        # Two widely separated "good" snapshots are not evidence about
        # intervening spikes. Never fill gaps or interpolate missing readings.
        return denied
    # Require ten minutes of dense, aligned readings, not a last value/mean.
    for tick in at:
        limit = maximum[tick]
        value = used[tick]
        if (limit < _MIN_FREE or value >= limit or
                limit-value < _MIN_FREE or value/limit > _MAX_RATIO):
            return {**denied, 'status':'memory-pressure'}
    return {**denied, 'status':'memory-headroom-observed',
            'sampleCount':len(at), 'oldestSampleAt':at[0],
            'newestSampleAt':at[-1]}


def report():
    """At most two authorized read-only Render metrics GETs per minute."""
    global _cache, _cached_at
    key = os.environ.get('BOB_RENDER_METRICS_API_KEY', '').strip()
    if not key:
        return {'status':'memory-proof-unavailable', 'maintenanceAuthorized':False}
    now = time.time()
    with _lock:
        if _cache is not None and 0 <= now - _cached_at < _CACHE_SECONDS:
            result = dict(_cache)
            if (result.get('status') == 'memory-headroom-observed'
                    and not 0 <= now-result.get('newestSampleAt', 0) <= _FRESH):
                return {'status':'memory-proof-unavailable',
                        'maintenanceAuthorized':False}
            return result
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            data = []
            for typ in _TYPES:
                url = _ENDPOINT + typ + '?resource=' + RESOURCE + '&resolutionSeconds=60'
                req = urllib.request.Request(url, headers={
                    'Authorization':'Bearer '+key, 'Accept':'application/json'})
                with opener.open(req, timeout=5) as response:
                    raw = response.read(1_000_001)
                    if len(raw) > 1_000_000:
                        raise ValueError('Provider response too large')
                    data.append(json.loads(raw))
            result = assess(data[0], data[1], now)
        except Exception:
            # Never log provider error bodies, redirect targets or credentials.
            result = {'status':'memory-proof-unavailable',
                      'maintenanceAuthorized':False}
        _cache, _cached_at = dict(result), now
        return dict(result)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
