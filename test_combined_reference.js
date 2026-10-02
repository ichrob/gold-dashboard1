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
for(const isin of ['DE000FG4JXV7','DE000FG7EPT1','DE000FG5GUT0']){const next=clone(p);next.isin=isin;next.quote.isin=isin;next.quote.productModel.isin=isin;const ref=clone(r);ref.isin=isin;ref.barriers.forEach(x=>x.isin=isin);products.push(next);refs.push(ref);}
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
