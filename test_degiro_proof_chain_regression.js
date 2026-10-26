'use strict';
// Regression contract: a DEGIRO list screenshot proves identity, not live execution.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const c={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};
vm.createContext(c);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),c);
const b=c.window.BobDegiro;
const isin='DE000FG4JXV7';
const row='SG Gold Turbo BEST Open-End Put BAR 4460 BP 4460 Bv 10 | '+isin+'\nSociete Generale OTC EUR (K) (V)';
const parsed=b.parseDegiroListRow(row);
assert.equal(parsed.isin,isin);
assert.equal(parsed.listRow.complete,true);
assert.equal(parsed.price,'');
assert.equal(parsed.leverage,'');
assert.equal(parsed.listRow.sourceTime,null);
const evidence=require('./product_evidence_contract.js');
const combined=evidence.fromCombined({isin,inWatchlist:true});
assert.equal(combined.isin,isin);
assert.equal(combined.identity.state,'observed');
assert.match(combined.identity.text,/Screenshotidentität/);
assert.equal(combined.tradeable,false);
assert.equal(combined.executableQuote,false);
const status=evidence.productEvidence({isin});
assert.equal(status.tradeable,false);
assert.equal(status.venue.state,'unknown');
console.log('DEGIRO screenshot identity / approval separation contract passed');

const storage=new Map();
const sandbox={window:{},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),sandbox);
const prior={isin,direction:'SHORT',value:4460,currency:'USD',source:'original screenshot',imageSource:'list',userConfirmed:true,confirmedAt:'2026-10-26T10:00:00Z'};
storage.set('bobFixedScreenshotKoV1',JSON.stringify({[isin]:prior}));
assert.equal(sandbox.window.BobCombined.resetFixedList(),true);
assert.equal(JSON.parse(storage.get('bobFixedScreenshotKoV1'))[isin],null);
assert.equal(JSON.parse(storage.get('bobFixedScreenshotKoHistoryV1'))[isin][0].confirmedAt,prior.confirmedAt);
assert.equal(sandbox.window.BobCombined.resetFixedList(),true);
assert.equal(JSON.parse(storage.get('bobFixedScreenshotKoHistoryV1'))[isin].length,1);
console.log('DEGIRO KO evidence archived without current-generation approval');

(async()=>{
 for(const mode of ['corrupt','archive-write-denied','revocation-write-denied']){
  const store=new Map([['bobFixedScreenshotKoV1',JSON.stringify({[isin]:prior})]]);
  if(mode==='corrupt')store.set('bobFixedScreenshotKoHistoryV1','{invalid');
  let archiveOpens=0;
  const env={window:{},indexedDB:{open(){archiveOpens++;throw Error('Replacement must not start');}},localStorage:{
   getItem:k=>store.get(k)||null,
   setItem(k,v){if(mode==='archive-write-denied'&&k==='bobFixedScreenshotKoHistoryV1'||mode==='revocation-write-denied'&&k==='bobFixedScreenshotKoV1')return;store.set(k,v);}
  }};
  vm.createContext(env);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),env);
  await assert.rejects(env.window.BobDegiro.saveReplacementListArchive([],[]),/Liste nicht ersetzt/,mode);
  assert.equal(archiveOpens,0,mode);
  assert.equal(JSON.parse(store.get('bobFixedScreenshotKoV1'))[isin].confirmedAt,prior.confirmedAt,mode);
 }
 console.log('Replacement list rejected before archive commit on corrupt or silently failed KO storage');
})().catch(e=>{console.error(e);process.exitCode=1;});
