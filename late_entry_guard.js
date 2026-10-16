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
 const initial={version:'late-entry-v1',available:false,allowed:false,late:false,
                reason:'Keine geprüfte Einstiegschance',mode:'ABWARTEN',maxDeviationAtr:1.5,
                maxImpulseAtr:2.5,maxSignalMinutes:15};
 function gate(bundle,direction,now=Date.now(),confirmedAt=null){
   const fail=reason=>({...initial,reason});
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
     if(rows.some((b,i)=>b.instrument!=='XAU/USD'||b.estimated===true||b.openTime%step!==0
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
   if(Math.abs(spot.xaus-latest.close)>atr*0.80)
     return fail('Aktueller Spot und letzter Kerzenschluss weichen über 0,8 ATR ab');
   const deviation=sign*(spot.xaus-ema20)/atr;
   const impulse=sign*(latest.close-bars.at(-4).close)/atr;
   const age=finite(confirmedAt)&&confirmedAt>0
      ?Math.max(0,(now-confirmedAt)/60000):null;
   const prev=bars.at(-2),prev2=bars.at(-3);
   // A new, CLOSED pullback-and-resumption is a fresh opportunity, even in an
   // older trend. It is not inferred from a still-forming candle.
   const reset=sign*(prev.low-ema20)<=0.65*atr &&
      sign*(latest.close-prev.close)>0 &&
      sign*(latest.close-latest.open)>0 &&
      sign*(prev2.close-prev.close)>0 &&
      deviation>=-0.25&&deviation<=0.80&&impulse<1.20;
   const reasons=[];
   if(deviation>1.5)reasons.push('Preis über 1,5 ATR von EMA20 in Trendrichtung entfernt');
   if(impulse>2.5&&deviation>0.80)reasons.push('Bewegung der letzten 3×5m-Kerzen bereits über 2,5 ATR');
   if((age===null||age>15)&&!reset)
     reasons.push(age===null?'Signalzeit unbekannt; kein neues bestätigtes Rücksetzer-Setup':
                            'Bestätigtes Einstiegssignal älter als 15 Minuten ohne neuen Rücksetzer');
   const metrics={...initial,available:true,late:reasons.length>0,allowed:reasons.length===0,
       mode:reasons.length?'ABWARTEN':'EINSTIEGSFENSTER',direction,
       reason:reasons.join(' · ')||(reset?'Neuer Rücksetzer mit bestätigter Fortsetzung':
                                  'Bestätigung aktuell, Bewegung nicht überdehnt'),
       deviationAtr:Math.round(deviation*100)/100,impulseAtr:Math.round(impulse*100)/100,
       signalAgeMinutes:age===null?null:Math.round(age*10)/10,
       pullbackReset:reset,atr5m:atr,barAt:latest.openTime,
       priceAt:closeTime,reference:spot.xaus};
   return metrics;
 }
 return {check:gate};
});
