const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('degiro_assistant.js','utf8');
const keys=['isin','currency','entry','quantity','bid','goldReference','fxReference','fxScenario','source','referenceAt','ratio','strike','ko','direction','simpleSpotTurbo','referenceConfirmed'];
const fields=Object.fromEntries(keys.map(k=>[k,{dataset:{exit:k},value:'',type:/Confirmed|Turbo/.test(k)?'checkbox':'text',checked:false}]));
const output={textContent:''};let events=0,calls=0,saved=null;
const panel={querySelector:s=>s==='[data-exit-output]'?output:fields[s.match(/"([^"]+)"/)[1]],querySelectorAll:()=>Object.values(fields),dispatchEvent:()=>events++};
const ctx={document:{getElementById:()=>panel},window:{BobDegiro:{validIsin:v=>/^DE/.test(v),exitReference:isin=>({isin,ratio:0.1,source:'issuer'})}},localStorage:{getItem:()=>saved,setItem:(_,v)=>{saved=v}},Event:class{},automaticTradeReference:()=>calls++};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function selectProduct('),source.indexOf('function issuerTradeFields(')),ctx);
fields.isin.value='DE000FG309G0';fields.entry.value='4.5';fields.quantity.value='8';fields.ko.value='3000';fields.referenceConfirmed.checked=true;
ctx.selectProduct('DE000FC1CHB7');assert.equal(fields.entry.value,'');assert.equal(fields.quantity.value,'');assert.equal(fields.ko.value,'');assert.equal(fields.referenceConfirmed.checked,false);assert.equal(fields.ratio.value,0.1);
fields.entry.value='8.4';fields.quantity.value='12';ctx.selectProduct('DE000FC1CHB7');assert.equal(fields.entry.value,'8.4');assert.equal(fields.quantity.value,'12');assert.equal(calls,2);
saved=JSON.stringify({isin:'DE000FG309G0',entry:'3.2',quantity:'5',referenceConfirmed:true});ctx.selectProduct('DE000FG309G0');assert.equal(fields.entry.value,'3.2');assert.equal(fields.quantity.value,'5');assert.equal(fields.referenceConfirmed.checked,false);
// Source recovery messages distinguish an actual in-flight request from an old failure.
const h={researchResults:new Map(),pendingQuotes:new Set(),productProblemLabels:()=>['Hebel'],};vm.createContext(h);vm.runInContext(source.slice(source.indexOf('function productHelpState('),source.indexOf('function renderProductHelp(')),h);
const p={isin:'DE000FC1CHB7',index:1};assert(!h.productHelpState(p).checking);h.pendingQuotes.add(1);assert(h.productHelpState(p).checking);assert(!h.productHelpState(p).manual);h.pendingQuotes.clear();h.researchResults.set(1,{isin:p.isin,sourceFailure:true});assert(h.productHelpState(p).manual);
console.log('Guided trade: same-ISIN purchase preservation, cross-product clearing, stored purchase reuse, no restored confirmations, honest recovery status passed');
