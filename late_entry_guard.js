/* Shared Bob late-entry protection. Applies ONLY to NEW entry signals and
   candidate selection. Never changes active trade stops, direction analysis,
   broker orders, old fills or ongoing KO monitoring.
   Heuristic ATR thresholds require prospective validation before optimization. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.BobLateEntryGuard=api;
})(typeof window==='object'?window:null,function(){
 'use strict';
 const STEPS={'5m':300000,'15m':900000};
 const finite=v=>typeof v==='number'&&Number.isFinite(v);
 const pos=v=>finite(v)&&v>0;
 const initial={version:'late-entry-v2',available:false,allowed:false,late:false,
                reason:'Keine geprüfte Einstiegschance',mode:'ABWARTEN',maxDeviationAtr:1.5,maxFreshContinuationDeviationAtr:2.0,
                maxImpulseAtr:2.5,maxSignalMinutes:15};
 function gate(bundle,direction,now=Date.now(),confirmedAt=null,paperOnly=false,noEma=false,study=null){
   const limits=study?{...initial,maxDeviationAtr:study.distance,maxSignalMinutes:study.age,paperOnly:true}:paperOnly?{...initial,maxDeviationAtr:2.5,paperOnly:true}:initial;
   const fail=reason=>({...limits,reason});
   if(study&&Number.isFinite(confirmedAt)&&confirmedAt>now)return fail('Signalzeit liegt in der Zukunft');
   if(!['LONG','SHORT'].includes(direction))return fail('Keine bestätigte Einstiegsrichtung');
   if(!finite(now)||now<=0)return fail('Prüfzeit unbekannt');
   const frames=bundle?.history?.bars_by_tf,spot=bundle?.spots||{},verified={};
   if(!frames)return fail('Geschlossene 5m-/15m-Kerzen fehlen');
   for(const [tf,step] of Object.entries(STEPS)){
     const all=frames[tf];
     if(!Array.isArray(all))return fail(tf+': Kerzen fehlen');
     if(all.some(b=>b&&b.isOpen!==true&&finite(b.openTime)&&b.openTime>now))
       return fail(tf+': Kerzenzeit liegt in der Zukunft');
     const rows=all.filter(b=>b&&!b.isOpen&&finite(b.openTime)&&b.openTime+step<=now).slice(-100);
     if(rows.length<50)return fail(tf+': weniger als 50 geschlossene Kerzen');
     if(rows.some((b,i)=>b.instrument!=='XAU/USD'||b.estimated===true||(study&&b.providerIsOpen===true)||b.openTime%step!==0
          ||!['open','high','low','close'].every(k=>pos(b[k]))
          ||b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close)
          ||(i>0&&b.openTime<=rows[i-1].openTime)))
       return fail(tf+': Basiswert, OHLC oder Zeitstempel ungültig');
     if(rows.slice(-20).some((b,i,a)=>i>0&&b.openTime-a[i-1].openTime!==step))
       return fail(tf+': jüngste Kerzen haben Lücken');
     const age=now-rows.at(-1).openTime-step;
     if(age<0||age>step)return fail(tf+': letzte bestätigte Kerze ist nicht aktuell');
     verified[tf]=rows;
   }
   const closeTime=Date.parse(spot.spot_price_as_of||'');
   if(spot.is_genuine_xauusd_spot!==true||spot.spot_error||!pos(spot.xaus)||
      !finite(closeTime)||closeTime>now||now-closeTime>60000)
     return fail('Gold-Spot nicht aktuell oder Quellenidentität nicht bestätigt');
   const bars=verified['5m'],closes=bars.map(b=>b.close),latest=bars.at(-1),sign=direction==='LONG'?1:-1;
   let ema20=closes[0];
   const alpha=2/21;
   for(const price of closes.slice(1))ema20=price*alpha+ema20*(1-alpha);
   let atr=0;
   for(let i=bars.length-14;i<bars.length;i++){
     const b=bars[i],previous=bars[i-1].close;
     atr+=Math.max(b.high-b.low,Math.abs(b.high-previous),Math.abs(b.low-previous));
   }
   atr/=14;
   if(!pos(atr))return fail('ATR aus geprüften Kerzen nicht berechenbar');
   // Do not classify a new, corroborated minute breakout as a source mismatch.
   // EMA distance, impulse, age and all trade approvals remain checked below.
   if(Math.abs(spot.xaus-latest.close)>atr*0.80 && !minuteConfirmation(bundle,direction,now,latest,spot.xaus,atr))
     return fail('Aktueller Spot und letzter Kerzenschluss weichen über 0,8 ATR ab');
   const deviation=sign*(spot.xaus-ema20)/atr;
   const impulse=sign*(latest.close-bars.at(-4).close)/atr;
   const age=finite(confirmedAt)&&confirmedAt>0
      ?Math.max(0,(now-confirmedAt)/60000):null;
   const prev=bars.at(-2),prev2=bars.at(-3);
   // A new, CLOSED pullback-and-resumption is a fresh opportunity, even in an
   // older trend. It is not inferred from a still-forming candle.
   const reset=sign*((sign>0?prev.low:prev.high)-ema20)<=0.65*atr &&
      sign*(latest.close-prev.close)>0 &&
      sign*(latest.close-latest.open)>0 &&
      sign*(prev2.close-prev.close)>0 &&
      deviation>=-0.25&&deviation<=0.80&&impulse<1.20;
   // A late 15m signal may be followed by an independently NEW, source-verified
   // closed 5m breakout. Never reuse the old confirmation time, an open bar or a wick.
   const minutesSinceFiveClose=(now-latest.openTime-STEPS['5m'])/60000;
   const continuationChecks={
     recentClosedBar:minutesSinceFiveClose>=0&&minutesSinceFiveClose<=1.5,
     distanceWithinTwoAtr:deviation>0&&deviation<=2.0,
     impulseWithinLimit:impulse<=2.5,
     previousCandleAligned:sign*(prev.close-prev.open)>0,
     latestCandleAligned:sign*(latest.close-latest.open)>0,
     previousCloseProgress:sign*(prev.close-prev2.close)>0,
     closedBreakout:sign*(latest.close-(sign>0?prev.high:prev.low))>0,
     minimumFollowThrough:sign*(latest.close-prev.close)>=0.15*atr,
     spotHoldsBreakout:sign*(spot.xaus-latest.close)>=-0.25*atr
   };
   const continuation=Object.values(continuationChecks).every(Boolean);
   const reasons=[];
   if(!noEma&&deviation>limits.maxDeviationAtr&&!continuation)reasons.push('Preis über '+String(limits.maxDeviationAtr).replace('.',',')+' ATR von EMA20 in Trendrichtung entfernt');
   if(impulse>2.5&&deviation>0.80)reasons.push('Bewegung der letzten 3×5m-Kerzen bereits über 2,5 ATR');
   if((age===null||age>limits.maxSignalMinutes)&&!reset&&!continuation)
     reasons.push(age===null?'Signalzeit unbekannt; kein neues bestätigtes Rücksetzer-Setup':
                            'Bestätigtes Einstiegssignal älter als '+limits.maxSignalMinutes+' Minuten ohne neuen Rücksetzer');
   const metrics={...limits,emaDistanceDisabled:noEma,available:true,late:reasons.length>0,allowed:reasons.length===0,
       mode:reasons.length?'ABWARTEN':'EINSTIEGSFENSTER',direction,
       setup:reasons.length?'blocked':continuation?'fresh-5m-continuation':reset?'closed-5m-pullback':'confirmed-main',
       reason:reasons.join(' · ')||(continuation?'Neuer, geschlossener 5m-Folgeimpuls; nicht dem alten 15m-Signal hinterherlaufen':
                                  reset?'Neuer Rücksetzer mit bestätigter Fortsetzung':
                                  'Bestätigung aktuell, Bewegung nicht überdehnt'),
       deviationAtr:Math.round(deviation*100)/100,impulseAtr:Math.round(impulse*100)/100,
       signalAgeMinutes:age===null?null:Math.round(age*10)/10,
       continuationChecks,minutesSinceFiveClose,
       freshContinuation:continuation&&reasons.length===0,
       freshContinuationAt:continuation?latest.openTime+STEPS['5m']:null,
       pullbackReset:reset,atr5m:atr,barAt:latest.openTime,
       priceAt:closeTime,reference:spot.xaus};
   return metrics;
 }
 function minuteConfirmation(bundle,direction,now,five,price,atr){
   const rows=(bundle.history?.bars_by_tf?.['1m']||[]).filter(b=>b?.isOpen===false && b.openTime+60000<=now).slice(-2);
   const sign=direction==='LONG'?1:-1;
   if(rows.length!==2||rows.some(b=>b.instrument!=='XAU/USD'||b.estimated===true||b.providerIsOpen===true||
     !Number.isFinite(b.openTime)||b.openTime%60000!==0||!['open','high','low','close'].every(k=>pos(b[k]))||
     b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close)))return false;
   const [a,b]=rows;
   return a.openTime>=five.openTime+300000 && b.openTime-a.openTime===60000 &&
     now-b.openTime-60000>=0 && now-b.openTime-60000<=60000 &&
     sign*(a.close-a.open)>0 && sign*(b.close-b.open)>0 && sign*(b.close-a.close)>0 &&
     sign*(a.close-(sign>0?five.high:five.low))>0 &&
     sign*(price-b.close)>=-0.25*atr && Math.abs(price-b.close)<=0.25*atr;
 }
 return {checkStudy:(bundle,direction,now,confirmedAt,options)=>{
   if(!options||![1.5,2.5].includes(options.distance)||![15,20].includes(options.age))throw Error('Unknown study thresholds');
   return gate(bundle,direction,now,confirmedAt,false,false,options);
 },checkPaperNoEma:(bundle,direction,now,confirmedAt)=>gate(bundle,direction,now,confirmedAt,false,true),
   check:(bundle,direction,now,confirmedAt)=>gate(bundle,direction,now,confirmedAt),
   checkPaper25:(bundle,direction,now,confirmedAt)=>gate(bundle,direction,now,confirmedAt,true)};
});
