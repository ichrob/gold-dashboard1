"""Explicit transcript context for time-aligned, display-only Fibonacci comparison."""
import re
from datetime import datetime


def context(segments, at):
    text=' '.join(s.get('text','') for s in segments if isinstance(s.get('at'),(int,float)) and abs(s['at']-at)<=90)
    # Require an explicit analysis/recording timestamp including timezone.
    stamps=[]
    pattern=r'(?:Analysezeit|Stand|Aufnahmezeit|as of|recorded at)\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})[ T,]+(?:um\s*)?(\d{2}:\d{2}(?::\d{2})?)\s*(Z|UTC|GMT|MEZ|MESZ|CET|CEST|[+-]\d{2}:\d{2})(?![\w+-])'
    for m in re.finditer(pattern,text,re.I):
        try:
            day=m[1] if '-' in m[1] else datetime.strptime(m[1],'%d.%m.%Y').strftime('%Y-%m-%d')
            zone=m[3].upper();zone={'Z':'+00:00','UTC':'+00:00','GMT':'+00:00','MEZ':'+01:00','CET':'+01:00','MESZ':'+02:00','CEST':'+02:00'}.get(zone,zone)
            stamps.append((int(datetime.fromisoformat(day+'T'+m[2]+zone).timestamp()*1000),m[0]))
        except ValueError:pass
    frames=set()
    for tf,pattern in [('1m',r'\b1\s*(?:m\b|min|minute)'),('5m',r'\b5\s*(?:m\b|min|minute)'),('15m',r'\b15\s*(?:m\b|min|minute)'),('30m',r'\b30\s*(?:m\b|min|minute)'),('1h',r'\b(?:1\s*h|1\s*hour|Stundenchart|hourly)\b'),('4h',r'\b(?:4\s*h|4\s*hour)\b')]:
        if re.search(pattern,text,re.I):frames.add(tf)
    spot=bool(re.search(r'\bXAU\s*/?\s*USD\b|\bGold\s*Spot\b|\bSpot\s*Gold\b',text,re.I))
    conflict=bool(re.search(r'\b(?:future[s]?|CFD|GC[A-Z]?\d{0,2})\b',text,re.I))
    result={'analysisAt':None,'timeframe':next(iter(frames)) if len(frames)==1 else None,
            'instrument':'XAU/USD' if spot and not conflict else None,'currency':'USD' if spot and not conflict else None}
    if len({s[0] for s in stamps})==1:result.update(analysisAt=stamps[0][0],timeEvidence=stamps[0][1])
    result['timeConflict']=len({s[0] for s in stamps})>1
    dates=set()
    for raw in re.findall(r'\b(?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\b',text):
        try:dates.add(datetime.strptime(raw,'%Y-%m-%d' if '-' in raw else '%d.%m.%Y').strftime('%Y-%m-%d'))
        except ValueError:pass
    if len(dates)==1:result['analysisDay']=next(iter(dates))
    quotes=[]
    price=r'([1-9]\d{3,4}(?:[.,]\d{1,2})?|[1-9]\d?[.,]\d{3}(?:[.,]\d{1,2})?)'
    pattern=r'\b(?:Gold|XAU\s*/?\s*USD)(?:preis)?\s+(?:(?:notiert|steht|handelt)(?:\s+(?:aktuell|jetzt|gerade))?\s+bei|(?:is\s+)?(?:currently\s+)?trading\s+at)\s*\$?\s*'+price+r'(?![\d.,])'
    for segment in segments:
        if not isinstance(segment.get('at'),(int,float)) or abs(segment['at']-at)>90:continue
        for sentence in re.split(r'(?<=[!?])\s+|(?<=\.)\s+(?=[A-Z])',segment.get('text','')):
            if re.search(r'\b(?:wenn|falls|if|could|würde|wäre|ziel|target|gestern|yesterday)\b',sentence,re.I):continue
            for match in re.finditer(pattern,sentence,re.I):
                raw=match[1]
                if re.fullmatch(r'\d{1,2}[.,]\d{3}(?:[.,]\d{1,2})?',raw):
                    index=next(i for i,c in enumerate(raw) if c in '.,');raw=raw[:index]+raw[index+1:]
                raw=raw.replace(',','.')
                value=float(raw)
                if 500<=value<=25000:
                    decimals=len(raw.split('.')[1]) if '.' in raw else 0
                    quotes.append(dict(price=value,tolerance=0.5*10**(-decimals),at=segment['at'],evidence=match[0][:200]))
    if len({q['price'] for q in quotes})==1:result['currentGoldQuote']=quotes[0]
    return result
