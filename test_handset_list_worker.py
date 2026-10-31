import json
import subprocess
import unittest
from unittest.mock import patch
import handset_list_worker as worker

class WorkerTests(unittest.TestCase):
    def test_semantic_path_never_starts_ocr(self):
        from types import SimpleNamespace
        text={'before':['row'],'after':['row']}
        with patch('evaluator_runtime.run',side_effect=[SimpleNamespace(stdout='[["row","row"]]'),SimpleNamespace(stdout='{"items":[]}')]) as run:
            worker.process({'images':[{'png':'private image','appText':text}]},'2026-10-30T12:00:00Z')
        self.assertEqual(run.call_count,2)
        self.assertTrue(all(c.args[0][0]=='node' for c in run.call_args_list))
        self.assertNotIn('private image',run.call_args_list[0].kwargs['input'])
        self.assertEqual(json.loads(run.call_args_list[1].kwargs['input'])['appSources'],[True])

    def test_ocr_defers_before_spawn_when_headroom_is_insufficient(self):
        with patch.object(worker,'container_memory_bytes',return_value=300*1024*1024),patch('subprocess.Popen') as spawn:
            with self.assertRaises(worker.OcrMemoryDeferred):
                worker.guarded_ocr_run(['ocr'],input='[]',text=True,capture_output=True,timeout=35,check=True,env={},close_fds=True)
            spawn.assert_not_called()


    def test_persistence_retries_transient_conflicts_after_transaction_exit(self):
        from types import SimpleNamespace
        from contextlib import contextmanager
        parsed={'items':[{'isin':str(n)} for n in range(10)],'evidence':{'products':[]}}
        events=[]
        class Conflict(Exception):sqlstate='55P03'
        class Conn:
            def execute(self,sql,args=()):
                if sql.startswith('SELECT'):return SimpleNamespace(fetchone=lambda:(None,))
                events.append('write')
            def commit(self):events.append('commit')
        @contextmanager
        def connect():
            events.append('enter')
            try:yield Conn()
            finally:events.append('exit')
        def sleep(delay):
            self.assertEqual(events[-1],'exit')
            events.append('sleep')
        with patch('paper_simulation.sync',side_effect=[Conflict(),{'ok':True,'products':10}]) as sync:
            self.assertEqual(worker.persist_parsed(connect,'a'*32,parsed,sleep),'synced')
            self.assertEqual(sync.call_count,2)
        self.assertEqual(events.count('commit'),1)
        self.assertEqual(events.count('write'),1)
        events.clear()
        with patch('paper_simulation.sync',side_effect=Conflict()) as sync:
            with self.assertRaises(Conflict):worker.persist_parsed(connect,'a'*32,parsed,sleep)
            self.assertEqual(sync.call_count,5)
        self.assertEqual(events.count('sleep'),4)
        self.assertNotIn('commit',events)
        with patch('paper_simulation.sync',side_effect=ValueError('invalid evidence')) as sync:
            with self.assertRaises(ValueError):worker.persist_parsed(connect,'a'*32,parsed,sleep)
            self.assertEqual(sync.call_count,1)

    def test_strip_context_overlaps_but_line_ownership_never_doubles(self):
        for height in (1,511,512,513,896,897,1536,2400,3200):
            strips=list(worker.ocr_strips(height))
            self.assertEqual(strips[0][0],0)
            self.assertEqual(strips[-1][1],height)
            for top,bottom,lower,upper in strips:
                self.assertLessEqual(bottom-top,512)
                self.assertLessEqual(top,lower)
                self.assertLessEqual(upper,bottom)
            for before,after in zip(strips,strips[1:]):
                self.assertEqual(before[3],after[2])
                self.assertGreaterEqual(before[1]-after[0],128)
            for y in range(height):
                self.assertEqual(sum(lo<=y<hi for _,_,lo,hi in strips),1)

    def test_ocr_child_is_killed_before_shared_container_limit(self):
        class Child:
            args=['ocr']
            returncode=None
            killed=False
            waited=False
            def poll(self):return self.returncode
            def kill(self):self.killed=True;self.returncode=-9
            def wait(self,timeout=None):self.waited=timeout;return self.returncode
        child=Child()
        with self.assertRaises(MemoryError):
            worker.wait_ocr(child,lambda:worker.OCR_CONTAINER_LIMIT,clock=lambda:0,sleep=lambda _:None)
        self.assertTrue(child.killed);self.assertEqual(child.waited,5)
        child=Child()
        with self.assertRaises(RuntimeError):
            worker.wait_ocr(child,lambda:None,clock=lambda:0,sleep=lambda _:None)
        self.assertTrue(child.killed)

    def test_ocr_images_share_admission_and_release_between_images(self):
        from types import SimpleNamespace
        with patch('evaluator_runtime.run',side_effect=[
            SimpleNamespace(stdout='[["a","a","a"]]'),
            SimpleNamespace(stdout='[["b","b","b"]]'),
            SimpleNamespace(stdout='{"items":[]}')]) as run:
            worker.process({'images':[{'png':'one'},{'png':'two'}]},'2026-10-29T20:00:00Z')
        self.assertEqual(run.call_count,3)
        for call in run.call_args_list[:2]:
            self.assertEqual(len(json.loads(call.kwargs['input'])),1)
            self.assertEqual(call.kwargs['priority'],2)
            self.assertEqual(call.kwargs['timeout'],35)
            self.assertTrue(call.kwargs['close_fds'])
        self.assertEqual(run.call_args_list[-1].args[0][0],'node')

    def test_alt_ocr_is_used_only_for_locally_tagged_retry(self):
        from types import SimpleNamespace
        def outputs():
            return [SimpleNamespace(stdout='[["a","a","a"]]'),
                    SimpleNamespace(stdout='{"items":[]}')]
        base={'images':[{'png':'not transmitted'}]}
        for payload, expected in ((base,False),
                (dict(base,_ocr_mode='enhanced'),True)):
            with patch('evaluator_runtime.run',side_effect=outputs()) as run:
                worker.process(payload,'2026-10-31T19:13:55Z')
            command=run.call_args_list[0].args[0]
            self.assertEqual('--enhanced' in command,expected)
            self.assertEqual(command[2],'--ocr')
            self.assertEqual(len(json.loads(run.call_args_list[0].kwargs['input'])),1)

    def test_list_verification_failure_gets_one_bounded_alternate_try(self):
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class DB:
            def __init__(self,attempts,error):
                self.attempts=attempts;self.error=error;self.writes=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def commit(self):pass
            def execute(self,sql,args=()):
                if sql.startswith('SELECT i.batch_id'):
                    return Result(('a'*32,{'images':[{'at':'2026-10-31T19:13:55Z'}]},
                        None,self.attempts,{'stage':'read-failed','error':self.error}))
                if sql.startswith('SELECT i.import_receipt'):return Result((None,))
                if 'import_receipt=%s' in sql:self.writes.append(json.loads(args[0]))
                return Result(None)
        def attempt(attempts,error):
            db=DB(attempts,error);calls=[]
            def runner(payload,at):
                calls.append(payload.get('_ocr_mode'))
                raise worker.ListVerificationError('Do not log private OCR text')
            worker.tick(lambda:db,runner)
            self.assertEqual(db.writes[-1]['error'],'ListVerificationError')
            return calls
        self.assertEqual(attempt(2,'ListVerificationError'),['enhanced'])
        self.assertEqual(attempt(1,'ListVerificationError'),[None])
        self.assertEqual(attempt(2,'OcrChildError'),[None])
        self.assertEqual(attempt(3,'ListVerificationError'),[None])

    def test_phone_ocr_size_is_bounded_without_changing_original(self):
        for width,height in [(1080,2400),(1440,3200),(5000,3000),(709,1536)]:
            for scale in (.85,1,2.5):
                w,h=worker.ocr_size(width,height,scale)
                self.assertLessEqual(w,1200)
                self.assertLessEqual(w*h,1602500)
                self.assertAlmostEqual(w/h,width/height,delta=.002)

    def test_worker_status_reports_queue_failure_without_private_error_text(self):
        def broken():raise RuntimeError('private database information')
        with patch('video_ocr.tick', return_value='idle'), patch('handset_list_worker.time.sleep',side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):worker.loop(broken)
        result=worker.status()
        self.assertEqual(result['state'],'queue-error')
        self.assertEqual(result['error'],'RuntimeError')
        self.assertTrue(result['fresh'])
        self.assertNotIn('private',json.dumps(result))


    def test_shared_parser_requires_ten_agreed_rows_and_preserves_quote_gaps(self):
        script=r'''
const {parse,normalizeLayout,appImage}=require('./handset_list_parse');
const fs=require('fs'),vm=require('vm'),c={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),c);
const valid=c.window.BobDegiro.validIsin;
function id(n){const prefix='DE000ZZ'+String(n).padStart(4,'0');for(let i=0;i<10;i++)if(valid(prefix+i))return prefix+i;}
function row(n,bar=4000){return `SG Gold Turbo BEST Open-End Call BAR ${bar} BP ${bar} Bv 10 | ${id(n)}\nSociete Generale OTC EUR K V`;}
const images=[[1,2,3,4],[4,5,6,7],[7,8,9,10]].map(ns=>{let t=ns.map(n=>row(n)).join('\n');return [t,t];});
const out=parse(images,'2026-10-29T19:00:00Z');
const compact=images.map(passes=>passes.map(t=>t.replaceAll('SG Gold Turbo BEST Open-End Call BAR','SGGoldTurboBESTOpen-EndCallBAR')));
if(parse(compact,'2026-10-29T19:00:00Z').items.length!==10)throw Error('Compact label boundaries');
if(normalizeLayout('BAR4400BP4400Bv\n1019/03/2027|')!=='BAR4400BP4400Bv\n10 19/03/2027|')throw Error('Compact ratio date');
if(normalizeLayout('Bv 1019/03/2027 |')!=='Bv 10 19/03/2027 |')throw Error('Ratio date separator');
if(normalizeLayout('BNPGOLDMiniLongSL3690.3449STR3617.9852 R 10')!=='BNP GOLD Mini Long SL3690.3449STR3617.9852 R 10')throw Error('BNP label boundaries');
if(normalizeLayout('DE000ZZ00001 3970.33')!=='DE000ZZ00001 3970.33')throw Error('Identity or numbers changed');

if(out.items.length!==10||out.evidence.products.some(p=>p.price!==null||p.isinConfirmed!==false||!p.listVenueEvidence))throw Error('Evidence boundaries');
for(const invalid of [images.slice(0,2),images.map(p=>p.slice(0,1)),[...images,[row(4,4100),row(4,4100)]]]){
 let rejected=false;try{parse(invalid,'2026-10-29T19:00:00Z')}catch(_){rejected=true}if(!rejected)throw Error('Unsafe list');
}
const app=images.map(p=>({before: p[0].split(/\n(?=SG Gold)/),after:p[0].split(/\n(?=SG Gold)/)}));
const direct=parse(app.map(appImage),'2026-10-29T19:00:00Z',[true,true,true]);
if(direct.items.length!==10||direct.items.some(i=>i.listRow.source!=='DEGIRO-App-Text'||i.listRow.crossChecked)||direct.evidence.products.some(p=>p.listVenueEvidence||p.quote||p.price))throw Error('App provenance or approval');
for(const bad of [{before:[row(1)],after:[row(2)]},{before:[row(1),row(1)],after:[row(1),row(1)]},{before:['bad'],after:['bad']}])if(appImage(bad)!==null)throw Error('Bad semantic text');
console.log(JSON.stringify(out));
'''
        result=subprocess.run(['node','-e',script],text=True,capture_output=True,check=True)
        parsed=json.loads(result.stdout)
        self.assertEqual(len(parsed['items']),10)
        rows=[i['name']+' | '+i['isin']+'\n'+i['listRow']['venue']+' '+i['listRow']['currency'] for i in parsed['items']]
        # Run the actual subprocess protocol end to end. Invalid PNG data proves
        # that a complete semantic capture never invokes the image decoder.
        imported=worker.process({'images':[{'png':'not decoded','appText':{'before':rows,'after':rows}}]},'2026-10-29T19:00:00Z')
        self.assertEqual(len(imported['items']),10)
        self.assertTrue(all(i['listRow']['source']=='DEGIRO-App-Text' for i in imported['items']))

    def test_worker_ack_only_after_persistence_and_keeps_failed_batch(self):
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class DB:
            def __init__(self):self.receipts=[];self.commits=0
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def commit(self):self.commits+=1
            def execute(self,sql,args=()):
                if sql.startswith('SELECT i.batch_id'):return Result(('a'*32,{'images':[{'at':'2026-10-29T19:00:00Z'}]},None,0,None))
                if sql.startswith('SELECT i.import_receipt'):return Result((None,))
                if 'processing_attempts=processing_attempts+1' in sql:self.receipts.append(json.loads(args[0]))
                if 'SET parsed_items=' in sql:self.receipts.append(json.loads(args[1]))
                if 'SET import_receipt=%s' in sql:self.receipts.append(json.loads(args[0]))
                return Result(None)
        db=DB()
        with patch('paper_simulation.sync',return_value={'ok':True,'products':10}) as sync:
            worker.tick(lambda:db,lambda p,at:{'items':[{'isin':str(n)} for n in range(10)],'evidence':{'listUploadedAt':at,'products':[{'isin':str(n)} for n in range(10)]}})
            self.assertTrue(sync.called);self.assertEqual(db.receipts[0]['stage'],'reading');self.assertEqual(db.receipts[-1]['stage'],'synced');self.assertEqual(db.commits,2)
        db=DB()
        def fail(*_):raise ValueError('private image text must never leak')
        worker.tick(lambda:db,fail)
        self.assertEqual(db.receipts[-1]['stage'],'read-failed')
        self.assertNotIn('private',json.dumps(db.receipts))

class DatabaseTests(unittest.TestCase):
    def test_committed_receipt_owned_by_paired_device(self):
        import os, uuid, time, copy
        from datetime import datetime, timezone
        from contextlib import contextmanager
        url=os.environ.get('BOB_TEST_DATABASE_URL')
        if not url:self.skipTest('CI PostgreSQL not configured')
        import psycopg
        import android_telemetry, android_remote, android_list
        from test_android_list import batch
        schema='handset_'+uuid.uuid4().hex
        with psycopg.connect(url) as admin:
            admin.execute('CREATE SCHEMA '+schema)
        @contextmanager
        def connect():
            with psycopg.connect(url) as conn:
                conn.execute('SET search_path TO '+schema)
                yield conn
        try:
            now=int(time.time());value=batch()
            for i,image in enumerate(value['images']):image['at']=datetime.fromtimestamp(now-10+i,timezone.utc).isoformat()
            with connect() as conn:
                android_telemetry.init(conn);android_remote.init(conn)
                conn.execute('CREATE TABLE bob_paper_products(id INTEGER PRIMARY KEY,payload JSONB)')
                for token in ('a'*64,'b'*64):
                    android_telemetry.handle(conn,{'action':'register','tokenHash':android_telemetry.token_hash(token)})
                state={'sessionId':value['sessionId'],'active':True,'expiresAt':now+900,'seenAt':now}
                conn.execute('INSERT INTO bob_android_remote VALUES(%s,%s::jsonb)',(android_telemetry.token_hash('a'*64),json.dumps(state)))
                android_list.handle(conn,{'action':'list-upload','token':'a'*64,'value':value},now)
                conn.execute("UPDATE bob_android_list_images SET processing_attempts=3,processing_at=now()-interval '5 minutes' WHERE batch_id=%s",(value['batchId'],))
            products=[{'isin':str(n),'name':'test'} for n in range(10)]
            parsed={'items':products,'evidence':{'products':products,'listUploadedAt':value['images'][-1]['at']}}
            def sync(conn,payload):
                conn.execute('INSERT INTO bob_paper_products VALUES(1,%s::jsonb)',(json.dumps(payload),))
                return {'ok':True,'products':10}
            with patch('paper_simulation.sync',side_effect=sync):worker.tick(connect,lambda *_:parsed)
            with connect() as conn:
                own=android_list.handle(conn,{'action':'list-status','token':'a'*64,'value':{'batchId':value['batchId']}},now)
                other=android_list.handle(conn,{'action':'list-status','token':'b'*64,'value':{'batchId':value['batchId']}},now)
                self.assertEqual(own['import']['stage'],'synced')
                self.assertEqual(conn.execute('SELECT processing_attempts FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0],4)
                self.assertIsNone(other['import']);self.assertEqual(other['detailIsins'],[])
                android_list.handle(conn,{'action':'list-receipt','value':{'batchId':value['batchId'],'stage':'reading','count':0}},now)
                again=android_list.handle(conn,{'action':'list-status','token':'a'*64,'value':{'batchId':value['batchId']}},now)
                self.assertEqual(again['import']['stage'],'synced','late browser receipt cannot undo confirmation')
                conn.execute("UPDATE bob_android_list_images SET processing_attempts=4,processing_at=now()-interval '5 minutes',import_receipt=%s::jsonb WHERE batch_id=%s",
                    (json.dumps({'stage':'read-failed','error':'MemoryError'}),value['batchId']))
            with patch('paper_simulation.sync',return_value={'ok':True,'products':10}):
                self.assertTrue(worker.tick(connect,lambda *_:parsed))
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT processing_attempts FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0],5)
                conn.execute("UPDATE bob_android_list_images SET processing_at=now()-interval '5 minutes',import_receipt=%s::jsonb WHERE batch_id=%s",
                    (json.dumps({'stage':'read-failed','error':'MemoryError'}),value['batchId']))
            self.assertFalse(worker.tick(connect,lambda *_:self.fail('Unbounded memory retry')))
            with connect() as conn:
                conn.execute("UPDATE bob_android_list_images SET import_receipt=%s::jsonb WHERE batch_id=%s",
                    (json.dumps({'stage':'read-failed','error':'LockNotAvailable'}),value['batchId']))
                conn.execute('CREATE TABLE retry_probe(id INTEGER PRIMARY KEY)')
            calls=[]
            def transient_sync(conn,payload):
                conn.execute('INSERT INTO retry_probe VALUES(1)')
                calls.append(1)
                if len(calls)==1:raise psycopg.errors.LockNotAvailable('test conflict')
                return {'ok':True,'products':10}
            with patch('paper_simulation.sync',side_effect=transient_sync):
                self.assertTrue(worker.tick(connect,lambda *_:parsed))
            self.assertEqual(len(calls),2,'failed transaction must roll back its first insert')
            with connect() as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM retry_probe').fetchone()[0],1)
                self.assertEqual(conn.execute('SELECT processing_attempts FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()[0],6)
                self.assertEqual(android_list.handle(conn,{'action':'list-status','token':'a'*64,'value':{'batchId':value['batchId']}},now)['import']['stage'],'synced')

        finally:
            with psycopg.connect(url) as admin:admin.execute('DROP SCHEMA '+schema+' CASCADE')

if __name__=='__main__':unittest.main()
