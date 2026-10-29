import json
import subprocess
import unittest
from unittest.mock import patch
import handset_list_worker as worker

class WorkerTests(unittest.TestCase):
    def test_shared_parser_requires_ten_agreed_rows_and_preserves_quote_gaps(self):
        script=r'''
const {parse}=require('./handset_list_parse');
const fs=require('fs'),vm=require('vm'),c={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),c);
const valid=c.window.BobDegiro.validIsin;
function id(n){const prefix='DE000ZZ'+String(n).padStart(4,'0');for(let i=0;i<10;i++)if(valid(prefix+i))return prefix+i;}
function row(n,bar=4000){return `SG Gold Turbo BEST Open-End Call BAR ${bar} BP ${bar} Bv 10 | ${id(n)}\nSociete Generale OTC EUR K V`;}
const images=[[1,2,3,4],[4,5,6,7],[7,8,9,10]].map(ns=>{let t=ns.map(n=>row(n)).join('\n');return [t,t];});
const out=parse(images,'2026-10-29T19:00:00Z');
if(out.items.length!==10||out.evidence.products.some(p=>p.price!==null||p.isinConfirmed!==false||!p.listVenueEvidence))throw Error('Evidence boundaries');
for(const invalid of [images.slice(0,2),images.map(p=>p.slice(0,1)),[...images,[row(4,4100),row(4,4100)]]]){
 let rejected=false;try{parse(invalid,'2026-10-29T19:00:00Z')}catch(_){rejected=true}if(!rejected)throw Error('Unsafe list');
}
console.log(JSON.stringify(out));
'''
        result=subprocess.run(['node','-e',script],text=True,capture_output=True,check=True)
        self.assertEqual(len(json.loads(result.stdout)['items']),10)

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
                if sql.startswith('SELECT i.batch_id'):return Result(('a'*32,{'images':[{'at':'2026-10-29T19:00:00Z'}]},None))
                if sql.startswith('SELECT i.import_receipt'):return Result((None,))
                if 'SET parsed_items=' in sql:self.receipts.append(json.loads(args[1]))
                if 'SET import_receipt=' in sql:self.receipts.append(json.loads(args[0]))
                return Result(None)
        db=DB()
        with patch('paper_simulation.sync',return_value={'ok':True,'products':10}) as sync:
            worker.tick(lambda:db,lambda p,at:{'items':[],'evidence':{'listUploadedAt':at}})
            self.assertTrue(sync.called);self.assertEqual(db.receipts[-1]['stage'],'synced');self.assertEqual(db.commits,2)
        db=DB()
        def fail(*_):raise ValueError('private image text must never leak')
        worker.tick(lambda:db,fail)
        self.assertEqual(db.receipts[-1]['stage'],'read-failed')
        self.assertNotIn('private',json.dumps(db.receipts))

if __name__=='__main__':unittest.main()
