const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,isin='DE000FG4JXV7',now=Date.parse('2026-10-02T19:22:30Z');
const directSource=b.renderProductSources({isin,index:99,quote:{isin,productVerified:true,
 source:'BNP Paribas · offizielle Produktdaten',sourceUrl:'https://derivate.bnpparibas.com/',
 metadata:{termsDated:false},exchangeResearch:{productVerified:false,source:'comdirect failed'}}});
assert(directSource.includes('BNP Paribas'));assert(!directSource.includes('comdirect failed'));
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
r=b.selectionWorkflow([{...p,snapshot:null}],context,{});assert.equal(r.requests.length,1);assert.equal(r.groups.length,0);assert(b.renderSelectionWorkflow(r).includes('Bilder / PDF hinzufügen'));
assert(b.isFutureProduct({name:'SG Gold Future Turbo Put'}));
r=b.selectionWorkflow([{...p,name:'SG Gold Future Faktor Long',productDirection:'LONG'}],{...context,direction:'LONG'},{});assert.equal(r.groups.length,0);assert(r.waiting[0].reason.includes('Faktorprodukt'));
// A Future never enters a Spot ranking from a fresh screenshot alone.
r=b.selectionWorkflow([{...p,name:'SG Gold Future Turbo Put'}],context,{});assert.equal(r.groups.length,0);assert(r.requests[0].reasons.some(x=>x.includes('Future')));
console.log('selection flow: timestamps, identity, ranking, NEUTRAL and Future boundaries passed');

const at=sec=>new Date(now+sec*1000).toISOString();
const f={...p,isin:'DE000FG309G0',name:'SG Gold Future Turbo Put',ko:4500};
f.snapshot={...p.snapshot,isin:f.isin,evidence:{...p.snapshot.evidence,KO:{source:'quote.jpg',value:4500,at:at(0)}}};
f.snapshot.terms=terms({ratio:.1,strike:4500,underlying:'Gold Future Dec 2026',contract:'GCZ26',type:'Turbo',maturity:'Open End',currency:'EUR',quanto:'Nein'});
f.quote={isin:f.isin,productVerified:true,metadata:{underlyingType:'FUTURE',contract:'GCZ26'},futureResearch:{contract:'GCZ26',direction:'SHORT',marketOpen:true,tradingEndAt:at(3600),bidAt:at(-1000),askAt:at(-1000),bid:0,ask:0,fxDataAt:at(0),fxEffectiveAt:at(0),ko:4500,strike:4500,ratio:.1,usdEur:.88,calculatedFuture:{available:true,contract:'GCZ26',priceUsd:4000,comparisonErrorUsd:2,priceAt:at(0),referenceAt:at(-900),proxySource:'Gold-API Spot (Berechnung)',validation:{ready:true,sampleCount:21,maxAbsoluteError:2}},contractAnalysis:{available:true,contract:'GCZ26',direction:'SHORT',technicalSourceFamilies:1,checkedAt:at(0),expiresAt:at(180),rsi:40,macdHistogram:-1,atr:20,frames:{'5m':{available:true,ema20:4010},'15m':{available:true,trend:'SHORT'},'1h':{available:true,trend:'SHORT',ema50:4020,ema200:4050},'4h':{available:true}}}}};
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
 assert.equal((html.match(/data-selection-blocked=/g)||[]).length,result.notApproved.length);
 assert.equal((html.match(/<b>Aktuelle Auswahl:<\/b> nicht ausgewählt/g)||[]).length,result.notApproved.length);
 assert.equal((html.match(/Warum derzeit nicht ausgewählt\?/g)||[]).length,result.notApproved.length);
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
assert(foldedHtml.includes('Fundort auf der SG-Produktseite:'));
assert(!foldedHtml.includes('DEGIRO →'));
assert(foldedHtml.includes('Stammdaten:')); 
assert(!/<details[^>]*data-missing-values[^>]*\\bopen\\b/.test(foldedHtml));
const beforeFold=foldedHtml.slice(0,foldedHtml.indexOf('data-missing-values'));
assert(beforeFold.includes('Marktsignal neutral'));
assert(beforeFold.includes('Referenzkontrakt / Futures Contract')); // Location is now also in the compact missing-values disclosure.
assert(beforeFold.includes('Exakter Gold-Future-Kontrakt fehlt')); // Concrete blocker now visible by user request.
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
const partialBnpTitle=b.detailScreenshotData(bnpTitle,'DE000PJ9NB98');
assert(partialBnpTitle.ok);
assert(partialBnpTitle.importWarnings.some(reason=>reason.includes('eindeutig angeben')));
assert(!partialBnpTitle.terms.strike,'No USD strike may be inferred from a currency-less value');
assert.equal(partialBnpTitle.leverage,'30.53');
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

// Android 05.10-4 diagnostic from 1000070603: REFERENZZINS was incorrectly
// counted as a second ISIN; phone OCR read 9 as O in both labelled identifiers.
const androidBnpOcr=browserEngineBnpOcr.replace('Referenzzins','REFERENZZINS').replace('PJSNB9','PJONB9');
const androidRead=b.detailScreenshotData(androidBnpOcr,'DE000PJ9NB98');
assert(androidRead.ok,androidRead.reason);
assert.equal(androidRead.isin,'DE000PJ9NB98');
assert.equal(androidRead.terms.strike.value,3996.2705);
assert.equal(androidRead.terms.ko.value,3996.2705);
assert.equal(b.parseScreenshotCandidates(androidBnpOcr).length,1);
assert.equal(b.parseScreenshotCandidates('REFERENZZINS STAMMDATEN').length,0);
assert(!b.imageIdentityDiagnostic(androidBnpOcr).includes('REFERENZZINS'));
for(const changed of [androidBnpOcr+'\nISIN DE000PG0XK25',androidBnpOcr.replace('PJONB9','PJONC9'),androidBnpOcr.replace('3.996,2705','3.995,2705'),androidBnpOcr.replace('derivate.bnpparibas.com','other.com')])assert(!b.detailScreenshotData(changed,'DE000PJ9NB98').ok);
console.log('Android real failure: text labels excluded, reviewed 9/O identity and conflicting evidence checked');

// Original 1000070567 WASM text, with WKN independently read from its badge pixels.
const bnpQuoteOcr="19:18 BE \u00a9 N%.\u20ac\nderivate.bnpparibas.com\n\nBNP Paribas Zertifikate > Knockouts\n\n\u00a35 GOLD Unlimited\nLong | 3.996,2705\nusb\n\n(LE @ Markt gedffnet\n\nHandelszeiten!*) 08:00:00 - 22:00:00 - Knock-\nOut 00:00:00 - 24:00:00\n\n\u00a9 8B \u00a9 & OE\n=\n\nVerkaufen Kaufen\n\n\u20ac11,62 \u20ac11,63\n\n8.000 Stick 8.000 Stick\nAnderung Hebel GOLD\n\n-15,00 % 31,71 4.127,16 USD\n[1 O <\n\nWKN PJ9NB9";
const quote567=b.detailScreenshotData(bnpQuoteOcr,"DE000PJ9NB98");
assert(quote567.ok,quote567.reason);assert.equal(quote567.bid,11.62);assert.equal(quote567.ask,11.63);assert.equal(quote567.leverage,"31.71");assert.equal(quote567.sourceTime,"");
assert(!b.detailScreenshotData(bnpQuoteOcr.replace("PJ9NB9","PJ9NCK"),"DE000PJ9NB98").ok);
assert(!b.detailScreenshotData(bnpQuoteOcr.replace("€11,63","€11,61"),"DE000PJ9NB98").ok);
assert(!b.detailScreenshotData(bnpQuoteOcr+"\nISIN DE000PG0XK25","DE000PJ9NB98").ok);
assert.equal(b.bnpBadgeRect({text:"other issuer",words:[]}),null);
console.log("BNP original quote: side-by-side prices, badge identity, leverage and missing source time verified");

// Real Android upload order: dated BNP terms followed by its quote image.
const bnpNow=Date.parse('2026-10-05T18:54:00Z');
const bnpSnapshot=b.mergeScreenshotEvidence(b.mergeScreenshotEvidence(null,androidRead,'1000070573.jpg'),quote567,'1000070567.jpg');
const bnpProduct={isin:'DE000PJ9NB98',isinConfirmed:true,productDirection:'LONG',ko:3996.2705,price:11.63,leverage:31.71,snapshot:bnpSnapshot};
let bnpStatus=b.productTermsStatus(bnpProduct,bnpNow);
assert(!bnpStatus.reasons.some(r=>/Produkttyp|Basispreis|Knock-out/.test(r)),bnpStatus.reasons.join('; '));
assert(bnpStatus.reasons.some(r=>/Basiswert/.test(r)));
assert(!b.selectionDetailStatus(bnpProduct,bnpNow).reasons.some(r=>/KO-Barriere|Knock-out|Basispreis|Produkttyp/.test(r)));
assert(b.selectionDetailStatus(bnpProduct,bnpNow).reasons.some(r=>/Kurszeit/.test(r)));
assert.equal(bnpSnapshot.sourceTime,'');
assert.equal(bnpSnapshot.terms.strike.at,null);
assert.equal(bnpSnapshot.evidence.KO.at,null);
// Saved version-8 records are re-evaluated without upload or changing their clocks.
const stored=JSON.parse(JSON.stringify(bnpProduct));stored.snapshot.terms.type.automatic=false;
assert(!b.productTermsStatus(stored,bnpNow).reasons.some(r=>/Produkttyp/.test(r)));
for(const stamp of ['2026-10-04T21:59:59Z','2026-10-05T22:00:00Z']){
 const reasons=b.productTermsStatus(stored,Date.parse(stamp)).reasons;
 assert(reasons.some(r=>/Basispreis/.test(r)));assert(reasons.some(r=>/Knock-out/.test(r)));
}
for(const mutate of [p=>p.snapshot.terms.ko.dateText='31.02.2026',p=>p.snapshot.terms.ko.ocrCorrection='uncertain',p=>p.snapshot.terms.ko.conflict=true,p=>p.snapshot.identityBasis='',p=>p.snapshot.isin='DE000PG0XK25',p=>p.ko=3997]){
 const bad=JSON.parse(JSON.stringify(stored));mutate(bad);
 assert(b.productTermsStatus(bad,bnpNow).reasons.some(r=>/Knock-out/.test(r)));
}
const wrongDirection=JSON.parse(JSON.stringify(stored));wrongDirection.productDirection='SHORT';
assert(b.productTermsStatus(wrongDirection,bnpNow).reasons.some(r=>/Produktrichtung/.test(r)));
assert.equal(b.selectionWorkflow([bnpProduct],{...context,now:bnpNow,direction:'NEUTRAL'},{}).groups.length,0);
console.log('BNP dated terms survive actual two-image order and saved-state reload; midnight, direction, identity, missing quote time and neutral gates verified');

// New mobile original 1000070630: the browser address bar is collapsed, but
// the BNP PARIBAS masthead and the same labelled product evidence are visible.
const bnpBannerOcr=androidBnpOcr.replace('derivate.bnpparibas.com','BNP PARIBAS\nZERTIFIKATE');
for(const raw of [bnpBannerOcr,bnpBannerOcr.replaceAll('PJONB9','PJSNB9')]){
 const read=b.detailScreenshotData(raw,'DE000PJ9NB98');
 assert(read.ok,read.reason);assert.equal(read.isin,'DE000PJ9NB98');
 assert.equal(read.terms.ko.value,3996.2705);assert.equal(read.terms.type.value,'Unlimited Long');
 const old=JSON.parse(JSON.stringify(stored.snapshot));
 old.terms.type.automatic=false;
 assert(!b.screenshotSummary(old).includes('Produkttyp: Unlimited Long</b><div>Quelle: 1000070573.jpg</div><div>Wert eingelesen'));
}
for(const raw of [bnpBannerOcr.replace('BNP PARIBAS','OTHER ISSUER'),bnpBannerOcr.replace('PJONB9','PJONC9'),bnpBannerOcr.replace('3.996,2705','3.995,2705'),bnpBannerOcr.replace('Unlimited Long','Unlimited Short'),bnpBannerOcr+'\nISIN DE000PG0XK25']){
 assert(!b.detailScreenshotData(raw,'DE000PJ9NB98').ok);
}
assert(!b.detailScreenshotData(bnpBannerOcr,'DE000PG0XK25').ok);
console.log('BNP masthead without browser address: reviewed identity recovery and negative controls passed');

// Real browser-engine outputs: enlargement corrupts WKN and ratio; original
// resolution retains the same product and clean terms. Never borrow another ID.
const enlargedBnp=bnpBannerOcr.replace('WKN PJONB9','WKN PJOSNBS').replace('Bezugsverhaltnis 0,1','Bezugsverhaltnis © 01').replace('Laufzeit @ Open End','Laufzeit EB Open End');
const originalBnp=bnpBannerOcr.replace('Bezugsverhaltnis 0,1','Bezugsverhaltnis @ 0,1');
assert(b.preferOriginalTableRead(enlargedBnp,originalBnp));
assert(!b.preferOriginalTableRead(enlargedBnp,originalBnp+'\nISIN DE000PG0XK25'));
assert(!b.preferOriginalTableRead('ISIN DE000PG0XK25',originalBnp));
assert(!b.preferOriginalTableRead(enlargedBnp,originalBnp.replace('BNP PARIBAS','OTHER')));
assert(!b.preferOriginalTableRead(enlargedBnp,originalBnp.replace('0,1','unreadable')));

// Full alphabet/digit inventory: letters must never become numeric values.
for(const char of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'){
 assert.strictEqual(b.strictOcrNumber('12,'+char+'9'),null,char);
 assert.strictEqual(b.strictOcrNumber(char),null,char);
 assert(b.ocrGlyphPair(char,char));
}
for(const char of '0123456789')assert.strictEqual(b.strictOcrNumber('12,'+char+'9'),Number('12.'+char+'9'));
for(const token of ['01','12,O9','12,9O','1.2.3','1,2,3','12.99x'])assert.strictEqual(b.strictOcrNumber(token),null,token);
assert.strictEqual(b.strictOcrNumber('3.996,2705'),3996.2705);
assert.strictEqual(b.strictOcrNumber('0,1'),.1);
const numericText='Bezugsverhältnis 0,1\nBasispreis 3.996,2705 USD\nGeld 12,88\nBrief 12,89\nHebel 31,71';
assert.equal(b.unconfirmedOcrFields(numericText,[numericText]).length,5);
assert.equal(b.unconfirmedOcrFields(numericText,[numericText,numericText]).length,0);
const disagreement=numericText.replace('12,89','12,09');
assert(b.unconfirmedOcrFields(numericText,[numericText,numericText,disagreement,disagreement]).includes('ask'));
assert(!b.ocrGlyphPair('X','9'));
assert(b.ocrGlyphPair('O','9'));
assert(b.parseProductTerms('Bezugsverhältnis 01').error);
console.log('A–Z, 0–9, malformed numeric tokens and independent numeric agreement passed');

const badgeQuote='BNP PARIBAS\nPJONB9 13,07 / 13,08 €\nWKN PJ9NB9\nWKN-Bildprüfung: PJ9NB9\nGeld 13,07\nBrief 13,08';
assert(b.detailScreenshotData(badgeQuote,'DE000PJ9NB98').ok);
assert(!b.detailScreenshotData(badgeQuote.replace('WKN-Bildprüfung: PJ9NB9',''),'DE000PJ9NB98').ok);
assert(!b.detailScreenshotData(badgeQuote.replace('PJONB9 13','AB1234 13'),'DE000PJ9NB98').ok);
assert(!b.detailScreenshotData(badgeQuote,'DE000PJ9NCK0').ok);
console.log('Focused badge evidence resolves only confusable same-image WKN readings');

const refreshed={isin:'DE000PJ9NB98',productDirection:'LONG',price:13.07,leverage:28.28,ko:3996.2705,snapshot:{isin:'DE000PJ9NB98',identityBasis:'WKN',direction:'LONG',evidence:{Kurs:{value:13.08},Hebel:{value:28.25},KO:{value:3996.2705}}},quote:{isin:'DE000PJ9NB98',productVerified:true,direction:'LONG',price:13.07,leverage:28.28}};
assert(b.automaticIdentity(refreshed));
assert(!b.automaticIdentity({...refreshed,quote:{...refreshed.quote,productVerified:false}}));
assert(!b.automaticIdentity({...refreshed,price:99}));
const chartRefreshed={...refreshed,quote:{...refreshed.quote,found:false,price:undefined,analysisQuote:{price:refreshed.price}}};
assert(b.automaticIdentity(chartRefreshed),'verified SG chart update must not conflict with old image price');
assert(!b.automaticIdentity({...chartRefreshed,price:99}));
assert(!b.automaticIdentity({...chartRefreshed,quote:{...chartRefreshed.quote,direction:undefined,metadata:{direction:'SHORT'}}}));
assert(!b.automaticIdentity({...chartRefreshed,quote:{...chartRefreshed.quote,productVerified:false}}));

assert(!b.automaticIdentity({...refreshed,ko:4000}));
assert(!b.automaticIdentity({...refreshed,quote:{...refreshed.quote,direction:'SHORT'}}));
// Batch timing: only same-product accepted images in one selection may donate.
function timingBatch(){return [{ok:true,name:'terms.jpg',raw:'BNP PARIBAS\nBasispreis (05.10.2026) 3.996,2705 USD',data:{isin:'DE000PJ9NB98',terms:{strike:{dateText:'05.10.2026',value:3996.2705}},times:{}}},{ok:true,name:'quote.jpg',raw:'BNP PARIBAS\nAnderung Hebel GOLD\n-4,39% 28,25 4.143,13 USD\n21:35:52.211\nIndikation\n21:35:42',data:{isin:'DE000PJ9NB98',bid:13.07,ask:13.08,leverage:'28.25',sourceTime:'',times:{quote:{present:false}}}}];}
let batch=timingBatch();let series=b.linkScreenshotSeries(batch);
assert.equal(series.text,'05.10.2026 21:35:52');assert.equal(series.at,'2026-10-05T19:35:52.000Z');assert(series.userDeclaredSimultaneous);
assert.equal(batch[1].data.times.quote.at,series.at);assert.equal(batch[1].data.times.leverage.at,series.at);
assert.equal(batch[0].data.terms.strike.dateText,'05.10.2026');assert(!batch[0].data.times.quote);
assert.equal(b.linkScreenshotSeries(timingBatch().reverse()).text,series.text);
batch=timingBatch();batch[0].ok=false;assert.equal(b.linkScreenshotSeries(batch),null);
batch=timingBatch();batch[0].data.isin='DE000PJ9NCK0';assert.equal(b.linkScreenshotSeries(batch),null);
batch=timingBatch();batch[0].raw+='\n04.10.2026';assert.equal(b.linkScreenshotSeries(batch),null);
batch=timingBatch();batch[1].raw='BNP PARIBAS\n21:35\nHandelszeiten 08:00:00 - 22:00:00';assert.equal(b.linkScreenshotSeries(batch),null);
batch=timingBatch();batch[0].data.sourceTime='05.10.2026 21:35:52';batch[1].data.sourceTime='05.10.2026 21:34:00';assert.equal(b.linkScreenshotSeries(batch),null);
batch=timingBatch();batch[1].data.times.bid={present:true,text:'05.10.2026 21:34:00',at:'2026-10-05T19:34:00Z'};b.linkScreenshotSeries(batch);assert.equal(batch[1].data.times.bid.at,'2026-10-05T19:34:00Z');
console.log('Same-selection timing, provenance, conflicts, original timestamps and product boundaries passed');

// Preferred CFD reference reaches the future ranking; stale and unmeasured stay blocked.
const direct=JSON.parse(JSON.stringify(f));
direct.quote.futureResearch.futureReference={available:true,contract:'GCZ26',kind:'cfd-reference',priceUsd:3990,priceAt:at(0),proxySource:'Investing.com CFD',comparisonErrorUsd:2,validation:{ready:true,sampleCount:21,maxAbsoluteError:2}};
const cfdCandidate=b.conditionalCandidate(direct,context,now);assert(cfdCandidate.ok,cfdCandidate.reason);assert.equal(cfdCandidate.basis,3990);assert(cfdCandidate.priceKind.includes('Gold-CFD'));
assert(b.futureResearchText(direct.quote,now).includes('GOLD-CFD ALS FUTURE-REFERENZ'));
direct.quote.futureResearch.futureReference.validation.ready=false;assert(!b.conditionalCandidate(direct,context,now).ok);
direct.quote.futureResearch.futureReference.validation.ready=true;direct.quote.futureResearch.futureReference.priceAt=at(-61);assert(!b.conditionalCandidate(direct,context,now).ok);
console.log('CFD-first future reference, source label, independent validation and expiry passed');

// Today's independently dated BNP terms supersede expired screenshot terms.
const bnpDateNow=Date.parse('2026-10-06T07:30:00Z');
const datedSource='https://derivate.bnpparibas.com/product-details/DE000PJ9NB98/';
const datedConditions={};
for(const [key,value] of Object.entries({strike:3997.1452,ko:3997.1452,ratio:.1,underlying:'XAU/USD',type:'Unlimited Long',maturity:'Open End',currency:'EUR'}))datedConditions[key]={value,source:datedSource,at:null,dateText:['strike','ko'].includes(key)?'06.10.2026':undefined,conditionVerified:true,reviewedAt:'2026-10-06T07:29:00Z'};
const datedProduct={isin:'DE000PJ9NB98',isinConfirmed:true,productDirection:'LONG',ko:3997.1452,quote:{isin:'DE000PJ9NB98',productVerified:true,source:datedSource,checkedAt:'2026-10-06T07:29:00Z',metadata:{ko:3997.1452,strike:3997.1452,status:1,termsDated:true,termsDate:'06.10.2026'},conditions:datedConditions},snapshot:{isin:'DE000PJ9NB98',identityBasis:'ISIN',terms:{strike:{value:3996.2705,source:'old.jpg',dateText:'05.10.2026'}},evidence:{KO:{value:3996.2705,source:'old.jpg',dateText:'05.10.2026'}}}};
assert(b.productTermsStatus(datedProduct,bnpDateNow).complete,JSON.stringify(b.productTermsStatus(datedProduct,bnpDateNow)));
assert(!b.productTermsStatus(datedProduct,bnpDateNow+86400000).complete);
const datedConflict=JSON.parse(JSON.stringify(datedProduct));datedConflict.snapshot.terms.strike.dateText='06.10.2026';
assert(b.productTermsStatus(datedConflict,bnpDateNow).reasons.some(r=>r.includes('widersprechen')));
assert(b.renderIssuerHelp(datedProduct,['Basispreis fehlt']).includes(datedSource));
assert.equal(b.parseScreenshotCandidates(bnpLine.replace('DEOOOPJINCKO','DE000PJONCKO'))[0].isin,bnp.isin);
assert.notEqual(b.parseScreenshotCandidates(bnpLine.replace('DEOOOPJINCKO','DE000PJONCKO').replace('BNP','SG'))[0].isin,bnp.isin);
console.log('BNP direct dated terms: stale images, midnight expiry, conflicts, issuer link and known OCR variant passed');

assert.equal(b.cleanStoredProduct({isin:'DE000PJONCKO',name:bnpLine,direction:'LONG'}).isin,bnp.isin);
const koConflict=JSON.parse(JSON.stringify(datedProduct));koConflict.snapshot.evidence.KO.dateText='06.10.2026';assert(b.productTermsStatus(koConflict,bnpDateNow).reasons.some(r=>r.includes('widersprechen')));

// A complete BNP direct import must not fall through to screenshot requests.
const liveBnp={...p,isin:'DE000PG0XK25',name:'BNP GOLD Unlimited Short',snapshot:null};
liveBnp.quote={isin:liveBnp.isin,productVerified:true,found:true,eligible:true,marketOpen:true,
 source:'BNP Paribas',currency:'EUR',direction:'SHORT',price:p.price,bid:20,ask:p.price,
 leverage:p.leverage,ko:p.ko,quoteAt:at(0),bidAt:at(0),askAt:at(0),leverageAt:at(0),snapshotAt:at(0),tradingEndAt:at(3600),checkedAt:at(0),
 metadata:{status:1,direction:'SHORT',underlyingType:'SPOT',ko:p.ko,termsDated:true},
 conditions:terms({ratio:.1,strike:4460,underlying:'XAU/USD',type:'Turbo',maturity:'Open End',currency:'EUR'})};
liveBnp.isinConfirmed=b.automaticIdentity(liveBnp);
assert(b.currentQuote(liveBnp,now));assert(b.finalProductStatus(liveBnp,now).complete);
const liveSelection=b.selectionWorkflow([liveBnp],context,{});
assert.equal(liveSelection.groups.length,1);assert.equal(liveSelection.requests.length,0);
const neutralLive=b.selectionWorkflow([liveBnp],{...context,direction:'NEUTRAL'},{});
assert.equal(neutralLive.groups.length,0);assert.equal(neutralLive.notApproved[0].missingReasons.length,0);
const expiredLive=b.selectionWorkflow([liveBnp],{...context,now:now+91000},{});
assert.equal(expiredLive.groups.length,0);assert(expiredLive.requests.length>0);
console.log('BNP direct-only import: no false screenshot requests, neutral and expiry remain blocked');

// A fresh bid/ask pair cannot conceal an expired independent leverage clock.
const staleLeverage={...liveBnp,quote:{...liveBnp.quote,leverageAt:at(-91)}};
const staleStatus=b.finalProductStatus(staleLeverage,now);
assert(!staleStatus.complete);
assert(staleStatus.reasons.some(x=>x.startsWith('BNP-Kursabruf:')));
assert(!staleStatus.reasons.some(x=>x.includes('Detailbild mit derselben ISIN')));
assert(b.missingValueLocation(staleStatus.reasons.at(-1)).includes('Automatische BNP-Quelle'));
assert.equal(b.selectionWorkflow([staleLeverage],context,{}).groups.length,0);
const wrongBnp={...staleLeverage,isinConfirmed:false};
assert(b.finalProductStatus(wrongBnp,now).reasons.some(x=>x.includes('Produktzuordnung')));
console.log('BNP source delay is explicit; stale leverage and identity remain blocked');

// Separate SG leverage screenshot inherits only the same selection's capture reference.
function sgSeries(){return [
 {ok:true,name:'sg-kurs.jpg',data:{isin:'DE000FG7K283',bid:7.72,ask:7.73,sourceTime:'06.10.2026 19:10:00',times:{}}},
 {ok:true,name:'sg-hebel.jpg',data:{isin:'DE000FG7K283',leverage:48.0293,times:{}}}
];}
let sg=sgSeries();const sgTime=b.linkScreenshotSeries(sg);
assert(sgTime);assert.equal(sg[1].data.times.leverage.at,sgTime.at);
assert(sg[1].data.times.leverage.fromSeries);assert(!sg[1].data.sourceTime);
const linked=b.mergeScreenshotEvidence(null,sg[1].data,'sg-hebel.jpg');
assert(linked.evidence.Hebel.fromSeries);
assert.deepEqual(linked.evidence.Hebel.timeSources,['sg-kurs.jpg']);
assert(b.screenshotSummary(linked).includes('Hebel aus derselben Aufnahmeserie'));
assert(b.cleanStoredProduct({isin:'DE000FG7K283',snapshot:linked}).snapshot.evidence.Hebel.fromSeries);
sg=sgSeries();sg[1].data.times.leverage={present:true,at:null,text:'unlesbar'};
b.linkScreenshotSeries(sg);assert.equal(sg[1].data.times.leverage.at,null);
sg=sgSeries();sg[1].data.times.leverage={present:true,at:'2026-10-06T16:00:00Z'};
b.linkScreenshotSeries(sg);assert.equal(sg[1].data.times.leverage.at,'2026-10-06T16:00:00Z');
sg=sgSeries();delete sg[0].data.sourceTime;
assert.equal(b.linkScreenshotSeries(sg),null);assert(!sg[1].data.times.leverage);
sg=sgSeries();assert.equal(b.linkScreenshotSeries([sg[1]]),null);
sg=sgSeries();sg[1].data.isin='DE000PJ9NB98';assert.equal(b.linkScreenshotSeries(sg),null);
sg=sgSeries();b.linkScreenshotSeries(sg.reverse());assert(sg[0].data.times.leverage.fromSeries);
console.log('Separate SG leverage timing, provenance, persistence and timestamp boundaries passed');

{
// A terminal issuer banner needs identity, but no quote/ratio/leverage uploads.
const koOriginal=fs.readFileSync('test_fixtures/sg_fg5nmh_knocked_out.txt','utf8');
const deadIsin='DE000FG5NMH8',dead={isin:deadIsin,name:'SG Gold BEST Turbo Call',productDirection:'LONG'};
assert(b.validIsin(deadIsin));
const koRead=b.detailScreenshotData(koOriginal,deadIsin);
assert(koRead.ok);assert.equal(koRead.lifecycle.status,'KNOCKED_OUT');
assert.equal(koRead.identityBasis,'WKN');
assert(!b.detailScreenshotData(koOriginal,isin).ok);
for(const text of ['Nicht ausgeknockt','Produkt ist nicht KNOCKED OUT','Bei Erreichen der Barriere wird es ausgeknockt.','Knock-Out-Barriere 4114,6610'])assert(!b.explicitKnockout(text));
assert(!b.knockoutStatus({...dead,isin:'DE000FG5NMF2'}));
for(const direction of ['LONG','SHORT','NEUTRAL']){
 const flow=b.selectionWorkflow([dead],{...context,direction},{});
 assert.equal(flow.requests.length,0);assert.equal(flow.approvedCount,0);
 const markup=b.renderSelectionWorkflow(flow,[dead]);
 assert(markup.includes('Ausgeknockt – Produkt ausgeschlossen'));
 assert(!markup.includes('Fehlende Werte'));assert(!markup.includes('Bilder / PDF hinzufügen'));
 assert(!markup.includes('aktuelle Screenshots erneut hochladen'));
}
assert(!b.evaluateProduct({...p,...dead}).ok);
assert(b.finalProductStatus(dead).terminal);
// Lifecycle evidence is identity-bound and persists through later images/reloads.
const memory=new Map(),koEnv={window:{},localStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v)}};
vm.createContext(koEnv);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),koEnv);
const kb=koEnv.window.BobDegiro,other='DE000FG7K283';
const event=kb.detailScreenshotData('WKN FG7K28\nKNOCKED OUT',other);
assert(event.ok);
let merged=kb.mergeScreenshotEvidence({isin:other},event,'issuer-status.jpg');
assert(kb.knockoutStatus({isin:other,snapshot:merged}));
merged=kb.mergeScreenshotEvidence(merged,{isin:other,terms:{},price:'10'},'older-quote.jpg');
assert.equal(merged.lifecycle.status,'KNOCKED_OUT');
assert(kb.knockoutStatus({isin:other}));
assert(!kb.knockoutStatus({isin,snapshot:merged}));
assert(!kb.conditionalCandidate({isin:other}).ok);
assert(!kb.finalProductStatus({isin:other,snapshot:merged}).complete);
assert.equal(kb.cleanStoredProduct({isin:other,snapshot:merged}).snapshot.lifecycle.source,'issuer-status.jpg');
console.log('Knock-out: original SG banner, identity, no upload requests, neutral precedence, persistent terminal exclusion and non-status negative controls passed');

}

// A generic historical BNP list label cannot overwrite identified issuer terms.
const genericList=JSON.parse(JSON.stringify(datedProduct));
genericList.snapshot.terms.type={value:'BNP Unlimited',reviewed:true,source:'historical-list.jpg'};
assert(b.productTermsStatus(genericList,bnpDateNow).complete);
assert(b.missingValueLocation('Produkttyp nicht als Turbo / Knock-out bestätigt').includes('Typ / Produktart'));
const endedCard=b.compactProductCard({...genericList,quote:{...genericList.quote,metadata:{status:2}}});
assert(endedCard.includes('Keine weiteren Daten oder Screenshots erforderlich'));
assert(!endedCard.includes('Bilder / PDF hinzufügen'));
const factorCard=b.compactProductCard({isin:'DE000FE4UF01',name:'Gold Future Faktor'});
assert(factorCard.includes('Faktorprodukt ausgeschlossen'));assert(!factorCard.includes('Bilder / PDF hinzufügen'));
const fixedIssuer=JSON.parse(JSON.stringify(datedProduct));
fixedIssuer.quote.source='SG';fixedIssuer.quote.metadata.termsDated=false;fixedIssuer.quote.metadata.termsFixed=true;delete fixedIssuer.quote.metadata.termsDate;
for(const key of ['strike','ko'])fixedIssuer.quote.conditions[key]={value:3997.1452,source:'https://www.sg-zertifikate.de/product-details/test',conditionVerified:true,fixed:true,validUntil:'2026-12-18',reviewedAt:'2026-10-06T07:29:00Z',policySource:'https://www.sg-zertifikate.de/contentmgmt/media/c5bihw1s/bro_turbo-optionsscheine.pdf'};
assert(b.productTermsStatus(fixedIssuer,bnpDateNow).complete);
assert(!b.productTermsStatus(fixedIssuer,Date.parse('2026-12-18T08:00:00Z')).complete);
console.log('Issuer terms precedence, correct missing-field label, terminal/factor cards and fixed-contract evidence passed');

// Missing screenshot identity must not masquerade as an issuer identity failure.
const directNoImage={...refreshed,snapshot:null};
const directNoImageCard=b.compactProductCard(directNoImage,['Detailbild mit derselben ISIN']);
assert(directNoImageCard.includes('Produktidentität automatisch bestätigt'));
assert(!directNoImageCard.includes('Produktzuordnung oder Bildwerte nicht eindeutig'));
assert(!directNoImageCard.includes('Detailbild mit derselben ISIN'));
assert(!b.finalProductStatus(directNoImage).complete);
const unknownIdentityCard=b.compactProductCard({...directNoImage,quote:{...directNoImage.quote,productVerified:false}},['Detailbild mit derselben ISIN']);
assert(unknownIdentityCard.includes('Produktzuordnung oder Bildwerte nicht eindeutig'));
const conflictingIdentityCard=b.compactProductCard({...directNoImage,quote:{...directNoImage.quote,direction:'SHORT'}},['Detailbild mit derselben ISIN']);
assert(conflictingIdentityCard.includes('Produktzuordnung oder Bildwerte nicht eindeutig'));

// User-authorized chart/calculated-gearing release preserves market and risk gates.
const analysisProduct={...p,snapshot:{...p.snapshot,currency:null,bid:null,ask:null,evidence:{KO:p.snapshot.evidence.KO}},quote:{isin:p.isin,productVerified:true,direction:'SHORT',metadata:{status:1},leverage:15,
 analysisQuote:{bid:20,ask:20.01,price:20.01,currency:'EUR',source:'SG chart',bidAt:at(0),askAt:at(0)},
 leverageCalculation:{available:true,inputsFresh:true,value:15,inputs:{askEur:20.01,askAt:at(0),basisAt:at(0),fxDataAt:at(0),fxEffectiveAt:at(0)}}}};
assert(b.analysisReleaseQuote(analysisProduct,now));
assert(b.finalProductStatus(analysisProduct,now).complete);
assert(b.conditionalCandidate(analysisProduct,context,now).ok);
assert(b.selectionWorkflow([analysisProduct],context,{}).approved);
assert(!b.selectionWorkflow([analysisProduct],{...context,direction:'NEUTRAL'},{}).approved);
assert(!b.selectionWorkflow([{...analysisProduct,ko:4141}],context,{}).approved);
assert(!b.analysisReleaseQuote(analysisProduct,now+301000));
const skewed=JSON.parse(JSON.stringify(analysisProduct));skewed.quote.leverageCalculation.inputs.basisAt=at(-91);
assert(!b.analysisReleaseQuote(skewed,now));
assert(!b.analysisReleaseQuote({...analysisProduct,quote:{...analysisProduct.quote,productVerified:false}},now));
assert(!b.currentQuote(analysisProduct,now));
const backupAnalysisProduct=JSON.parse(JSON.stringify(analysisProduct));
backupAnalysisProduct.quote.analysisQuote.source='Onvista · BNP Paribas';
backupAnalysisProduct.quote.analysisQuote.priceKind='secondary-market';
assert(b.analysisReleaseQuote(backupAnalysisProduct,now));
assert(b.finalProductStatus(backupAnalysisProduct,now).complete);
assert(b.conditionalCandidate(backupAnalysisProduct,context,now).priceKind.includes('Ersatzquellenkurs'));
assert(!b.selectionWorkflow([backupAnalysisProduct],{...context,direction:'NEUTRAL'},{}).approved);
