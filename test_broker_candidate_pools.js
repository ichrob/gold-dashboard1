/* Fail-closed broker candidate admission and separate future research lists. */
'use strict';
const assert=require('node:assert/strict');
const m=require('./broker_candidate_pools');
function fakeIsin(n){
 const prefix='DETEST'+String(n).padStart(5,'0');
 for(let k=0;k<10;k++)if(m.isValidISIN(prefix+k))return prefix+k;
 throw Error('Invalid sample ISIN');
}
function storage(){
 const items=new Map();
 return {getItem:k=>items.has(k)?items.get(k):null,
  setItem:(k,v)=>items.set(k,String(v)),removeItem:k=>items.delete(k)};
}
const id=fakeIsin(1), other=fakeIsin(2);
const uploadedAt='2026-10-20T06:00:00Z';
const now=Date.parse('2026-10-20T10:30:00+02:00');
const record={isin:id,name:'Test Gold Knock-out',origin:'historical-issuer-candidate',issuerVerified:true};
const watchlist=[{isin:id,listUploadedAt:uploadedAt}];
const evidence={
 isin:id,broker:'DEGIRO',venue:'Societe Generale OTC',currency:'EUR',
 kind:'owner-reviewed-screenshot',listingConfirmed:true,executionConfirmed:false,
 timezone:'Europe/Zurich',timePrecision:'minute',
 imageReference:'DEGIRO-Produktdetail user approved original',
 listUploadedAt:uploadedAt,observedMinute:'2026-10-20T10:15',
 validUntil:'2026-10-20T22:00:00+02:00'
};
const audit={status:'ok',listUploadedAt:uploadedAt,items:[{isin:id,brokerVenueEvidence:evidence}]};
assert(m.isValidISIN(id));
assert(!m.isValidISIN(id.slice(0,11)+'X'));
assert.equal(m.verifiedBrokerProof(id,record,audit,watchlist,now),true);
for(const [key,bad] of [
 ['old report status',{...audit,status:'stale'}],
 ['incomplete report',{...audit,status:'partial'}],
 ['wrong screenshot',{...audit,listUploadedAt:'2026-10-19T06:00:00Z'}],
 ['issuer claim',{status:'ok',listUploadedAt:uploadedAt,items:[{isin:id,degiroListed:true,brokerVenueEvidence:null}]}],
 ['missing proof',{...audit,items:[{isin:id}]}],
 ['wrong ISIN',{...audit,items:[{isin:id,brokerVenueEvidence:{...evidence,isin:other}}]}],
 ['wrong venue',{...audit,items:[{isin:id,brokerVenueEvidence:{...evidence,venue:'Swiss DOTS'}}]}],
 ['execution confirmed',{...audit,items:[{isin:id,brokerVenueEvidence:{...evidence,executionConfirmed:true}}]}],
 ['uncorroborated origin',{...audit,items:[{isin:id,brokerVenueEvidence:{...evidence,kind:'issuer-only'}}]}],
 ['wrong timestamp',{...audit,items:[{isin:id,brokerVenueEvidence:{...evidence,observedMinute:'2026-10-19T10:15'}}]}],
 ['future proof',{...audit,items:[{isin:id,brokerVenueEvidence:{...evidence,observedMinute:'2026-10-20T11:00'}}]}]
]){
 assert.equal(m.verifiedBrokerProof(id,record,bad,watchlist,now),false,key);
}
assert.equal(m.verifiedBrokerProof(id,record,audit,[],now),false,'Issuer proof without screenshot list must fail');
assert.equal(m.verifiedBrokerProof(id,record,audit,watchlist,Date.parse('2026-10-20T22:00:00+02:00')),false,'End-of-day proof expired');
assert.equal(m.verifiedBrokerProof(id,record,audit,watchlist,Date.parse('2026-10-21T10:30:00+02:00')),false,'Next-day proof expired');
const manual=storage();
assert.equal(m.queueManual(manual,' '+other.toLowerCase()+' ').length,1);
assert.equal(m.queueManual(manual,other).length,1,'Same ISIN cannot be queued twice');
assert.equal(m.readLocal(manual)[0].issuerVerified,false);
assert.throws(()=>m.queueManual(manual,'INVALID'),/ISIN/);
const historical={lastScanAt:'2026-10-20T06:00:00+00:00',candidates:[{
 isin:id,name:'Test Gold Knock-out',direction:'LONG',issuerVerified:true,
 issuerStatus:'verified',degiroListed:true,liveApproved:true,eligibleForTop3:true,
 brokerageExecutionConfirmed:true
}]};
const normalized=m.normalizeCatalog(historical);
assert.equal(normalized.length,1);
assert.equal(normalized[0].origin,'historical-issuer-candidate');
assert.equal(normalized[0].issuerVerified,true);
assert.equal(normalized[0].listingConfirmed,false,'Issuer catalogue cannot claim DEGIRO listing');
let pools=m.researchUniverse(m.readLocal(manual),historical,[],audit,now);
assert.equal(pools.confirmed.length,0,'No active matching screenshot');
assert.equal(pools.unverified.length,2);
assert.equal(pools.automaticDegiroAdditions,0);
assert(pools.unverified.every(r=>!r.degiroListed && !r.degiroTradeApproved &&
 r.ibkrStatus==='not-checked' && r.igStatus==='not-checked' && !r.addToDegiroRankings));
pools=m.researchUniverse(m.readLocal(manual),historical,watchlist,audit,now);
assert.equal(pools.confirmed.length,1,'Current backend screenshot proof may label listing');
assert.equal(pools.confirmed[0].isin,id);
assert.equal(pools.confirmed[0].degiroTradeApproved,false);
assert.equal(pools.confirmed[0].executableQuoteVerified,false);
assert.equal(pools.unverified.length,1,'Broker-neutral candidate retained');
m.removeLocal(manual,other);
assert.equal(m.readLocal(manual).length,0,'Candidate removal persists');
assert.equal(m.researchUniverse([],historical,watchlist,audit,
 Date.parse('2026-10-20T22:01:00+02:00')).confirmed.length,0,'Candidate drops back to research when proof expires');
console.log('Issuer research vs DEGIRO listing: no invented listing or trading permission, broker futures pending, proof expires');
