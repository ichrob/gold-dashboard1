const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});const b=window.BobDegiro;
// Return upload resolves identity again after list replacement/reordering.
const returnIsin='DE000FG5NMF2',otherIsin='DE000FG309G0';
assert.equal(b.screenshotReturnRow(returnIsin,[{isin:otherIsin,index:1},{isin:returnIsin,index:8}]).index,8);
assert.equal(b.screenshotReturnRow(returnIsin,[{isin:otherIsin,index:8}]),null);
assert.equal(b.screenshotReturnRow(returnIsin,[{isin:returnIsin,index:1},{isin:returnIsin,index:2}]),null);
assert.equal(b.screenshotReturnRow('invalid',[{isin:'invalid',index:1}]),null);
assert(b.compactProductCard({isin:returnIsin,index:8},['Geld fehlt']).includes('data-screenshot-product="'+returnIsin+'"'));
const now=Date.parse('2026-10-02T07:00:00Z'),at=s=>new Date(now+s*1000).toISOString();
const bundle={fetched_at:now/1000,spots:{xaus:4200,xaus_age_seconds:0,spot_price_as_of:at(0),is_genuine_xauusd_spot:true}};
const p={isin:'DE000FG6XB39',isinConfirmed:true,name:'SG Gold Turbo BEST Open-End Put BAR 4403.17 Bv 10 LV 19.4',productDirection:'SHORT',ko:4403.17,leverage:19.4,snapshot:{isin:'DE000FG6XB39',direction:'SHORT',bid:19.33,ask:19.34,currency:'EUR',sourceTime:'02/10/2026 08:31',evidence:{}}};
let state=b.screenshotCurrentState(p,bundle,now);
assert(Math.abs(state.koDistancePct-(4403.17-4200)/4200*100)<1e-10);
assert.equal(state.leverage,null);assert.equal(state.eligible,false);assert.equal(state.liveVerified,false);
assert(state.rows[0].text.includes('Szenario'));assert(state.rows[3].text.includes('Geld '));
assert(b.renderScreenshotCurrentState(p,bundle,now).includes('Keine zusätzliche Live-Freigabe'));
const before=JSON.stringify(p);b.screenshotCurrentState(p,bundle,now);assert.equal(JSON.stringify(p),before);
assert.equal(b.screenshotCurrentState({...p,isinConfirmed:false},bundle,now).basis,null);
for(const mutate of [x=>x.spots.spot_price_as_of=at(-61),x=>x.spots.spot_price_as_of=at(1),x=>delete x.spots.spot_price_as_of,x=>x.spots.is_genuine_xauusd_spot=false,x=>x.fetched_at=now/1000+1,x=>x.spots.spot_error='outage']){const bad=JSON.parse(JSON.stringify(bundle));mutate(bad);assert.equal(b.screenshotCurrentState(p,bad,now).basis,null);}
assert.equal(b.screenshotCurrentState(p,bundle,now+61000).basis,null);
const crossed={...bundle,spots:{...bundle.spots,xaus:4500}};
assert(b.screenshotCurrentState(p,crossed,now).koDistancePct<0);
assert(b.screenshotCurrentState(p,crossed,now).rows[1].text.includes('jenseits'));
assert.equal(b.screenshotCurrentState({...p,name:'Gold Future Dec 26'},bundle,now).basis,null);
assert.equal(b.screenshotCurrentState({...p,quote:{isin:p.isin,productVerified:true,metadata:{underlyingType:'UNSUPPORTED'}}},bundle,now).basis,null);
const model={isin:p.isin,verifiedSimpleTurbo:true,underlying:'XAU/USD',direction:'SHORT',ratio:.1,strike:4403.17,ko:4403.17,tradingEndAt:at(100)};
const c={available:true,direction:'SHORT',ratio:.1,strikeUsd:4403.17,goldUsd:4200,usdEur:.88,askEur:18,priceAt:at(0),goldAt:at(0),fxDataAt:at(0),fxEffectiveAt:at(0),referenceAt:at(-100)};
const modeled={...p,quote:{isin:p.isin,productVerified:true,metadata:{ko:4403.17,underlyingType:'SPOT',underlying:'XAU/USD',direction:'SHORT'},productModel:model,calculatedProduct:c}};
assert(Math.abs(b.screenshotCurrentState(modeled,bundle,now).leverage-4200*.88*.1/18)<1e-10);
for(const modify of [q=>q.calculatedProduct.fxDataAt=at(-61),q=>q.calculatedProduct.referenceAt=at(-1801),q=>q.productModel.tradingEndAt=at(-1),q=>q.productModel.ratio=.01]){const bad=JSON.parse(JSON.stringify(modeled));modify(bad.quote);assert.equal(b.screenshotCurrentState(bad,bundle,now).leverage,null);}
const f={...p,isin:'DE000FG309G0',quote:{isin:'DE000FG309G0',productVerified:true,metadata:{underlyingType:'FUTURE',contract:'GCZ26',ko:4500,direction:'SHORT'},futureResearch:{contract:'GCZ26',direction:'SHORT',marketOpen:true,tradingEndAt:at(100),bid:24,ask:24.01,ratio:.1,usdEur:.88,bidAt:at(0),askAt:at(0),fxDataAt:at(0),fxEffectiveAt:at(0),calculatedFuture:{available:true,contract:'GCZ26',priceUsd:4250,priceAt:at(0),referenceAt:at(-100)}}}};
state=b.screenshotCurrentState(f,bundle,now);assert.equal(state.basis,4250);assert(state.rows[0].text.includes('keine Börsen-Echtzeit'));assert(state.leverage>0);assert.equal(state.eligible,false);
for(const change of [r=>r.contract='GCG27',r=>r.calculatedFuture.priceAt=at(-61),r=>r.calculatedFuture.referenceAt=at(-1801)]){const bad=JSON.parse(JSON.stringify(f));change(bad.quote.futureResearch);assert.equal(b.screenshotCurrentState(bad,bundle,now).basis,null);}
const escape={...p,name:'<script>alert(1)</script> Gold'};assert(!b.renderScreenshotCurrentState(escape,bundle,now).includes('<script>'));
const evidence={value:4403.17,currency:'USD',updatedAtRaw:'2026-10-02T01:12:16.267',timezoneKnown:false,retrievedAt:at(0),state:'issuer_reported'};
const dated=JSON.parse(JSON.stringify(modeled));dated.quote.metadata.koEvidence=evidence;
state=b.screenshotCurrentState(dated,bundle,now);
assert(state.rows.some(r=>r.label==='SG-KO-Nachweis'&&r.text.includes('Zeitzone nicht angegeben')&&r.text.includes('gerade abgerufene')));
assert.equal(state.eligible,false);assert.equal(state.liveVerified,false);
assert(b.screenshotCurrentState(dated,bundle,now+61000).rows.some(r=>r.text.includes('Abruf nicht mehr frisch')));
for(const change of [e=>e.value=4400,e=>e.currency='EUR',e=>e.state='screenshot']){const bad=JSON.parse(JSON.stringify(dated));change(bad.quote.metadata.koEvidence);assert(!b.screenshotCurrentState(bad,bundle,now).rows.some(r=>r.label==='SG-KO-Nachweis'));}
console.log('Screenshot current-state tests: OK');


assert(!b.renderScreenshotCurrentState(p,bundle,now).includes('Spread'));
