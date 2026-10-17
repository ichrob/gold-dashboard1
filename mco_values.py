"""Typed numeric statements from captions, retaining unclassified evidence."""
import re
from mco_comparison import context
NUM=r'[-+]?(?:\d{1,2}[.,]\d{3}(?:[.,]\d{1,3})?|\d+(?:[.,]\d+)?)'
JOIN=r'\s*(?:(?:liegt|steht|is|liegt aktuell|steht aktuell)\s*)?(?:bei|at|=|:)\s*\$?\s*'

def number(raw, price_format=True):
    sign=-1 if raw.startswith('-') else 1
    raw=raw.lstrip('+-')
    if price_format and re.fullmatch(r'\d{1,2}[.,]\d{3}(?:[.,]\d{1,3})?',raw):
        i=next(i for i,c in enumerate(raw) if c in '.,');raw=raw[:i]+raw[i+1:]
    return sign*float(raw.replace(',','.'))

def extract(segments):
    values=[];others=[];seen=set();total=0
    for segment in segments:
        text=segment.get('text','');at=segment.get('at')
        if not isinstance(text,str) or not isinstance(at,(int,float)) or isinstance(at,bool) or not 0<=at<=86400:continue
        if not re.search(r'\d',text):continue
        ctx=None;spans=[]
        def add(metric,label,raw,match,unit='USD',**extra):
            nonlocal ctx,total
            try:value=number(raw,metric not in ('rsi','adx','atr','plusDI','minusDI','stochastic','macd','macdSignal','macdHist'))
            except ValueError:return
            if unit=='USD' and metric not in ('atr','macd','macdSignal','macdHist') and not 500<=value<=25000:return
            if unit=='Punkte' and not 0<=value<=100:return
            identity=(metric,value,at,tuple(sorted(extra.items())))
            if identity in seen:return
            seen.add(identity);spans.append(match.span());total+=1
            if len(values)>=200:return
            if ctx is None:ctx=context(segments,at)
            ctx=dict(ctx)
            currencies=set(re.findall(r'\b(?:EUR|CHF|USD)\b',text,re.I))
            currencies={c.upper() for c in currencies}
            if currencies & {'EUR','CHF'}:
                ctx['currency']=next(iter(currencies)) if len(currencies)==1 else None
                if unit=='USD':unit=ctx['currency'] or 'Einheit offen'
            if re.search(r'\b(?:silver|silber|bitcoin|DXY|NASDAQ|S&P|crude oil)\b',text,re.I):ctx['instrument']=None
            values.append(dict(metric=metric,label=label,price=value,unit=unit,at=at,quote=text[:600],comparisonContext=ctx,
                conditional=bool(re.search(r'\b(wenn|falls|if|could|würde|wäre|target|ziel)\b',text,re.I)),**extra))
        for m in re.finditer(r'\b(EMA|SMA)\s*\(?\s*(\d{1,3})\s*\)?'+JOIN+'('+NUM+r')(?!\d|[.,]\d)',text,re.I):
            p=int(m[2]);add(m[1].lower(),m[1].upper()+' '+str(p),m[3],m,period=p)
        for m in re.finditer(r'\b(RSI|ADX|ATR|\+DI|-DI|Stochastik|Stochastic)\s*(?:\(\s*(\d{1,3})\s*\)|(\d{1,3}))?'+JOIN+'('+NUM+r')(?!\d|[.,]\d)',text,re.I):
            kind={'rsi':'rsi','adx':'adx','atr':'atr','+di':'plusDI','-di':'minusDI','stochastik':'stochastic','stochastic':'stochastic'}[m[1].lower()]
            p=int(m[2] or m[3]) if m[2] or m[3] else None
            add(kind,m[1].upper()+((' '+str(p)) if p else ' · Periode offen'),m[4],m,'USD' if kind=='atr' else 'Punkte',period=p)
        for m in re.finditer(r'\bMACD(?:[-\s]+(Signal|Histogramm|Histogram|Linie|Line))?\s*(?:\(\s*(\d+)\s*[,/]\s*(\d+)\s*[,/]\s*(\d+)\s*\))?'+JOIN+'('+NUM+r')(?!\d|[.,]\d)',text,re.I):
            kind={'signal':'macdSignal','histogramm':'macdHist','histogram':'macdHist'}.get((m[1] or '').lower(),'macd')
            add(kind,'MACD '+(m[1] or 'Linie'),m[5],m,fast=int(m[2]) if m[2] else None,slow=int(m[3]) if m[3] else None,signal=int(m[4]) if m[4] else None)
        for m in re.finditer(r'\bBollinger[-\s]+(Oberband|Unterband|Mittellinie|upper|lower|middle)\s*(?:\(\s*(\d+)\s*[,/]\s*(\d+(?:\.\d+)?)\s*\))?'+JOIN+'('+NUM+r')(?!\d|[.,]\d)',text,re.I):
            band={'oberband':'up','upper':'up','unterband':'lo','lower':'lo','mittellinie':'mid','middle':'mid'}[m[1].lower()]
            add('boll','Bollinger '+m[1],m[4],m,period=int(m[2]) if m[2] else None,multiplier=float(m[3]) if m[3] else None,band=band)
        labels={'unterstützung':('support','Unterstützung'),'support':('support','Unterstützung'),'widerstand':('resistance','Widerstand'),'resistance':('resistance','Widerstand'),'kursziel':('target','Kursziel'),'target':('target','Kursziel'),'ziel':('target','Kursziel'),'stopp':('stop','Stopp'),'stop loss':('stop','Stopp'),'stop-loss':('stop','Stopp'),'einstieg':('entry','Einstieg'),'entry':('entry','Einstieg'),'tageshoch':('dayHigh','Tageshoch'),'tagestief':('dayLow','Tagestief'),'vwap':('vwap','VWAP')}
        for m in re.finditer(r'\b('+ '|'.join(re.escape(k) for k in labels)+r')'+JOIN+'('+NUM+r')(?!\d|[.,]\d)',text,re.I):
            kind,label=labels[m[1].lower()];add(kind,label,m[2],m)
        # Only an explicit current quote can supply the time-estimation anchor.
        if ctx is None:ctx=context(segments,at)
        q=ctx.get('currentGoldQuote')
        if q and q['at']==at and not any(v['metric']=='goldPrice' and v['at']==at for v in values):
            total+=1
            if len(values)<200:values.append(dict(metric='goldPrice',label='Aktueller Goldkurs laut Video',price=q['price'],unit='USD',at=at,quote=text[:600],comparisonContext=ctx,conditional=False))
        # Preserve numeric source statements even when their meaning is unsupported.
        if len(others)<200:others.append(dict(at=at,text=text[:1000],classified=bool(spans or q and q['at']==at)))
    return dict(values=values,numericStatements=others,totalValues=total,totalNumericStatements=sum(bool(re.search(r'\d',s.get('text',''))) for s in segments),
                scope='Gesprochene Zahlen aus verfügbaren Untertiteln. Rein eingeblendete Werte ohne Untertitel sind nicht automatisch erfasst.',limit=200)
