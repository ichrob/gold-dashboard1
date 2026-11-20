// Bob Oracle A1: guarded 30-minute retry independent of Cloud Shell.
// No public execution endpoint; all OCI secrets belong in Worker secrets.
const HOST='resourcemanager.eu-zurich-1.oraclecloud.com';
const ROOT='https://'+HOST;
const CAPACITY=/out.of.host.capacity|outofhostcapacity|no.capacity.for.shape|shape.*capacity.*not.available|capacity.*not.available/i;
const ACTIVE=new Set(['ACCEPTED','IN_PROGRESS','CANCELING','WAITING']);
const trim=x=>typeof x==='string'?x.trim():'';
function isOcid(v,t){return new RegExp('^ocid1\\.'+t+'\\.oc1[.a-z0-9_-]*$','i').test(trim(v));}
function validate(e){
  if(e.ENABLED!=='true'||e.ALLOW_APPLY!=='true'||e.PLAN_VERIFIED_ALWAYS_FREE!=='true')return {status:'disabled'};
  const required=['OCI_TENANCY_OCID','OCI_USER_OCID','OCI_API_FINGERPRINT','OCI_PRIVATE_KEY_PEM','OCI_STACK_OCID','OCI_PLAN_JOB_OCID'];
  if(required.some(k=>!trim(e[k])))return {status:'configuration_required'};
  if(!isOcid(e.OCI_TENANCY_OCID,'tenancy')||!isOcid(e.OCI_USER_OCID,'user')||!isOcid(e.OCI_STACK_OCID,'ormstack')||!isOcid(e.OCI_PLAN_JOB_OCID,'ormjob'))return {status:'invalid_configuration'};
  if(!/^([a-f0-9]{2}:){15}[a-f0-9]{2}$/i.test(e.OCI_API_FINGERPRINT))return {status:'invalid_fingerprint'};
  return null;
}
function b64(bytes){let s='';for(const x of bytes)s+=String.fromCharCode(x);return btoa(s);}
function unb64(s){return Uint8Array.from(atob(s),x=>x.charCodeAt(0));}
let cachedKey;
async function key(env){
  if(cachedKey)return cachedKey;
  const pem=env.OCI_PRIVATE_KEY_PEM.replace(/\\n/g,'\n');
  const data=pem.replace(/-----BEGIN (RSA )?PRIVATE KEY-----|-----END (RSA )?PRIVATE KEY-----|\s/g,'');
  if(!data)throw Error('bad_private_key');
  cachedKey=await crypto.subtle.importKey('pkcs8',unb64(data),{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']);
  return cachedKey;
}
async function request(env,method,path,obj,extra={}){
  const date=new Date().toUTCString();
  const body=obj===undefined?undefined:JSON.stringify(obj);
  const headers={'x-date':date};
  const signed=['(request-target)','host','x-date'];
  const lines=['(request-target): '+method.toLowerCase()+' '+path,'host: '+HOST,'x-date: '+date];
  if(body!==undefined){
    const bytes=new TextEncoder().encode(body);
    const sha=b64(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)));
    headers['x-content-sha256']=sha;
    headers['content-type']='application/json';
    headers['content-length']=String(bytes.byteLength);
    signed.push('x-content-sha256','content-type','content-length');
    lines.push('x-content-sha256: '+sha,'content-type: application/json','content-length: '+bytes.byteLength);
  }
  const sig=b64(new Uint8Array(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',await key(env),new TextEncoder().encode(lines.join('\n')))));
  const id=[env.OCI_TENANCY_OCID,env.OCI_USER_OCID,env.OCI_API_FINGERPRINT].map(trim).join('/');
  headers.authorization='Signature version="1",keyId="'+id+'",algorithm="rsa-sha256",headers="'+signed.join(' ')+'",signature="'+sig+'"';
  Object.assign(headers,extra);
  const r=await fetch(ROOT+path,{method,headers,body,redirect:'error'});
  if(!r.ok)return {ok:false,status:r.status};
  const type=r.headers.get('content-type')||'';
  return {ok:true,status:r.status,data:type.includes('json')?await r.json():await r.text(),next:r.headers.get('opc-next-page')};
}
async function listJobs(env){
  let items=[],page='';
  for(let n=0;n<20;n++){
    const path='/20180917/jobs?stackId='+encodeURIComponent(trim(env.OCI_STACK_OCID))+'&limit=100'+(page?'&page='+encodeURIComponent(page):'');
    const r=await request(env,'GET',path);
    if(!r.ok||!Array.isArray(r.data))return {error:'list_failed',http:r.status};
    items.push(...r.data);
    if(!r.next)return {jobs:items};
    page=r.next;
  }
  return {error:'job_list_too_long'};
}
// OCI retry tokens are idempotent for 24h. A stable token for the same failed
// Apply and reviewed plan prevents overlapping Cloudflare runs creating two jobs.
async function retryToken(failedJobId,planJobId){
  const data=new TextEncoder().encode('bob-oracle-a1-retry|'+failedJobId+'|'+planJobId);
  const bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',data));
  return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
}
const state=j=>String(j.lifecycleState||'').toUpperCase();
async function run(env){
  const invalid=validate(env);if(invalid)return invalid;
  const listing=await listJobs(env);
  if(listing.error)return {status:listing.error,http:listing.http};
  const jobs=listing.jobs;
  if(jobs.some(j=>ACTIVE.has(state(j))))return {status:'job_in_progress'};
  const applies=jobs.filter(j=>String(j.operation||j.jobOperationDetails?.operation||'').toUpperCase()==='APPLY');
  if(applies.some(j=>state(j)==='SUCCEEDED'))return {status:'already_succeeded'};
  applies.sort((a,b)=>new Date(b.timeCreated||0)-new Date(a.timeCreated||0));
  const last=applies[0];
  if(!last)return {status:'no_previous_apply'};
  if(state(last)!=='FAILED')return {status:'non_failed_last_apply'};
  // The cooldown begins when Oracle marked the FAILED job finished, not when it started.
  const finishedAt=Date.parse(last.timeFinished||'');
  const age=Date.now()-finishedAt;
  // Missing/invalid/future finish timestamps must never authorize a new Apply.
  if(!Number.isFinite(finishedAt)||finishedAt<=0||!Number.isFinite(age)||age<25*60*1000)return {status:'cooldown'};
  if(!isOcid(last.id,'ormjob'))return {status:'invalid_last_job'};
  const log=await request(env,'GET','/20180917/jobs/'+encodeURIComponent(last.id)+'/logs/content');
  if(!log.ok||typeof log.data!=='string')return {status:'logs_unavailable',http:log.status};
  if(!CAPACITY.test(log.data.slice(-150000)))return {status:'not_a_capacity_failure'};
  const plan=await request(env,'GET','/20180917/jobs/'+encodeURIComponent(trim(env.OCI_PLAN_JOB_OCID)));
  if(!plan.ok||plan.data?.operation!=='PLAN'||plan.data?.lifecycleState!=='SUCCEEDED'||plan.data?.stackId!==trim(env.OCI_STACK_OCID))return {status:'plan_not_valid'};
  const details={stackId:trim(env.OCI_STACK_OCID),displayName:'Bob A1 capacity retry',jobOperationDetails:{operation:'APPLY',executionPlanStrategy:'FROM_PLAN_JOB_ID',executionPlanJobId:trim(env.OCI_PLAN_JOB_OCID)}};
  const created=await request(env,'POST','/20180917/jobs',details,{'opc-retry-token':await retryToken(last.id,trim(env.OCI_PLAN_JOB_OCID))});
  if(!created.ok)return {status:'apply_rejected',http:created.status};
  return {status:'apply_submitted',jobId:created.data?.id||null};
}
export default {
  async fetch(){return new Response('Not found',{status:404});},
  async scheduled(event,env,ctx){ctx.waitUntil(run(env).then(x=>console.log('bob_oracle_a1',JSON.stringify(x))).catch(()=>console.error('bob_oracle_a1','request_or_key_failed')));}
};
export {validate,run,retryToken};
