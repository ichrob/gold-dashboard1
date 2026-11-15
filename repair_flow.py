"""Bounded owner-reported repair progress, never a lock or proof of recovery."""
from datetime import datetime, timezone
import re

PREFIX = '<!-- BOB_REPAIR_FLOW_V1:'
PHASES = ('accepted', 'working', 'testing', 'awaiting-live', 'blocked')
OWNERS = ('chatgpt', 'gemini')
KEYS = ('owner', 'acceptedAt', 'progressAt', 'nextCheckAt', 'phase')
STAMP = r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ'
MARKER = re.compile(r'(?m)^<!-- BOB_REPAIR_FLOW_V1:owner=(chatgpt|gemini);acceptedAt=('
    + STAMP + r');progressAt=(' + STAMP + r');nextCheckAt=(' + STAMP
    + r');phase=(accepted|working|testing|awaiting-live|blocked) -->$')


def clock(value):
    if not isinstance(value, str) or not re.fullmatch(STAMP, value):
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def sanitize(value, *, created_at=None, now=None):
    if not isinstance(value, dict):
        return None
    if value.get('owner') not in OWNERS or value.get('phase') not in PHASES:
        return None
    accepted, progress, due = (clock(value.get(k)) for k in KEYS[1:4])
    if any(t is None for t in (accepted, progress, due)):
        return None
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    created = clock(created_at)
    if not accepted <= progress <= now or due < progress:
        return None
    if created is not None and accepted < created:
        return None
    return {k: value[k] for k in KEYS}


def parse(tail, *, created_at=None, now=None):
    if not isinstance(tail, str):
        return None
    # Multiple owners/claims are ambiguous, not a last-writer-wins lock.
    if tail.count(PREFIX) != 1:
        return None
    found = MARKER.findall(tail)
    if len(found) != 1:
        return None
    return sanitize(dict(zip(KEYS, found[0])), created_at=created_at, now=now)


def marker(value, *, created_at=None, now=None):
    value = sanitize(value, created_at=created_at, now=now)
    return ('\n' + PREFIX + ';'.join(k + '=' + value[k] for k in KEYS) + ' -->') if value else ''


def diagnostic_item(item, *, now=None):
    """Explicit nested projection: diagnostics.fields deliberately drops dicts."""
    from bob_diagnostics import fields
    item = item if isinstance(item, dict) else {}
    result = fields(item, ('code', 'number', 'state', 'createdAt', 'updatedAt',
                          'title', 'reason', 'message', 'kiStatus', 'kiStatusLabel'))
    value = sanitize(item.get('repairFlow'), created_at=item.get('createdAt'), now=now)
    if value is not None:
        result['repairFlow'] = value
    return result


def summary(index, *, now=None):
    """Age/acknowledgement coverage of this open-index sample, not success rate."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    checked = index.get('checkedAt')
    at = clock(checked.replace('+00:00', 'Z')) if isinstance(checked, str) else None
    fresh = index.get('status') == 'ok' and at is not None and 0 <= now-at <= 1200
    rows = index.get('problems')
    available = isinstance(rows, list) and type(index.get('count')) is int
    rows = rows[:100] if available else []
    flows = [(row, sanitize(row.get('repairFlow'), created_at=row.get('createdAt'), now=now))
             for row in rows if isinstance(row, dict)]
    accepted = [(r, f) for r, f in flows if f]
    due = [r['number'] for r, f in accepted if clock(f['nextCheckAt']) < now
           and type(r.get('number')) is int] if fresh else []
    waits = [now-clock(f['acceptedAt']) for _, f in accepted]
    return dict(status='observed' if fresh and available else 'stale' if available else 'unavailable',
        checkedAt=index.get('checkedAt'), scope='bounded-open-issues-owner-reported-progress',
        sampledCases=len(flows) if available else None,
        declaredAccepted=len(accepted) if available else None,
        missingAcknowledgement=len(flows)-len(accepted) if available else None,
        overdueIssueNumbers=due, overdueCount=len(due) if fresh and available else None,
        oldestAcceptedAgeSeconds=round(max(waits)) if waits else None,
        truncated=available and index['count'] > len(flows),
        verifiedRepairRatePct=None, verifiedRepairDurationSeconds=None,
        note='Übernahme ist eine dokumentierte Zusage, keine atomare Sperre oder Ausführung. '
             'Ein offener Index enthält keine vollständigen verifizierten Abschlüsse; '
             'Erfolgsquote und Reparaturdauer bleiben unbekannt.')
