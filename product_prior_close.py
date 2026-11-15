"""Exact-ISIN SG research percentage versus a dated *observed* prior-session bid.

This is not an official exchange closing price, broker quote or execution proof.
Use only the last observed bid near 22:00 Zurich on the preceding trading day.
The bounded in-process reference is deliberately not silently re-dated.
"""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Zurich')


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _prior_business_day(today):
    prior = today - timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= timedelta(days=1)
    return prior


def _late_session(at):
    local = at.astimezone(ZONE)
    return 21 * 60 + 55 <= local.hour * 60 + local.minute < 22 * 60


def evaluate(product, points, isin, *, now=None, market=None, verified_id=None, reference=None):
    """Return {'dailyChange': evidence|None, 'lateReference': evidence|None}.

    The reference may come from an earlier issuer request on the same process,
    but only its ORIGINAL source timestamp is used, and its product identity,
    currency, market and prior-business-day date must still match.
    """
    from product_quotes import _validate_sg_chart_identity, sg_market, stamp, number
    now = now or datetime.now(timezone.utc)
    market = market or sg_market(isin)
    _validate_sg_chart_identity(product, isin, verified_id, market)
    if (product.get('Status', 0) & (2 | 8 | 16 | 32)
            or not product.get('Status', 0) & 1
            or product.get('TodayBarrierHitDate')
            or not isinstance(points, list) or not 0 < len(points) <= 10000):
        return dict(dailyChange=None, lateReference=None)
    today = now.astimezone(ZONE).date()
    if today.weekday() >= 5 or now.astimezone(ZONE).hour < 8:
        return dict(dailyChange=None, lateReference=None)
    previous_day = _prior_business_day(today)
    last_at = None
    late = None
    current = None
    prior = None
    for point in points:
        try:
            at = stamp(point['Date'])
            bid = number(point['Bid'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('SG-Geldkursdaten fehlen') from exc
        if not _positive(bid) or at > now or (last_at is not None and at < last_at):
            raise ValueError('SG-Geldkurs oder Quellzeit ungültig')
        last_at = at
        local_day = at.astimezone(ZONE).date()
        if local_day == previous_day and _late_session(at):
            prior = (at, bid)
        if local_day == today:
            if at.astimezone(ZONE).hour >= 8:
                current = (at, bid)
            if _late_session(at):
                late = (at, bid)
    if isinstance(reference, dict):
        try:
            saved_at = stamp(reference['referenceAt'])
            saved_bid = reference['referenceBid']
            valid = (reference.get('isin') == isin
                     and reference.get('currency') == market[2]
                     and reference.get('productId') == product['Id']
                     and reference.get('exchangeCode') == market[1]
                     and reference.get('kind') == 'last-observed-late-session-bid'
                     and _positive(saved_bid)
                     and saved_at <= now
                     and saved_at.astimezone(ZONE).date() == previous_day
                     and _late_session(saved_at))
            if valid and (prior is None or saved_at > prior[0]):
                prior = (saved_at, saved_bid)
        except (TypeError, KeyError, ValueError):
            pass
    saved = None
    if late:
        saved = dict(isin=isin, currency=market[2], productId=product['Id'],
                     exchangeCode=market[1], kind='last-observed-late-session-bid',
                     referenceBid=late[1], referenceAt=late[0].isoformat())
    daily = None
    if current and prior and prior[0] < current[0]:
        daily = dict(isin=isin, percent=(current[1]/prior[1]-1)*100,
                     bid=current[1], previousClose=prior[1],
                     at=current[0].isoformat(), referenceAt=prior[0].isoformat(),
                     currency=market[2], source='SG · datierte Geldkursbeobachtung',
                     sourceUrl=market[0]+'product-details/'+isin.lower(),
                     basis='bid-vs-last-observed-prior-day',
                     referenceKind='last-observed-late-session-bid',
                     isExecutableQuote=False, degiroExecutable=False)
    return dict(dailyChange=daily, lateReference=saved)
