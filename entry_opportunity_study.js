// Frozen prospective hypotheses. No live signals, orders or account mutations.
'use strict';
const Late=require('./late_entry_guard.js');
const VERSION='entry-opportunities-v1';
const ARMS={reference:{distance:1.5,age:15},distance25:{distance:2.5,age:15},
  age20:{distance:1.5,age:20},combined:{distance:2.5,age:20},
  minute:{distance:1.5,age:15,minute:true},zones:{distance:1.5,age:15,zones:true}};
const positive=x=>Number.isFinite(x)&&x>0;
function zones(side,plan,riskData){
  if(!riskData?.available||!positive(riskData.atr)||!Array.isArray(riskData.bars))return null;
  const bars=riskData.bars.slice(-180),sign=side==='LONG'?1:-1,key=sign>0?'high':'low';
  if(bars.length<40)return null;
  const width=.2*riskData.atr,levels=[];
  // Two neighbours on EACH side confirm a pivot. Separate touches by >=3 bars.
  for(let i=2;i<bars.length-2;i++){
    const value=bars[i][key];
    if([-2,-1,1,2].every(j=>sign*(value-bars[i+j][key])>0)){
      const group=levels.find(g=>Math.abs(g.value-value)<=width);
      if(group){if(i-group.last>=3){group.touches++;group.last=i;}}
      else levels.push({value,touches:1,last:i});
    }
  }
  // The outer 40-bar boundary remains a strong obstacle even with one touch.
  const boundary=(sign>0?Math.max:Math.min)(...bars.slice(-40).map(b=>b[key]));
  levels.push({value:boundary,touches:2,last:bars.length-1});
  const strong=levels.filter(g=>g.touches>=2 &&
    !bars.slice(-2).every(b=>sign*(b.close-g.value)>width) &&
    sign*(g.value-plan.entry)>0 && sign*(plan.target-g.value)>=0);
  const obstacle=strong.length?(sign>0?Math.min:Math.max)(...strong.map(g=>g.value)):null;
  const risk=Math.abs(plan.entry-plan.stop);
  return {entrySuitable:obstacle===null||Math.abs(obstacle-plan.entry)/risk>=2,
    obstacle,weakZones:levels.filter(g=>g.touches===1).length,strongZones:strong.length};
}
function evaluate({bundle,direction,now,confirmationAt,ready,rawReason,riskData,makePlan}){
  const out={version:VERSION,comparisonOnly:true,liveRulesChanged:false,realOrders:false,
    checkedAt:now,direction,confirmationAt,sourceAt:Date.parse(bundle.spots?.spot_price_as_of||''),
    reason:String(rawReason||'').slice(0,250),arms:{}};
  if(!ready||!['LONG','SHORT'].includes(direction))return {...out,status:'waiting-for-input-or-direction'};
  // Called independently of the live plan: a rejected baseline cannot erase a trial.
  const p=makePlan(direction),sign=direction==='LONG'?1:-1;
  const valid=['entry','stop','target'].every(k=>positive(p[k]))&&
    sign*(p.entry-p.stop)>0&&sign*(p.target-p.entry)>=2*Math.abs(p.entry-p.stop);
  for(const [id,cfg] of Object.entries(ARMS)){
    const gate=Late.checkStudy(bundle,direction,now,confirmationAt,cfg);
    const zone=cfg.zones&&valid?zones(direction,p,riskData):null;
    const suitable=cfg.zones?zone?.entrySuitable===true:p.available===true&&p.entrySuitable===true;
    const allowed=valid&&gate.allowed===true&&suitable;
    out.arms[id]={allowed,reason:!gate.allowed?gate.reason:!valid?'risk-plan-unavailable':
      !suitable?'target-obstacle':'eligible',gate:{deviationAtr:gate.deviationAtr??null,
      atr5m:gate.atr5m??null,signalAgeMinutes:gate.signalAgeMinutes??null,
      barAt:gate.barAt??null,setup:gate.setup??null},zone,
      plan:allowed?{direction,entry:p.entry,stop:p.stop,target:p.target}:null};
    if(Number.isFinite(gate.barAt))out.barAt=gate.barAt;
  }
  out.status='observed';return out;
}
module.exports={VERSION,ARMS,zones,evaluate};
