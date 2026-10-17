"""Fixed entry-time labels, descriptive only. Unknown evidence stays unknown."""
import math
VERSION='entry-regimes-v1'

def finite(v):return type(v) in (int,float) and math.isfinite(v)

def classify(market):
    c=market.get('context') or {};adx=c.get('adx');atr=c.get('atr');price=market.get('price')
    valid=market.get('ready') is True and market.get('priceFresh') is True
    trend=('strong-trend' if adx>=25 else 'sideways' if adx<20 else 'transition') if valid and finite(adx) and 0<=adx<=100 else 'unknown'
    pct=atr/price*100 if valid and finite(atr) and atr>0 and finite(price) and price>0 else None
    volatility=('high' if pct>=.3 else 'low' if pct<.1 else 'normal') if pct is not None else 'unknown'
    return dict(version=VERSION,trend=trend,volatility=volatility,adx=adx if finite(adx) else None,
        atrPct=pct,at=market.get('dataAt'),barAt=c.get('barAt',market.get('analysisBarAt')),
        note='Feste Grenzen: ADX <20 / 20–25 / ≥25; ATR/Gold <0,1 % / 0,1–0,3 % / ≥0,3 %. Keine neue Handelsregel.')


def summarize(rows,lifecycles):
    lookup={(r['currency'],r['slot']):r for r in lifecycles};groups={}
    for row,outcome in rows:
        label=row.get('regime') or {};key=(row['currency'],label.get('trend','unknown'),label.get('volatility','unknown'))
        g=groups.setdefault(key,dict(currency=key[0],trend=key[1],volatility=key[2],total=0,
            horizonCount=0,exitCount=0,horizonChosen=[],horizonBest=[],exitChosen=[],exitBest=[]))
        g['total']+=1
        for prefix,result in (('horizon',outcome),('exit',lookup.get((row['currency'],row['slot'])))):
            if (result or {}).get('complete'):
                g[prefix+'Count']+=1;g[prefix+'Chosen'].append(result['chosenPct']);g[prefix+'Best'].append(result['bestPct'])
    for g in groups.values():
        for key in ('horizonChosen','horizonBest','exitChosen','exitBest'):
            values=g.pop(key);g[key+'MeanPct']=sum(values)/len(values) if values else None
    return dict(version=VERSION,descriptiveOnly=True,limit=100,groups=list(groups.values()),
        note='Marktphase beim Einstieg festgehalten. Nur jüngste 100 Gruppen; Währungen getrennt. Beste Rendite erst im Rückblick bekannt. Keine automatische Regel je Marktphase.')
