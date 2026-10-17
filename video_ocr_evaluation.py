"""Reproducible labeled image benchmark, separate development and held-out sets."""
import base64
import io
import json
from pathlib import Path


def source_fingerprint():
    import hashlib
    return hashlib.sha256(b''.join(Path(__file__).with_name(name).read_bytes() for name in
        ('video_ocr.py','video_values.py','video_ocr_evaluation.py'))).hexdigest()


def score(expected,predicted):
    # Multisets: duplicated or wrongly attributed values count as false positives.
    from collections import Counter
    def key(v):return (v['metric'],round(v['value'],6),v.get('period'),v.get('ratio'),v.get('unit'))
    truth=Counter(key(v) for v in expected);got=Counter(key(v) for v in predicted)
    correct=sum((truth&got).values());missed=sum((truth-got).values());wrong=sum((got-truth).values())
    return dict(correct=correct,wrong=wrong,missed=missed)


def aggregate(rows):
    totals={k:sum(r[k] for r in rows) for k in ('correct','wrong','missed')}
    c,w,m=totals.values()
    return dict(totals,precision=c/(c+w) if c+w else None,recall=c/(c+m) if c+m else None,
                error=w+m)


def promotion_allowed(report):
    if report.get('status')!='evaluated' or report.get('engine')!='rapidocr-local-v3' or report.get('candidate')!='contrast':return False
    if not report.get('disjointSets') or report.get('holdoutImages',0)<8:return False
    for split in ('development','holdout'):
        baseline=report.get(split,{}).get('baseline',{});candidate=report.get(split,{}).get('contrast',{})
        if not all(isinstance(x.get('error'),(int,float)) for x in (baseline,candidate)):return False
        if candidate['error']>=baseline['error'] or candidate.get('wrong',999)>baseline.get('wrong',-1):return False
        if candidate.get('correct',0)<baseline.get('correct',0):return False
    return True


def fixtures(split):
    from PIL import Image,ImageDraw,ImageFont,ImageFilter
    # Different texts, values, and chart backgrounds in each split; never runtime MCO data.
    shift=0 if split=='development' else 173
    for i in range(8):
        price=4200.50+shift+i*7;rsi=51.2+i+(0 if split=='development' else 4)
        metric=['goldPrice','ema','rsi','target','stop','fibonacci','support',None][i]
        value=rsi if metric=='rsi' else price
        labels={'goldPrice':f'Gold: {price:.2f}','ema':f'EMA 20: {price:.2f}','rsi':f'RSI (14): {rsi:.1f}',
                'target':f'Target: {price:.2f}','stop':f'Stop: {price:.2f}','fibonacci':f'Fib 61.8%: {price:.2f}',
                'support':f'Support: {price:.2f}',None:'MCO Chart analysis'}
        dark=i%3==1;bg=(24,28,34) if dark else (250,250,250);fg=(230,230,230) if dark else (20,20,20)
        im=Image.new('RGB',(640,360),bg);draw=ImageDraw.Draw(im)
        font=ImageFont.truetype('DejaVuSans.ttf',22 if i%2 else 25)
        draw.text((20,18),'XAU/USD 15m',font=font,fill=fg)
        draw.text((20,64),labels[metric],font=font,fill=fg)
        for j in range(14):
            x=30+j*37;y=230+((j*19+shift)%65)-32
            draw.line((x,y-20,x,y+25),fill=(45,130,100),width=2);draw.rectangle((x-4,y-8,x+4,y+12),fill=(45,130,100))
        if i==6:im=im.filter(ImageFilter.GaussianBlur(.6))
        buf=io.BytesIO();im.save(buf,'JPEG',quality=70 if i%2 else 88)
        frame=dict(at=i*20,dataUrl='data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode())
        expected=[] if metric is None else [dict(metric=metric,value=value,unit='Punkte' if metric=='rsi' else 'USD',
                    **({'period':20} if metric=='ema' else {'period':14} if metric=='rsi' else {'ratio':61.8} if metric=='fibonacci' else {}))]
        yield f'{split}-{i}',frame,expected


def evaluate():
    import hashlib
    import video_ocr
    from datetime import datetime,timezone
    report=dict(evaluatedAt=datetime.now(timezone.utc).isoformat(),sourceFingerprint=source_fingerprint(),status='evaluated',engine=video_ocr.VERSION,candidate='contrast',scope='Synthetische beschriftete Chartbilder; keine gemessene Genauigkeit auf echten MCO-Videos.',
                developmentImages=8,holdoutImages=8,disjointSets=True,fixtureVersion='charts-v2',datasets={})
    for split in ('development','holdout'):
        cases=list(fixtures(split));report['datasets'][split]=[hashlib.sha256(f['dataUrl'].encode()).hexdigest() for _,f,_ in cases];report[split]={}
        for profile in ('baseline','contrast'):
            rows=[]
            for start in (0,4):
                subset=cases[start:start+4];result=video_ocr.run([f for _,f,_ in subset],profile=profile)
                if result['status']!='complete':raise RuntimeError('OCR benchmark did not complete')
                images={im['index']:im for im in result['images']}
                for index,(_,frame,expected) in enumerate(subset):
                    rows.append(score(expected,images.get(index,{}).get('typed',{}).get('values',[])))
            report[split][profile]=aggregate(rows)
    report['disjointSets']=not bool(set(report['datasets']['development'])&set(report['datasets']['holdout']))
    report['activeProfile']='contrast' if promotion_allowed(report) else 'baseline'
    return report

if __name__=='__main__':
    Path(__file__).with_name('video_ocr_evaluation.json').write_text(json.dumps(evaluate(),ensure_ascii=False,indent=2)+'\n')
