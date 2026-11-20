import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {validate,run,retryToken} from './worker.js';
const keys=await webcrypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
const der=new Uint8Array(await webcrypto.subtle.exportKey('pkcs8',keys.privateKey));
const pem='-----BEGIN PRIVATE KEY-----\n'+Buffer.from(der).toString('base64')+'\n-----END PRIVATE KEY-----';
const e={ENABLED:'true',ALLOW_APPLY:'true',PLAN_VERIFIED_ALWAYS_FREE:'true',OCI_TENANCY_OCID:'ocid1.tenancy.oc1..test',OCI_USER_OCID:'ocid1.user.oc1..test',OCI_API_FINGERPRINT:'00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00',OCI_PRIVATE_KEY_PEM:pem,OCI_STACK_OCID:'ocid1.ormstack.oc1..test',OCI_PLAN_JOB_OCID:'ocid1.ormjob.oc1..plan'};
assert.equal(validate({}).status,'disabled');
assert.equal(validate({...e,OCI_PRIVATE_KEY_PEM:''}).status,'configuration_required');
const failed={id:'ocid1.ormjob.oc1..last',operation:'APPLY',lifecycleState:'FAILED',timeCreated:new Date(Date.now()-7200000).toISOString(),timeFinished:new Date(Date.now()-3600000).toISOString()};
let writes=0, tokens=[];
function mock(jobs,text='Out of host capacity'){
  writes=0; tokens=[];
  globalThis.fetch=async (url,opts)=>{
    const p=new URL(url).pathname;
    let result;
    if(opts.method==='POST'){writes++;tokens.push(opts.headers['opc-retry-token']);result={id:'ocid1.ormjob.oc1..created'};}
    else if(p.endsWith('/jobs'))result=jobs;
    else if(p.endsWith('/logs/content'))result=text;
    else result={id:e.OCI_PLAN_JOB_OCID,operation:'PLAN',lifecycleState:'SUCCEEDED',stackId:e.OCI_STACK_OCID};
    return new Response(typeof result==='string'?result:JSON.stringify(result),{headers:{'content-type':typeof result==='string'?'text/plain':'application/json'}});
  };
}
mock([{...failed,lifecycleState:'SUCCEEDED'}]);assert.equal((await run(e)).status,'already_succeeded');assert.equal(writes,0);
mock([{...failed,lifecycleState:'IN_PROGRESS'}]);assert.equal((await run(e)).status,'job_in_progress');assert.equal(writes,0);
mock([failed],'Unauthorized');assert.equal((await run(e)).status,'not_a_capacity_failure');assert.equal(writes,0);
mock([failed]);assert.equal((await run(e)).status,'apply_submitted');assert.equal(writes,1);
// Simulate two overlapping cron runs: OCI receives the SAME idempotency token.
mock([failed]);
const both=await Promise.all([run(e),run(e)]);
assert.deepEqual(both.map(r=>r.status),['apply_submitted','apply_submitted']);
assert.equal(writes,2); // Mock counts HTTP calls; OCI deduplicates equal retry tokens.
assert.equal(tokens.length,2);
assert.equal(tokens[0],tokens[1]);
assert.match(tokens[0],/^[0-9a-f]{64}$/);
assert.equal(await retryToken(failed.id,e.OCI_PLAN_JOB_OCID),tokens[0]);
assert.notEqual(await retryToken('ocid1.ormjob.oc1..other',e.OCI_PLAN_JOB_OCID),tokens[0]);
assert.notEqual(await retryToken(failed.id,'ocid1.ormjob.oc1..otherplan'),tokens[0]);
// Missing, invalid, and future Apply finish dates fail closed.
for(const timeFinished of [undefined,'invalid',new Date(Date.now()+3600000).toISOString()]){
  mock([{...failed,timeFinished}]);
  assert.equal((await run(e)).status,'cooldown');
  assert.equal(writes,0);
}
// A long Apply that failed 5 minutes ago must not retry despite an old creation time.
mock([{...failed,timeCreated:new Date(Date.now()-7200000).toISOString(),timeFinished:new Date(Date.now()-300000).toISOString()}]);
assert.equal((await run(e)).status,'cooldown');
assert.equal(writes,0);
console.log('oracle-a1-retry: safety guards, signed retry, idempotency and timestamps OK');
