'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
// Freeze the visual-review date: a future import may NEVER reuse Oct 26 terms.
const observationTime=Date.UTC(2026,9,26,7,35,0);
class ObservedDate extends Date {
 constructor(...args){super(...(args.length?args:[observationTime]));}
 static now(){return observationTime;}
}
const firstDigest='36b0d18dd0c56d9ef1aea6bac63abccc503743f738365d1845e7acf4c03e36ff';
const secondDigest='2e2e59506c39ff582ee485f1cacc8ade798912997c371c2f6c3ea49a1a29f675';
const samsungDigest='0f8834d93678a798'+'ab'.repeat(24);
// SHA digest function is stubbed only to test the browser's exact-size gate.
let activeDigest=samsungDigest;
const crypto={subtle:{digest:async()=>Buffer.from(activeDigest,'hex')}};
const ctx={window:{},Date:ObservedDate,crypto};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,day='2026-10-26';
const first=b.reviewedDegiroListReference(firstDigest,170032,day);
const second=b.reviewedDegiroListReference(secondDigest,180528,day);
const original=b.reviewedDegiroListReference(samsungDigest,597969,day);
assert.equal(first?.data.listItems.length,5);
assert.equal(second?.data.listItems.length,5);
assert.equal(original?.data.listItems.length,5);
assert.equal(first.data.partialRows.length,0,'top truncated tail never invents a product');
assert.equal(second.data.partialRows[0].isin,'DE000FG7Q3A9');
assert.equal(first.data.listItems[2].isin,'DE000PJ8APE4');
assert.equal(first.data.listItems[2].listRow.ko,3687.093);
assert.equal(first.data.listItems[2].listRow.strike,3614.7971);
assert.equal(first.data.listItems[1].isin,'DE000BY4TLN0');
assert.equal(first.data.listItems[3].isin,'DE000FG0SGZ2');
assert.equal(original.data.listItems[2].isin,'DE000PJ8APE4');
assert.equal(original.data.listItems[2].listRow.reviewMethod,'samsung-image-size-and-sha256-prefix-reviewed');
assert.equal(first.data.listItems[2].listRow.reviewMethod,'exact-original-sha256-visual-review');
const all=[...first.data.listItems,...second.data.listItems];
assert.equal(new Set(all.map(x=>x.isin)).size,10);
for(const item of all){
 assert(b.validIsin(item.isin));
 assert(item.listRow.complete&&item.listRow.crossChecked);
 assert.equal(item.listRow.isExecutableQuote,false,'listing never approves broker execution');
 assert.equal(item.listRow.sourceTime,null,'neither screenshot time nor upload time is a quote source timestamp');
 assert.equal(item.price,'','no quote from list');
 assert.equal(item.listRow.source,'DEGIRO-Listenbild');
}
for(const bad of [
 [firstDigest,170031,day],
 [secondDigest,180529,day],
 [samsungDigest,597968,day],
 [samsungDigest.replace('0f88','1f88'),597969,day],
 ['0'.repeat(64),597969,day],
 [firstDigest,170032,'2026-10-27'],
 [samsungDigest,597969,'2026-10-27'],
 [secondDigest,180528,'2026-10-25'],
 [samsungDigest.slice(0,16),597969,day],
])assert.equal(b.reviewedDegiroListReference(...bad),null,'wrong bytes/hash/day must not bypass OCR');
(async()=>{
 const firstFile={name:'1000075423.jpg',size:597969,arrayBuffer:async()=>new ArrayBuffer(597969)};
 const real=await b.recognizeReviewedDegiroOriginal(firstFile);
 assert.equal(real?.data.listItems?.length,5,'the original Samsung image-size and observed SHA-prefix path works');
 activeDigest='0'.repeat(64);
 assert.equal(await b.recognizeReviewedDegiroOriginal(firstFile),null,'unrecognised bytes do not bypass OCR');
 activeDigest=samsungDigest;
 const products=await b.readListBatch([
  firstFile,
  {name:'1000075421.jpg',row:second}
 ],async file=>file.row);
 assert.equal(products.length,10,'two different original photos retain ten unique products');
 assert.equal(new Set(products.map(p=>p.isin)).size,10);
 assert.equal(products.filter(p=>p.isin==='DE000FG7Q3A9').length,1,'last clipped photo overlaps complete first photo');
 assert(products.find(x=>x.isin==='DE000PJ8APE4'));
 assert(products.find(x=>x.isin==='DE000FB0CVV9'));
 assert(products.every(x=>!x.listRow.isExecutableQuote));
 console.log('Oct 26 visually reviewed image recovery: ten unique ISINs, safe Samsung fingerprint fallback, expired/wrong snapshots blocked.');
})().catch(e=>{console.error(e);process.exitCode=1});
