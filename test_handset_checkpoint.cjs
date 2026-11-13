'use strict';
const assert=require('node:assert/strict');
const {nativeImage,parse}=require('./handset_list_parse');
const vm=require('node:vm'),fs=require('node:fs');
const context={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),context);
function id(n){const stem='DE000ZZ'+String(n).padStart(4,'0');for(let i=0;i<10;i++)if(context.window.BobDegiro.validIsin(stem+i))return stem+i;}
function row(n,bar=4000){return `SG Gold Turbo BEST Open-End Call BAR ${bar} BP ${bar} Bv 10 | ${id(n)} Societe Generale OTC EUR`;}
const images=[[1,2,3,4],[4,5,6,7],[7,8,9,10]].map(ns=>Array(3).fill(ns.map(n=>row(n)).join('\n')));
const checkpoints=images.map(nativeImage);
assert(checkpoints.every(Boolean));
assert.equal(JSON.stringify(parse(images,'2026-11-04T08:00:00Z')),
             JSON.stringify(parse(checkpoints,'2026-11-04T08:00:00Z')));
assert.equal(nativeImage([row(1)]),null,'A checkpoint cannot invent a second optical read');
assert.equal(nativeImage(['not a row','not a row']),null);
const eleven=Array.from({length:11},(_,i)=>row(i+1)).join('\n');
assert.equal(nativeImage([eleven,eleven]),null,'Never truncate an extra product into a ten-row list');
const conflicting=checkpoints.concat([nativeImage([row(4,4100),row(4,4100)])]);
assert.throws(()=>parse(conflicting,'2026-11-04T08:00:00Z'),/Conflicting/);
const privateOutside='Portfolio secret\n'+row(1)+'\nKontostand secret';
assert.deepEqual(nativeImage([privateOutside,privateOutside]),[row(1),row(1)]);
console.log('Bounded OCR checkpoint grammar, privacy, original fields and conflict regression passed.');
