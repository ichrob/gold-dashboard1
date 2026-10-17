"""Conservative OCR value typing. Labels are required; all output stays unverified."""
import re
import math
NUMBER=r'[-+]?\d+(?:[.,]\d+)*'


def numeric(raw,metric):
    raw=raw.replace(' ','')
    if ',' in raw and '.' in raw:
        decimal=',' if raw.rfind(',')>raw.rfind('.') else '.'
        raw=raw.replace('.' if decimal==',' else ',','').replace(decimal,'.')
    elif re.fullmatch(r'[-+]?\d{1,3}[.,]\d{3}',raw) and metric not in ('rsi','adx','macd','atr'):
        return None # 4.200 can mean 4.2 or 4200; never guess a price convention.
    else:raw=raw.replace(',','.')
    try:value=float(raw)
    except ValueError:return None
    return value if math.isfinite(value) else None


def extract(lines):
    joined=' '.join(x.get('text','') for x in lines)
    joined=re.sub(r'(XAU\s*/\s*USD)(1m|5m|15m|30m|1h|4h)\b',r'\1 \2',joined,flags=re.I)
    currencies=set(re.findall(r'\b(?:USD|EUR|CHF)\b',joined.upper()))
    currency=next(iter(currencies)) if len(currencies)==1 else None
    instrument='XAU/USD' if re.search(r'\bXAU\s*/\s*USD\b',joined,re.I) and not re.search(r'\b(?:CFD|futures?|GC\w*|silver|silber|bitcoin|EUR/USD)\b',joined,re.I) else None
    timeframes=set(re.findall(r'(?<!\w)(?:1m|5m|15m|30m|1h|4h)(?!\w)',joined))
    timeframe=next(iter(timeframes)).lower() if len(timeframes)==1 else None
    values=[];unknown=[]
    for index,line in enumerate(lines):
        text=line.get('text','');matches=[]
        specs=[
            ('goldPrice','Goldkurs',r'(?:Gold(?:preis)?|XAU/USD)\s*[:=]\s*('+NUMBER+r')',None),
            ('ema','EMA',r'\bEMA\s*\(?\s*(\d{1,3})\s*\)?\s*[:=]\s*('+NUMBER+r')','period'),
            ('sma','SMA',r'\bSMA\s*\(?\s*(\d{1,3})\s*\)?\s*[:=]\s*('+NUMBER+r')','period'),
            ('rsi','RSI',r'\bRSI(?:\s*\(\s*(\d{1,3})\s*\))?\s*[:=]\s*('+NUMBER+r')','period'),
            ('adx','ADX',r'\bADX(?:\s*\(\s*(\d{1,3})\s*\))?\s*[:=]\s*('+NUMBER+r')','period'),
            ('atr','ATR',r'\bATR(?:\s*\(\s*(\d{1,3})\s*\))?\s*[:=]\s*('+NUMBER+r')','period'),
            ('target','Ziel',r'\b(?:Target|Ziel|Kursziel)\s*[:=]\s*('+NUMBER+r')',None),
            ('stop','Stopp',r'\b(?:Stop(?:[- ]?Loss)?|Stopp)\s*[:=]\s*('+NUMBER+r')',None),
            ('entry','Einstieg',r'\b(?:Entry|Einstieg)\s*[:=]\s*('+NUMBER+r')',None),
            ('support','Unterstützung',r'\b(?:Support|Unterst.tzung)\s*[:=]\s*('+NUMBER+r')',None),
            ('resistance','Widerstand',r'\b(?:Resistance|Widerstand)\s*[:=]\s*('+NUMBER+r')',None),
            ('fibonacci','Fibonacci',r'\b(?:Fib(?:onacci)?)\s*\(?\s*(38[.,]2|50(?:[.,]0)?|61[.,]8|78[.,]6|127[.,]2|161[.,]8)\s*%?\s*\)?\s*[:=]\s*('+NUMBER+r')','ratio'),
        ]
        for metric,label,pattern,param in specs:
            for m in re.finditer(pattern,text,re.I):
                raw=m[2] if param else m[1];value=numeric(raw,metric)
                if value is None or metric in ('rsi','adx') and not 0<=value<=100 or metric not in ('rsi','adx') and value<=0:continue
                unit='Punkte' if metric in ('rsi','adx') else currency or 'Einheit offen'
                record=dict(metric=metric,label=label,value=value,unit=unit,lineIndex=index,quote=text,
                            instrument=instrument,currency=currency,timeframe=timeframe,verified=False,
                            marketTimeStatus='unknown',readingStatus=line.get('readingStatus','single'))
                if param:record[param]=numeric(m[1],metric) if m[1] else None
                record['contextComplete']=bool(instrument and currency and timeframe and (not param or record[param] is not None))
                values.append(record);matches.append(m.span())
        if re.search(r'\d',text) and not matches:unknown.append(dict(lineIndex=index,text=text,reason='Bedeutung oder Zahlenformat nicht eindeutig'))
    return dict(values=values,unclassified=unknown,instrument=instrument,currency=currency,timeframe=timeframe,
                scope='Beschriftete Bildwerte, ungeprüfte OCR. Videoposition ist kein Marktzeitpunkt.')
