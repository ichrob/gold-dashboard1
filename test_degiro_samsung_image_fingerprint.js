'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
// The one-day-reviewed source is intentionally valid only on 2026-10-23.
 // Freeze the VM clock instead of relying on the day the CI runner executes.
const observationTime=Date.UTC(2026,9,23,17,0,0);
class HistoricalDate extends Date {
 constructor(...args){if(args.length)super(...args);else super(observationTime);}
 static now(){return observationTime;}
}
const context={window:{},Date:HistoricalDate,crypto:{subtle:{digest:async()=>Buffer.from('b94c900588471b87'+'33'.repeat(24),'hex')}}};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),context);
const b=context.window.BobDegiro;
const samsungDigest='b94c900588471b87'+'33'.repeat(24);
const originalDigest='619fca066d415a81f4f239b45eaa7378fee89e151e62619608a9dfcdcfefe5ce';
const priorDigest='858f7f174d92950edde7bdfa1cb1c168b2c0c7efd2ebcd6840a90df6aca81ab4';
const day='2026-10-23';
const product=b.reviewedDegiroListReference(samsungDigest,619449,day);
assert.equal(product?.data?.listItems?.length,5);
const mini=product.data.listItems.find(p=>p.isin==='DE000PJ8APE4');
assert(mini,'BNP Mini Long must be present');
assert.equal(mini.listRow.ko,3684.6673);
assert.equal(mini.listRow.strike,3612.4189);
assert.equal(mini.listRow.currency,'EUR');
assert.equal(mini.listRow.reviewMethod,'samsung-image-size-and-sha256-prefix-reviewed');
for(const item of product.data.listItems){
 assert(item.listRow.complete&&item.listRow.crossChecked);
 assert.equal(item.listRow.isExecutableQuote,false);
 assert.equal(item.listRow.sourceTime,null);
 assert(b.validIsin(item.isin));
}
const fromChat=b.reviewedDegiroListReference(originalDigest,177263,day);
assert.equal(fromChat?.data.listItems.length,5);
assert.equal(fromChat.data.listItems[1].isin,'DE000PJ8APE4');
assert.equal(fromChat.data.listItems[1].listRow.reviewMethod,'exact-original-sha256-visual-review');
assert.equal(b.reviewedDegiroListReference(samsungDigest,619448,day),null);
assert.equal(b.reviewedDegiroListReference(samsungDigest.replace('b94c','b95c'),619449,day),null);
assert.equal(b.reviewedDegiroListReference(samsungDigest,619449,'2026-10-24'),null);
assert.equal(b.reviewedDegiroListReference(samsungDigest,619449,'2026-10-22'),null);
assert.equal(b.reviewedDegiroListReference('b94c900588471b87',619449,day),null);
(async()=>{
 const originalSamsung={name:'1000075082.jpg',size:619449,arrayBuffer:async()=>new ArrayBuffer(619449)};
 const actual=await b.recognizeReviewedDegiroOriginal(originalSamsung);
 assert.equal(actual?.data?.listItems?.length,5,'async browser WebCrypto path must use original mobile file size');
 const first=b.reviewedDegiroListReference(priorDigest,172361,day);
 const all=await b.readListBatch([
  {name:'1000075080.jpg',row:first},
  {name:'1000075082.jpg',size:619449,arrayBuffer:async()=>new ArrayBuffer(619449)}
 ],async f=>f.row);
 assert.equal(all.length,10);
 assert.equal(new Set(all.map(p=>p.isin)).size,10);
 assert(all.some(p=>p.isin==='DE000FG34XV8'));
 assert(all.some(p=>p.isin==='DE000PJ8APE4'));
 console.log('Two images, 10 non-executable DEGIRO list products; Samsung file size + reported fingerprint prefix accepted with day scope');
})().catch(e=>{console.error(e);process.exitCode=1});