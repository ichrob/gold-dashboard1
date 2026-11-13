const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].find(m=>m[1].includes('const quotes={spot:null,future:null,estimate:null}'))[1];
let now=Date.parse('2026-11-13T17:30:00Z');const RealDate=Date;
class Clock extends RealDate{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
const elements=new Map(),el=id=>{if(!elements.has(id))elements.set(id,{textContent:'',style:{},dataset:{},getClientRects:()=>[{}]});return elements.get(id);};
el('earlyImpulseStatus').dataset.marketRendered='true';
const intervals=[],reports=[];let fail=false;
const payload={spot:{price:3880.10,at:new Clock().toISOString(),kind:'spot',symbol:'XAU/USD'}};
const ctx={window:{},crypto:{randomUUID:()=> 'a'.repeat(32)},document:{visibilityState:'visible',getElementById:id=>html.includes('id="'+id+'"')?el(id):null,addEventListener(){}},setInterval:(fn,ms)=>intervals.push({fn,ms}),setTimeout:()=>0,clearTimeout(){},AbortController,Date:Clock,Number,
 fetch:async(url,opts)=>{if(url==='/api/diag'){if(fail)throw Error('offline');reports.push(JSON.parse(opts.body).details.code);return {ok:true};}return {ok:true,json:async()=>payload};}};
vm.createContext(ctx);vm.runInContext(script,ctx);
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 await flush();const check=intervals.find(i=>i.ms===10000).fn;
 check();await flush();assert.deepEqual(reports,['ok']);
 el('gold-spot-price').textContent='—';check();await flush();
 assert.deepEqual(reports,['ok','spot-mismatch','ok']);assert.equal(el('gold-spot-price').textContent,'3.880,10');
 ctx.document.visibilityState='hidden';el('gold-spot-price').textContent='—';check();await flush();assert.equal(reports.length,3);
 ctx.document.visibilityState='visible';fail=true;check();await flush();assert.equal(el('gold-spot-price').textContent,'3.880,10','report transport failure must not prevent redraw');
 fail=false;now+=50000;delete el('earlyImpulseStatus').dataset.marketRendered;
 ctx.window.renderEarlyImpulseStatus=()=>{el('earlyImpulseStatus').dataset.marketRendered='true';};
 check();await flush();assert.deepEqual(reports.slice(-2),['warning-unrendered','ok']);
 now+=180000;check();await flush();assert.equal(reports.at(-1),'data-unavailable');
 console.log('Market watchdog: visible DOM mismatch, repair, hidden tab, failed transport, stalled warning and stale clock passed');
})().catch(e=>{console.error(e);process.exitCode=1});
