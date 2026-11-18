'use strict';
// Standalone, forward-only PAPER hypothesis: two original closed 5m candles
// agreeing with the confirmed higher trend. NEVER changes main signal/KO rules.
const VERSION='two-closed-5m-paper-v1';
const SOURCE='two-candle-5m-paper-v1';
const STEP=300000, FIFTEEN=900000;
const SOURCES=new Set(['biquote · XAU/USD Broker/MT5','XAUS · datierte XAU/USD-Historie']);
const number=x=>typeof x==='number'&&Number.isFinite(x);
const positive=x=>number(x)&&x>0;
function evaluate({bundle,now,ready,priceFresh,price,trendContext,dmi,paperRisk,makePlan}={}){
 const base={version:VERSION,source:SOURCE,paperOnly:true,comparisonOnly:true,
  realOrders:false,liveRulesChanged:false,entryApproved:false,productApproved:false,
  status:'waiting',reason:'Noch keine bestätigten zwei Original-5m-Kerzen im Haupttrend',
  direction:'NEUTRAL',plan:null,barAt:null,sourceAt:null};
 const wait=reason=>({...base,reason});
 if(!number(now)||!positive(price)||ready!==true||priceFresh!==true)
  return wait('Marktdaten oder aktuelle Analyse nicht bestätigt');
 const at=Date.parse(bundle?.spots?.spot_price_as_of||'');
 if(bundle?.spots?.is_genuine_xauusd_spot!==true||bundle?.spots?.spot_error||
    !number(at)||at>now||now-at>60000||Math.abs(bundle.spots.xaus-price)>.01)
  return wait('Original-Gold-Spot und Quellenzeit nicht frisch und identisch');
 if(trendContext?.available!==true||trendContext?.intact!==true||
    !['LONG','SHORT'].includes(trendContext.direction))
  return wait('Übergeordneter Trend nicht eindeutig bestätigt');
 const direction=trendContext.direction,sign=direction==='LONG'?1:-1;
 const frame15=dmi?.frames?.['15m'],frame1h=dmi?.frames?.['1h'];
 if(frame15?.available!==true||frame1h?.available!==true||
    (frame15.direction!=='NEUTRAL'&&frame15.direction!==direction)||
    frame1h.direction!==direction)
  return wait('15m/1h-Trend widerspricht oder fehlt');
 const sourceBars=bundle?.history?.bars_by_tf,all=sourceBars?.['5m'],all15=sourceBars?.['15m'];
 if(!Array.isArray(all)||!Array.isArray(all15))
  return wait('Original-5m-/15m-Kerzen fehlen');
 const valid=(b,step)=>b?.isOpen===false&&b.providerIsOpen!==true&&
   SOURCES.has(b.source)&&b.instrument==='XAU/USD'&&b.estimated!==true&&
   number(b.openTime)&&b.openTime%step===0&&b.openTime+step<=now&&
   ['open','high','low','close'].every(k=>positive(b[k]))&&
   b.low<=Math.min(b.open,b.close)&&b.high>=Math.max(b.open,b.close)&&b.low<=b.high;
 const rows=all.filter(b=>valid(b,STEP)).slice(-2),rows15=all15.filter(b=>valid(b,FIFTEEN)).slice(-1);
 if(rows.length!==2||rows15.length!==1)return wait('Zu wenige geschlossene originale 5m-/15m-Kerzen');
 const [previous,current]=rows,latest15=rows15[0];
 if(current.openTime-previous.openTime!==STEP||current.source!==previous.source||
    now-current.openTime-STEP<0||now-current.openTime-STEP>=STEP||
    now-latest15.openTime-FIFTEEN<0||now-latest15.openTime-FIFTEEN>=FIFTEEN)
  return wait('Zwei lückenlose jüngste 5m-Schlusskerzen und aktuelle 15m-Schlusskerze erforderlich');
 // The last two eligible closes must also be the last *actual* closed rows:
 // otherwise skipping a malformed newer candle could create a fake entry.
 const last5=all.filter(b=>b?.isOpen===false&&number(b.openTime)&&b.openTime+STEP<=now).at(-1);
 const last15=all15.filter(b=>b?.isOpen===false&&number(b.openTime)&&b.openTime+FIFTEEN<=now).at(-1);
 if(last5!==current||last15!==latest15)
  return wait('Neueste echte Schlusskerze ist nicht quellenbestätigt');
 if(sign*(previous.close-previous.open)<=0||sign*(current.close-current.open)<=0||
    sign*(current.close-previous.close)<=0)
  return wait('Noch keine zwei gleichgerichteten geschlossenen 5m-Kerzen');
 if(paperRisk?.available!==true||!positive(paperRisk.atr))
  return wait('Originalbasierter Stopp-/Ziel-Risikoplan fehlt');
 const atr=paperRisk.atr;
 if(sign*(current.close-previous.open)<.2*atr)
  return wait('Zwei 5m-Kerzen ergeben noch keinen ausreichenden Impuls');
 if(Math.abs(price-current.close)>.8*atr)
  return wait('Original-Spot weicht über 0,8 ATR vom letzten 5m-Schluss ab');
 if(typeof makePlan!=='function')return wait('Unabhängige Stopp-/Zielberechnung fehlt');
 const target=makePlan(direction,price,paperRisk);
 const stop=target?.stop,take=target?.target,risk=Math.abs(price-stop);
 if(!positive(stop)||!positive(take)||!positive(risk)||
    sign*(price-stop)<=0||sign*(take-price)<2*risk-1e-7||
    target.entrySuitable===false)
  return wait(target?.warning||'Mindest-CRV 2:1 oder Stopp-/Zielprüfung nicht erfüllt');
 return {...base,status:'ready',reason:'Zwei originale 5m-Schlusskerzen im bestätigten 1h-Trend',
   direction,barAt:current.openTime,sourceAt:at,
   plan:{kind:'candidate',direction,entry:price,stop,target:take,unit:'USD/oz',
    source:SOURCE,experimental:true,paperOnly:true,entrySuitable:true,
    entrySetup:'two-closed-original-5m'}};
}
module.exports={VERSION,SOURCE,evaluate};
