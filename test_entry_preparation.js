const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const NativeDate=Date,now=Date.parse('2026-11-05T09:12:00Z');
global.Date=class extends NativeDate{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}};
const late=require('./late_entry_guard'),original=late.check;
const {evaluate}=require('./background_analysis');
const bars={};
for(const [tf,step] of Object.entries({'5m':300000,'15m':900000,'1h':3600000,'4h':14400000})){
 const end=Math.floor(now/step)*step;
 bars[tf]=Array.from({length:240},(_,i)=>({openTime:end-(240-i)*step,
  open:4100-i*.1,high:4104-i*.1,low:4096-i*.1,close:4100-i*.1+Math.sin(i/8),isOpen:false,instrument:'XAU/USD'}));
}
const bundle={spots:{xaus:4076,is_genuine_xauusd_spot:true,spot_price_as_of:new Date(now).toISOString()},history:{bars_by_tf:bars}};
const learningPolicy={campaign:'entry-filter-v1-20261009',base:'intraday-trend-follow-v7',variant:'baseline',version:'baseline',issuedAt:now,expiresAt:now+120000};
try{
 late.check=()=>({allowed:false,reason:'Bestätigung ist zu alt'});
 const blocked=evaluate({bundle,learningPolicy});
 assert.equal(blocked.direction,'SHORT');assert.equal(blocked.plan,null);
 assert.equal(blocked.entryPlanState.code,'ENTRY_TIMING');
 assert.equal(blocked.entryPlanState.reason,'Bestätigung ist zu alt');
 assert.equal(blocked.entryPreparation.entryApproved,false);
 assert.equal(blocked.entryPreparation.productApproved,false);
 assert.equal(blocked.entryPreparation.positionSize,null);
 const stale=evaluate({learningPolicy,bundle:{...bundle,spots:{...bundle.spots,spot_error:'offline'}}});
 assert.equal(stale.plan,null);assert.equal(stale.entryPreparation.plan,null);
}finally{late.check=original;}
const html=fs.readFileSync('Bob.html','utf8'),start=html.indexOf('function earlyPreparationText('),end=html.indexOf('function renderEarlyImpulseStatus()',start);
const context={Date,Number,$:()=>null,intradayRiskData:()=>({available:true,atr:10}),stopModel:()=>({stop:3990}),targetModel:()=>({target:4020,entrySuitable:true})};
vm.createContext(context);vm.runInContext(html.slice(start,end),context);
const warning={available:true,state:'active',direction:'LONG',expiresAt:now+60000};
const current={spots:{xaus:4000,is_genuine_xauusd_spot:true,spot_price_as_of:new Date(now).toISOString()}};
assert(context.earlyPreparationText(warning,current,now).includes('Gold-Stopp 3990.00'));
assert.equal(context.earlyPreparationText({...warning,state:'withdrawn'},current,now),'');
assert.equal(context.earlyPreparationText({...warning,expiresAt:now},current,now),'');
assert(!context.earlyPreparationText(warning,{spots:{...current.spots,spot_error:'offline'}},now).includes('3990'));
context.targetModel=()=>({target:4020,entrySuitable:false,warning:'Widerstand vor dem Ziel'});
assert(context.earlyPreparationText(warning,current,now).includes('Widerstand vor dem Ziel'));
assert(!context.earlyPreparationText(warning,current,now).includes('Gold-Stopp'));
console.log('Entry timing reasons, advisory preparation, original source freshness and obstacle guard passed.');
