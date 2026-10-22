'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const {createAuditReadPool}=require('./bob_audit_read_pool.js');
(async()=>{
 let requests=0,finish;
 const sample={status:'ok',lastCheckedAt:new Date(Date.now()-60000).toISOString(),
  items:[{isin:'DE000FG14AV8',direction:'LONG',state:'analysis-evidence-complete'}],incomplete:0};
 const env={BobSession:{expired:()=>false},
  fetch:(path,options)=>{
   requests++;
   assert.equal(path,'/api/degiro/audit');
   assert.equal(options.credentials,'same-origin');
   assert.equal(options.cache,'no-store');
   assert(options.signal);
   return new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>sample});});
  }};
 const pool=createAuditReadPool(env,{cacheMs:3000});
 const r1=pool.read(),r2=pool.read();
 assert.equal(requests,1,'Two views must share one in-flight GET');
 finish();
 const [a,b]=await Promise.all([r1,r2]);
 assert.equal(a.lastCheckedAt,sample.lastCheckedAt,'Original source time unchanged');
 assert.equal(b.lastCheckedAt,sample.lastCheckedAt);
 assert.notStrictEqual(a,b);
 a.items[0].isin='CORRUPTED';
 assert.equal(b.items[0].isin,sample.items[0].isin,'Consumers must not mutate shared cache');
 const cached=await pool.read();
 assert.equal(requests,1,'Near-simultaneous reads do not request another GET');
 assert.equal(cached.items[0].isin,sample.items[0].isin);
 const force=pool.read({force:true});assert.equal(requests,2);finish();
 const f=await force;assert.equal(f.lastCheckedAt,sample.lastCheckedAt);
 assert.equal(pool.diagnostics().network,2);
 assert.equal(pool.diagnostics().shared,1);
 assert.equal(pool.diagnostics().cached,1);
 assert.equal(pool.diagnostics().readOnly,true);
 assert.equal(pool.diagnostics().tradeable,false);
 assert(!('items' in pool.diagnostics()),'No private ISINs in diagnostic counters');
 let rejectRequest;
 env.fetch=()=>{requests++;return Promise.resolve({ok:false,status:503})};
 pool.clear();
 await assert.rejects(pool.read({force:true}),/503/);
 assert.equal(pool.diagnostics().cacheAgeMs,null,'Do not hide source failure behind green cache');
 env.fetch=()=>{requests++;return Promise.resolve({ok:true,json:async()=>({
   status:'ok',lastCheckedAt:new Date(Date.now()+10000).toISOString(),items:[]})})};
 await assert.rejects(pool.read({force:true}),/Originalzeit/,'Future timestamp must fail closed');
 env.BobSession.expired=()=>true;
 await assert.rejects(pool.read(),/Anmeldung/);
 assert.equal(requests,4,'Expired session must never fetch');
 const server=fs.readFileSync('server.py','utf8');
 const all=fs.readFileSync('degiro_all_products.js','utf8');
 const overview=fs.readFileSync('bob_unified_workspace.js','utf8');
 const panel=fs.readFileSync('degiro_product_audit_panel.py','utf8');
 assert(server.includes('BOB_AUDIT_READ_POOL_JS'));
 assert(server.includes('"/bob_audit_read_pool.js"'));
 assert(server.indexOf('src="/bob_audit_read_pool.js"')>server.indexOf('src="/product_evidence_contract.js"'));
 assert(server.indexOf('src="/bob_audit_read_pool.js"')<server.indexOf('src="/degiro_all_products.js"'));
 for(const source of [all,overview,panel])assert(source.includes('BobProductAuditReadPool?.read'),
  'All three views should use the shared read-only audit pool');
 console.log('Audit read pool: 3 views, 1 shared request, original times, clone isolation, rejected errors, expired session passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
