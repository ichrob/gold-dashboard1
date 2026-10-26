/* A single, read-only product evidence contract for Bob's mobile views.
 * Keep issuer, screenshot, CSV and broker evidence separate. NEVER grants trading.
 */
(function(root){
'use strict';
function validIsin(value){
 if(typeof value!=='string'||!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(value))return false;
 const digits=value.replace(/[A-Z]/g,c=>String(c.charCodeAt(0)-55));
 let sum=0;[...digits].reverse().forEach((c,i)=>{const n=Number(c)*(i%2?2:1);sum+=n>9?n-9:n;});
 return sum%10===0;
}
function originalAge(value,now=Date.now()){
 if(typeof value!=='string'||!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value))return null;
 const time=Date.parse(value);
 return Number.isFinite(time)&&time<=now?now-time:null;
}
function productEvidence(p,now=Date.now()){
 const unknown=t=>({state:'unknown',text:t});
 const out={isin:null,tradeable:false,automaticOrder:false,
  direction:unknown('LONG/SHORT fehlt'),currency:unknown('EUR/CHF fehlt'),
  prices:unknown('Geld/Brief und Originalzeiten fehlen'),
  barrier:unknown('KO-Originalnachweis fehlt'),leverage:unknown('Emittenten-Hebel mit Uhrzeit fehlt'),
  venue:unknown('DEGIRO-Handelsplatznachweis separat erforderlich')};
 if(!validIsin(p?.isin))return out;
 out.isin=p.isin;
 const q=p.quote?.isin===p.isin?p.quote:null,r=p.reference?.isin===p.isin?p.reference:null;
 const dirs=[p.direction,q?.metadata?.direction,r?.direction].filter(x=>['LONG','SHORT'].includes(x));
 out.direction=!dirs.length?out.direction:new Set(dirs).size>1?
  {state:'conflict',text:'Richtungsangaben widersprechen sich'}:
  {state:'observed',text:dirs[0]+' aus Produktidentität, keine Handelsfreigabe'};
 const ccys=[q?.currency,q?.metadata?.currency,r?.currency].filter(x=>['EUR','CHF'].includes(x));
 out.currency=!ccys.length?out.currency:new Set(ccys).size>1?
  {state:'conflict',text:'Produktwährungen widersprechen sich'}:
  {state:'observed',text:ccys[0]+' aus Produktbeobachtung'};
 const bid=Number(q?.bid),ask=Number(q?.ask);
 const bidAge=originalAge(q?.bidAt,now),askAge=originalAge(q?.askAt,now);
 if(q?.productVerified===true&&q?.found===true){
  if(q.paperSelectionOnly||q.paperQuoteAccepted||/estimated|calculated|paper|issuer-chart|simulation/i.test(String(q.priceKind||'')))
   out.prices=unknown('Nur Chart-/Modell-/Simulationskurs, kein aktuelles Emittenten-Kurspaar');
  else if(q?.metadata?.status===2||q?.metadata?.tradingHalted===true||q?.sourceDisabled===true)
   out.prices={state:'conflict',text:'Produkt ausgesetzt oder beendet'};
  else if(!(bid>0&&ask>=bid))out.prices={state:'conflict',text:'Geld-/Briefwerte fehlen oder widersprechen sich'};
  else if(bidAge===null||askAge===null)out.prices=unknown('Mindestens eine Originalkurszeit fehlt');
  else if(Math.max(bidAge,askAge)>90000||Math.abs(bidAge-askAge)>90000)
   out.prices={state:'stale',text:'Originalkurszeiten nicht aktuell oder nicht zusammengehörig'};
  else out.prices={state:'observed',text:'Geld '+bid+' / Brief '+ask+' · Originalzeit '+q.bidAt+' / '+q.askAt+
    ' · '+String(q.source||'Emittent').slice(0,90)+' · keine DEGIRO-Orderquotierung'};
 }
 const ko=Number(r?.ko);
 if(ko>0&&Number.isFinite(ko))out.barrier={state:'observed',
  text:'Genannter KO-Wert '+ko+' · Original-KO-Zeit und 8h-Gültigkeit separat prüfen'};
 const lev=Number(q?.leverage),levAge=originalAge(q?.leverageAt,now);
 if(lev>0&&Number.isFinite(lev))out.leverage=levAge!==null&&levAge<=90000?
  {state:'observed',text:'Hebel '+lev+' · Emittenten-Zeit '+q.leverageAt}:
  {state:'stale',text:'Hebel '+lev+' · gültiger eigener Zeitnachweis nicht vorhanden'};
 return out;
}


function fromCombined(row,now=Date.now()){
 const id=validIsin(row?.isin)?row.isin:null;
 const unknown={state:'unknown',text:'Quelle oder Nachweis fehlt'};
 if(!id)return {isin:null,tradeable:false,automaticOrder:false,identity:unknown};
 const reasons=[];
 if(row.inDepot)reasons.push('lokaler Depot-CSV-Export (historisch)');
 if(row.inWatchlist)reasons.push('gespeicherte DEGIRO-Screenshotidentität (nicht live)');
 if(row.inAudit)reasons.push('Bob-Produktprüfbericht (nur Quellnachweise)');
 if(row.quote)reasons.push('datierter Emittentenvergleich (keine Ausführung)');
 // 'quote' on the combined row is already labelled research-only; it is not
 // the full issuer quote shape that can satisfy productEvidence().
 const q=row.quote;
 const quoteAge=originalAge(q?.at,now);
 const qState=!q?'unknown':q.fresh===true&&quoteAge!==null&&quoteAge<=90000?'observed':'stale';
 return {
  isin:id,identity:{state:'observed',text:'Gültige ISIN; Quellen: '+(reasons.join(' · ')||'keine nachgewiesen')},
  direction:row.direction||null,currency:row.currency||q?.currency||null,
  quote:{state:qState,text:q?String(q.source||'Quelle unbekannt').slice(0,100)+' · Originalzeit '+String(q.at||'fehlt')+' · keine DEGIRO-Ausführung':'Keine datierte Emittentenbeobachtung'},
  broker:{state:'unknown',text:'Keine bestätigte ausführbare DEGIRO-Order und kein aktueller Handelsplatznachweis'},
  tradeable:false,automaticOrder:false,executableQuote:false
 };
}
// Independent research approval for computed values; never grants broker execution.
function calculatedApproval(p,market={},now=Date.now()){
 const reasons=[];
 if(!validIsin(p?.isin))reasons.push('ISIN nicht verifiziert');
 const direction=p?.productDirection||p?.direction;
 if(!['LONG','SHORT'].includes(direction))reasons.push('Produktrichtung fehlt');
 if(!['LONG','SHORT'].includes(market?.direction)||market?.direction!==direction||market?.spotFresh!==true)reasons.push('Kein aktuelles passendes Marktsignal');
 const spot=Number(market?.spot),atr=Number(market?.atr),ko=Number(p?.ko),price=Number(p?.price),leverage=Number(p?.leverage);
 if(!(spot>0&&atr>0))reasons.push('Aktueller Goldkurs oder ATR fehlt');
 if(!(ko>0&&price>0&&leverage>=1))reasons.push('KO, Preis oder Hebel fehlt');
 if(spot>0&&ko>0&&((direction==='LONG'&&ko>=spot)||(direction==='SHORT'&&ko<=spot)))reasons.push('KO-Schwelle erreicht oder widersprüchlich');
 if(/FAKTOR|FACTOR|FUTURE/i.test(String(p?.name||'')))reasons.push('Nicht unterstützter Produkttyp');
 if(p?.quote?.isin&&p.quote.isin!==p.isin||p?.snapshot?.isin&&p.snapshot.isin!==p.isin)reasons.push('Produktidentität widersprüchlich');
 const calculated=!!(p?.calculated||p?.estimated||p?.priceCalculated||p?.leverageCalculated||p?.koCalculated);
 const fields=[['price',price],['leverage',leverage],['ko',ko]];
 for(const [field,value] of fields){
  const estimated=!!(p?.calculated||p?.estimated||p?.[field+'Calculated']);
  if(!estimated)continue;
  const proof=p?.calculationEvidence?.[field];
  if(!proof||proof.method==null||!proof.source||!proof.at||!Number.isFinite(Date.parse(proof.at))||Date.parse(proof.at)>now||now-Date.parse(proof.at)>90000||!Number.isFinite(value)||value<=0)
   reasons.push('Berechnung '+field+' ohne aktuelle prüfbare Quelle');
 }
 return {status:reasons.length?'blocked':calculated?'calculated-approved':'observed-approved',approved:reasons.length===0,calculated,reasons,brokerTradeable:false,executableQuote:false,automaticOrder:false};
}
const api={validIsin,originalAge,productEvidence,fromCombined,calculatedApproval};
root.BobProductEvidence=api;
if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
