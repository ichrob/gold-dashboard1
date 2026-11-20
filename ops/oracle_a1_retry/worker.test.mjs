import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {validate,run,retryToken,verifyPlan} from './worker.js';
const keys=await webcrypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
const der=new Uint8Array(await webcrypto.subtle.exportKey('pkcs8',keys.privateKey));
const pem='-----BEGIN PRIVATE KEY-----\n'+Buffer.from(der).toString('base64')+'\n-----END PRIVATE KEY-----';
const e={ENABLED:'true',ALLOW_APPLY:'true',PLAN_VERIFIED_ALWAYS_FREE:'true',OCI_TENANCY_OCID:'ocid1.tenancy.oc1..test',OCI_USER_OCID:'ocid1.user.oc1..test',OCI_API_FINGERPRINT:'00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00',OCI_PRIVATE_KEY_PEM:pem,OCI_STACK_OCID:'ocid1.ormstack.oc1..test',OCI_PLAN_JOB_OCID:'ocid1.ormjob.oc1..plan'};
assert.equal(validate({}).status,'disabled');
assert.equal(validate({...e,OCI_PRIVATE_KEY_PEM:''}).status,'configuration_required');
const failed={id:'ocid1.ormjob.oc1..last',operation:'APPLY',lifecycleState:'FAILED',timeCreated:new Date(Date.now()-7200000).toISOString(),timeFinished:new Date(Date.now()-3600000).toISOString()};
let writes=0, tokens=[];
const networkState={version:4,resources:[
  {mode:'managed',type:'oci_core_vcn',name:'bob',instances:[{attributes:{id:'vcn',compartment_id:'bob-comp'}}]},
  {mode:'managed',type:'oci_core_subnet',name:'test',instances:[{attributes:{id:'subnet',vcn_id:'vcn',compartment_id:'bob-comp',prohibit_public_ip_on_vnic:true}}]},
  {mode:'managed',type:'oci_core_security_list',name:'isolated',instances:[{attributes:{id:'acl',vcn_id:'vcn',ingress_security_rules:[],egress_security_rules:[]}}]}
]};
const goodPlan={resource_changes:[{
  address:'oci_core_instance.bob',mode:'managed',type:'oci_core_instance',
  change:{actions:['create'],after:{
    display_name:'bob-ocr-zurich',compartment_id:'bob-comp',availability_domain:'JJTG:EU-ZURICH-1-AD-1',
    shape:'VM.Standard.A1.Flex',shape_config:[{ocpus:1,memory_in_gbs:4}],
    source_details:[{source_type:'image',source_id:'ocid1.image.oc1.eu-zurich-1.aaaaaaaadk22jaklt42vd4entg5pfsn5jfwbakrs7nsrawqvv5ya7iefhgiq',boot_volume_size_in_gbs:50,boot_volume_vpus_per_gb:10}],
    create_vnic_details:[{subnet_id:'subnet',assign_public_ip:false}],
    instance_options:[{are_legacy_imds_endpoints_disabled:true}]
  }}
}]};
assert.equal(verifyPlan(goodPlan,networkState),true);
for (const bad of [
  {...goodPlan,resource_changes:[...goodPlan.resource_changes,{address:'oci_core_vcn.extra',mode:'managed',type:'oci_core_vcn',change:{actions:['create'],after:{}}}]},
  {...goodPlan,resource_changes:[{...goodPlan.resource_changes[0],change:{...goodPlan.resource_changes[0].change,after:{...goodPlan.resource_changes[0].change.after,shape_config:[{ocpus:2,memory_in_gbs:8}]}}}]},
  {...goodPlan,resource_changes:[{...goodPlan.resource_changes[0],change:{...goodPlan.resource_changes[0].change,after:{...goodPlan.resource_changes[0].change.after,create_vnic_details:[{subnet_id:'subnet',assign_public_ip:true}]}}}]},
  {...goodPlan,resource_changes:[{...goodPlan.resource_changes[0],change:{...goodPlan.resource_changes[0].change,after:{...goodPlan.resource_changes[0].change.after,source_details:[{...goodPlan.resource_changes[0].change.after.source_details[0],source_id:'unexpected'}]}}}]}
])assert.equal(verifyPlan(bad,networkState),false);
function mock(jobs,text='Out of host capacity',vmPresent=false,stateStatus=200,planFile=goodPlan){
  writes=0; tokens=[];
  globalThis.fetch=async (url,opts)=>{
    const p=new URL(url).pathname;
    let result;
    if(opts.method==='POST'){writes++;tokens.push(opts.headers['opc-retry-token']);result={id:'ocid1.ormjob.oc1..created'};}
    else if(p.endsWith('/jobs'))result=jobs;
    else if(p.endsWith('/logs/content'))result=text;
    else if(p.endsWith('/tfState')){
      if(stateStatus!==200)return new Response('state unavailable',{status:stateStatus});
      result={...networkState,resources:[...networkState.resources,...(vmPresent?[{mode:'managed',type:'oci_core_instance',name:'bob',instances:[{attributes:{id:'ocid1.instance.oc1..test'}}]}]:[])]};
    }
    else if(p.endsWith('/tfPlan'))result=planFile;
    else result={id:e.OCI_PLAN_JOB_OCID,operation:'PLAN',lifecycleState:'SUCCEEDED',stackId:e.OCI_STACK_OCID};
    return new Response(typeof result==='string'?result:JSON.stringify(result),{headers:{'content-type':typeof result==='string'?'text/plain':'application/json'}});
  };
}
mock([{...failed,lifecycleState:'SUCCEEDED'}]);assert.equal((await run(e)).status,'non_failed_last_apply');assert.equal(writes,0);
mock([{...failed,lifecycleState:'IN_PROGRESS'}]);assert.equal((await run(e)).status,'job_in_progress');assert.equal(writes,0);
mock([failed],'Unauthorized');assert.equal((await run(e)).status,'not_a_capacity_failure');assert.equal(writes,0);
mock([failed]);assert.equal((await run(e)).status,'apply_submitted');assert.equal(writes,1);
mock([failed],'Out of host capacity',false,200,{resource_changes:[...goodPlan.resource_changes,{address:'oci_core_vcn.other',mode:'managed',type:'oci_core_vcn',change:{actions:['create'],after:{}}}]});
assert.equal((await run(e)).status,'plan_not_allowlisted');assert.equal(writes,0);
// A historical network-only Apply must not mask a newer capacity failure.
const olderSuccess={...failed,id:'ocid1.ormjob.oc1..older',lifecycleState:'SUCCEEDED',timeCreated:new Date(Date.now()-10800000).toISOString()};
mock([olderSuccess,failed]);
assert.equal((await run(e)).status,'apply_submitted');assert.equal(writes,1);
// A server already recorded in stack state always blocks another Apply.
mock([failed],'Out of host capacity',true);
assert.equal((await run(e)).status,'instance_present');assert.equal(writes,0);
// No readable/valid Terraform state means no authority to provision.
mock([failed],'Out of host capacity',false,403);
assert.equal((await run(e)).status,'state_unavailable');assert.equal(writes,0);
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
