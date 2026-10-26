const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(__dirname+'/Bob.html','utf8');
for(const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
const source=html.slice(html.indexOf('function dmiCalc('),html.indexOf('function confirmedMarketStructure'));
const ctx={};vm.createContext(ctx);vm.runInContext(source,ctx);
const now=1800000000000;
function rows(step,sign=1){const end=Math.floor(now/step)*step;return Array.from({length:100},(_,i)=>{const price=2000+sign*i;return {openTime:end-(100-i)*step,open:price,close:price,high:price+1,low:price-1,instrument:'XAU/USD',source:'biquote · XAU/USD Broker/MT5',isOpen:false};});}
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
const unlike=JSON.parse(JSON.stringify(bundle));
unlike.history.bars_by_tf['1h'].at(-8).source='XAUS · datierte XAU/USD-Historie';
const unlikeState=ctx.dmiContext(unlike,now);
assert.equal(unlikeState.frames['1h'].available,false,'mixed 1h sources must not be analysed as continuous');
assert.match(unlikeState.frames['1h'].reason,/Kerzenquelle/);
const unproven=JSON.parse(JSON.stringify(bundle));
delete unproven.history.bars_by_tf['5m'][95].source;
assert.equal(ctx.dmiContext(unproven,now).frames['5m'].available,false,'original source required');
const providerOpen=JSON.parse(JSON.stringify(bundle));
providerOpen.history.bars_by_tf['15m'][80].providerIsOpen=true;
assert.equal(ctx.dmiContext(providerOpen,now).frames['15m'].available,false,'provider-open bar must not act as closed');
const shortHistory=JSON.parse(JSON.stringify(bundle));
shortHistory.history.bars_by_tf['1h']=shortHistory.history.bars_by_tf['1h'].slice(-14);
const shortage=ctx.dmiContext(shortHistory,now);
assert.equal(shortage.frames['1h'].available,false);
assert.equal(shortage.frames['1h'].confirmedClosedBars,14);
assert.match(shortage.frames['1h'].reason,/14 zusammenhängende Original-Schlusskerzen/);

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

// Actual XAUS weekend boundary observed independently on 2026-10-26.
const friday={openTime:Date.parse('2026-10-23T20:00:00Z'),source:'XAUS · datierte XAU/USD-Historie'};
const sunday={...friday,openTime:Date.parse('2026-10-25T22:00:00Z')};
assert(ctx.dmiAdjacent(friday,sunday,3600000));
assert(!ctx.dmiAdjacent({...friday,source:'biquote · XAU/USD Broker/MT5'},{...sunday,source:'biquote · XAU/USD Broker/MT5'},3600000));
assert(!ctx.dmiAdjacent(friday,{...sunday,openTime:sunday.openTime+3600000},3600000));
assert(!ctx.dmiAdjacent({...friday,openTime:friday.openTime-3600000},sunday,3600000));
assert(!ctx.dmiAdjacent(friday,sunday,300000));
assert(ctx.dmiAdjacent({...friday,openTime:Date.parse('2026-10-30T20:00:00Z')},{...sunday,openTime:Date.parse('2026-11-01T23:00:00Z')},3600000));
const weekendRows=[...Array.from({length:17},(_,i)=>({...friday,openTime:friday.openTime-(16-i)*3600000})),...Array.from({length:20},(_,i)=>({...sunday,openTime:sunday.openTime+i*3600000}))].map((b,i)=>({...b,open:2000+i,high:2002+i,low:1999+i,close:2001+i,instrument:'XAU/USD',isOpen:false}));
assert(ctx.dmiContext({history:{bars_by_tf:{'1h':weekendRows}}},weekendRows.at(-1).openTime+3600000).frames['1h'].available);
weekendRows.splice(-3,1);
assert(!ctx.dmiContext({history:{bars_by_tf:{'1h':weekendRows}}},weekendRows.at(-1).openTime+3600000).frames['1h'].available);
