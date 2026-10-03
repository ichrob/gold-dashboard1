const fs=require('fs'),vm=require('vm'),assert=require('assert');
const store=new Map(),fields={};
const context={window:{},localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)}};
vm.createContext(context);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),context);
const b=context.window.BobDegiro,isin='DE000FG4JXV7';
const at='01/10/2026 06:00:00 CEST',now=Date.parse('2026-10-01T04:00:30Z');
assert.equal(b.sourceTimestamp(at),'2026-10-01T04:00:00.000Z');
assert.equal(b.sourceTimestamp('01/10/2026 04:00:00 UTC'),b.sourceTimestamp(at));
assert.equal(b.sourceTimestamp('01/10/2026 06:00:00 +02:00'),b.sourceTimestamp(at));
for(const t of ['01/10/2026 06:00 CEST','01/10/2026 06:00:00','31/02/2026 06:00:00 UTC','01/10/2026 25:00:00 UTC','01/10/2026 06:00:00 +15:00','01/10/2026 06:00:00 Europe/Zurich'])assert.equal(b.sourceTimestamp(t),null,t);
const read=extra=>b.detailScreenshotData(isin+'\nEUR\nSHORT\nGeld 24,81\nBrief 24,82\nHebel 14.01\nKO 4460\n'+extra,isin);
const snapshot=b.mergeScreenshotEvidence(null,read('Kurszeit: '+at+'\nHebelzeit: '+at+'\nKO-Zeit: '+at),'full.jpg');
const product={isin,price:24.82,spread:0.01,leverage:14.01,ko:4460,productDirection:'SHORT',isinConfirmed:true,spot:4000};
assert(b.manualSnapshotStatus(product,snapshot,now).complete);
assert(!b.manualSnapshotStatus(product,snapshot,now).liveVerified);
assert(b.manualSnapshotStatus(product,snapshot,now+14*3600000-30000).complete); // exactly 14 hours
assert(!b.manualSnapshotStatus(product,snapshot,now+14*3600000-29999).complete);
assert(!b.manualSnapshotStatus(product,snapshot,now-30001).complete); // future source time
assert(!b.manualSnapshotStatus({...product,isinConfirmed:false},snapshot,now).complete);
assert(!b.manualSnapshotStatus({...product,leverage:15},snapshot,now).complete);
assert(!b.manualSnapshotStatus({...product,ko:0},snapshot,now).complete);
assert(!b.manualSnapshotStatus({...product,isin:'DE000PJ9NCK0'},snapshot,now).complete);
assert(!b.currentQuote({...product,snapshot},now)); // a screenshot is never a fabricated API quote
assert(b.needsDirectionalData(product,'SHORT'));
assert(!b.needsDirectionalData(product,'LONG'));
assert(!b.needsDirectionalData(product,'NEUTRAL'));
assert(b.needsDirectionalData({...product,productDirection:'LONG'},'LONG'));
assert(!b.rankProducts([{...product,snapshot}],{requireFreshQuotes:true,spotFresh:true,direction:'SHORT',now}).tradeable);
for(const extra of ['Kurszeit: '+at,'Kurszeit: 01/10/2026 06:00:00','Kurszeit: 01/10/2026 06:00 CEST',at,'Uploadzeit: '+at]){
 const x=b.mergeScreenshotEvidence(null,read(extra),'unknown.jpg');assert(!b.manualSnapshotStatus(product,x,now).complete,extra);
}
const delayed=b.mergeScreenshotEvidence(null,read('Kurszeit: '+at+'\nHebelzeit: '+at+'\nKO-Zeit: '+at+'\nKurse verzögert'),'delayed.jpg');
assert(!b.manualSnapshotStatus(product,delayed,now).complete);
const invalidSide=b.mergeScreenshotEvidence(null,read('Kurszeit: '+at+'\nGeldzeit: 01/10/2026 06:00:00\nHebelzeit: '+at+'\nKO-Zeit: '+at),'invalid.jpg');
assert.equal(invalidSide.evidence.Geld.at,null); // cannot conceal missing timezone with a shared quote time
const conflicting=b.mergeScreenshotEvidence(null,read('Kurszeit: '+at+'\nKurszeit: 01/10/2026 05:59:00 CEST'),'conflicting.jpg');
assert.equal(conflicting.evidence.Geld.at,null);
const separate=b.mergeScreenshotEvidence(null,read('Geldzeit: 01/10/2026 05:59:00 CEST\nBriefzeit: '+at+'\nHebelzeit: '+at+'\nKO-Zeit: '+at),'separate.jpg');
assert.equal(separate.evidence.Spread.at,separate.evidence.Geld.at);
assert(!b.manualSnapshotStatus(product,separate,now).complete);
const newQuotes=b.detailScreenshotData(isin+'\nEUR\nGeld 25,00\nBrief 25,01\nKurszeit: 01/10/2026 06:01:00 CEST',isin);
const merged=b.mergeScreenshotEvidence(snapshot,newQuotes,'new-quotes.jpg');
assert.equal(merged.evidence.Hebel.at,snapshot.evidence.Hebel.at);
assert.equal(merged.evidence.KO.source,'full.jpg');
assert.equal(merged.leverage,'14.01');assert.equal(merged.ko,'4460');
assert.equal(merged.evidence.Geld.source,'new-quotes.jpg');
assert(b.manualSnapshotStatus({...product,price:25.01},merged,now+60000).complete);
const onlyDetails=b.detailScreenshotData(isin+'\nKO 4461\nKO-Zeit: '+at,isin);
const added=b.mergeScreenshotEvidence(snapshot,onlyDetails,'details.jpg');
assert.equal(added.evidence.Geld.at,snapshot.evidence.Geld.at);
assert.equal(added.evidence.Geld.source,'full.jpg');
assert.equal(added.currency,'EUR');assert.equal(added.ask,24.82);
assert.equal(added.evidence.KO.source,'details.jpg');
const undatedKO=b.mergeScreenshotEvidence(snapshot,b.detailScreenshotData(isin+'\nKO 4461',isin),'undated.jpg');
assert.equal(undatedKO.evidence.KO.at,null);
const comparisonProduct={...product,snapshot};
const comparisonContext={atr:20,direction:'SHORT',spotFresh:true,spot:4000,now};
assert.equal(b.rankManualSnapshots([comparisonProduct],comparisonContext).total,1);
assert.equal(b.rankManualSnapshots([comparisonProduct],comparisonContext).liveVerified,false);
for(const change of [{direction:'NEUTRAL'},{direction:'LONG'},{spotFresh:false},{now:now+14*3600000-29999},{trend:'LONG',trend2:'LONG',mtf:'LONG',hist:1,momentum:1,rsi:65}]){
 assert.equal(b.rankManualSnapshots([comparisonProduct],{...comparisonContext,...change}).total,0);
}
assert.equal(b.rankManualSnapshots([{...comparisonProduct,isinConfirmed:false}],comparisonContext).total,0);
assert.equal(b.rankManualSnapshots([{...comparisonProduct,ko:4500}],{...comparisonContext,spot:4600}).total,0);
const lower={...comparisonProduct,leverage:20,snapshot:{...snapshot,evidence:{...snapshot.evidence,Hebel:{...snapshot.evidence.Hebel,value:20}}}};
const ordered=b.rankManualSnapshots([lower,{...comparisonProduct,leverage:5,snapshot:{...snapshot,evidence:{...snapshot.evidence,Hebel:{...snapshot.evidence.Hebel,value:5}}}}],comparisonContext);
assert.equal(ordered.total,2);assert.equal(ordered.candidates[0].evaluation.score,ordered.candidates[1].evaluation.score);
context.document={getElementById:()=>null};
for(const direction of ['NEUTRAL','LONG','SHORT']){
 const cards=b.productUploadCards([comparisonProduct,{...comparisonProduct,productDirection:'LONG',name:'<img onerror=bad>'}],direction,now);
 assert(cards.includes('data-selection-upload="1"'));assert(cards.includes('data-selection-upload="2"'));assert(cards.includes('&lt;img onerror=bad&gt;'));
 assert(cards.includes('data-card-confirm="1"'));
 if(direction==='LONG')assert(cards.indexOf('data-selection-upload="2"')<cards.indexOf('data-selection-upload="1"'));
}
context.document={querySelector:sel=>{const m=sel.match(/data-dg="([^"]+)".*data-i="(\d+)"/);return m?fields[m[2]+':'+m[1]]:null;}};
for(const [key,value] of Object.entries({isin,name:'SG Gold SHORT',dir:'SHORT',price:'24.82',lev:'14.01',ko:'4460',spread:'.01'}))fields['1:'+key]={value};
b.saveIdentities();const saved=JSON.parse(store.get('bobDegiroIdentitiesV1'));
assert.deepEqual(Object.keys(saved[0]).sort(),['direction','isin','name']);
assert.equal(b.loadIdentities()[0].isin,isin);assert.equal(b.loadIdentities()[0].price,24.82);
store.delete('bobDegiroProductsV2');store.set('bobDegiroIdentitiesV1','bad json');assert.equal(b.loadIdentities().length,0);
store.set('bobDegiroIdentitiesV1',JSON.stringify([{isin:'invalid'}]));assert.equal(b.loadIdentities().length,0);
const server=fs.readFileSync('server.py','utf8');
assert(server.includes('manualSnapshotStatus'));assert(server.includes('bobDegiroIdentitiesV1'));
console.log('Manual DEGIRO timestamp / provenance / persistence regressions: OK');



// Reload must preserve full evidence and confirmation without refreshing source clocks.
const makeApi=()=>{const env={window:{},localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},document:{getElementById:()=>null,querySelector:sel=>{const m=sel.match(/data-dg="([^"]+)".*data-i="(\d+)"/);return m?fields[m[2]+':'+m[1]]:null;}}};vm.createContext(env);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),env);return env.window.BobDegiro;};
store.clear();const first=makeApi();
const full={...product,direction:product.productDirection,isinConfirmed:true,snapshot,reference:{isin,quoteAt:snapshot.evidence.Geld.at,reviewed:true}};
assert(first.writeStoredProducts([full]));const second=makeApi(),loaded=second.loadIdentities();
assert.equal(loaded[0].isinConfirmed,true);assert.equal(loaded[0].snapshot.evidence.Geld.at,snapshot.evidence.Geld.at);
assert.equal(loaded[0].reference.quoteAt,snapshot.evidence.Geld.at);
fields['1:confirmed']={checked:false};second.restoreProductRows(loaded);second.saveIdentities();
assert.equal(fields['1:confirmed'].checked,true);assert.equal(second.loadIdentities()[0].snapshot.evidence.KO.source,'full.jpg');
assert(!second.manualSnapshotStatus({...product,snapshot:loaded[0].snapshot},loaded[0].snapshot,now+15*3600000).complete);
const wrong=second.cleanStoredProduct({...full,snapshot:{isin:'DE000PJ9NCK0'},reference:{isin:'DE000PJ9NCK0'}});
assert.equal(wrong.snapshot,undefined);assert.equal(wrong.reference,undefined);
const recovered=second.recoverReviewedLists([]);assert.equal(recovered.length,10);assert(recovered.every(x=>second.validIsin(x.isin)));
const sg=recovered.find(x=>x.isin==='DE000FG5GUT0');assert.equal(sg.snapshot.terms.strike.value,4069.25);assert.equal(sg.snapshot.terms.strike.at,null);assert.equal(sg.snapshot.terms.ratio,undefined);assert.equal(sg.snapshot.terms.quanto,undefined);
assert(!second.productTermsStatus({...sg,productDirection:sg.direction},now).complete);
const newer={...sg,snapshot:{...sg.snapshot,terms:{strike:{value:4070,at:'2026-10-03T08:00:00Z',source:'new.jpg'}}}};
assert.equal(second.recoverReviewedLists([newer])[0].snapshot.terms.strike.value,4070);
assert(second.writeStoredProducts([]));assert.equal(makeApi().loadIdentities().length,0);
store.set('bobDegiroProductsV2','broken');const corrupt=makeApi();assert.equal(corrupt.loadIdentities().length,0);assert(!corrupt.writeStoredProducts([]));assert.equal(store.get('bobDegiroProductsV2'),'broken');
console.log('Full evidence reload, identity isolation, historical recovery, empty list and corrupt-store preservation: OK');
