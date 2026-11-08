"""Durable, bounded local OCR of paired handset lists; no browser or paid API."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import math
import tempfile
import hashlib
import ocr_workload_priority

_state = {"state": "not-started", "checkedAt": None, "error": None}
_state_lock = threading.Lock()

def observe(state, error=None):
    with _state_lock:
        _state.update(state=state, checkedAt=time.time(), error=error)

def status():
    with _state_lock:
        value=dict(_state)
    value["fresh"]=value["checkedAt"] is not None and time.time()-value["checkedAt"]<180
    value['ocrMemoryLimitMiB']=OCR_CONTAINER_LIMIT//(1024*1024)
    value['ocrStartReserveMiB']=OCR_START_RESERVE//(1024*1024)
    value['workloadPriority']=ocr_workload_priority.status()
    return value


def ocr_size(width, height, scale):
    # Full-resolution phone images must not be enlarged into tens of millions
    # of pixels on the shared small server. Preserve aspect ratio and originals.
    factor=min(scale, 1200/width, math.sqrt(1600000/(width*height)))
    return max(1,round(width*factor)),max(1,round(height*factor))


def ocr_strips(height):
    """Overlapping context, but disjoint ownership of each detected line centre."""
    if height<1:raise ValueError('Image height')
    starts=[0]
    while starts[-1]+512<height:starts.append(starts[-1]+384)
    for k,top in enumerate(starts):
        bottom=min(top+512,height)
        lower=0 if k==0 else (top+min(starts[k-1]+512,height))/2
        upper=height if k==len(starts)-1 else (bottom+starts[k+1])/2
        yield top,bottom,lower,upper


def recognize(images, enhanced=False):
    from PIL import Image
    import cv2
    from handset_ocr_engine import offline_engine
    cv2.setNumThreads(1)
    engine=offline_engine()
    from rapidocr_onnxruntime.ch_ppocr_det.utils import DetPreProcess
    detector=engine.text_det
    # The library's default 'min' limit only enlarges images; it is not a cap.
    # Bound detection tensors, while recognition crops retain source resolution.
    detector.get_preprocess=lambda _:DetPreProcess(448,'max',detector.mean,detector.std)
    result=[]
    for item in images:
        with Image.open(io.BytesIO(base64.b64decode(item['png'],validate=True))) as source:
            if source.format!='PNG' or source.width*source.height>16000000:raise ValueError('Image bounds')
            original=source.convert('RGB')
        try:
            result.append(recognize_image(original,engine,enhanced))
        finally:
            original.close()
    return result


def recognize_image(original,engine,enhanced=False):
    """Release working images on success and failure; keep optical rules intact."""
    from PIL import ImageOps, ImageEnhance
    import numpy as np
    passes=[]
    settings=((.95,'sharpen'),(1.,'sharpen'),(1.,'contrast')) if enhanced else (
        (.85,'plain'),(1.,'plain'),(1.,'contrast'))
    for scale,transform in settings:
        im=original.resize(ocr_size(original.width,original.height,scale))
        actual_scale=im.width/original.width
        try:
            if transform=='contrast':
                with im.convert('L') as gray:
                    with ImageOps.autocontrast(gray) as contrasted:
                        transformed=contrasted.convert('RGB')
                im.close()
                im=transformed
            elif transform=='sharpen':
                transformed=ImageEnhance.Sharpness(im).enhance(1.6)
                im.close()
                im=transformed
            rows=[]
            for top,bottom,lower,upper in ocr_strips(im.height):
                with im.crop((0,top,im.width,bottom)) as tile:
                    left,upper_edge,right,lower_edge=content_bounds(tile)
                    with tile.crop((left,upper_edge,right,lower_edge)) as content:
                        pixels=np.asarray(content)[:,:,::-1]
                        try:found,_=engine(pixels,use_cls=False)
                        finally:del pixels
                for points,text,score in found or []:
                    shifted=[[float(x)+left,float(y)+top+upper_edge] for x,y in points]
                    center=sum(p[1] for p in shifted)/4
                    if lower<=center<upper:rows.append([shifted,text,score])
                del found
                __import__('gc').collect()
                __import__('memory_watch').release_free_pages()
        finally:
            im.close()
        rows=[r for r in (rows or []) if float(r[2])>=.7]
        rows.sort(key=lambda r:sum(p[1] for p in r[0])/4)
        lines=[]
        for points,text,_ in rows:
            y=sum(p[1] for p in points)/4
            fragment=(min(p[0] for p in points),text)
            if lines and abs(lines[-1][0]-y)<14*actual_scale:lines[-1][1].append(fragment)
            else:lines.append([y,[fragment]])
        passes.append('\n'.join(' '.join(t for _,t in sorted(parts)) for _,parts in lines))
        del im, rows
        __import__('gc').collect()
        __import__('memory_watch').release_free_pages()
    return passes


def content_bounds(image):
    """Remove only exact uniform border pixels, not faint text or numbers."""
    from PIL import Image, ImageChops
    with Image.new(image.mode,image.size,image.getpixel((0,0))) as background:
        with ImageChops.difference(image,background) as difference:
            bounds=difference.getbbox()
    if bounds is None:return (0,0,image.width,image.height)
    left,top,right,bottom=bounds
    # Keep context for the existing detector, never threshold away text.
    return (max(0,left-8),max(0,top-8),min(image.width,right+8),min(image.height,bottom+8))


# User-approved ceiling: keep 7 MiB below the 512-MiB Render container limit.
# Admission still reserves 200 MiB for the native OCR model and its peak work.
OCR_CONTAINER_LIMIT = 505 * 1024 * 1024
OCR_START_RESERVE = 200 * 1024 * 1024
# Four admission checks at the existing four-minute lease cadence. Persisted
# in the receipt so a restart cannot reset a permanently blocked batch.
OCR_MAX_MEMORY_DEFERRALS = 4


def memory_deferrals(receipt):
    value=(receipt or {}).get('memoryDeferrals',0)
    return min(value,OCR_MAX_MEMORY_DEFERRALS) if type(value) is int and value>=0 else 0


def deferred_memory_receipt(batch,previous):
    count=memory_deferrals(previous)+1
    exhausted=count>=OCR_MAX_MEMORY_DEFERRALS
    value={'batchId':batch,'stage':'read-failed' if exhausted else 'waiting-memory',
           'count':0,'memoryDeferrals':count,'retryAllowed':not exhausted,
           'reason':'OCR_MEMORY_WAIT_EXHAUSTED' if exhausted else 'OCR_MEMORY_RESERVE',
           'at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    # Keep the existing, device-owned daily-list fallback available. This is
    # an honest memory failure, never a successful import or new list proof.
    if exhausted:value['error']='MemoryError'
    return value

def container_memory_bytes():
    """Current container memory, or None when no enforceable cgroup counter exists."""
    for path in ('/sys/fs/cgroup/memory.current','/sys/fs/cgroup/memory/memory.usage_in_bytes'):
        try:
            value=int(Path(path).read_text().strip())
            if value>0:return value
        except (OSError,ValueError):
            pass
    return None

def wait_ocr(child,memory_reader=container_memory_bytes,clock=time.monotonic,sleep=time.sleep,timeout=120,measurement=None):
    """Fail closed before local OCR can kill the shared 512-MiB service."""
    deadline=clock()+timeout
    while child.poll() is None:
        used=memory_reader()
        if measurement is not None and used is not None:
            measurement['peakBytes']=max(measurement.get('peakBytes') or 0,used)
            measurement['samples']+=1
        if used is None or used>=OCR_CONTAINER_LIMIT or clock()>=deadline:
            child.kill()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
            if used is None:raise RuntimeError('OCR memory counter unavailable')
            if used>=OCR_CONTAINER_LIMIT:raise MemoryError('OCR container budget')
            raise subprocess.TimeoutExpired(child.args,timeout)
        sleep(.05)
    return child.returncode


def report_ocr_memory(measurement, outcome, started):
    # One bounded record per image, no image bytes, identities or exceptions.
    # This is whole-container sampling, not exclusive child allocation or PSS.
    try:
        def mib(value):return round(value/(1024*1024),1) if value is not None else None
        record={
            'scope':'container-during-one-ocr-image', 'outcome':outcome,
            'beforeMiB':mib(measurement.get('beforeBytes')),
            'sampledPeakMiB':mib(measurement.get('peakBytes')),
            'afterMiB':mib(container_memory_bytes()),
            'samples':measurement['samples'],
            'durationMs':round((time.monotonic()-started)*1000),
        }
        # Expose the latest bounded observation in existing private status,
        # without an accumulating journal or automated reserve reduction.
        with _state_lock:
            _state['lastOcrMemory']=record
        print('BOB_OCR_MEMORY '+json.dumps(record,allow_nan=False),flush=True)
    except Exception:
        pass  # Diagnostics must not change OCR results or protection.

def guarded_ocr_run(args, *, input, text, capture_output, timeout, check, env, close_fds):
    # Preserve the cgroup-wide fail-closed guard and file-backed streams.
    # Return free parent heap pages before loading the child's native models.
    # No cache or evidence is deleted; the user-approved kill threshold is 505 MiB.
    __import__('gc').collect()
    __import__('memory_watch').release_free_pages()
    # Reserve measured OCR peak plus headroom before starting native models.
    used=container_memory_bytes()
    started=time.monotonic()
    measurement={'beforeBytes':used,'peakBytes':used,'samples':0}
    if used is None or used+OCR_START_RESERVE>=OCR_CONTAINER_LIMIT:
        report_ocr_memory(measurement,'deferred',started)
        raise OcrMemoryDeferred('OCR awaiting free container memory')
    with tempfile.TemporaryFile(mode='w+',encoding='utf-8') as source, \
         tempfile.TemporaryFile(mode='w+',encoding='utf-8') as output, \
         tempfile.TemporaryFile(mode='w+',encoding='utf-8') as errors:
        source.write(input);source.seek(0)
        child=subprocess.Popen(args,stdin=source,stdout=output,stderr=errors,
                               text=True,env=env,close_fds=close_fds,start_new_session=True)
        outcome='failed'
        try:
            code=wait_ocr(child,timeout=timeout,measurement=measurement)
            outcome='completed' if code==0 else 'child-failed'
        except MemoryError:
            outcome='memory-limit'
            raise
        except subprocess.TimeoutExpired:
            outcome='timeout'
            raise
        finally:
            report_ocr_memory(measurement,outcome,started)
        output.seek(0);stdout=output.read(100001)
        errors.seek(0);stderr=errors.read(100001)
    if code and check:raise subprocess.CalledProcessError(code,args,stdout,stderr)
    return subprocess.CompletedProcess(args,code,stdout,stderr)


class OcrChildError(RuntimeError):pass
class ListVerificationError(ValueError):pass
class OcrMemoryDeferred(ocr_workload_priority.OcrWorkloadDeferred):pass



OCR_PROGRESS_REVISION='native-product-rows-v1'


def image_work_key(image,enhanced):
    # Include exact original timestamp/PNG/attachments and optical mode. Never
    # reuse another batch or an older recognition/preprocessing revision.
    return hashlib.sha256(json.dumps([OCR_PROGRESS_REVISION,enhanced,image],
        sort_keys=True,separators=(',',':')).encode()).hexdigest()


def sanitize_native_passes(passes):
    import evaluator_runtime
    result=evaluator_runtime.run(['node',str(Path(__file__).with_name('handset_list_parse.js'))],
        input=json.dumps({'mode':'prepare-native','passes':passes}),
        text=True,capture_output=True,timeout=20,check=True)
    return json.loads(result.stdout)


def process(payload,at,*,progress=None,save_progress=None):
    # Acquire before evaluator admission: a draining maintenance task may itself
    # need the evaluator. Holding it while waiting here would deadlock.
    with ocr_workload_priority.ocr_slot():
        return _process(payload,at,progress=progress,save_progress=save_progress)


def _process(payload,at,*,progress=None,save_progress=None):
    # An internal, bounded second pass only for a verification failure.
    # Original screenshot bytes are never changed or persisted in this mode.
    enhanced=payload.get('_ocr_mode')=='enhanced'
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LD_LIBRARY_PATH')}
    env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    import evaluator_runtime
    images=[]
    prepared=[None]*len(payload['images'])
    remote_sources=[False]*len(payload['images'])
    saved={} if not isinstance(progress,dict) or len(json.dumps(progress))>120000 else dict(progress)
    if any('appText' in image or 'localOcr' in image for image in payload['images']):
        # Prefer paired on-device reading over heavyweight server native OCR.
        # Only bounded, whitelisted product rows reach the JS parser. Full
        # screenshots remain in their existing authenticated original batch.
        result=evaluator_runtime.run(['node',str(Path(__file__).with_name('handset_list_parse.js'))],
            input=json.dumps({'mode':'prepare-app','images':[
                {'appText':i.get('appText'),'localOcr':i.get('localOcr')}
                for i in payload['images']]}),
            text=True,capture_output=True,timeout=20,check=True)
        prepared=json.loads(result.stdout)
    # Share subprocess admission with Node analyses, releasing it after each
    # image. Never overlap a native OCR model with a heavy JS evaluator.
    for index,image in enumerate(payload['images']):
        if prepared[index] is not None:
            images.append(prepared[index]);continue
        key=image_work_key(image,enhanced)
        candidate=saved.get(str(index))
        cached=None
        if (isinstance(candidate,dict) and set(candidate) in ({'key','passes'},{'key','passes','source'})
                and candidate['key']==key and candidate.get('source','native') in ('native','remote')):
            cached=sanitize_native_passes(candidate['passes'])
        if cached is not None:
            images.append(cached)
            remote_sources[index]=candidate.get('source')=='remote'
            continue
        try:
            child=evaluator_runtime.run([sys.executable,__file__,'--ocr']+
                (['--enhanced'] if enhanced else []),priority=2,runner=guarded_ocr_run,
                input=json.dumps([image]),text=True,capture_output=True,timeout=35,check=True,env=env,close_fds=True)
            if len(child.stdout)>100000:raise ValueError('OCR output limit')
            recognized=json.loads(child.stdout)
        except (OcrMemoryDeferred,MemoryError):
            # Preserve the exact legacy error/retry behavior while disabled.
            # Remote offload can only run after explicit private configuration.
            from remote_ocr_fallback import configured as remote_configured, recognize as remote_recognize
            if not remote_configured():raise
            try:recognized=remote_recognize(image,enhanced)
            except Exception:
                raise OcrMemoryDeferred('Remote OCR unavailable after local memory failure') from None
            if recognized is None:
                raise OcrMemoryDeferred('Remote OCR disabled after local memory failure') from None
            remote_sources[index]=True
        except subprocess.CalledProcessError as exc:
            raise OcrChildError('Isolated image recognition failed') from exc
        if not isinstance(recognized,list) or len(recognized)!=1:raise ValueError('OCR image output')
        # Keep the original output for this invocation's existing final parser;
        # checkpoint only the whitelisted, genuinely repeated product rows.
        images.extend(recognized)
        if save_progress is not None:
            clean=sanitize_native_passes(recognized[0])
            if clean is not None:
                checkpoint={'key':key,'passes':clean}
                if remote_sources[index]:checkpoint['source']='remote'
                saved[str(index)]=checkpoint
                if len(saved)<=4 and len(json.dumps(saved))<=120000:save_progress(saved)
    try:
        result=evaluator_runtime.run(['node',str(Path(__file__).with_name('handset_list_parse.js'))],input=json.dumps({'images':images,'at':at,
            'appSources':[p is not None and 'appText' in image for p,image in zip(prepared,payload['images'])],
            'localSources':[p is not None and 'localOcr' in image for p,image in zip(prepared,payload['images'])],
            'remoteSources':remote_sources}),text=True,capture_output=True,timeout=20,check=True)
    except subprocess.CalledProcessError as exc:
        raise ListVerificationError('Ten-row list verification failed') from exc
    return json.loads(result.stdout)


def persist_progress(connect,batch,progress):
    """Save only this leased batch's small intermediate; never mark it synced."""
    raw=json.dumps(progress)
    if len(raw)>120000 or len(progress)>4:raise ValueError('OCR progress bounds')
    with connect() as conn:
        conn.execute("""UPDATE bob_android_list_images i SET ocr_progress=%s::jsonb,processing_at=now()
            FROM bob_android_diagnostic_devices d WHERE i.token_hash=d.token_hash
            AND i.batch_id=%s AND NOT d.revoked AND d.expires_at>now()
            AND i.import_receipt->>'stage'='reading'""",(raw,batch))
        conn.commit()


def persist_parsed(connect,batch,parsed,sleep=time.sleep):
    """Retry transient write conflicts with a fresh transaction, never rerun OCR."""
    for attempt in range(5):
        try:
            with connect() as conn:
                current=conn.execute('SELECT i.import_receipt FROM bob_android_list_images i JOIN bob_android_diagnostic_devices d USING(token_hash) WHERE i.batch_id=%s AND NOT d.revoked AND d.expires_at>now() FOR UPDATE OF i',(batch,)).fetchone()
                if not current:return 'cancelled'
                if (current[0] or {}).get('stage') in ('synced','superseded'):return current[0]['stage']
                import paper_simulation
                result=paper_simulation.sync(conn,parsed['evidence'])
                if not result.get('ok') or (not result.get('preserved') and result.get('products')!=10):raise ValueError('Persistence not confirmed')
                stage='superseded' if result.get('preserved') else 'synced'
                receipt={'batchId':batch,'stage':stage,'count':10,'at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
                conn.execute('UPDATE bob_android_list_images SET parsed_items=%s::jsonb,import_receipt=%s::jsonb,ocr_progress=NULL WHERE batch_id=%s',(json.dumps(parsed['items']),json.dumps(receipt),batch))
                conn.commit()
            return stage
        except Exception as exc:
            if getattr(exc,'sqlstate',None) not in ('55P03','40P01','40001') or attempt==4:
                raise
            # The failed connection/transaction has exited before waiting.
            sleep(.25*(2**attempt))


def tick(connect,runner=process):
    observe("checking")
    with connect() as conn:
        # A process killed during OCR cannot write its failure receipt. End the
        # bounded retry series explicitly once its lease has expired.
        conn.execute("""UPDATE bob_android_list_images SET import_receipt=jsonb_build_object(
            'batchId',batch_id,'stage','read-failed','count',0,'error','InterruptedWorker')
            WHERE processing_attempts>=3 AND import_receipt->>'stage'='reading'
            AND processing_at<now()-interval '4 minutes'""")
        row=conn.execute("""SELECT i.batch_id,i.payload,i.created_at,i.processing_attempts,i.import_receipt,i.ocr_progress FROM bob_android_list_images i
            JOIN bob_android_diagnostic_devices d USING(token_hash)
            WHERE NOT d.revoked AND d.expires_at>now() AND i.created_at>now()-interval '24 hours'
            AND COALESCE(i.import_receipt->>'stage','') NOT IN ('synced','superseded')
            AND (i.import_receipt->>'stage'='waiting-memory' OR i.processing_attempts<3 OR (i.processing_attempts=3 AND (i.import_receipt IS NULL OR i.import_receipt->>'error' IN ('MemoryError','ListVerificationError')))
                OR (i.processing_attempts=4 AND i.import_receipt->>'error' IN ('InterruptedWorker','MemoryError'))
                OR (i.processing_attempts=5 AND i.import_receipt->>'error' IN ('CalledProcessError','LockNotAvailable','DeadlockDetected','SerializationFailure')))
            AND (i.processing_at IS NULL OR i.processing_at<now()-interval '4 minutes')
            ORDER BY i.created_at DESC LIMIT 1 FOR UPDATE OF i SKIP LOCKED""").fetchone()
        if not row:
            observe("idle")
            return False
        batch,payload,created,attempts,previous,*extra=row
        progress=extra[0] if extra else None
        # One enhanced pass after three failed list-verification attempts.
        # It is never repeated for a second verification failure.
        # The original evidence and strict 10-ISIN gate remain unchanged.
        alternate=(attempts==3 and (previous or {}).get('stage')=='read-failed'
            and (previous or {}).get('error')=='ListVerificationError')
        reading={'batchId':batch,'stage':'reading','count':0,
                 'memoryDeferrals':memory_deferrals(previous)}
        conn.execute("UPDATE bob_android_list_images SET processing_at=now(),processing_attempts=processing_attempts+1,import_receipt=%s::jsonb WHERE batch_id=%s",(json.dumps(reading),batch))
        conn.commit()
    observe("reading")
    try:
        # Backward-compatible fast path: original raw PNG rows require no
        # extra query. Future device-scoped pointer rows must be reconstructed
        # with their exact original bytes before any OCR or list parsing.
        # A missing reference becomes a sanitized read-failed receipt.
        import android_image_readthrough
        if android_image_readthrough.is_reference(payload):
            with connect() as evidence_conn:
                payload=android_image_readthrough.materialize(
                    evidence_conn,batch,payload)
        request=dict(payload)
        if alternate:request['_ocr_mode']='enhanced'
        if runner is process:
            parsed=runner(request,payload['images'][-1]['at'],progress=progress,
                save_progress=lambda value:persist_progress(connect,batch,value))
        else:parsed=runner(request,payload['images'][-1]['at'])
        if len(parsed.get('items',[]))!=10 or len({x.get('isin') for x in parsed['items']})!=10:
            raise ValueError('Incomplete list')
        if {p.get('isin') for p in parsed.get('evidence',{}).get('products',[])}!={x['isin'] for x in parsed['items']}:
            raise ValueError('Mismatched evidence')
        stage=persist_parsed(connect,batch,parsed)
        observe(stage)
    except OcrMemoryDeferred:
        receipt=deferred_memory_receipt(batch,previous)
        exhausted=not receipt['retryAllowed']
        observe(receipt['stage'],'MemoryError' if exhausted else None)
        with connect() as conn:
            # Six is beyond every existing retry allowance, including the
            # historical MemoryError recovery. No immediate child was spawned.
            attempts_sql='GREATEST(processing_attempts,6)' if exhausted else 'GREATEST(processing_attempts-1,0)'
            conn.execute("UPDATE bob_android_list_images SET processing_attempts="+attempts_sql+",import_receipt=%s::jsonb WHERE batch_id=%s AND import_receipt->>'stage'='reading'",
                (json.dumps(receipt),batch))
            conn.commit()
    except Exception as exc:
        observe("read-failed", type(exc).__name__)
        with connect() as conn:
            # A failed global reconciliation must permit fresh optical reads;
            # an individually agreed subset is not proof of a complete image.
            clear_progress=',ocr_progress=NULL' if isinstance(exc,ListVerificationError) else ''
            conn.execute("UPDATE bob_android_list_images SET import_receipt=%s::jsonb"+clear_progress+" WHERE batch_id=%s AND COALESCE(import_receipt->>'stage','') NOT IN ('synced','superseded')",(json.dumps({'batchId':batch,'stage':'read-failed','count':0,'error':type(exc).__name__,'memoryDeferrals':memory_deferrals(previous)}),batch))
            conn.commit()
    return True


def loop(connect):
    print('BOB_HANDSET_LIST policy=bounded-ocr limitMiB='+str(OCR_CONTAINER_LIMIT//(1024*1024))+
          ' startReserveMiB='+str(OCR_START_RESERVE//(1024*1024)),flush=True)
    # One OCR process at a time on the small server. Keep the existing video
    # reader's two-minute cadence, with handset work first in each cycle.
    import video_ocr
    last_video=0.0
    last_image_gc=0.0
    while True:
        try:tick(connect)
        except Exception as exc:
            observe("queue-error", type(exc).__name__)
            print("BOB_HANDSET_LIST error="+type(exc).__name__,flush=True)
        # One small cleanup only every ten minutes. No raw image IDs, PNGs,
        # source values or product identifiers are ever logged. This does not
        # delay a new authenticated handset import and never scans all images.
        if time.monotonic()-last_image_gc>=600:
            try:
                from android_image_retention import sweep_once
                freed=sweep_once(connect)
                if freed['removed']:
                    print('BOB_ANDROID_IMAGE_EXPIRY rows='+str(freed['removed'])+
                          ' logicalPayloadBytes='+str(freed['logicalPayloadBytes'])+
                          ' physicalBytesFreed=unknown',flush=True)
            except Exception as exc:
                print('BOB_ANDROID_IMAGE_EXPIRY status=blocked error='+type(exc).__name__,flush=True)
            last_image_gc=time.monotonic()
        if time.monotonic()-last_video>=120:
            try:print('BOB_VIDEO_OCR status='+video_ocr.tick(connect),flush=True)
            except Exception as exc:print('BOB_VIDEO_OCR error='+type(exc).__name__,flush=True)
            last_video=time.monotonic()
        time.sleep(10)

if __name__=='__main__' and '--ocr' in sys.argv:
    from ocr_sandbox import deny_network
    deny_network()  # Fail closed before native imports or threads.
    import socket, resource
    def no_network(*args,**kwargs):raise RuntimeError('Local OCR network disabled')
    socket.socket.connect=no_network
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    raw=sys.stdin.read(8100001)
    if len(raw)>8100000:raise ValueError('Image input limit')
    print(json.dumps(recognize(json.loads(raw),enhanced='--enhanced' in sys.argv)))

