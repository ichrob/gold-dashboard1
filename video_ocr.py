"""Bounded offline OCR for retained public storyboard frames; never a quote source."""
import base64
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
VERSION='rapidocr-local-v1'


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_video_ocr (
        video_id TEXT PRIMARY KEY REFERENCES bob_research_enhancements(video_id) ON DELETE CASCADE,
        fingerprint TEXT NOT NULL,version TEXT NOT NULL,status TEXT NOT NULL,
        result JSONB,attempted_at TIMESTAMPTZ NOT NULL DEFAULT now())''')


def lines_checked(rows,width,height,scale):
    lines=[]
    for row in (rows or [])[:120]:
        try:
            points,text,confidence=row
            if not isinstance(text,str) or not text.strip() or not math.isfinite(float(confidence)) or not .55<=float(confidence)<=1:continue
            xs=[float(p[0])/scale for p in points];ys=[float(p[1])/scale for p in points]
            if len(xs)!=4 or not all(math.isfinite(v) for v in xs+ys):continue
            left=max(0,min(width,min(xs)));top=max(0,min(height,min(ys)))
            right=max(left,min(width,max(xs)));bottom=max(top,min(height,max(ys)))
            if right-left<1 or bottom-top<1:continue
            lines.append(dict(text=text[:240],confidence=round(float(confidence),3),numeric=bool(re.search(r'\d',text)),
                              bounds=[round(left,1),round(top,1),round(right-left,1),round(bottom-top,1)],verified=False))
        except (ValueError,TypeError,IndexError):continue
    return lines


def recognize(frames):
    if not any(isinstance(f,dict) and not f.get('isCover') for f in frames[:5]):
        return dict(status='no-timed-images',engine=VERSION,images=[],note='Keine zeitlich zugeordneten Videobilder; Titelbilder werden nicht als Chartbeleg gelesen.')
    from PIL import Image
    import cv2
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    cv2.setNumThreads(1)
    engine=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1,det_limit_side_len=640,rec_batch_num=1)
    images=[]
    for index,frame in enumerate(frames[:5]):
        if not isinstance(frame,dict) or frame.get('isCover'):continue
        url=frame.get('dataUrl');at=frame.get('at')
        if not isinstance(url,str) or not re.fullmatch(r'data:image/jpeg;base64,[A-Za-z0-9+/=]{100,140000}',url) or isinstance(at,bool) or not isinstance(at,(int,float)) or not 0<=at<=86400:continue
        try:
            raw=base64.b64decode(url.split(',',1)[1],validate=True)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format!='JPEG' or source.width*source.height>500000:continue
                width,height=source.size
                if width<200 or height<100:
                    images.append(dict(index=index,at=at,status='too-small',lines=[],width=width,height=height));continue
                scale=min(2,960/max(width,height));im=source.convert('RGB').resize((round(width*scale),round(height*scale)))
            rows,_=engine(np.asarray(im)[:,:,::-1],use_cls=False)
            lines=lines_checked(rows,width,height,scale)
            images.append(dict(index=index,at=at,status='read' if lines else 'unreadable',lines=lines,width=width,height=height))
        except (OSError,ValueError):images.append(dict(index=index,at=at,status='unreadable',lines=[]))
    return dict(status='complete' if images else 'no-timed-images',engine=VERSION,images=images,
                note='Lokale OCR ohne API-Gebühr. Bildlesungen sind ungeprüft; Erkennungswerte sind keine Genauigkeitsgarantie. Storyboard-Videostellen sind angenähert, keine Marktzeitpunkte.')


def run(frames):
    # No API credentials, external OCR endpoints or model downloads in the child.
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LD_LIBRARY_PATH')}
    env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child'],input=json.dumps(frames),
                              text=True,capture_output=True,timeout=35,env=env,check=True)
        if len(result.stdout)>300000:raise ValueError('Output limit')
        data=json.loads(result.stdout)
        if not isinstance(data,dict) or not isinstance(data.get('images'),list):raise ValueError('Invalid OCR result')
        return data
    except Exception as exc:
        return dict(status='error',images=[],engine=VERSION,note='Lokale Bilderkennung nicht verfügbar; kein kostenpflichtiger Ersatz.',error=type(exc).__name__)


def tick(connect,runner=run):
    with connect() as conn:
        if not conn.execute('SELECT pg_try_advisory_xact_lock(68431032)').fetchone()[0]:return 'busy'
        row=conn.execute('''SELECT e.video_id,e.frames,md5(e.frames::text) FROM bob_research_enhancements e
            LEFT JOIN bob_video_ocr o ON o.video_id=e.video_id
            WHERE e.frames IS NOT NULL AND jsonb_array_length(e.frames)>0
            AND (o.video_id IS NULL OR o.fingerprint<>md5(e.frames::text) OR o.version<>%s
                OR o.status='pending' AND o.attempted_at<now()-interval '5 minutes'
                OR o.status='error' AND o.attempted_at<now()-interval '24 hours')
            ORDER BY e.updated_at DESC LIMIT 1''',(VERSION,)).fetchone()
        if not row:return 'idle'
        identity,frames,fingerprint=row
        conn.execute('''INSERT INTO bob_video_ocr(video_id,fingerprint,version,status) VALUES(%s,%s,%s,'pending')
            ON CONFLICT(video_id) DO UPDATE SET fingerprint=excluded.fingerprint,version=excluded.version,
            status='pending',result=NULL,attempted_at=now()''',(identity,fingerprint,VERSION));conn.commit()
    result=runner(frames)
    with connect() as conn:
        conn.execute('''UPDATE bob_video_ocr SET status=%s,result=%s::jsonb
            WHERE video_id=%s AND fingerprint=%s AND version=%s''',
            (result['status'],json.dumps(result),identity,fingerprint,VERSION));conn.commit()
    return result['status']


def report(conn,identity):
    row=conn.execute('''SELECT o.result FROM bob_video_ocr o JOIN bob_research_enhancements e ON e.video_id=o.video_id
        WHERE o.video_id=%s AND o.fingerprint=md5(e.frames::text) AND o.version=%s''',(identity,VERSION)).fetchone()
    return row[0] if row and row[0] else dict(status='pending',images=[],note='Kostenlose lokale Bilderkennung wartet auf den nächsten Hintergrundlauf.')


def loop(connect):
    while True:
        try:print('BOB_VIDEO_OCR status='+tick(connect),flush=True)
        except Exception as exc:print('BOB_VIDEO_OCR error='+type(exc).__name__,flush=True)
        time.sleep(120)


if __name__=='__main__':
    import socket
    def no_network(*args,**kwargs):raise RuntimeError('OCR network disabled')
    socket.socket.connect=no_network
    # Native models are packaged with the pinned OCR dependency.
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    print(json.dumps(recognize(json.loads(sys.stdin.read(800000)))))
