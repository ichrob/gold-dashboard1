"""Read-only Sunday research for ONLY still-missing leverage in the last phone run.

Never writes quotes, trade approval, handset commands, or original timestamps.
Uses already configured issuer/comdirect/SG/BNP fallback in paper_simulation.quote_cache.
"""
import copy
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from product_quotes import valid_isin

ZURICH = ZoneInfo('Europe/Zurich')
RETRY_MS = 5 * 60_000
LATER_RETRY_MS = 60 * 60_000
MAX_LOOKUP = 3
MAX_RUN_AGE_MS = 6 * 60 * 60_000
MAX_LIST_SKEW_MS = 10 * 60_000


def timestamp(value):
    try:
        if not isinstance(value, str):
            return None
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.timestamp() * 1000 if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def targets(feed, run, now_ms):
    """No blanket 10-product refresh. Trust only the exact current list/phone run."""
    if not isinstance(feed, dict) or not isinstance(run, dict):
        return []
    if feed.get('listOrigin') != 'degiro-screenshot' or run.get('listSource') != 'degiro-gold-search':
        return []
    list_at, run_list_at, run_at = (timestamp(feed.get('listUploadedAt')),
                                  timestamp(run.get('listUploadedAt')),
                                  timestamp(run.get('receivedAt')))
    if (list_at is None or run_list_at is None or run_at is None
            or abs(list_at-run_list_at) > MAX_LIST_SKEW_MS
            or not 0 <= now_ms - run_at <= MAX_RUN_AGE_MS):
        return []
    current = {p.get('isin') for p in feed.get('products', [])
               if isinstance(p, dict) and valid_isin(p.get('isin'))}
    missing = []
    for row in run.get('results', [])[:12]:
        if not isinstance(row, dict) or row.get('code') != 'PARTIAL':
            continue
        isin = row.get('isin')
        if (isin not in current or isin in missing
                or row.get('matchedCurrentList') is not True
                or row.get('requestedFields') != ['Geld', 'Brief', 'Anzeigezeit', 'Hebel']):
            continue
        obs = row.get('observation')
        if not isinstance(obs, dict) or obs.get('missingFields') != ['Hebel']:
            continue
        missing.append(isin)
    return missing[:MAX_LOOKUP]


def plan(feed, run, audit, now_ms):
    """Produce an idempotent, rate-limited list of exact ISINs for issuer research."""
    if datetime.fromtimestamp(now_ms / 1000, ZURICH).weekday() < 5:
        return []
    if not isinstance(audit, dict) or audit.get('listUploadedAt') != feed.get('listUploadedAt'):
        return []
    by_isin = {i.get('isin'): i for i in audit.get('items', []) if isinstance(i, dict)}
    selected = []
    for isin in targets(feed, run, now_ms):
        item = by_isin.get(isin, {})
        previous = item.get('weekendLeverageFollowup') or {}
        if (item.get('state') in ('terminated', 'excluded-factor') or
                not {'leverage', 'leverage-time'}.intersection(item.get('missing', [])) or
                item.get('leverageReference') or now_ms < previous.get('retryAfterMs', 0)):
            continue
        selected.append(isin)
    return selected


def evidence(raw, isin, now_ms):
    """Issuer-first, then mathematically reproducible dated calculation."""
    if not isinstance(raw, dict) or raw.get('isin') != isin or raw.get('productVerified') is not True:
        return None
    from leverage_backup import historical_reference
    ref = historical_reference(raw, datetime.fromtimestamp(now_ms / 1000, timezone.utc))
    if (not isinstance(ref, dict) or ref.get('current') is not False
            or ref.get('tradeApproved') is not False or ref.get('researchOnly') is not True
            or ref.get('kind') not in ('historical-issuer-leverage', 'historical-calculated-gearing')
            or timestamp(ref.get('at')) is None):
        return None
    return copy.deepcopy(ref)


def update(audit, feed, selected, quotes, now_ms):
    """Do not change market quotes, other items, missing proof gates or provenance."""
    out = copy.deepcopy(audit)
    if out.get('listUploadedAt') != feed.get('listUploadedAt'):
        return audit
    chosen = set(selected)
    for item in out.get('items', []):
        if not isinstance(item, dict) or item.get('isin') not in chosen:
            continue
        if item.get('state') in ('terminated', 'excluded-factor'):
            continue
        isin = item['isin']
        prior = item.get('weekendLeverageFollowup') or {}
        value = evidence(quotes.get(isin), isin, now_ms)
        attempts = min(20, prior.get('attempts', 0) + 1)
        if value:
            item['leverageReference'] = value
        item['weekendLeverageFollowup'] = {
            'state': 'historical-reference' if value else 'source-evidence-unavailable',
            'checkedAt': datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(),
            'attempts': attempts,
            'retryAfterMs': now_ms + (LATER_RETRY_MS if attempts >= 3 else RETRY_MS),
            'researchOnly': True, 'tradeApproved': False
        }
    return out


def once(database, now_ms=None, collect=None):
    """Single advisory-locked, read-only sourcing cycle. Never opens DEGIRO."""
    from paper_simulation import quote_cache, stamp
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000) if now_ms is None else now_ms
    if datetime.fromtimestamp(now_ms / 1000, ZURICH).weekday() < 5:
        return dict(state='paused', checked=0, ordersEnabled=False)
    with database() as conn:
        # Do not hold a DB lock during issuer network lookup; source cache is
        # asynchronous. The second transaction rechecks current list generation.
        row = conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
        feed = row[0] if row else {}
        audit_row = conn.execute('SELECT payload FROM bob_degiro_product_audit WHERE id=1').fetchone()
        audit = audit_row[0] if audit_row else {}
        run_row = conn.execute('SELECT payload FROM bob_android_read_runs ORDER BY received_at DESC LIMIT 1').fetchone()
        reader = run_row[0] if run_row else {}
    selected = plan(feed, reader, audit, now_ms)
    if not selected:
        return dict(state='no-missing-targets', checked=0, ordersEnabled=False)
    products = [p for p in feed.get('products', []) if p.get('isin') in selected]
    # Existing source collectors bound concurrency and preserve independent
    # source stamps. This never uses device screen operations or live trade data.
    quotes = (collect or quote_cache)(products, [], now_ms)
    if not isinstance(quotes, dict):
        quotes = {}
    with database() as conn:
        with conn.transaction():
            lock = conn.execute('SELECT pg_try_advisory_xact_lock(72610408)').fetchone()
            if not lock or lock[0] is not True:
                return dict(state='busy', checked=0, ordersEnabled=False)
            row = conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
            fresh_feed = row[0] if row else {}
            audit_row = conn.execute('SELECT payload FROM bob_degiro_product_audit WHERE id=1').fetchone()
            fresh_audit = audit_row[0] if audit_row else {}
            if fresh_feed.get('listUploadedAt') != feed.get('listUploadedAt'):
                return dict(state='list-changed', checked=0, ordersEnabled=False)
            due = set(plan(fresh_feed, reader, fresh_audit, now_ms))
            chosen = [isin for isin in selected if isin in due]
            if not chosen:
                return dict(state='already-checked', checked=0, ordersEnabled=False)
            revised = update(fresh_audit, fresh_feed, chosen, quotes, now_ms)
            conn.execute("UPDATE bob_degiro_product_audit SET payload=%s::jsonb, checked_at=NOW() WHERE id=1",
                         (json.dumps(revised, ensure_ascii=False),))
        conn.commit()
    return dict(state='research-only', checked=len(chosen), ordersEnabled=False)
