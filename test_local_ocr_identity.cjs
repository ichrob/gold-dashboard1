'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {canonicalLocalOcrIdentity:canonical,localOcrImage,appImage}=require('./handset_list_parse');
const ctx={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro;
const id='DE000SQ02JQ6',raw='DEOOOSQO2JQ6',other='DE000FG8NHQ3';
const row=`SG Gold Turbo Unlimited Mini Call BAR 2166 BP 2126.05 Bv 10 | ${raw} Societe Generale OTC EUR`;
assert.equal(canonical(raw),id);assert.equal(canonical(raw.toLowerCase()),id);
assert.equal(canonical(other),other);
assert.equal(canonical('DEOOOSQO2JQ5'),null);
assert.equal(canonical('DEOOOPU8APE4'),null,'Do not introduce context-specific reviewed aliases into this path');
const local={expectedIsins:[id],passes:[[row],[row]]};
assert.deepEqual(localOcrImage(local),[row,row],'Original optical spelling must survive');
assert.equal(appImage({before:[row],after:[row]}),null,'Accessibility text remains exact');
for(const wrong of [row.replace(raw,other),row.replace(raw,'DEOOOSQO2JQ5'),row.replace(raw,raw+' '+id),row.replace('BP 2126.05','BP 21O6.05')]){
 assert.equal(localOcrImage({expectedIsins:[id],passes:[[wrong],[wrong]]}),null);
}
for(let n=1;n<=100;n++){
 const stem='DE000ZZ'+String(n).padStart(4,'0');
 const valid=Array.from({length:10},(_,i)=>stem+i).find(b.validIsin);
 assert.equal(canonical(valid),valid);
 for(const prefix of ['DEOOO','DEQO0','DE000']){
  const optical=prefix+valid.slice(5).replace(/0/g,'O').replace(/1/g,'I');
  const expected=b.validIsin(optical)&&optical.startsWith('DE000')?optical:valid;
  assert.equal(canonical(optical),expected);
  assert.equal(canonical(optical),b.normalizeOcrIsin(optical).isin,'Same restricted server glyph rule');
 }
}
console.log('Local OCR raw-evidence preservation, checksum, wrong-ID rejection, numeric isolation and 300 server-parity cases passed.');
