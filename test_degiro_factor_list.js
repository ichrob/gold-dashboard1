'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const ctx={window:{}};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro;
function id(n){const stem='DE000ZZ'+String(n).padStart(4,'0');for(let d=0;d<10;d++)if(b.validIsin(stem+d))return stem+d;}
const factor=`SG Gold Future Faktor Long HB 15 | ${id(1)}\nSociete Generale OTC EUR K V`;
const ko=`SG Gold Turbo Open End Call BAR 3000 BP 3000 Bv 10 | ${id(2)}\nSociete Generale OTC EUR K V`;
const excluded=b.agreedExcludedDegiroFactorRow([factor,factor]);
assert(excluded.listRow.excluded);
assert.equal(excluded.listRow.complete,false);
assert.equal(excluded.listRow.crossChecked,false);
assert.equal(excluded.listRow.isExecutableQuote,false);
assert.equal(b.agreedDegiroListRow([factor,factor]),null);
assert.equal(b.evaluateProduct(excluded).ok,false);
for(const reads of [[factor],[factor,ko],[factor,factor.replace(id(1),id(3))],
 [factor,factor.replace('EUR','CHF')],[factor,factor.replace('Long','Short')],
 [factor,factor.replace('Societe Generale','BNP')],[factor,factor+'\n'+ko],
 [ko,ko],[factor.replace('Faktor',''),factor.replace('Faktor','')]]){
 assert.equal(b.agreedExcludedDegiroFactorRow(reads),null);
}
// Exercise actual row-recognition control flow, with synthetic OCR responses.
// No screenshot pixels or private product identifiers are committed.
ctx.createImageBitmap=async()=>({width:700,height:500,close(){}});
ctx.document={getElementById:()=>null,createElement:()=>({getContext:()=>({drawImage(){}}),toBlob:cb=>cb({})})};
ctx.setTimeout=setTimeout;ctx.clearTimeout=clearTimeout;
const words=[];
for(const y of [10,210])words.push(
 {text:'SG',bbox:{x0:10,x1:30,y0:y,y1:y+20}},
 {text:'Gold',bbox:{x0:40,x1:80,y0:y,y1:y+20}},
 {text:'OTC',bbox:{x0:100,x1:140,y0:y+100,y1:y+120}});
(async()=>{
 let calls=0;const texts=[factor,factor,ko,ko];
 const worker={setParameters:async()=>{},recognize:async()=>({data:{text:texts[calls++]}})};
 const result=await b.recognizeDegiroList(worker,{}, {data:{words}},'');
 assert.equal(calls,4,'factor must not exhaust KO retries');
 assert.equal(result.data.listItems.length,2);
 assert(result.data.listItems[0].listRow.excluded);
 assert(result.data.listItems[1].listRow.complete);
 const merged=await b.readListBatch([{name:'synthetic.png'}],async()=>result);
 assert.equal(merged.length,2);
 assert.equal(merged[0].listRow.imageReference,'synthetic.png');
 console.log('Factor exclusion, conflicting reads and mixed-list recognition passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
