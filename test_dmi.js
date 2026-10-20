const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(__dirname+'/Bob.html','utf8');
for(const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
const source=html.slice(html.indexOf('function dmiCalc('),html.indexOf('function confirmedMarketStructure'));
const ctx={};vm.createContext(ctx);vm.runInContext(source,ctx);
const now=1800000000000;
function rows(step,sign=1){const end=Math.floor(now/step)*step;return Array.from({length:100},(_,i)=>{const price=2000+sign*i;return {openTime:end-(100-i)*step,open:price,close:price,high:price+1,low:price-1,instrument:'XAU/USD',isOpen:false};});}
const up=ctx.dmiCalc(rows(300000)),down=ctx.dmiCalc(rows(300000,-1));
assert(up.plusDI>up.minusDI);assert(down.minusDI>down.plusDI);assert(Math.abs(up.adx-down.adx)<1e-10);assert.equal(up.adx,100);
assert.equal(ctx.dmiCalc([]).available,false);
const flat=rows(300000).map(b=>({...b,open:2000,high:2000,low:2000,close:2000}));assert.equal(ctx.dmiCalc(flat).adx,0);
const bundle={history:{bars_by_tf:Object.fromEntries(Object.entries({'5m':300000,'15m':900000,'1h':3600000}).map(([k,v])=>[k,rows(v)]))}};
const baseline=JSON.stringify(ctx.dmiContext(bundle,now));assert(ctx.dmiContext(bundle,now).available);
const recovered=JSON.parse(JSON.stringify(bundle));
// An old session break must not invalidate 79 subsequent confirmed candles.
recovered.history.bars_by_tf['1h'].splice(20,1);
assert(ctx.dmiContext(recovered,now).available);
const recentGap=JSON.parse(JSON.stringify(bundle));
recentGap.history.bars_by_tf['1h'].splice(80,1);
assert.equal(ctx.dmiContext(recentGap,now).available,false);
bundle.history.bars_by_tf['5m'].push({...rows(300000).at(-1),openTime:now,close:99999,isOpen:true});assert.equal(JSON.stringify(ctx.dmiContext(bundle,now)),baseline);
bundle.history.bars_by_tf['15m'].splice(90,1);assert.equal(ctx.dmiContext(bundle,now).available,false);
assert.equal(ctx.dmiContext(bundle,now+7200000).available,false);
console.log('DMI tests passed: direction symmetry, ADX, flat/short history, closed bars, gaps, freshness, script syntax');

// Known weekday maintenance hour is accepted only for the observed hourly feeds.
const prior={openTime:Date.parse('2026-10-19T20:00:00Z'),source:'biquote · XAU/USD Broker/MT5'};
const after={...prior,openTime:Date.parse('2026-10-19T22:00:00Z')};
assert(ctx.dmiAdjacent(prior,after,3600000));
assert(!ctx.dmiAdjacent({...prior,source:'unknown'},{...after,source:'unknown'},3600000));
assert(!ctx.dmiAdjacent({...prior,openTime:prior.openTime-3600000},{...after,openTime:after.openTime-3600000},3600000));
assert(!ctx.dmiAdjacent(prior,after,300000));
assert(!ctx.dmiAdjacent(prior,{...after,openTime:after.openTime+3600000},3600000));
// New York winter time: pause moves to 22:00 UTC, not a fixed UTC hour.
assert(ctx.dmiAdjacent({...prior,openTime:Date.parse('2026-11-02T21:00:00Z')},{...after,openTime:Date.parse('2026-11-02T23:00:00Z')},3600000));
const sessionNow=Date.parse('2026-10-20T07:30:00Z');
const hourly=Array.from({length:80},(_,i)=>({...prior,openTime:Date.parse('2026-10-20T06:00:00Z')-(79-i)*3600000,open:2000+i,high:2002+i,low:1999+i,close:2001+i,instrument:'XAU/USD',isOpen:false})).filter(b=>new Date(b.openTime).getUTCHours()!==21);
const state=ctx.dmiContext({history:{bars_by_tf:{'1h':hourly}}},sessionNow);
assert(state.frames['1h'].available);assert(state.frames['1h'].sessionBreaks>0);
hourly.splice(hourly.length-5,1);
assert(!ctx.dmiContext({history:{bars_by_tf:{'1h':hourly}}},sessionNow).frames['1h'].available);
