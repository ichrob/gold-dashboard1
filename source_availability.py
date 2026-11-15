"""Bounded hourly evidence; missing observations never count as uptime."""
import math

HOUR = 3600
BAD = ('stale', 'unavailable', 'incomplete')


def record(row, previous, start, end):
    buckets = row.setdefault('availabilityHours', {})
    if end <= start:
        return
    # A gap larger than the monitor tolerance is entirely unobserved.
    category = 0 if previous == 'current' else 1 if previous in BAD else 2 if previous == 'paused' else None
    if end - start > 90:
        category = None
    if category is not None:
        cursor = start
        while cursor < end:
            hour = int(cursor // HOUR)
            stop = min(end, (hour + 1) * HOUR)
            values = buckets.setdefault(str(hour), [0, 0, 0])
            values[category] = round(values[category] + stop - cursor, 3)
            cursor = stop
    cutoff = int(end // HOUR) - 168
    row['availabilityHours'] = {k: v for k, v in buckets.items() if int(k) >= cutoff}


def windows(row, now):
    # Completed UTC hours give exact, reproducible 24h/7d boundaries.
    end = math.floor(now / HOUR) * HOUR
    result = {}
    for label, hours in (('24h', 24), ('7d', 168)):
        start = end - hours * HOUR
        good = bad = paused = 0
        for key, values in row.get('availabilityHours', {}).items():
            if start <= int(key) * HOUR < end:
                good += values[0]
                bad += values[1]
                paused += values[2]
        observed = good + bad
        unknown = max(0, end - start - observed - paused)
        result[label] = dict(startAt=start, endAt=end,
            currentSeconds=round(good, 3), badSeconds=round(bad, 3),
            pausedSeconds=round(paused, 3), unknownSeconds=round(unknown, 3),
            availabilityPct=round(100 * good / observed, 2) if observed else None,
            coveragePct=round(100 * observed / (observed + unknown), 2) if observed + unknown else None,
            scope='observed-freshness-completed-UTC-hours-not-provider-uptime')
    return result
