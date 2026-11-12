const assert=require('node:assert/strict');
const NativeDate=Date,now=Date.parse('2026-11-12T12:00:00Z');
global.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}};
const opportunity=require('./entry_opportunity_study');
const {evaluate}=require('./background_analysis');
const frames={};
for(const [tf,step] of Object.entries({'5m':300000,'15m':900000,'1h':3600000,'4h':14400000})){
 const end=Math.floor(now/step)*step;
 frames[tf]=Array.from({length:240},(_,i)=>({openTime:end-(240-i)*step,
   open:4100-i*.1,close:4100-i*.1+Math.sin(i/8),high:4104-i*.1,low:4096-i*.1,
   isOpen:false,instrument:'XAU/USD'}));
}
const input={bundle:{spots:{xaus:frames['5m'].at(-1).close,is_genuine_xauusd_spot:true,
 spot_price_as_of:new Date(now).toISOString()},history:{bars_by_tf:frames}},
 learningPolicy:{campaign:'entry-filter-v1-20261009',base:'intraday-trend-follow-v7',
 variant:'baseline',version:'baseline',issuedAt:now,expiresAt:now+120000}};
const normal=evaluate(input);
assert.equal(normal.entryOpportunityStudy.version,opportunity.VERSION);
assert.equal(normal.entryOpportunityStudy.status,'observed');
assert.equal(Object.keys(normal.entryOpportunityStudy.arms).length,6);
assert.equal(normal.entryTimingGate.maxDeviationAtr,1.5);
opportunity.evaluate=()=>{throw Error('isolated study fault');};
const isolated=evaluate(input);
assert.equal(isolated.entryOpportunityStudy.status,'unavailable');
delete normal.entryOpportunityStudy;delete isolated.entryOpportunityStudy;
assert.deepEqual(JSON.parse(JSON.stringify(normal)),JSON.parse(JSON.stringify(isolated)));
console.log('Entry opportunity runtime: six independent arms, unchanged live calculation and isolated faults OK');
