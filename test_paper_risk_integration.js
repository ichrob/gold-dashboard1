'use strict';
const assert=require('node:assert/strict');
const LateEntry=require('./late_entry_guard.js');
const {evaluate}=require('./background_analysis.js');
const NativeDate=Date,now=Date.parse('2026-11-05T09:12:00Z'),M=60000;
global.Date=class extends NativeDate{
 constructor(...args){super(...(args.length?args:[now]));}
 static now(){return now;}
};
function bundle(){
 const bars={};
 for(const [tf,step] of Object.entries({'5m':5*M,'15m':15*M,'1h':60*M,'4h':240*M})){
  const end=Math.floor(now/step)*step;
  bars[tf]=Array.from({length:240},(_,i)=>({
   openTime:end-(240-i)*step,open:4100-i*.1,high:4104-i*.1,
   low:4096-i*.1,close:4100-i*.1+Math.sin(i/8),
   isOpen:false,providerIsOpen:false,estimated:false,instrument:'XAU/USD',
   source:tf==='5m'?'biquote · XAU/USD Broker/MT5':'XAUS · datierte XAU/USD-Historie'
  }));
 }
 // An observed missing 15m period invalidates ONLY the normal strict 15m
 // stop/target. It must not be silently treated as a real close.
 bars['15m'].splice(-20,1);
 return {spots:{xaus:4076,is_genuine_xauusd_spot:true,
   spot_price_as_of:new Date(now-15000).toISOString()},
  history:{bars_by_tf:bars}};
}
const learningPolicy={campaign:'entry-filter-v1-20261009',base:'intraday-trend-follow-v7',
 variant:'baseline',version:'baseline',issuedAt:now,expiresAt:now+120000};
const original={check:LateEntry.check,checkPaperCampaign:LateEntry.checkPaperCampaign};
try{
 LateEntry.check=()=>({allowed:false,reason:'Live-Einstiegszeit nicht bestätigt'});
 LateEntry.checkPaperCampaign=(b,d,t,at,profile)=>({
  allowed:true,paperOnly:true,paperProfile:profile,spotDistance:profile==='trend800nov'?1.25:1.4,
  maxSignalMinutes:30,maxDeviationAtr:1.5,reason:'Nur Paper-Test'});
 const b=bundle(),result=evaluate({bundle:b,learningPolicy,
  handsetPlanSettings:{trailAtr:1.5,minRR:2}});
 assert.equal(result.paperRiskReference.available,true,JSON.stringify(result.paperRiskReference));
 assert.equal(result.paperRiskReference.timeframe,'5m');
 assert.equal(result.paperRiskReference.confirmedBars,40);
 assert.equal(result.atr,null,'main 15m stop/target must remain unavailable');
 assert.equal(result.direction,'SHORT','test fixture should retain original directional signal');
 assert.equal(result.referencePlan,null,'live reference must not inherit paper fallback');
 assert.equal(result.plan,null,'live entry gate remains blocked');
 const handset=result.handsetPlans.SHORT;
 assert.equal(handset.available,true,JSON.stringify(handset));
 assert.equal(handset.paperOnly,true);
 assert.equal(handset.modelReferenceOnly,true);
 assert.equal(handset.riskTimeframe,'5m');
 assert.equal(handset.entryApproved,false);
 assert.equal(handset.productApproved,false);
 assert.equal(handset.executable,false);
 assert.equal(handset.copyAllowed,false);
 for(const name of ['trend800nov','normal1000nov']){
  const paper=result.paperCampaignEntries[name];
  assert.equal(paper.paperOnly,true);
  const ref=paper.plan||paper.preparation?.plan;
  assert(ref,'validated paper 5m bars should support a calculated risk corridor: '+name+' '+paper.preparation?.reason);
  assert.equal(ref.direction,'SHORT');
  assert(ref.stop>ref.entry&&ref.entry>ref.target);
  assert.equal(paper.preparation.entryApproved,false);
  assert.equal(paper.preparation.productApproved,false);
 }
 const untrusted=bundle();
 untrusted.history.bars_by_tf['5m'][227].estimated=true;
 const rejected=evaluate({bundle:untrusted,learningPolicy});
 assert.equal(rejected.paperRiskReference.available,false);
 assert.equal(rejected.referencePlan,null);
 const spotFail=bundle();spotFail.spots.spot_price_as_of=new Date(now-61000).toISOString();
 const noSpot=evaluate({bundle:spotFail,learningPolicy});
 assert.equal(noSpot.plan,null);
 assert.equal(noSpot.paperCampaignEntries.normal1000nov.plan,null);
}finally{
 LateEntry.check=original.check;
 LateEntry.checkPaperCampaign=original.checkPaperCampaign;
 global.Date=NativeDate;
}
console.log('Paper only fallback integrates stop/target without promoting live trades or invalid originals');
