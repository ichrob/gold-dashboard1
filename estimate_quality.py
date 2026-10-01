"""Empirical errors of frozen estimates, matched to dated observations.

The observed maximum is a comparison band, not a probabilistic confidence
interval or guarantee. Keep validation separate by identity and anchor horizon.
"""
import math
import threading
from datetime import datetime, timezone

_lock = threading.RLock()
_pending = {}
_errors = {}
_seen = {}
MIN_SAMPLES = 20
MIN_SPAN_SECONDS = 600
MAX_MATCH_SECONDS = 5


def seconds(at):
    value = datetime.fromisoformat(at.replace('Z','+00:00'))
    if value.tzinfo is None:
        raise ValueError('Validierungszeit ohne Zeitzone')
    return value.timestamp()


def horizon_bucket(age):
    if not 0 < age <= 1800:
        return None
    return '0–60s' if age<=60 else '61–300s' if age<=300 else '301–900s' if age<=900 else '901–1800s'


def record(key, value, at, reference_at, created_at):
    try:
        point, ref, created = map(seconds,(at,reference_at,created_at))
        if isinstance(value,bool) or not math.isfinite(value) or value<=0 or not ref < point <= created:
            return
        bucket=horizon_bucket(point-ref)
        if not bucket:
            return
        scoped=(key,bucket)
        with _lock:
            if len(_pending)>=1024 and scoped not in _pending:
                oldest=next(iter(_pending));_pending.pop(oldest,None);_errors.pop(oldest,None);_seen.pop(oldest,None)
            rows=_pending.setdefault(scoped,[])
            # Preserve the first calculation; a new reference must not rewrite
            # an earlier prediction at the same observation time.
            if any(r['at']==point for r in rows):return
            rows.append(dict(at=point,value=value,created=created,horizon=point-ref))
            rows[:]=[r for r in rows if created-r['created']<=7200][-300:]
    except (ValueError,TypeError,OverflowError):
        return


def observe(key, value, at, received_at):
    try:
        point,received=map(seconds,(at,received_at))
        if isinstance(value,bool) or not math.isfinite(value) or value<=0 or point>received:return
        with _lock:
            for scoped,rows in list(_pending.items()):
                if scoped[0]!=key:continue
                seen=_seen.setdefault(scoped,[])
                if point in seen:continue
                choices=[r for r in rows if abs(r['at']-point)<=MAX_MATCH_SECONDS and r['created']<=received]
                if not choices:continue
                prediction=min(choices,key=lambda r:abs(r['at']-point))
                # Every prediction and every dated truth are used only once.
                rows.remove(prediction)
                seen.append(point);seen[:]=seen[-300:]
                errors=_errors.setdefault(scoped,[])
                errors.append(dict(at=point,received=received,error=prediction['value']-value,
                                   offset=abs(prediction['at']-point),horizon=prediction['horizon']))
                errors[:]=[r for r in errors if received-r['received']<=21600][-200:]
    except (ValueError,TypeError,OverflowError):
        return


def quality(key, horizon, now=None):
    now=now or datetime.now(timezone.utc)
    bucket=horizon_bucket(horizon)
    with _lock:
        rows=[r for r in _errors.get((key,bucket),[]) if 0<=now.timestamp()-r['received']<=21600]
    count=len(rows)
    span=max(r['at'] for r in rows)-min(r['at'] for r in rows) if rows else 0
    last=max((r['received'] for r in rows),default=0)
    ready=bool(count>=MIN_SAMPLES and span>=MIN_SPAN_SECONDS and now.timestamp()-last<=1800)
    out=dict(ready=ready,sampleCount=count,minSamples=MIN_SAMPLES,horizonBucket=bucket,
             observedSpanSeconds=round(span,1),maxMatchSeconds=MAX_MATCH_SECONDS,
             kind='empirical-observed-errors',isConfidenceInterval=False,
             note='Bisher gemessene Abweichungen; zukünftige Fehler können größer sein.')
    if rows:
        out.update(meanAbsoluteError=sum(abs(r['error']) for r in rows)/count,
                   maxAbsoluteError=max(abs(r['error']) for r in rows),
                   lastValidationAt=datetime.fromtimestamp(last,timezone.utc).isoformat())
    if not ready:
        out['reason']='Genauigkeit noch nicht ausreichend für diesen Referenz-Abstand gemessen'
    return out
