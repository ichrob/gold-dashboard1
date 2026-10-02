const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobCombined,now=Date.parse('2026-10-02T10:00:00Z'),at=s=>new Date(now+s*1000).toISOString();
const bundle={fetched_at:now/1000,spots:{xaus:4200,xaus_age_seconds:0,spot_price_as_of:at(0),is_genuine_xauusd_spot:true}};
const p={isin:'DE000FG6XB39',isinConfirmed:true,name:'SG Gold Turbo',productDirection:'SHORT',quote:{isin:'DE000FG6XB39',productVerified:true,metadata:{underlyingType:'SPOT',underlying:'XAU/USD',direction:'SHORT',ko:4403},productModel:{isin:'DE000FG6XB39',verifiedSimpleTurbo:true,underlying:'XAU/USD',direction:'SHORT',ratio:.1,strike:4403,ko:4403,tradingEndAt:at(5000)},calculatedProduct:{usdEur:.9,fxDataAt:at(0),fxEffectiveAt:at(0)}}};
const barrier=value=>({isin:p.isin,value,currency:'USD',source:'SG',url:'https://issuer.example/product',at:at(-60),validUntil:at(500),confirmed:true});
const r={isin:p.isin,source:'Onvista',venue:'SG OTC',url:'https://quote.example/product',bid:18,ask:18.01,quoteAt:at(-100),paired:true,reviewed:true,barriers:[barrier(4403),barrier(4403.8)],goldReference:4201,fxReference:.9,goldAt:at(-100),fxAt:at(-100),goldUrl:'https://gold.example',fxUrl:'https://fx.example',referenceConfirmed:true};
const clone=x=>JSON.parse(JSON.stringify(x));
const before=JSON.stringify([p,r,bundle]);let s=b.assess(p,r,bundle,now);
assert.equal(s.ko.value,4403);assert(Math.abs(s.ko.differenceUsd-.8)<1e-8);assert.equal(s.distanceUsd,203);
assert(s.estimated);assert(Math.abs(s.estimate.ask-18.10)<1e-8);assert.equal(s.eligible,false);assert.equal(s.tradeable,false);assert.equal(s.quote.liveVerified,false);
assert.equal(JSON.stringify([p,r,bundle]),before);
const long=clone(p);long.productDirection='LONG';long.quote.metadata.direction='LONG';long.quote.productModel.direction='LONG';assert.equal(b.assess(long,r,bundle,now).ko.value,4403.8);
for(const mutate of [x=>x.barriers[1].value=4404.01,x=>x.barriers[0].currency='EUR',x=>x.barriers[0].isin='DE000FG309G0',x=>x.barriers[0].confirmed=false,x=>x.barriers[0].at='2026-10-02T09:00:00',x=>x.barriers[0].validUntil=at(-1),x=>x.barriers[0].at=at(-86401)]){
 const bad=clone(r);mutate(bad);const out=b.assess(p,bad,bundle,now);assert.equal(out.ko,null);assert.equal(out.estimated,false);
}
for(const mutate of [x=>x.paired=false,x=>x.source='finanzen.net',x=>x.venue='',x=>x.ask=17,x=>x.quoteAt=at(-1801),x=>x.quoteAt=at(1),x=>x.quoteAt='2026-10-02T10:00:00',x=>x.reviewed=false]){const bad=clone(r);mutate(bad);assert.equal(b.assess(p,bad,bundle,now).quote,null);}
for(const mutate of [x=>x.fxAt=at(-106),x=>x.goldReference='',x=>x.referenceConfirmed=false,x=>x.goldUrl='']){const bad=clone(r);mutate(bad);assert.equal(b.assess(p,bad,bundle,now).estimated,false);}
const inactive=clone(p);inactive.quote.metadata.status=8;assert.equal(b.assess(inactive,r,bundle,now).ko,null);
const exact=clone(r);exact.barriers[1].value=4404;assert.equal(b.assess(p,exact,bundle,now).ko.differenceUsd,1);
const bad=clone(p);bad.quote.calculatedProduct.fxDataAt=at(-61);assert.equal(b.assess(bad,r,bundle,now).estimated,false);
assert.equal(b.assess({...p,isinConfirmed:false},r,bundle,now).ko,null);
assert.equal(b.assess(p,r,bundle,now+1801000).quote,null);
const crossed=clone(bundle);crossed.spots.xaus=4500;assert(b.assess(p,r,crossed,now).distanceUsd<0);assert.equal(b.assess(p,r,crossed,now).estimated,false);
assert.equal(b.assess({...p,isin:'DE000FG309G0'}, {...r,isin:'DE000FG309G0'},bundle,now).basis,null);
assert(b.render(s).includes('Schätzung, keine SG-Quotierung'));assert(b.render(s).includes('Keine Live-Freigabe'));
const hostile=clone(r);hostile.venue='<script>alert(1)</script>';assert(!b.render(b.assess(p,hostile,bundle,now)).includes('<script>'));
console.log('Combined manual references: passed');
const context={now,direction:'SHORT',spotFresh:true,spot:4200,atr:10,trend:'SHORT',trend2:'SHORT',mtf:'SHORT',rsi:40,hist:-1,adx:30,momentum:-1};
let ranked=b.rank([p],[r],bundle,context);
assert.equal(ranked.candidates.length,1);assert.equal(ranked.selection.isin,p.isin);assert(ranked.selection.estimated);assert.equal(ranked.tradeable,false);
assert.equal(ranked.candidates[0].ko,4403);assert(Math.abs(ranked.candidates[0].price-18.10)<1e-8);
assert(b.renderTop3(ranked).includes('Platz 1'));assert(b.renderTop3(ranked).includes('Bedingte Schätzung'));
assert.equal(b.rank([p],[r],bundle,{...context,direction:'NEUTRAL'}).candidates.length,0);
assert.equal(b.rank([p],[r],bundle,{...context,direction:'LONG'}).candidates.length,0);
assert.equal(b.rank([p],[r],bundle,{...context,spotFresh:false}).candidates.length,0);
assert.equal(b.rank([p],[r],bundle,{...context,trend:'LONG',trend2:'LONG',mtf:'LONG',hist:1,momentum:1}).candidates.length,0);
assert.equal(b.rank([p],[r],bundle,{...context,now:now+61000}).candidates.length,0);
for(const mutate of [x=>x.barriers[1].value=4404.01,x=>x.quoteAt=at(-1801),x=>x.referenceConfirmed=false]){const bad=clone(r);mutate(bad);const result=b.rank([p],[bad],bundle,context);assert.equal(result.candidates.length,0);assert(result.excluded.length);}
const products=[p],refs=[r];
for(const isin of ['DE000FG4JXV7','DE000FG7EPT1','DE000FG5GUT0']){const next=clone(p);next.ko=4403;next.isin=isin;next.quote.isin=isin;next.quote.productModel.isin=isin;const ref=clone(r);ref.isin=isin;ref.barriers.forEach(x=>x.isin=isin);products.push(next);refs.push(ref);}
const unchanged=JSON.stringify([products,refs,bundle]);ranked=b.rank(products,refs,bundle,context);
assert.equal(ranked.total,4);assert.equal(ranked.candidates.length,3);assert.equal(ranked.selection,null);assert.equal(JSON.stringify([products,refs,bundle]),unchanged);
assert.equal(b.rank([p,p],[r,r],bundle,context).total,1);
// A fresh confirmed price is never replaced by an estimate for the same row.
const live=clone(p);Object.assign(live,{price:18.1,leverage:20,ko:4403,spread:.01});Object.assign(live.quote,{found:true,eligible:true,marketOpen:true,currency:'EUR',price:18.1,leverage:20,ko:4403,spread:.01,direction:'SHORT',quoteAt:at(0),bidAt:at(0),askAt:at(0),leverageAt:at(0),snapshotAt:at(0),tradingEndAt:at(5000),source:'SG'});
const mixed=b.rank([live,products[1]],[r,refs[1]],bundle,context);assert.equal(mixed.candidates.length,2);assert.equal(mixed.candidates[0].estimated,false);assert.equal(mixed.candidates[1].estimated,true);
const future=clone(p);future.isin='DE000FG309G0';assert.equal(b.rank([future],[r],bundle,context).total,0);
assert(b.rank([future],[r],bundle,context).excluded[0].reason.includes('Kontrakt-MTF'));
const unsafeName=clone(p);unsafeName.name='<script>alert(1)</script>';assert(!b.renderTop3(b.rank([unsafeName],[r],bundle,context)).includes('<script>'));
console.log('Automatic combined Top-3: passed');
const onvista='onvista.de\nISIN '+p.isin+'\nSociete Generale (EUR)\nGeld · 25.000 Stk.\n21,280 EUR\nheute, 12:24:13\nBrief · 25.000 Stk.\n21,290 EUR\nheute, 12:24:13';
const draft=b.screenshotDraft(onvista,p.isin);
assert.equal(draft.source,'Onvista');assert.equal(draft.fields.bid,'21.28');assert.equal(draft.fields.ask,'21.29');assert.equal(draft.fields.quoteAt,'heute, 12:24:13');
assert(!draft.fields.ko1);assert.equal(draft.fields.venue,'Société Générale');
const imported=window.BobDegiro.detailScreenshotData(onvista,p.isin);assert(imported.ok);assert.equal(imported.bid,21.28);assert.equal(imported.ask,21.29);
const details=b.screenshotDraft('onvista.de\n'+p.isin+'\nKO-Schwelle\n4.403,305 USD\nBasispreis\n4.403,305 USD\nBezugsverhältnis\n0,100\nGoldpreis 4.179,120 USD',p.isin);
assert.equal(details.fields.ko1,'4403.305');assert.equal(details.fields.koUntil1,'');assert(!details.hasQuote);
assert.equal(window.BobDegiro.ocrExtract('Goldpreis 4.179,120 USD\nBasispreis 4.403,305 USD').price,'');
const merged=b.mergeDraft(b.mergeDraft(null,draft,'quote.jpg'),details,'details.jpg');
assert.equal(merged.fields.bid,'21.28');assert.equal(merged.fields.quoteAt,'heute, 12:24:13');assert.equal(merged.evidence.bid,'quote.jpg');assert.equal(merged.evidence.ko1,'details.jpg');
const degiro=b.screenshotDraft('DEGIRO\n'+p.isin+'\nBörse Societe Generale OTC\nEUR\nGeld € 19,33\nBrief € 19,34\nKurszeit: 02/10/2026 12:24:13 CEST',p.isin);
assert.equal(degiro.source,'DEGIRO');assert.equal(degiro.fields.quoteAt,'2026-10-02T10:24:13.000Z');assert.equal(degiro.fields.venue,'Societe Generale OTC');
const replaced=b.mergeDraft(merged,degiro,'degiro.jpg');assert.equal(replaced.fields.source,'DEGIRO');assert.equal(replaced.fields.bid,'19.33');assert.equal(replaced.evidence.bid,'degiro.jpg');
for(const raw of [onvista+'\nGeld 22 EUR\nBrief 23 EUR',onvista.replace('21,280 EUR',''),onvista.replace('21,290 EUR','20,000 EUR')]){const x=b.screenshotDraft(raw,p.isin);assert(!x.paired);assert.equal(window.BobDegiro.detailScreenshotData(raw,p.isin).ok,false);assert(!b.mergeDraft(merged,x,'ambiguous.jpg').fields.bid);}
assert(!b.screenshotDraft(onvista,'DE000FG309G0').ok);
assert(!b.screenshotDraft(onvista+'\nDE000FG309G0',p.isin).ok);
const delayed=b.screenshotDraft(onvista+'\nverzögert',p.isin);assert(delayed.delayed);
assert.equal(b.assess(p,{...r,source:'DEGIRO'},bundle,now).estimated,true);
assert.equal(b.assess(p,{...r,source:'DEGIRO',delayed:true},bundle,now).quote,null);
console.log('Screenshot-to-form drafts: passed');
const imageReference=clone(r);imageReference.url='';imageReference.source='DEGIRO';imageReference.imageEvidence={bid:'quote.jpg',ask:'quote.jpg'};
imageReference.barriers.forEach(x=>{x.url='';x.imageSource='details.jpg';});
assert(b.assess(p,imageReference,bundle,now).estimated);
assert.equal(b.assess(p,{...imageReference,imageEvidence:{bid:'a.jpg',ask:'b.jpg'}},bundle,now).quote,null);
assert.equal(b.assess(p,{...imageReference,barriers:imageReference.barriers.map(x=>({...x,imageSource:null}))},bundle,now).ko,null);

assert(!b.screenshotDraft('DEGIRO\n'+p.isin+'\nEUR\nGeld 25.000 Stk.\nBrief 25.000 Stk.',p.isin).paired);

// Exercise the actual bridge with DOM-like fields, including confirmation reset.
const bridgeContext={window:{}};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={prefillCombinedForm,resetCombinedForm,'),bridgeContext);
const formFields={};for(const key of ['source','bid','ask','quoteAt','venue','url','ko1','koSource1','koUrl1','koAt1','koUntil1','goldReference','goldAt','goldUrl','fxReference','fxAt','fxUrl'])formFields[key]={value:''};
formFields.reviewed={type:'checkbox',checked:true};formFields.referenceConfirmed={type:'checkbox',checked:true};
const summary={innerHTML:''},formNode={open:false,querySelector:selector=>formFields[selector.match(/data-combined="([^\"]+)"/)?.[1]],querySelectorAll:selector=>selector.includes('checkbox')?[formFields.reviewed,formFields.referenceConfirmed]:Object.values(formFields)};
bridgeContext.document={querySelector:()=>formNode,getElementById:()=>summary};
formFields.goldReference.value='old gold';bridgeContext.window.BobDegiro.prefillCombinedForm(1,draft,'quote.jpg');
assert.equal(formFields.bid.value,'21.28');assert.equal(formFields.goldReference.value,'');assert.equal(formFields.reviewed.checked,false);assert(formNode.open);assert(summary.innerHTML.includes('quote.jpg'));
bridgeContext.window.BobDegiro.prefillCombinedForm(1,details,'details.jpg');assert.equal(formFields.bid.value,'21.28');assert.equal(formFields.ko1.value,'4403.305');assert.equal(formFields.koUntil1.value,'');
bridgeContext.window.BobDegiro.resetCombinedForm(1);assert.equal(formFields.bid.value,'');assert.equal(formFields.reviewed.checked,false);
console.log('Screenshot form bridge: passed');
// Fixed screenshot barriers persist independently of quote freshness and SG terms.
const storage={};const fixedWindow={};const localStorage={getItem:k=>storage[k]||null,setItem:(k,v)=>storage[k]=v};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window:fixedWindow,localStorage});
const fb=fixedWindow.BobCombined,fp={isin:'DE000FG4JXV7',productDirection:'SHORT',name:'SG Gold Turbo Classic Put',ko:4460};
assert.equal(fb.fixedFor(fp).value,4460);assert(fb.saveFixed(fp,'detail.jpg'));assert.equal(fb.fixedFor(fp).value,4460);
const fixedState=fb.assess(fp,null,bundle,now);assert.equal(fixedState.ko.value,4460);assert.equal(fixedState.distanceUsd,260);assert.equal(fixedState.tradeable,false);assert.equal(fixedState.quote,null);assert(fb.render(fixedState).includes('fester Berechnungswert'));
assert.equal(fb.fixedFor({...fp,ko:4450}),null);assert.equal(fb.fixedFor({...fp,productDirection:'LONG'}),null);assert.equal(fb.fixedFor({...fp,isin:p.isin}),null);
const reloaded={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window:reloaded,localStorage});assert.equal(reloaded.BobCombined.fixedFor(fp).value,4460);
assert(!fb.saveFixed({...fp,ko:0}));fb.removeFixed(fp.isin);assert.equal(fb.fixedFor(fp),null);
assert(Number.isNaN(b.time('02/10/2026 15:04')));assert.equal(b.assess(p,{...r,quoteAt:'02/10/2026 15:04'},bundle,now).quote,null);
console.log('Fixed screenshot barrier and honest minute precision: passed');
const mt=b.minuteTime('02/10/2026 15:04');assert.equal(mt.at,'2026-10-02T15:04:05+02:00');assert(mt.assumedSeconds&&mt.assumedTimezone);
assert.equal(b.minuteTime('02/01/2026 15:04').at,'2026-01-02T15:04:05+01:00');
for(const stamp of ['31/02/2026 15:04','02/10/2026 25:04','25/10/2026 02:30','29/03/2026 02:30','02/10/2026 15:04:19','15:04'])assert.equal(b.minuteTime(stamp),null);
const minuteDraft=b.screenshotDraft('DEGIRO\n'+p.isin+'\nEUR\nGeld € 19,37\nBrief € 19,38\n02/10/2026 15:04',p.isin);assert.equal(minuteDraft.fields.quoteAt,mt.at);assert(minuteDraft.supplementedTime.assumedSeconds);
const marked=b.mergeDraft(null,minuteDraft,'minute.jpg');assert(marked.supplementedTime.assumedSeconds);assert(b.mergeDraft(marked,details,'detail.jpg').supplementedTime.assumedSeconds);assert.equal(b.mergeDraft(marked,degiro,'seconds.jpg').supplementedTime,null);
assert.equal(b.assess(p,{...r,assumedSeconds:true},bundle,now).quote,null);assert(b.render(b.assess(p,{...r,assumedSeconds:true},bundle,now)).includes('auf Nutzerwunsch auf 05'));
console.log('User-requested seconds 05 with precision provenance: passed');
