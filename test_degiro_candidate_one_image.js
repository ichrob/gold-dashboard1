'use strict';
const assert=require('node:assert/strict');
const policy=require('./broker_candidate_pools');
function exampleISIN(n){
 const base='DETEST'+String(n).padStart(5,'0');
 for(let i=0;i<10;i++)if(policy.isValidISIN(base+i))return base+i;
 throw Error('Invalid synthetic ISIN');
}
const isin=exampleISIN(1),other=exampleISIN(2);
const now=Date.parse('2026-10-20T08:30:00Z');
const raw={
 isin,venue:'Société Générale OTC',currency:'CHF',
 sourceTime:'20.10.2026 10:15',source:'DEGIRO-Produktdetail',
 brokerDisplayConfirmed:true,isExecutableQuote:false,
 orderWindowVerified:false,orderSubmitted:false,executionGuaranteed:false,
 bid:5.55,ask:5.57
};
const file={size:120000,type:'image/png'};
const hash='a'.repeat(64);
const payload=policy.screenshotPayload(raw,file,hash);
assert.equal(payload.isin,isin);
assert.equal(payload.imageSha256,hash);
assert.equal(payload.imageBytes,120000);
assert.equal(payload.imageMime,'image/png');
assert.equal(payload.isExecutableQuote,false);
assert.equal(payload.orderSubmitted,false);
assert(!('text' in payload)&&!('originalImage' in payload)&&!('account' in payload));
assert.equal(policy.screenshotPayload({...raw,bid:undefined,ask:undefined},file,hash).bid,null);
for(const variation of [
 {...raw,isin:other,source:'Emittent'},
 {...raw,source:'SG'},
 {...raw,venue:'unknown'},
 {...raw,currency:'USD'},
 {...raw,brokerDisplayConfirmed:false},
 {...raw,isExecutableQuote:true},
 {...raw,orderSubmitted:true},
 {...raw,sourceTime:'20.10.2026'},
 {...raw,bid:7,ask:3},
]){
 assert.throws(()=>policy.screenshotPayload(variation,file,hash));
}
assert.throws(()=>policy.screenshotPayload(raw,{size:120000,type:'text/html'},hash));
assert.throws(()=>policy.screenshotPayload(raw,file,'short'));
assert.throws(()=>policy.screenshotPayload(raw,{size:12000001,type:'image/png'},hash));
const ocr='Kursdaten Geld 5,55 CHF Brief 5,57 CHF Börse Société Générale OTC Symbol | ISIN '+isin;
assert.equal(policy.imageISIN(ocr,{normalizeOcrIsin:word=>({isin:word})}),isin);
assert.throws(()=>policy.imageISIN(ocr+' '+other,{normalizeOcrIsin:word=>({isin:word})}),/eindeutige/);
assert.throws(()=>policy.imageISIN('Only an issuer name'),/eindeutige/);
const proof={
 isin,broker:'DEGIRO',venue:'Société Générale OTC',currency:'CHF',
 kind:'user-uploaded-detail-ocr',origin:'user-uploaded-degiro-detail-image',
 observedAt:'2026-10-20T10:15:00+02:00',observedMinute:'2026-10-20T10:15',
 validUntil:'2026-10-20T22:00:00+02:00',imageSha256:hash,
 imageMime:'image/png',imageBytes:120000,
 listingConfirmed:true,brokerDisplayObserved:true,
 executionConfirmed:false,isExecutableQuote:false,tradeApproved:false,
 rankingsEligible:false,timezone:'Europe/Zurich',timePrecision:'minute'
};
const report={status:'ok',checkedAt:'2026-10-20T08:29:45Z',items:[proof]};
assert(policy.standaloneImageProof(isin,report,now));
for(const altered of [
 {...report,status:'stale'},
 {...report,checkedAt:'2026-10-20T08:20:00Z'},
 {...report,items:[{...proof,kind:'issuer-only'}]},
 {...report,items:[{...proof,listingConfirmed:false}]},
 {...report,items:[{...proof,executionConfirmed:true}]},
 {...report,items:[{...proof,tradeApproved:true}]},
 {...report,items:[{...proof,isin:other}]},
 {...report,items:[{...proof,observedMinute:'2026-10-19T10:15'}]},
 {...report,items:[{...proof,imageSha256:'fake'}]}
])assert.equal(policy.standaloneImageProof(isin,altered,now),null);
assert.equal(policy.standaloneImageProof(isin,report,Date.parse('2026-10-20T22:01:00+02:00')),null);
const collection={lastScanAt:'2026-10-20T08:25:00Z',candidates:[
 {isin:other,issuerVerified:true,issuerStatus:'verified',degiroListed:true}
]};
const cases=policy.researchUniverse([],collection,[],{status:'stale',items:[]},now,report);
assert.equal(cases.total,2,'Backend receipt adds candidate without uploading whole watchlist');
assert.equal(cases.confirmed.length,1);
assert.equal(cases.confirmed[0].isin,isin);
assert.equal(cases.confirmed[0].listingProofSource,'user-image');
assert.equal(cases.confirmed[0].degiroTradeApproved,false);
assert.equal(cases.confirmed[0].addToDegiroRankings,false);
assert.equal(cases.automaticDegiroAdditions,0);
assert.equal(cases.unverified.length,1);
console.log('Single DEGIRO image admission: strict OCR identity, no image transfer, server date, expiry and no trading');
