'use strict';
// Independent, PAPER-ONLY risk reference. It never authorizes a broker fill,
// replaces the normal 15m trade plan, or manufactures any missing candles.
const SOURCES=new Set([
 'biquote · XAU/USD Broker/MT5',
 'XAUS · datierte XAU/USD-Historie'
]);
const STEP=300000, COUNT=40;
function unavailable(reason){
 return {available:false,paperOnly:true,timeframe:'5m',basis:'closed-original-5m-v1',
   reason,confirmedBars:0};
}
function forPaper(bundle,now,primaryRisk,atrFn){
 // The normal 15m risk basis always takes precedence when it is available.
 if(primaryRisk&&primaryRisk.available===true)
   return {...primaryRisk,paperOnly:true,basis:'original-15m-primary'};
 if(!Number.isFinite(now)||typeof atrFn!=='function')
   return unavailable('Paper-Stopp/Ziel: gültige Zeit oder ATR-Funktion fehlt');
 const raw=bundle?.history?.bars_by_tf?.['5m'];
 if(!Array.isArray(raw))return unavailable('Paper-Stopp/Ziel: originale 5m-Kerzen fehlen');
 // These are 40 provider-confirmed closes, not locally closed or interpolated bars.
 const rows=raw.filter(b=>b?.isOpen===false&&b.providerIsOpen!==true&&
   Number.isFinite(b.openTime)&&b.openTime+STEP<=now).slice(-COUNT);
 if(rows.length!==COUNT)return unavailable('Paper-Stopp/Ziel: weniger als 40 geschlossene Original-5m-Kerzen');
 const source=rows[0].source;
 if(!SOURCES.has(source))return unavailable('Paper-Stopp/Ziel: 5m-Quellenidentität unbekannt');
 const valid=rows.every((b,i)=>b.source===source&&b.instrument==='XAU/USD'&&
   b.estimated!==true&&b.openTime%STEP===0&&
   ['open','high','low','close'].every(k=>typeof b[k]==='number'&&Number.isFinite(b[k])&&b[k]>0)&&
   b.low<=Math.min(b.open,b.close)&&b.high>=Math.max(b.open,b.close)&&
   b.low<=b.high&&(!i||b.openTime-rows[i-1].openTime===STEP));
 if(!valid)return unavailable('Paper-Stopp/Ziel: Original-5m-Kerzen lückenhaft oder ungeprüft');
 if(now-rows.at(-1).openTime>2*STEP)
   return unavailable('Paper-Stopp/Ziel: letzte Original-5m-Kerze nicht aktuell');
 const volatility=atrFn(rows);
 if(!(typeof volatility==='number'&&Number.isFinite(volatility)&&volatility>0))
   return unavailable('Paper-Stopp/Ziel: 5m-ATR nicht gültig berechenbar');
 return {available:true,paperOnly:true,liveTradeApproved:false,estimated:false,
   bars:rows,atr:volatility,timeframe:'5m',basis:'closed-original-5m-v1',
   source,sourceAt:rows.at(-1).openTime,confirmedBars:COUNT,
   reason:'Separater 5m-Modellrisikoplan aus 40 originalen Schlusskerzen – keine Live-Freigabe'};
}
module.exports={forPaper};
