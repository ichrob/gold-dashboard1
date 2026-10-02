const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,isin='DE000FG4JXV7',now=Date.parse('2026-10-02T19:22:30Z');
const w=b.selectionTimeWindow('02/10/2026 21:22');assert.equal(w.start,Date.parse('2026-10-02T19:22:00Z'));assert.equal(w.end-w.start,59999);assert(w.label.includes('Sekunden unbekannt'));
for(const raw of ['31/02/2026 21:22','25/10/2026 02:30','29/03/2026 02:30','21:22'])assert.equal(b.selectionTimeWindow(raw),null,raw);
const p={isin,name:'SG Gold Turbo Classic Put BAR 4460',productDirection:'SHORT',price:20.01,leverage:15,ko:4460,isinConfirmed:true};
p.snapshot={isin,currency:'EUR',bid:20,ask:20.01,sourceTime:'02/10/2026 21:22',evidence:{Geld:{source:'quote.jpg',value:20},Brief:{source:'quote.jpg',value:20.01},Hebel:{source:'quote.jpg',value:15}}};
assert(b.selectionDetailStatus(p,now).complete);assert(b.selectionDetailStatus(p,w.start+90000).complete);assert(!b.selectionDetailStatus(p,w.start+90001).complete);assert(!b.selectionDetailStatus(p,w.start-1).complete);
assert(!b.selectionDetailStatus({...p,isinConfirmed:false},now).complete);
assert(!b.selectionDetailStatus({...p,snapshot:{...p.snapshot,evidence:{...p.snapshot.evidence,Brief:{source:'other.jpg',value:20.01}}}},now).complete);
const context={now,direction:'SHORT',spotFresh:true,spot:4140,atr:10,trend:'SHORT',trend2:'SHORT',mtf:'SHORT',rsi:40,hist:-1,adx:30,momentum:-1};
let r=b.selectionWorkflow([p,p],context,{});assert.equal(r.total,1);assert.equal(r.groups.length,1);assert.equal(r.groups[0].candidates.length,1);assert.equal(r.stage,'TOP3');assert(!r.tradeable);assert(b.renderSelectionWorkflow(r).includes('Warum:'));
r=b.selectionWorkflow([p],{...context,direction:'NEUTRAL'},{});assert.equal(r.stage,'ABWARTEN');assert.equal(r.groups.length,0);
r=b.selectionWorkflow([{...p,snapshot:null}],context,{});assert.equal(r.requests.length,1);assert.equal(r.groups.length,0);assert(b.renderSelectionWorkflow(r).includes('Detailbilder ergänzen'));
assert(b.isFutureProduct({name:'SG Gold Future Turbo Put'}));
r=b.selectionWorkflow([{...p,name:'SG Gold Future Faktor Long',productDirection:'LONG'}],{...context,direction:'LONG'},{});assert.equal(r.groups.length,0);assert(r.waiting[0].reason.includes('Faktorprodukt'));
// A Future never enters a Spot ranking from a fresh screenshot alone.
r=b.selectionWorkflow([{...p,name:'SG Gold Future Turbo Put'}],context,{});assert.equal(r.groups.length,0);assert(r.waiting[0].reason.toLowerCase().includes('identität'));
console.log('selection flow: timestamps, identity, ranking, NEUTRAL and Future boundaries passed');

const at=sec=>new Date(now+sec*1000).toISOString();
const f={...p,isin:'DE000FG309G0',name:'SG Gold Future Turbo Put',ko:4500};
f.snapshot={...p.snapshot,isin:f.isin,evidence:{...p.snapshot.evidence,KO:{source:'quote.jpg',value:4500,at:at(0)}}};
f.quote={isin:f.isin,productVerified:true,metadata:{underlyingType:'FUTURE',contract:'GCZ26'},futureResearch:{contract:'GCZ26',direction:'SHORT',marketOpen:true,tradingEndAt:at(3600),bidAt:at(-1000),askAt:at(-1000),bid:0,ask:0,fxDataAt:at(0),fxEffectiveAt:at(0),ko:4500,strike:4500,ratio:.1,usdEur:.88,calculatedFuture:{available:true,contract:'GCZ26',priceUsd:4000,comparisonErrorUsd:2,priceAt:at(0),referenceAt:at(-900),proxySource:'Gold-API Spot (Berechnung)',validation:{ready:true,sampleCount:21,maxAbsoluteError:2}},contractAnalysis:{available:true,contract:'GCZ26',direction:'SHORT',technicalSourceFamilies:1,checkedAt:at(0),expiresAt:at(180),rsi:40,macdHistogram:-1,atr:20,frames:{'5m':{available:true,ema20:4010},'15m':{available:true},'1h':{available:true,trend:'SHORT',ema50:4020,ema200:4050},'4h':{available:true}}}}};
const fc=b.conditionalCandidate(f,context,now);assert(fc.ok,fc.reason);assert(fc.priceKind.includes('DEGIRO'));assert.equal(fc.price,20.01);
r=b.selectionWorkflow([f,p],context,{});assert.equal(r.groups.length,2);assert(r.groups.some(g=>g.scope==='GCZ26 · SHORT'));
f.quote.futureResearch.calculatedFuture.validation.ready=false;
r=b.selectionWorkflow([f],context,{});assert.equal(r.groups.length,0);assert(r.waiting[0].reason.includes('Genauigkeit'));
console.log('validated Future + screenshot path works without SG bid/ask; unvalidated estimate blocked');

assert(!b.selectionDetailStatus({...p,snapshot:{...p.snapshot,times:{bid:{present:true,text:"02/10/2026 21:25"}}}},now).complete);
assert(!b.selectionDetailStatus({...p,snapshot:{...p.snapshot,times:{leverage:{present:true,text:"invalid"}}}},now).complete);
