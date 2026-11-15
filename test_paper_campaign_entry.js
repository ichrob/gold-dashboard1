'use strict';
const assert=require('node:assert/strict');
const guard=require('./late_entry_guard.js');
const M=60000, now=Date.UTC(2026,10,13,14,0,0);
function bundle(side){
  const sign=side==='LONG'?1:-1, bars={};
  for(const [tf,step] of Object.entries({'5m':5*M,'15m':15*M})){
    const start=now-100*step;
    bars[tf]=Array.from({length:100},(_,i)=>{
      const close=3900+sign*i*.04,open=close-sign*.02;
      return {openTime:start+i*step,open,close,high:Math.max(open,close)+.5,
        low:Math.min(open,close)-.5,isOpen:false,instrument:'XAU/USD'};
    });
  }
  return {spots:{xaus:bars['5m'].at(-1).close+sign*.01,
    spot_price_as_of:new Date(now-10000).toISOString(),
    is_genuine_xauusd_spot:true,spot_error:null},
    history:{bars_by_tf:bars}};
}
for(const side of ['LONG','SHORT']){
  const sign=side==='LONG'?1:-1,b=bundle(side);
  const initial=guard.check(b,side,now,now-5*M);
  assert.equal(initial.allowed,true,side+' baseline valid: '+initial.reason);
  const atr=initial.atr5m,last=b.history.bars_by_tf['5m'].at(-1);
  function atDistance(r){
    const copy=structuredClone(b);
    copy.spots.xaus=last.close+sign*r*atr;
    return copy;
  }
  const d09=atDistance(.9);
  assert.equal(guard.check(d09,side,now,now-5*M).allowed,false);
  assert.equal(guard.checkPaperCampaign(d09,side,now,now-5*M,'trend800nov').allowed,true);
  assert.equal(guard.checkPaperCampaign(d09,side,now,now-5*M,'normal1000nov').allowed,true);
  const d11=atDistance(1.1);
  assert.equal(guard.checkPaperCampaign(d11,side,now,now-5*M,'trend800nov').allowed,false);
  assert.equal(guard.checkPaperCampaign(d11,side,now,now-5*M,'normal1000nov').allowed,true);
  assert.equal(guard.checkPaperCampaign(atDistance(1.3),side,now,now-5*M,'normal1000nov').allowed,false);
  for(const profile of ['trend800nov','normal1000nov']){
    const active=guard.checkPaperCampaign(b,side,now,now-19*M,profile);
    assert.equal(active.allowed,true,profile+' 19m: '+active.reason);
    assert.equal(active.paperOnly,true);
    assert.equal(active.maxSignalMinutes,20);
    assert.equal(guard.checkPaperCampaign(b,side,now,now-21*M,profile).allowed,false);
    assert.equal(guard.check(b,side,now,now-19*M).allowed,false,'live still 15m');
    const stale=structuredClone(b);
    stale.spots.spot_price_as_of=new Date(now-61000).toISOString();
    assert.equal(guard.checkPaperCampaign(stale,side,now,now-3*M,profile).allowed,false);
    const estimated=structuredClone(b);
    estimated.history.bars_by_tf['5m'].at(-1).estimated=true;
    assert.equal(guard.checkPaperCampaign(estimated,side,now,now-3*M,profile).allowed,false);
    const forged=structuredClone(b);
    forged.spots.is_genuine_xauusd_spot=false;
    assert.equal(guard.checkPaperCampaign(forged,side,now,now-3*M,profile).allowed,false);
  }
  // Two original 1m closes beyond the last checked 5m range create a NEW,
  // short-lived window without altering the old 15m signal clock.
  const b1=structuredClone(b),five=b1.history.bars_by_tf['5m'].at(-1);
  const min=(t,open,close)=>({openTime:t,open,close,
    high:Math.max(open,close)+.02,low:Math.min(open,close)-.02,
    isOpen:false,instrument:'XAU/USD'});
  const firstOpen=five.close+sign*.7,firstClose=five.close+sign*1.0,secondClose=five.close+sign*1.1;
  b1.history.bars_by_tf['1m']=[min(now,firstOpen,firstClose),min(now+M,firstClose,secondClose)];
  b1.spots.xaus=secondClose+sign*.01;
  const later=now+2*M;
  b1.spots.spot_price_as_of=new Date(later-10000).toISOString();
  for(const profile of ['trend800nov','normal1000nov']){
    const verified=guard.checkPaperCampaign(b1,side,later,now-31*M,profile);
    assert.equal(verified.allowed,true,profile+' minute '+side+': '+verified.reason);
    assert.equal(verified.setup,'fresh-1m-continuation');
    assert.equal(verified.freshContinuationAt,later);
    assert.equal(verified.signalAgeMinutes,33);
    const fake=structuredClone(b1);
    fake.history.bars_by_tf['1m'].at(-1).estimated=true;
    assert.equal(guard.checkPaperCampaign(fake,side,later,now-31*M,profile).allowed,false);
  }
  assert.equal(guard.check(b1,side,later,now-31*M).allowed,false,'live age cannot be bypassed');
}
assert.throws(()=>guard.checkPaperCampaign(bundle('LONG'),'LONG',now,now-5*M,'ema3000nov'),/Unknown paper/);
console.log('800/1000 EUR paper ATR, 20m, closed 1m re-entry, stale protection, baseline isolation OK');
