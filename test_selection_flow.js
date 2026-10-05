const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,isin='DE000FG4JXV7',now=Date.parse('2026-10-02T19:22:30Z');
const w=b.selectionTimeWindow('02/10/2026 21:22');assert.equal(w.start,Date.parse('2026-10-02T19:22:00Z'));assert.equal(w.end-w.start,59999);assert(w.label.includes('Sekunden unbekannt'));
for(const raw of ['31/02/2026 21:22','25/10/2026 02:30','29/03/2026 02:30','21:22'])assert.equal(b.selectionTimeWindow(raw),null,raw);
const p={isin,name:'SG Gold Turbo Classic Put BAR 4460',productDirection:'SHORT',price:20.01,leverage:15,ko:4460,isinConfirmed:true};
p.snapshot={isin,currency:'EUR',bid:20,ask:20.01,sourceTime:'02/10/2026 21:22',evidence:{Geld:{source:'quote.jpg',value:20},Brief:{source:'quote.jpg',value:20.01},Hebel:{source:'quote.jpg',value:15}}};
const terms=(values)=>Object.fromEntries(Object.entries(values).map(([k,value])=>[k,{value,at:'2026-10-02T19:00:00Z',source:'details.jpg'}]));
p.snapshot.terms=terms({ratio:.1,strike:4460,underlying:'XAU/USD',type:'Turbo',maturity:'Open End',currency:'EUR',quanto:'Nein'});
p.snapshot.evidence.KO={value:4460,source:'details.jpg',at:'2026-10-02T19:00:00Z'};
assert(b.selectionDetailStatus(p,now).complete);assert(b.selectionDetailStatus(p,w.start+14*3600000).complete);assert(!b.selectionDetailStatus(p,w.start+14*3600000+1).complete);assert(!b.selectionDetailStatus(p,w.start-1).complete);
assert(!b.selectionDetailStatus({...p,isinConfirmed:false},now).complete);
assert(!b.selectionDetailStatus({...p,snapshot:{...p.snapshot,evidence:{...p.snapshot.evidence,Brief:{source:'other.jpg',value:20.01}}}},now).complete);
const context={now,direction:'SHORT',spotFresh:true,spot:4140,atr:10,trend:'SHORT',trend2:'SHORT',mtf:'SHORT',rsi:40,hist:-1,adx:30,momentum:-1};
let r=b.selectionWorkflow([p,p],context,{});assert.equal(r.total,1);assert.equal(r.groups.length,1);assert.equal(r.groups[0].candidates.length,1);assert.equal(r.stage,'TOP3');assert(!r.tradeable);assert(b.renderSelectionWorkflow(r).includes('Warum:'));
r=b.selectionWorkflow([p],{...context,direction:'NEUTRAL'},{});assert.equal(r.stage,'ABWARTEN');assert.equal(r.groups.length,0);
r=b.selectionWorkflow([{...p,snapshot:null}],context,{});assert.equal(r.requests.length,1);assert.equal(r.groups.length,0);assert(b.renderSelectionWorkflow(r).includes('Detailbilder ergänzen'));
assert(b.isFutureProduct({name:'SG Gold Future Turbo Put'}));
r=b.selectionWorkflow([{...p,name:'SG Gold Future Faktor Long',productDirection:'LONG'}],{...context,direction:'LONG'},{});assert.equal(r.groups.length,0);assert(r.waiting[0].reason.includes('Faktorprodukt'));
// A Future never enters a Spot ranking from a fresh screenshot alone.
r=b.selectionWorkflow([{...p,name:'SG Gold Future Turbo Put'}],context,{});assert.equal(r.groups.length,0);assert(r.requests[0].reasons.some(x=>x.includes('Future')));
console.log('selection flow: timestamps, identity, ranking, NEUTRAL and Future boundaries passed');

const at=sec=>new Date(now+sec*1000).toISOString();
const f={...p,isin:'DE000FG309G0',name:'SG Gold Future Turbo Put',ko:4500};
f.snapshot={...p.snapshot,isin:f.isin,evidence:{...p.snapshot.evidence,KO:{source:'quote.jpg',value:4500,at:at(0)}}};
f.snapshot.terms=terms({ratio:.1,strike:4500,underlying:'Gold Future Dec 2026',contract:'GCZ26',type:'Turbo',maturity:'Open End',currency:'EUR',quanto:'Nein'});
f.quote={isin:f.isin,productVerified:true,metadata:{underlyingType:'FUTURE',contract:'GCZ26'},futureResearch:{contract:'GCZ26',direction:'SHORT',marketOpen:true,tradingEndAt:at(3600),bidAt:at(-1000),askAt:at(-1000),bid:0,ask:0,fxDataAt:at(0),fxEffectiveAt:at(0),ko:4500,strike:4500,ratio:.1,usdEur:.88,calculatedFuture:{available:true,contract:'GCZ26',priceUsd:4000,comparisonErrorUsd:2,priceAt:at(0),referenceAt:at(-900),proxySource:'Gold-API Spot (Berechnung)',validation:{ready:true,sampleCount:21,maxAbsoluteError:2}},contractAnalysis:{available:true,contract:'GCZ26',direction:'SHORT',technicalSourceFamilies:1,checkedAt:at(0),expiresAt:at(180),rsi:40,macdHistogram:-1,atr:20,frames:{'5m':{available:true,ema20:4010},'15m':{available:true},'1h':{available:true,trend:'SHORT',ema50:4020,ema200:4050},'4h':{available:true}}}}};
const fc=b.conditionalCandidate(f,context,now);assert(fc.ok,fc.reason);assert(fc.priceKind.includes('DEGIRO'));assert.equal(fc.price,20.01);
r=b.selectionWorkflow([f,p],context,{});assert.equal(r.groups.length,2);assert(r.groups.some(g=>g.scope==='GCZ26 · SHORT'));
f.quote.futureResearch.calculatedFuture.validation.ready=false;
r=b.selectionWorkflow([f],context,{});assert.equal(r.groups.length,0);assert(r.waiting[0].reason.includes('Genauigkeit'));
console.log('validated Future + screenshot path works without SG bid/ask; unvalidated estimate blocked');

assert(!b.selectionDetailStatus({...p,snapshot:{...p.snapshot,times:{bid:{present:true,text:"02/10/2026 21:25"}}}},now).complete);
assert(!b.selectionDetailStatus({...p,snapshot:{...p.snapshot,times:{leverage:{present:true,text:"invalid"}}}},now).complete);

// End-to-end text processing: two images, one ISIN, independent clocks.
const details=isin+'\nSHORT\nKO 4460\nKO-Zeit: 02/10/2026 21:00:00 CEST\nBezugsverhältnis: 0,100\nBasispreis: 4.460,00 USD\nBasiswert: XAU/USD\nProdukttyp: Turbo\nLaufzeit: Open End\nProduktwährung: EUR\nQuanto: Nein\nProduktdatenstand: 02/10/2026 21:00:00 CEST';
const quote=isin+'\nSHORT\nEUR\nGeld 20,00\nBrief 20,01\nHebel 15\nKurszeit: 02/10/2026 21:22:00 CEST';
const detailData=b.detailScreenshotData(details,isin),quoteData=b.detailScreenshotData(quote,isin);
assert(detailData.ok,detailData.reason);assert(quoteData.ok,quoteData.reason);
const imageSnapshot=b.mergeScreenshotEvidence(b.mergeScreenshotEvidence(null,quoteData,'quote.jpg'),detailData,'details.jpg');
const imageProduct={...p,snapshot:imageSnapshot};
assert.equal(imageSnapshot.terms.ratio.value,.1);assert.equal(imageSnapshot.terms.strike.value,4460);
assert.equal(imageSnapshot.times.quote.at,quoteData.times.quote.at);
assert.equal(imageSnapshot.evidence.Geld.at,quoteData.times.quote.at);
assert.equal(imageSnapshot.evidence.Geld.source,'quote.jpg');
assert(b.finalProductStatus(imageProduct,now).complete,JSON.stringify(b.finalProductStatus(imageProduct,now)));
assert.equal(b.selectionWorkflow([imageProduct],context,{}).groups.length,1);
const reverse=b.mergeScreenshotEvidence(b.mergeScreenshotEvidence(null,detailData,'details.jpg'),quoteData,'quote.jpg');
assert.deepEqual(JSON.parse(JSON.stringify(reverse.terms)),JSON.parse(JSON.stringify(imageSnapshot.terms)));
for(const key of ['ratio','strike','underlying','type','maturity','currency']){
 const bad=JSON.parse(JSON.stringify(imageProduct));delete bad.snapshot.terms[key];
 assert(!b.finalProductStatus(bad,now).complete,key);
 assert.equal(b.selectionWorkflow([bad],context,{}).groups.length,0,key);
}
for(const mutate of [
 x=>x.snapshot.terms.ratio.at='2026-10-01T19:22:29Z',
 x=>x.snapshot.terms.strike.at='2026-10-02T19:23:00Z',
 x=>x.snapshot.terms.underlying.value='Gold',
 x=>x.snapshot.terms.type.value='Faktor',
 x=>x.snapshot.terms.maturity.value='01/10/2026 20:00:00 CEST',
 x=>x.snapshot.direction='LONG',
 x=>x.snapshot.evidence.KO.at=null,
 x=>x.isinConfirmed=false,
 x=>x.snapshot.isin='DE000FG309G0',
 x=>x.snapshot.times.quote={present:true,text:'02/10/2026 07:20:00 CEST'},
 x=>x.snapshot.delayed=true
]){const bad=JSON.parse(JSON.stringify(imageProduct));mutate(bad);assert(!b.finalProductStatus(bad,now).complete);assert.equal(b.selectionWorkflow([bad],context,{}).groups.length,0);}
assert(!b.detailScreenshotData(details.replace(isin,'DE000FG309G0'),isin).ok);
assert(!b.detailScreenshotData(details+'\nDE000FG309G0',isin).ok);
assert(!b.detailScreenshotData(details+'\nLONG',isin).ok);
assert(!b.detailScreenshotData(details+'\nBezugsverhältnis: 0,01',isin).ok);
assert(!b.detailScreenshotData(details.replace('0,100','0'),isin).ok);
const noQuoteTime=b.detailScreenshotData(quote.replace(/Kurszeit:.*/,'')+'\nProduktdatenstand: 02/10/2026 21:22:00 CEST',isin);
assert.equal(noQuoteTime.sourceTime,'');
const noTime=b.mergeScreenshotEvidence(imageSnapshot,noQuoteTime,'undated-quote.jpg');
assert.equal(noTime.evidence.Geld.at,null);assert(!noTime.times.quote.at);
assert(!b.finalProductStatus({...p,snapshot:noTime},now).complete);
const other=b.mergeScreenshotEvidence(imageSnapshot,{isin:'DE000FG309G0',ko:'4500'},'other.jpg');
assert(!other.terms.ratio);assert(!other.evidence.Geld);
const update=b.detailScreenshotData(quote.replace('20,00','21,00').replace('20,01','21,01').replace('21:22:00','21:22:20'),isin);
const updated=b.mergeScreenshotEvidence(imageSnapshot,update,'new-quote.jpg');
assert.equal(updated.bid,21);assert.equal(updated.ask,21.01);assert.equal(updated.evidence.Geld.at,'2026-10-02T19:22:20.000Z');
assert.equal(updated.terms.strike.at,imageSnapshot.terms.strike.at);
const missingFuture=JSON.parse(JSON.stringify(f));delete missingFuture.snapshot.terms.contract;
assert(!b.productTermsStatus(missingFuture,now).complete);
const wrongFuture=JSON.parse(JSON.stringify(f));wrongFuture.snapshot.terms.contract.value='GCG27';
assert(!b.productTermsStatus(wrongFuture,now).complete);
// A reviewed old manual quote cannot use a fresh derived estimate to enter the final list.
const incomplete={...p,snapshot:{...p.snapshot,terms:{}}};
const oldRef={isin,reviewed:true,paired:true,source:'DEGIRO',venue:'SG',bid:20,ask:20.01,quoteAt:new Date(now-100000).toISOString()};
assert(!b.finalProductStatus({...imageProduct,snapshot:{...imageSnapshot,times:{quote:{present:true,text:'02/10/2026 07:00:00 CEST'}}}},now,oldRef).complete);
assert.equal(b.selectionWorkflow([incomplete],context,{},[oldRef]).groups.length,0);
console.log('Product completeness, exact contract, independent image clocks and final-ranking gates passed');
assert(!b.parseProductTerms(details+'\nBedingungenstand: 01/10/2026 21:00:00 CEST').ratio);
assert(b.parseProductTerms(details+'\nBedingungenstand: 01/10/2026 21:00:00 CEST').error);
assert.equal(b.selectionWorkflow([imageProduct,{...imageProduct,ko:4450}],context,{}).groups.length,0);
const wrongRatio=JSON.parse(JSON.stringify(f));wrongRatio.snapshot.terms.ratio.value=.01;
assert(!b.productTermsStatus(wrongRatio,now).complete);
// DEGIRO's two-column overview has unrelated EUR figures below the quote row.
const overview=isin+'\nGeld € 6,05 Brief € 6,06\nGeld Vol. 25K Brief Vol. 25K\nEröffnung € 10,25 Schluss € 9,485\nHoch € 13,71 12M High —\nTief € 4,92 12M Low —\nBörse Societe Generale OTC\nPosition € 6,07\nBreak-Even Preis € 5,95';
const overviewData=b.detailScreenshotData(overview,isin);
assert(overviewData.ok,overviewData.reason);assert.equal(overviewData.bid,6.05);assert.equal(overviewData.ask,6.06);
assert.equal(overviewData.sourceTime,'');assert.equal(overviewData.times.quote.at,null);
assert(!b.detailScreenshotData(overview+'\nGeld € 6,04\nBrief € 6,07',isin).ok);
// Reviewed BNP identity: I/1 -> 9 is permitted only for this exact product context.
const bnpLine='BNP GOLD Unlimited Long SL 3980.6468 STR\n3980.6468 R 10 | DEOOOPJINCKO\nBNP OTC\nEUR';
const bnp=b.parseScreenshotCandidates(bnpLine)[0];
assert.equal(bnp.isin,'DE000PJ9NCK0');assert.equal(bnp.direction,'LONG');assert(bnp.identityCorrection);assert.equal(bnp.originalIsin,'DEOOOPJINCKO');
assert(b.validIsin(bnp.isin));
assert.equal(b.parseScreenshotCandidates(bnpLine.replace('DEOOOPJINCKO','DE000PJ1NCK0'))[0].isin,bnp.isin);
for(const text of [bnpLine.replace('BNP','SG'),bnpLine.replace('Unlimited Long','Unlimited Short'),bnpLine.replace('GOLD','DAX'),bnpLine.replace('Unlimited Long','Faktor Long'),bnpLine.replace('PJINCKO','PJINCK1')])assert.notEqual(b.parseScreenshotCandidates(text)[0].isin,bnp.isin);
const mixed=b.parseScreenshotCandidates(bnpLine+'\nSG Gold Turbo Short\nDE000FG4JXV7');assert.equal(mixed.length,2);assert.equal(mixed[0].isin,bnp.isin);assert.equal(mixed[1].direction,'SHORT');
assert.equal(b.parseScreenshotCandidates(bnpLine+'\n'+bnpLine.replace('DEOOOPJINCKO',bnp.isin)).length,1);
assert(!b.finalProductStatus({isin:bnp.isin,name:bnp.name,productDirection:bnp.direction,isinConfirmed:true},now).complete);

// Point 5: an empty or short selection is intentional, never padded.
const copies=['DE000FG4JXV7','DE000FC1CHB7','DE000PJ9NCK0'].map(id=>{
 const x=JSON.parse(JSON.stringify(imageProduct));x.isin=id;x.snapshot.isin=id;x.snapshot.evidence.KO.at=new Date(now).toISOString();return x;
});
for(let count=0;count<=3;count++){
 const result=b.selectionWorkflow(copies.slice(0,count),context,{});
 assert.equal(result.approvedCount,count);assert.equal(result.approved,count>0);
 assert.equal(result.groups.flatMap(g=>g.candidates).length,count);
 const html=b.renderSelectionWorkflow(result);
 assert.equal((html.match(/<b>Platz /g)||[]).length,count);
 assert(html.includes(count?'Zur Produktauswahl freigegeben':'Abwarten – derzeit kein geeignetes Produkt'));
 assert(!html.includes('Begründete Top 3'));
}
for(const change of [
 {direction:'NEUTRAL'}, {direction:''}, {mtf:'NEUTRAL'}, {mtf:'LONG'},
 {trend:'LONG'}, {trend2:'LONG'}, {hist:1}, {momentum:1},
 {hist:null},{hist:''},{momentum:0},{atr:null},{trend:undefined},
 {mtf:'LONG / SHORT'}, {spotFresh:false}
]){
 const result=b.selectionWorkflow(copies,{...context,...change},{});
 assert.equal(result.approvedCount,0,JSON.stringify(change));
 assert(b.renderSelectionWorkflow(result).includes('Abwarten – derzeit kein geeignetes Produkt'));
 assert(result.gateReasons.length||result.waiting.length||result.requests.length);
}
const blocked=JSON.parse(JSON.stringify(copies[0]));blocked.snapshot.terms.type.value='Faktor';
assert.equal(b.selectionWorkflow([blocked,...copies.slice(1)],context,{}).approvedCount,2);
const expired=b.selectionWorkflow(copies,{...context,now:now+14*3600000+1},{});
assert.equal(expired.approvedCount,0);assert(expired.requests.every(x=>x.reasons.some(y=>/Kurs|Zeit|Hebel/.test(y))));
const tight=JSON.parse(JSON.stringify(copies[0]));tight.ko=4141;tight.snapshot.evidence.KO.value=4141;
assert.equal(b.selectionWorkflow([tight],context,{}).approvedCount,0);
assert(b.renderSelectionWorkflow(b.selectionWorkflow([tight],context,{})).includes('KO'));
const futureOk=JSON.parse(JSON.stringify(f));futureOk.quote.futureResearch.calculatedFuture.validation.ready=true;
assert.equal(b.selectionWorkflow([futureOk],context,{}).approvedCount,1);
for(const change of [
 x=>x.quote.futureResearch.contractAnalysis.frames['15m'].direction='LONG',
 x=>x.quote.futureResearch.contractAnalysis.direction='NEUTRAL',
 x=>x.quote.futureResearch.calculatedFuture.contract='GCG27',
 x=>x.quote.futureResearch.calculatedFuture.comparisonErrorUsd=170,
 x=>x.quote.futureResearch.calculatedFuture.validation.ready=false,
 x=>x.quote.futureResearch.calculatedFuture.priceAt=at(-61)
]){const x=JSON.parse(JSON.stringify(futureOk));change(x);const result=b.selectionWorkflow([x],context,{});assert.equal(result.approvedCount,0);assert(result.waiting.length||result.requests.length);}
const mix=b.selectionWorkflow([...copies,futureOk],context,{});assert.equal(mix.approvedCount,3);
console.log('No forced Top 3: 0/1/2/3, mixed blocked products, neutral/conflicting signals, expiration, KO and Future uncertainty passed');

// Production markup has an MTF legend with LONG, SHORT and NEUTRAL simultaneously.
for(const direction of ['LONG','SHORT','NEUTRAL']){
 const doc={getElementById:id=>({textContent:{blockMtf:direction,blockMomentum:direction,mtfSummary:direction+' 4 LONG · 0 SHORT · 0 NEUTRAL'}[id]})};
 const ui=b.selectionUiSignals(doc);
 assert.equal(ui.mtf,direction);assert.equal(ui.momentum,direction==='LONG'?1:direction==='SHORT'?-1:0);
 const result=b.selectionMarketGate({...context,direction,trend:direction,trend2:direction,hist:ui.momentum,...ui});
 assert.equal(result.ok,direction!=='NEUTRAL');
}
assert.equal(b.selectionUiSignals({getElementById:()=>null}).momentum,0);
assert(!b.evaluateProduct({...context,...copies[0],name:'Gold Faktor Short',spot:context.spot}).ok);
assert(!b.evaluateProduct({...context,...copies[0],name:'Gold Future Turbo Short',spot:context.spot}).ok);
// Every non-selected product remains visible with an explicit status and reason.
for(const c of [context,{...context,direction:'NEUTRAL'}, {...context,now:now+14*3600000+1}]){
 const products=[...copies,futureOk];const result=b.selectionWorkflow(products,c,{});
 const selected=new Set(result.groups.flatMap(g=>g.candidates).map(p=>p.isin));
 assert.equal(result.notApproved.length,products.length-selected.size);
 const html=b.renderSelectionWorkflow(result);
 for(const p of result.notApproved){assert(!selected.has(p.isin));assert(p.reasons.length);assert(html.includes(p.isin));}
 assert.equal((html.match(/<strong>Nicht freigegeben<\/strong>/g)||[]).length,result.notApproved.length);
 assert.equal((html.match(/Begründung:/g)||[]).length,result.notApproved.length);
}
const allBlocked=b.selectionWorkflow([...copies,futureOk],{...context,direction:'NEUTRAL'},{});
assert.equal(allBlocked.notApproved.length,4);assert(b.renderSelectionWorkflow(allBlocked).includes('data-selection-blocked="4"'));
const unidentified=b.selectionWorkflow([{name:'<unsicheres Produkt>'}],context,{});
assert.equal(unidentified.notApproved.length,1);assert(b.renderSelectionWorkflow(unidentified).includes('&lt;unsicheres Produkt&gt;'));assert(b.renderSelectionWorkflow(unidentified).includes('ISIN fehlt'));

// Push verification reruns the same evidence checks on the server and ignores
// client claims about approval. It also accounts for time spent in delivery.
const verifyPush=require('./selection_push_evaluator').evaluate;
const pushInput=products=>({products,context,capturedAt:now,bundle:{fetched_at:now/1000,spots:{xaus:4140,xaus_age_seconds:0},history:{data_state:{status:'fresh'}}}});
for(let count=0;count<=3;count++){
 const verified=verifyPush({...pushInput(copies.slice(0,count)),approved:true},now);
 assert.equal(verified.products.length,count);
 assert(verified.expiresAt<=now+30000);
}
for(const change of [{direction:'NEUTRAL'},{mtf:'LONG'},{trend2:'LONG'},{momentum:0},{atr:null}])assert.equal(verifyPush({...pushInput(copies),context:{...context,...change}},now).products.length,0);
for(const bad of [blocked,tight,{...copies[0],snapshot:null}])assert.equal(verifyPush(pushInput([bad]),now).products.length,0);
assert.equal(verifyPush(pushInput([futureOk]),now).products.length,1);
for(const mutate of [
 x=>x.quote.futureResearch.calculatedFuture.contract='GCG27',
 x=>x.quote.futureResearch.calculatedFuture.comparisonErrorUsd=170,
 x=>x.quote.futureResearch.calculatedFuture.validation.ready=false
]){const bad=JSON.parse(JSON.stringify(futureOk));mutate(bad);assert.equal(verifyPush(pushInput([bad]),now).products.length,0);}
assert.throws(()=>verifyPush({...pushInput(copies),capturedAt:now-16000},now),/veraltet/);
assert.equal(verifyPush({...pushInput(copies),bundle:{fetched_at:now/1000-61,spots:{xaus:4140,xaus_age_seconds:0},history:{data_state:{status:'fresh'}}}},now).products.length,0);
const nearExpiry=pushInput(copies);nearExpiry.bundle.spots.xaus_age_seconds=59;
assert.equal(verifyPush(nearExpiry,now).products.length,0);
console.log('Server push evaluator: 0/1/2/3, expiry, conflicting signals, mandatory evidence, contracts and uncertainty passed');


// Fixed product conditions are separate from daily KO/strike and quote evidence.
const researchNow=Date.parse('2026-10-05T08:00:00Z');
const researched=b.applyResearchedTerms([{isin:'DE000FG5GUT0',direction:'LONG'}])[0];
assert.equal(researched.snapshot.terms.ratio.value,.1);assert.equal(researched.snapshot.terms.underlying.value,'XAU/USD');assert.equal(researched.snapshot.terms.quanto.value,'Nein');
assert.equal(researched.snapshot.terms.ratio.at,null);assert(b.durableCondition(researched.snapshot.terms.ratio,'ratio',researchNow));
assert(!b.durableCondition(researched.snapshot.terms.ratio,'strike',researchNow));assert(!b.durableCondition(researched.snapshot.terms.ratio,'contract',researchNow));
assert(!b.durableCondition({...researched.snapshot.terms.ratio,revoked:true},'ratio',researchNow));assert(!b.durableCondition({...researched.snapshot.terms.ratio,reviewedAt:'2027-01-01T00:00:00Z'},'ratio',researchNow));
const checked=b.productTermsStatus({...researched,productDirection:'LONG',isinConfirmed:true},researchNow);
assert.equal(checked.values.ratio,.1);assert(!checked.complete);assert(checked.reasons.some(x=>x.includes('Basispreis')));assert(checked.reasons.some(x=>x.includes('Knock-out')));
assert.equal(b.applyResearchedTerms([{isin:'DE000FG309G0',direction:'SHORT'}])[0].snapshot,undefined);
assert.equal(b.applyResearchedTerms([{isin:'DE000FG5GUT0',direction:'SHORT'}])[0].snapshot,undefined);
const custom={...researched,snapshot:{...researched.snapshot,terms:{ratio:{value:.01,at:'2026-10-05T08:00:00Z',source:'new.jpg'}}}};
assert.equal(b.applyResearchedTerms([custom])[0].snapshot.terms.ratio.value,.01);
assert(b.durableCondition({value:'EUR',source:'list.jpg',reviewed:true},'currency',researchNow));
assert(!b.durableCondition({value:4460,source:'list.jpg',reviewed:true},'strike',researchNow));
assert.equal(b.maturityDeadline('18/12/2026'),Date.parse('2026-12-17T23:00:00Z'));assert.equal(b.maturityDeadline('31/02/2026'),null);
console.log('Researched conditions, no invented quote clocks/contracts, no overwrite, and conservative date-only maturity: OK');


// Contract guidance must remain visible when market direction prevents selection.
for(const direction of ['NEUTRAL','LONG']){
 const missing={...f,snapshot:{...f.snapshot,terms:{...f.snapshot.terms,contract:undefined}}};
 const result=b.selectionWorkflow([missing,p],{...context,direction},{});
 assert(result.notApproved.find(x=>x.isin===f.isin).reasons.some(x=>x.includes('Produktdetails → Dokumente')));
 assert(b.renderSelectionWorkflow(result).includes('Referenzkontrakt / Futures Contract'));
 assert(!result.notApproved.find(x=>x.isin===p.isin)?.reasons.some(x=>x.includes('Produktdetails → Dokumente')));
 assert(!result.groups.some(g=>g.candidates.some(x=>x.isin===f.isin)));
}
const confirmed=b.selectionWorkflow([f],{...context,direction:'NEUTRAL'},{});
assert(!confirmed.notApproved[0].reasons.some(x=>x.startsWith('Exakter Gold-Future-Kontrakt fehlt')));


// Missing evidence stays collapsed and separate from market reasons.
const folded=b.selectionWorkflow([{...f,snapshot:null}],{...context,direction:'NEUTRAL'},{});
const foldedHtml=b.renderSelectionWorkflow(folded);
assert(folded.notApproved[0].missingReasons.some(x=>x.includes('Bezugsverhältnis')));
assert(foldedHtml.includes('<strong>Fehlende Werte</strong>'));
assert(foldedHtml.includes('Screenshot auf der SG-Produktseite:'));
assert(!foldedHtml.includes('DEGIRO →'));
assert(foldedHtml.includes('Stammdaten:')); 
assert(!/<details[^>]*data-missing-values[^>]*\\bopen\\b/.test(foldedHtml));
const beforeFold=foldedHtml.slice(0,foldedHtml.indexOf('data-missing-values'));
assert(beforeFold.includes('Marktsignal neutral'));
assert(!beforeFold.includes('Referenzkontrakt / Futures Contract'));
assert(!beforeFold.includes('Exakter Gold-Future-Kontrakt fehlt'));
const completeFold=b.renderSelectionWorkflow(b.selectionWorkflow([p],{...context,direction:'NEUTRAL'},{}));
assert(!completeFold.includes('data-missing-values'));

for(const value of [undefined,'Ja','Nein','unbekannt']){const x=JSON.parse(JSON.stringify(imageProduct));if(value===undefined)delete x.snapshot.terms.quanto;else x.snapshot.terms.quanto.value=value;assert(b.finalProductStatus(x,now).complete);}

const explanation=b.renderProductDecision({direction:'LONG',score:78,reasons:['Risiko: KO 2.50%'],warnings:['Kurszeit fehlt oder ist veraltet','<img src=x>']});
for(const text of ['Warum ausgewählt?','Was spricht dagegen','Wann entfällt','KO 2.50%','Kurszeit fehlt','1,5 ATR','&lt;img'])assert(explanation.includes(text));
assert(!explanation.includes('<img'));
assert(b.renderProductDecision({},false,['Marktsignal neutral']).includes('Marktsignal neutral'));
console.log('Decision explanations preserve evaluation warnings and escape external text');

// User original 1000070469: tightly scoped recovery, never infer all I/1 as 9.
const nbLine='BNP GOLD Unlimited Long SL 3996.2705 STR\n3996.2705 R 10 | DEOOOPJINB98\nBNP OTC\nEUR';
const nb=b.parseScreenshotCandidates(nbLine)[0];
assert.equal(nb.isin,'DE000PJ9NB98');assert.equal(nb.direction,'LONG');assert.equal(nb.ko,3996.2705);
assert(nb.identityCorrection);assert(b.validIsin(nb.isin));
assert.equal(b.parseScreenshotCandidates(nbLine.replace('DEOOOPJINB98','DE000PJ1NB98'))[0].isin,nb.isin);
for(const bad of [nbLine.replace('BNP','SG'),nbLine.replace('Long','Short'),nbLine.replace('GOLD','DAX'),nbLine.replace('3996.2705','3995.2705'),nbLine.replace('R 10','R 100'),nbLine.replace('PJINB98','PJINB99')]){
 assert.notEqual(b.parseScreenshotCandidates(bad)[0].isin,nb.isin);
}
assert.notEqual(b.normalizeOcrIsin('DEOOOPJINB98').isin,nb.isin);
assert(!b.finalProductStatus({isin:nb.isin,name:nb.name,productDirection:nb.direction,isinConfirmed:true},now).complete);
console.log('Original-image BNP NB98 identity recovery and negative contexts passed');

// Intraday shadow does not inherit the slow EMA50/200 veto; live policy retains it.
{
 const fs=require('fs'),vm=require('vm');const ctx={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
 const api=ctx.window.BobDegiro,c={direction:'LONG',trend:'LONG',trend2:'SHORT',mtf:'LONG',hist:1,momentum:1,rsi:60,atr:2};
 assert(!api.selectionMarketGate(c).ok);
 assert(api.selectionMarketGate({...c,policy:'intraday-shadow-v1'}).ok);
 assert(api.technicalQuality({...c,policy:'intraday-shadow-v1'}).score>api.technicalQuality(c).score);
 assert(!api.selectionMarketGate({...c,policy:'intraday-shadow-v1',hist:-1}).ok);
 console.log('Intraday shadow: remove EMA200 veto only; keep live veto and MACD checks');
}

// DOM fixture: repeated refresh, changed counts, reordering and user-closing sections.
{
 const fs=require('fs'),vm=require('vm'),ctx={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
 let nodes=[],writes=0;
 const root={querySelectorAll:()=>nodes,contains:el=>nodes.some(n=>n.summary===el),set innerHTML(value){writes++;nodes=make(value==='first'?['A','B']:['B','A'],value==='first'?2:3);}};
 function make(ids,count){return ids.flatMap(id=>{const card={tagName:'DIV',parentElement:root,getAttribute:()=>id};const outer={tagName:'DETAILS',parentElement:card,open:false,closest:()=>card};outer.summary={tagName:'SUMMARY',textContent:'Quellen und Einzelheiten',parentElement:outer,focus(){ctx.document.activeElement=this;}};outer.querySelector=()=>outer.summary;const inner={tagName:'DETAILS',parentElement:outer,open:false,closest:()=>card};inner.summary={tagName:'SUMMARY',textContent:'Fehlende Werte ('+count+')',parentElement:inner,focus(){ctx.document.activeElement=this;}};inner.querySelector=()=>inner.summary;return [outer,inner];});}
 const api=ctx.window.BobDegiro;ctx.document={activeElement:null};api.updateProductHtml(root,'first');nodes[0].open=true;nodes[1].open=true;ctx.document.activeElement=nodes[1].summary;
 api.updateProductHtml(root,'second');assert(nodes[2].open&&nodes[3].open);assert(!nodes[0].open&&!nodes[1].open);assert.equal(ctx.document.activeElement,nodes[3].summary);
 assert.equal(api.updateProductHtml(root,'second'),false);assert.equal(writes,2);
 nodes[3].open=false;api.updateProductHtml(root,'third');assert(nodes[2].open);assert(!nodes[3].open);
 console.log('Product disclosure state: nested sections, ISIN reorder, count changes, explicit closing and unchanged-refresh focus preserved');
}

// BNP screenshots 1000070543 / 1000070545: issuer badge and browser title.
const bnpBadge='BNP PARIBAS CERTIFICATE\nGOLD Unlimited Long | 3.996,2705 USD\nPJ9NB9\nMarkt geöffnet\nVerkaufen\n€ 12,06\n8.000 Stück\nKaufen\n€ 12,07\n8.000 Stück';
const bnpRead=b.detailScreenshotData(bnpBadge,'DE000PJ9NB98');
assert(bnpRead.ok);assert.equal(bnpRead.identityBasis,'WKN');
assert.equal(bnpRead.bid,12.06);assert.equal(bnpRead.ask,12.07);
assert(!bnpRead.sourceTime,'Do not invent source time from phone clock or another image');
const bnpTitle='PJ9NB9 12,08 / 12,09 €\nderivate.bnpparibas.com\nBNP PARIBAS\nHebel 30,53\nÄhnliche Produkte\nAktuelles Produkt\nBasispreis 3.996,27\nKnock-Out Schwelle 3.996,27';
assert(b.detailScreenshotData(bnpTitle,'DE000PJ9NB98').reason.includes('eindeutig angeben'));
assert(b.detailScreenshotData(bnpTitle.replaceAll('3.996,27','3.996,27 USD'),'DE000PJ9NB98').ok);
for(const raw of [bnpBadge.replace('PJ9NB9','PJ9NCK'),bnpBadge+'\nPJ9NCK',bnpBadge.replace('BNP PARIBAS','Other issuer'),bnpBadge.replace('PJ9NB9','XPJ9NB9X'),bnpBadge.replace('PJ9NB9','')+'\nÄhnliche Produkte\nPJ9NB9'])assert(!b.detailScreenshotData(raw,'DE000PJ9NB98').ok);
console.log('BNP unlabeled WKN recognition, quote labels and identity rejection passed');

// BNP mobile table: date before amount and WKN badge beside market status.
const pg='DE000PG0XK25';
const pgQuote=bnpBadge.replace('PJ9NB9\nMarkt geöffnet','PG0XK2 ▣ ● Markt geöffnet').replace('3.996,2705','3.455,4922').replace('12,06','60,51').replace('12,07','60,52');
assert(b.detailScreenshotData(pgQuote,pg).ok);
assert.equal(b.detailScreenshotData(pgQuote,pg).bid,60.51);
const pgTerms='BNP PARIBAS\nStammdaten\nKnock-Out Schwelle\n(05.10.2026) 3.455,4922 USD\nBasispreis\n(05.10.2026)\n3.455,4922 USD\nBezugsverhältnis\n0,1\nLaufzeit\nOpen End\nWKN PG0XK2\nISIN DE000PG0XK25';
const pgResult=b.detailScreenshotData(pgTerms,pg);
assert(pgResult.ok,pgResult.reason);assert.equal(pgResult.terms.strike.value,3455.4922);assert.equal(pgResult.terms.ko.value,3455.4922);assert.equal(pgResult.terms.strike.dateText,'05.10.2026');assert.equal(pgResult.terms.ratio.value,.1);
assert(!b.detailScreenshotData(pgTerms,'DE000PJ9NB98').ok);
assert(!b.detailScreenshotData('BNP PARIBAS\nHebel 6,09\nÄhnliche Produkte\nAktuelles Produkt\nBasispreis 3.455,49',pg).ok);
console.log('BNP dated mobile table and inline WKN badge regressions passed');

const bnpUnderlying='PJ9NB9 11,99 / 12,00 €\nderivate.bnpparibas.com\nBasiswert\nBasiswert GOLD\nISIN USFX00000XAU\nWährung des Basiswertes USD';
assert(b.detailScreenshotData(bnpUnderlying,'DE000PJ9NB98').ok);
assert(!b.detailScreenshotData(bnpUnderlying.replace('PJ9NB9','PJ9NCK'),'DE000PJ9NB98').ok);
assert(!b.detailScreenshotData(bnpUnderlying+'\nISIN DE000PG0XK25','DE000PJ9NB98').ok);
assert(!b.detailScreenshotData(bnpUnderlying.replace('PJ9NB9','PJINBY'),'DE000PJ9NB98').ok);
console.log('BNP underlying identity scoped separately; ambiguous OCR remains blocked');

const actualBnpOcr="19:19 BG KP\nderivate.bnpparibas.com\nStammdaten\nKnock-Out Schwelle\n(05.10.2026) 3.996,2705 USD\nQ\nBasispreis\n(05.10.2026) 3.996,2705 USD\nBezugsverhaltnis 0,1\nLaufzeit & Open End\nReferenzzins SOFR\neat passungssatz 4,00 %\nWKN PJSNB9\nISIN DEOOOPJSNB98\nTyp Unlimited Long\nStuttoart. Frankfurt.\n-_\nRisikowarnung gem? ; \u2018 Bafin-Allgemeinv...\nIII O <\n";
const actualRead=b.detailScreenshotData(actualBnpOcr,'DE000PJ9NB98');
assert(actualRead.ok);assert.equal(actualRead.terms.strike.value,3996.2705);assert.equal(actualRead.terms.ko.value,3996.2705);assert.equal(actualRead.terms.ratio.value,.1);assert.equal(actualRead.terms.maturity.value,'Open End');assert.equal(actualRead.terms.type.value,'Unlimited Long');
for(const changed of [actualBnpOcr.replace('derivate.bnpparibas.com','other.com'),actualBnpOcr.replace('PJSNB9','PJSNC9'),actualBnpOcr.replace('3.996,2705','3.995,2705'),actualBnpOcr.replace('Unlimited Long','Unlimited Short')])assert(!b.detailScreenshotData(changed,'DE000PJ9NB98').ok);
console.log('Original BNP image OCR: reviewed identity and terms pass; mismatched evidence rejected');

const browserEngineBnpOcr="19:19 B& LHI 4\nderivate.bnpparibas.com\nStammdaten\nKnock-Out Schwelle\n(05.10.2026) 3.996,2705 USD\no\nBasispreis\n(05.10.2026) 3.996,2705 USD\nBezugsverhaltnis 0,1\nLaufzeit @ Open End\nReferenzzins SOFR\nASA passungssatz 4,00 %\nWKN PJSNB9\nISIN DEOOOPJONB98\nTyp Unlimited Long\nStuttoart. Frankfurt.\n-\nRisikowarnung gem\u00e9  \u00b0Bafin-Allgemeinv...\n[I O <\n";
const browserRead=b.detailScreenshotData(browserEngineBnpOcr,'DE000PJ9NB98');
assert(browserRead.ok);assert.equal(browserRead.isin,'DE000PJ9NB98');assert.equal(browserRead.terms.strike.value,3996.2705);assert.equal(browserRead.terms.ratio.value,.1);assert.equal(browserRead.terms.maturity.value,'Open End');
assert(!b.detailScreenshotData(browserEngineBnpOcr.replace('3.996,2705','3.995,2705'),'DE000PJ9NB98').ok);
assert(!b.detailScreenshotData(browserEngineBnpOcr,'DE000PG0XK25').ok);
console.log('Tesseract.js 5.1.1 original image transcript: correct identity and terms');
