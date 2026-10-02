const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const create=window.BobDegiro.createQuoteRefresh;
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 let clock=0,shown=true,active=0,peak=0,calls=[],release=[];
 let rows=[1,2,3,4].map(id=>({id,isin:'DE000FG4JXV7',key:'row'+id}));
 rows.push({id:5,isin:'invalid',key:'invalid'});
 const scheduler=create({rows:()=>rows,now:()=>clock,visible:()=>shown,request:id=>{
  calls.push(id);peak=Math.max(peak,++active);
  return new Promise(resolve=>release.push(()=>{active--;resolve();}));
 }});
 const initial=scheduler.refresh();assert.deepEqual(calls,[1,2]);
 assert.strictEqual(scheduler.refresh(true),initial);assert.equal(calls.length,2);
 // A screenshot replacement invalidates queued identities before any request.
 rows=rows.filter(row=>row.id!==3);
 release.shift()();await turn();assert.deepEqual(calls,[1,2,4]);
 release.splice(0).forEach(done=>done());await initial;assert.equal(peak,2);
 await scheduler.refresh();assert.equal(calls.length,3);
 clock=59999;await scheduler.refresh();assert.equal(calls.length,3);
 shown=false;clock=60000;await scheduler.refresh(true);assert.equal(calls.length,3);
 shown=true;const resumed=scheduler.refresh();assert.deepEqual(calls.slice(-2),[1,2]);
 shown=false;release.splice(0).forEach(done=>done());await resumed;
 assert.equal(calls.length,5); // No further work is started while hidden.
 shown=true;const remaining=scheduler.refresh();assert.equal(calls.at(-1),4);
 release.shift()();await remaining;
 // Changed valid identities refresh without waiting for the previous cadence.
 rows[0]={id:1,isin:'DE000FG309G0',key:'replacement'};
 const changed=scheduler.refresh();assert.equal(calls.at(-1),1);
 release.shift()();await changed;
 // Failed sources remain scheduled; failures do not trigger immediate retries.
 let failures=0;const failing=create({rows:()=>[{id:1,isin:'DE000FG309G0',key:'future'}],now:()=>clock,request:async()=>{failures++;throw Error('outage');}});
 await failing.refresh();await failing.refresh();assert.equal(failures,1);
 clock+=60000;await failing.refresh();assert.equal(failures,2);
 console.log('Automatic ISIN refresh: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
