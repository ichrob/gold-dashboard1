"""Durable, bounded local OCR of paired handset lists; no browser or paid API."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def recognize(images):
    from PIL import Image, ImageOps
    import numpy as np
    import cv2
    from video_ocr import offline_engine
    cv2.setNumThreads(1)
    engine=offline_engine()
    result=[]
    for item in images:
        with Image.open(io.BytesIO(base64.b64decode(item['png'],validate=True))) as source:
            if source.format!='PNG' or source.width*source.height>16000000:raise ValueError('Image bounds')
            original=source.convert('RGB')
        passes=[]
        for scale,contrast in ((1.5,False),(2,False),(2.5,True)):
            im=original.resize((round(original.width*scale),round(original.height*scale)))
            if contrast:im=ImageOps.autocontrast(im.convert('L')).convert('RGB')
            rows,_=engine(np.asarray(im)[:,:,::-1],use_cls=False)
            rows=[r for r in (rows or []) if float(r[2])>=.7]
            # OCR lines in screen reading order; currency on the same footer row.
            rows.sort(key=lambda r:(round(min(p[1] for p in r[0])/18),min(p[0] for p in r[0])))
            lines=[]
            for points,text,_ in rows:
                y=sum(p[1] for p in points)/4
                if lines and abs(lines[-1][0]-y)<14*scale:lines[-1][1]+=' '+text
                else:lines.append([y,text])
            passes.append('\n'.join(line[1] for line in lines))
        result.append(passes)
    return result


def process(payload,at):
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LD_LIBRARY_PATH')}
    env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    child=subprocess.run([sys.executable,__file__,'--ocr'],input=json.dumps(payload['images']),text=True,capture_output=True,timeout=120,check=True,env=env)
    if len(child.stdout)>300000:raise ValueError('OCR output limit')
    import evaluator_runtime
    result=evaluator_runtime.run(['node',str(Path(__file__).with_name('handset_list_parse.js'))],input=json.dumps({'images':json.loads(child.stdout),'at':at}),text=True,capture_output=True,timeout=20,check=True)
    return json.loads(result.stdout)


def tick(connect,runner=process):
    with connect() as conn:
        row=conn.execute("""SELECT i.batch_id,i.payload,i.created_at FROM bob_android_list_images i
            JOIN bob_android_diagnostic_devices d USING(token_hash)
            WHERE NOT d.revoked AND d.expires_at>now() AND i.created_at>now()-interval '24 hours'
            AND COALESCE(i.import_receipt->>'stage','') NOT IN ('synced','superseded')
            AND i.processing_attempts<3 AND (i.processing_at IS NULL OR i.processing_at<now()-interval '4 minutes')
            ORDER BY i.created_at DESC LIMIT 1 FOR UPDATE OF i SKIP LOCKED""").fetchone()
        if not row:return False
        batch,payload,created=row
        conn.execute("UPDATE bob_android_list_images SET processing_at=now(),processing_attempts=processing_attempts+1 WHERE batch_id=%s",(batch,))
        conn.commit()
    try:
        parsed=runner(payload,payload['images'][-1]['at'])
        if len(parsed.get('items',[]))!=10 or len({x.get('isin') for x in parsed['items']})!=10:
            raise ValueError('Incomplete list')
        if {p.get('isin') for p in parsed.get('evidence',{}).get('products',[])}!={x['isin'] for x in parsed['items']}:
            raise ValueError('Mismatched evidence')
        with connect() as conn:
            current=conn.execute('SELECT i.import_receipt FROM bob_android_list_images i JOIN bob_android_diagnostic_devices d USING(token_hash) WHERE i.batch_id=%s AND NOT d.revoked AND d.expires_at>now() FOR UPDATE OF i',(batch,)).fetchone()
            if not current or (current[0] or {}).get('stage')=='synced':return True
            import paper_simulation
            result=paper_simulation.sync(conn,parsed['evidence'])
            if not result.get('ok') or (not result.get('preserved') and result.get('products')!=10):raise ValueError('Persistence not confirmed')
            stage='superseded' if result.get('preserved') else 'synced'
            receipt={'batchId':batch,'stage':stage,'count':10,'at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
            conn.execute('UPDATE bob_android_list_images SET parsed_items=%s::jsonb,import_receipt=%s::jsonb WHERE batch_id=%s',(json.dumps(parsed['items']),json.dumps(receipt),batch))
            conn.commit()
    except Exception as exc:
        with connect() as conn:
            conn.execute("UPDATE bob_android_list_images SET import_receipt=%s::jsonb WHERE batch_id=%s AND COALESCE(import_receipt->>'stage','')!='synced'",(json.dumps({'batchId':batch,'stage':'read-failed','count':0,'error':type(exc).__name__}),batch))
            conn.commit()
    return True


def loop(connect):
    # One OCR process at a time on the small server. Keep the existing video
    # reader's two-minute cadence, with handset work first in each cycle.
    import video_ocr
    last_video=0.0
    while True:
        try:tick(connect)
        except Exception:pass  # Fixed receipts expose failures without screenshot text in logs.
        if time.monotonic()-last_video>=120:
            try:print('BOB_VIDEO_OCR status='+video_ocr.tick(connect),flush=True)
            except Exception as exc:print('BOB_VIDEO_OCR error='+type(exc).__name__,flush=True)
            last_video=time.monotonic()
        time.sleep(10)

if __name__=='__main__' and '--ocr' in sys.argv:
    import socket, resource
    def no_network(*args,**kwargs):raise RuntimeError('Local OCR network disabled')
    socket.socket.connect=no_network
    resource.setrlimit(resource.RLIMIT_CPU,(110,110))
    raw=sys.stdin.read(8100001)
    if len(raw)>8100000:raise ValueError('Image input limit')
    print(json.dumps(recognize(json.loads(raw))))
