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
    return result
