"""Private product quality summary from existing evidence; no source requests."""
import copy
import hashlib
import json
import math
from datetime import datetime,timezone


def stamp(value):
    if type(value) in (int,float):return value if math.isfinite(value) and value>1_600_000_000_000 else None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.timestamp()*1000 if parsed.tzinfo else None
    except (ValueError,TypeError,AttributeError):return None


def snapshot(quote):
    """Identical source evidence has the same identity across consumers/processes."""
    result=copy.deepcopy(quote)
    fields=('isin','currency','bid','ask','bidAt','askAt','source','sourceUrl','priceKind',
            'metadata','currencyConversion','comdirectBackup','swissquoteBackup')
    evidence={k:result.get(k) for k in fields}
    result['snapshotId']=hashlib.sha256(json.dumps(evidence,sort_keys=True,default=str).encode()).hexdigest()[:24]
    result['dataOrigin']='calculated' if result.get('priceKind') in ('calculated','calculated-turbo') else 'source-observation'
    return result


def summarize(audit,now=None):
    now=datetime.now(timezone.utc).timestamp()*1000 if now is None else now
    items=[r for r in audit.get('items',[]) if r.get('state')!='terminated']
    current=audit.get('status')=='ok' and stamp(audit.get('lastCheckedAt')) is not None and 0<=now-stamp(audit['lastCheckedAt'])<=180000
    fresh=sum(stamp(r.get('quoteSourceAt')) is not None and 0<=now-stamp(r['quoteSourceAt'])<=90000 and not set(r.get('missing',[]))&{'quote','quote-time'} for r in items)
    complete=sum(r.get('state') in ('issuer-evidence-complete','analysis-evidence-complete') and not r.get('missing') for r in items)
    gaps=[];conflicts=[]
    for item in items:
        for code,since in (item.get('missingSince') or {}).items():
            at=stamp(since)
            if code in item.get('missing',[]) and at is not None and 0<=now-at:
                labels=dict(zip(item.get('missing',[]),item.get('messages',[])))
                gaps.append(dict(isin=item.get('isin'),field=code,label=labels.get(code,code),since=since,minutes=int((now-at)/60000)))
        cross=item.get('marketCrossCheck') or {}
        if cross.get('status') in ('outlier','conflict','mismatch','divergent'):conflicts.append(item.get('isin'))
    comparisons=[]
    for isin,study in (audit.get('priceStudy') or {}).items():
        value=study.get('rawMae');count=study.get('validationCount',0)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 and count>0:
            comparisons.append(dict(isin=isin,currency=study.get('currency'),meanAbsoluteError=value,
                validationCount=count,lastAt=study.get('lastAt')))
    return dict(status='ok' if current else audit.get('status') if audit.get('status')!='ok' else 'stale',
        checkedAt=audit.get('lastCheckedAt'),listUploadedAt=audit.get('listUploadedAt'),total=len(items),
        fresh=fresh if current else None,complete=complete if current else None,
        freshPct=round(100*fresh/len(items),1) if current and items else None,
        completePct=round(100*complete/len(items),1) if current and items else None,
        gaps=gaps,conflicts=conflicts,comparisons=comparisons,
        snapshots=[dict(isin=r.get('isin'),id=r.get('snapshotId'),currency=r.get('nativeCurrency'),
                        source=r.get('dataQuoteSource'),sourceAt=r.get('quoteSourceAt'),kind=r.get('dataQuoteKind')) for r in items],
        note='Prüfnachweise der gespeicherten Produktliste, keine Handelsfreigabe. Kursabweichungen sind historische spätere Vergleiche derselben ISIN, Währung und Geldkursseite; kein Vergleichspreis bedeutet unbekannt. Lückendauer wird ab der ersten Erfassung dieser Anzeige gemessen.')


def read(conn):
    import degiro_product_audit
    return summarize(degiro_product_audit.read(conn))
