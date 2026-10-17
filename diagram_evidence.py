"""Descriptive signal evidence; sampling is fixed before looking at outcomes."""
from datetime import datetime
from zoneinfo import ZoneInfo
import math


def signal_evidence(rows, score):
    unique={}
    for row,truths in sorted(rows,key=lambda x:x[0].get('origin')!='background'):
        at=row.get('recordedAt')
        if type(at) not in (int,float) or not math.isfinite(at):continue
        if row.get('direction') not in ('LONG','SHORT'):continue
        unique.setdefault(row.get('barAt',at),(row,truths))
    result={}
    for index,h in enumerate((15,60,240)):
        last=None;blocks={};samples=0;selected=0
        for row,truths in sorted(unique.values(),key=lambda x:x[0]['recordedAt']):
            at=row['recordedAt']
            if last is not None and at-last<h*60000:continue
            last=at;selected+=1  # Missing outcomes still reserve their time window.
            outcome=score(row,truths[index],h)
            value=(outcome or {}).get('directionalPct')
            if type(value) not in (float,int) or not math.isfinite(value):continue
            day=datetime.fromtimestamp(at/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
            b=blocks.setdefault(day,dict(day=day,count=0,total=0.))
            b['count']+=1;b['total']+=value;samples+=1
        result[str(h)]=dict(selected=selected,separated=samples,missing=selected-samples,days=len(blocks),blocks=list(blocks.values()))
    return result
