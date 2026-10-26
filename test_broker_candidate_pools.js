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
const audit={status:'ok',listUploadedAt:uploadedAt,lastCheckedAt:'2026-10-20T08:29:15Z',items:[{isin:id,brokerVenueEvidence:evidence}]};
assert(m.isValidISIN(id));
assert(!m.isValidISIN(id.slice(0,11)+'X'));
assert.equal(m.verifiedBrokerProof(id,record,audit,watchlist,now),true);
assert.equal(m.verifiedBrokerProof(id,record,{...audit,lastCheckedAt:'2026-10-20T08:20:00Z'},watchlist,now),false,'Old audit receipt cannot confirm current listing');
assert.equal(m.verifiedBrokerProof(id,record,{...audit,lastCheckedAt:null},watchlist,now),false,'Undated audit is not current proof');
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
// A DEGIRO screen observation and an issuer quote can be compared only as
// display evidence, never as currently executable broker prices.
const screenTime=Date.parse('2026-10-20T10:15:59+02:00');
const screen={
 isin:id,kind:'user-uploaded-detail-ocr',origin:'user-uploaded-degiro-detail-image',
 listingConfirmed:true,brokerDisplayObserved:true,executionConfirmed:false,
 tradeApproved:false,isExecutableQuote:false,rankingsEligible:false,
 brokerDisplayRecent:true,displayClockRole:'screen-minute-not-quote-source-clock',
 venue:'Societe Generale OTC',currency:'EUR',
 observedAt:'2026-10-20T10:15:00+02:00',
 validUntil:'2026-10-20T22:00:00+02:00',bid:5.1,ask:5.12
};
const issuerQuote={
 isin:id,sourceRole:'issuer-comparison-only',issuerKind:'SG',
 executable:false,brokerTradeApproved:false,currency:'EUR',
 bid:5.11,ask:5.13,
 bidAt:'2026-10-20T10:15:35+02:00',askAt:'2026-10-20T10:15:35+02:00',
 leverageAt:'2026-10-20T10:15:35+02:00',snapshotAt:'2026-10-20T10:15:35+02:00'
};
let cross=m.compareBrokerDisplayToIssuer(screen,issuerQuote,screenTime);
assert.equal(cross.status,'display-aligned');
assert.equal(cross.checked,true);
assert.equal(cross.executableQuoteVerified,false);
assert.equal(cross.accountTradeableNowVerified,false);
assert.equal(cross.tradeApproved,false);
cross=m.compareBrokerDisplayToIssuer(screen,{...issuerQuote,bid:4,ask:4.1},screenTime);
assert.equal(cross.status,'display-divergent');
assert.equal(cross.checked,true);
for(const [reason,display,issuerSnap,at] of [
 ['different ISIN',screen,{...issuerQuote,isin:other},screenTime],
 ['stale display',screen,issuerQuote,screenTime+91000],
 ['missing display origin',{...screen,origin:'invented'},issuerQuote,screenTime],
 ['future display',{...screen,observedAt:'2026-10-20T10:17:00+02:00'},issuerQuote,screenTime],
 ['mismatched venue',{...screen,venue:'BNP OTC'},issuerQuote,screenTime],
 ['mismatched currency',{...screen,currency:'CHF'},issuerQuote,screenTime],
 ['false execution',{...screen,isExecutableQuote:true},issuerQuote,screenTime],
 ['missing issuer clock',screen,{...issuerQuote,askAt:null},screenTime],
 ['synthetic original clock',screen,{...issuerQuote,issuerKind:null},screenTime],
 ['late issuer quote',screen,{...issuerQuote,bidAt:'2026-10-20T10:12:00+02:00'},screenTime],
 ['stale source identity',{...screen,brokerDisplayRecent:false},issuerQuote,screenTime],
 ['calculated broker approval',screen,{...issuerQuote,brokerTradeApproved:true},screenTime],
 ['missing prices',{...screen,ask:null},issuerQuote,screenTime]
]){
 const denied=m.compareBrokerDisplayToIssuer(display,issuerSnap,at);
 assert.equal(denied.checked,false,reason);
 assert.equal(denied.executableQuoteVerified,false,reason);
 assert.equal(denied.tradeApproved,false,reason);
}
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
const researchRotation={
 lastScanAt:'2026-10-20T06:00:00+00:00',
 candidates:historical.candidates,
 historyResearchArchive:[
  {isin:other,direction:'SHORT',name:'Historischer Gold-KO',
   brokerHistoricallyTransacted:true,issuerIdentityMatched:true,
   issuerCheckedAt:'2026-10-20T08:00:00Z',
   currentlyDegiroListed:null,tradeApproved:false,
   issuerComparison:{isin:other,sourceRole:'issuer-comparison-only',
     bid:3.1,ask:3.2,currency:'EUR',
     bidAt:'2026-10-20T08:00:00Z',askAt:'2026-10-20T08:00:00Z'}},
  // Never import a historical artifact without validated broker history identity.
  {isin:fakeIsin(3),direction:'LONG',brokerHistoricallyTransacted:false}
 ]};
const historicalView=m.normalizeCatalog(researchRotation);
assert.equal(historicalView.length,2);
const historicalRow=historicalView.find(x=>x.isin===other);
assert.equal(historicalRow.origin,'historical-trade-research');
assert.equal(historicalRow.issuerVerified,true);
assert.equal(historicalRow.listingConfirmed,false);
assert.equal(historicalRow.issuerComparison.sourceRole,'issuer-comparison-only');
const historicalPool=m.researchUniverse([],researchRotation,[],null,now);
assert.equal(historicalPool.confirmed.length,0);
assert.equal(historicalPool.unverified.length,2);
assert(historicalPool.unverified.every(x=>x.addToDegiroRankings===false &&
 x.executableQuoteVerified===false && x.degiroTradeApproved===false));
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
