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
const bad=clone(p);bad.quote.calculatedProduct.fxDataAt=at(-61);assert.equal(b.assess(bad,r,bundle,now).estimated,false);
assert.equal(b.assess({...p,isinConfirmed:false},r,bundle,now).ko,null);
assert.equal(b.assess(p,r,bundle,now+1801000).quote,null);
const crossed=clone(bundle);crossed.spots.xaus=4500;assert(b.assess(p,r,crossed,now).distanceUsd<0);assert.equal(b.assess(p,r,crossed,now).estimated,false);
assert.equal(b.assess({...p,isin:'DE000FG309G0'}, {...r,isin:'DE000FG309G0'},bundle,now).basis,null);
assert(b.render(s).includes('Schätzung, keine SG-Quotierung'));assert(b.render(s).includes('Keine Live-Freigabe'));
const hostile=clone(r);hostile.venue='<script>alert(1)</script>';assert(!b.render(b.assess(p,hostile,bundle,now)).includes('<script>'));
console.log('Combined manual references: passed');
