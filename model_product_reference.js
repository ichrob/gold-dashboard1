'use strict';
/**
 * Per-ISIN model-only stop/target reference using verified spot-turbo terms.
 * No broker quotes, executable prices, trading approval or historical fills.
 * A fresh independently anchored estimate has stronger evidence than the
 * zero-premium intrinsic-only fallback, but neither is an observed bid/ask.
 */
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const positive=x=>finite(x)&&x>0;
const clock=value=>typeof value==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(value)?
  Date.parse(value):NaN;
const age=(value,now,limit)=>{const at=clock(value);return Number.isFinite(at)&&0<=now-at&&now-at<=limit};
const fail=reason=>({available:false,modelOnly:true,entryApproved:false,
  productApproved:false,copyAllowed:false,executable:false,simulationFillAllowed:false,
  reason,mode:'unavailable'});

function calculate({quote,plan,spots,now=Date.now()}={}){
 if(!Number.isFinite(now)||!quote||!plan||!spots)return fail('Produkt-, Gold- oder Modellplan-Daten fehlen');
 const m=quote.productModel||{}, meta=quote.metadata||{}, direction=m.direction;
 if(quote.isin!==m.isin||quote.productVerified!==true||quote.sourceDisabled||
    meta.status!==1||meta.tradingHalted===true||m.verifiedSimpleTurbo!==true||
    m.underlying!=='XAU/USD'||!['LONG','SHORT'].includes(direction)||
    meta.underlyingType&&meta.underlyingType!=='SPOT'||
    meta.direction&&meta.direction!==direction||
    quote.currency!=='EUR'&&meta.currency!=='EUR'||
    ![m.ratio,m.strike,m.ko].every(positive))
   return fail('Verifiziertes aktives EUR-Spot-Turbo-Modell mit passender ISIN fehlt');
 if(quote.state==='terminated'||quote.terminated===true||
    quote.quoteFailureCode==='TERMINATED')return fail('Produkt beendet; keine Modellplanung');
 if(plan.available!==true||plan.direction!==direction||
    ![plan.entry,plan.stop,plan.target].every(positive)||
    (direction==='LONG'?! (plan.stop<plan.entry&&plan.entry<plan.target):
                           !(plan.target<plan.entry&&plan.entry<plan.stop)))
   return fail('Aktueller, richtungsgerechter Gold-Stopp-/Zielplan fehlt');
 if(spots.is_genuine_xauusd_spot!==true||spots.spot_error||
    !positive(spots.xaus)||!age(spots.spot_price_as_of,now,60000)||
    Math.abs(spots.xaus-plan.entry)>.10)
   return fail('Originaler Gold-Spot nicht frisch oder nicht an Planreferenz gebunden');
 const fx=spots.usd_eur_meta||{};
 const fxTime=fx.fetchedAt||fx.dataAt||fx.at;
 if(!positive(fx.rate)||!age(fxTime,now,60000))
   return fail('Aktueller bestätigter USD/EUR-Kurs fehlt');
 if(m.tradingEndAt&&(!Number.isFinite(clock(m.tradingEndAt))||clock(m.tradingEndAt)<=now))
   return fail('Produktmodell außerhalb seiner zeitlichen Gültigkeit');
 const gold=spots.xaus,rate=fx.rate,sign=direction==='LONG'?1:-1;
 if(sign*(gold-m.ko)<=0||sign*(gold-m.strike)<=0)
   return fail('Gold steht an oder jenseits der Knock-out-/Basispreisschwelle');
 if(sign*(plan.stop-m.ko)<=0||sign*(plan.stop-m.strike)<=0)
   return fail('Geplanter Gold-Stopp liegt jenseits der KO-/Basispreisgrenze; anderes Produkt nötig');
 const intrinsic=at=>sign*(at-m.strike)*m.ratio*rate;
 const intrinsicStop=intrinsic(plan.stop),intrinsicTarget=intrinsic(plan.target);
 if(!positive(intrinsicStop)||!positive(intrinsicTarget)||intrinsicTarget<=intrinsicStop)
   return fail('Produkt-Stopp/Ziel aus verifizierten Vertragsbedingungen nicht sinnvoll berechenbar');

 const projected=quote.calculatedProduct||{};
 const dates=['priceAt','goldAt','fxDataAt','fxEffectiveAt','calculatedAt'];
 const aligned=dates.every(k=>age(projected[k],now,60000))&&
   Math.max(...dates.map(k=>clock(projected[k])))-
   Math.min(...dates.map(k=>clock(projected[k])))<=60000;
 const anchorAge=now-clock(projected.referenceAt);
 const anchorBound=projected.validation?.ready===true?1800000:300000;
 const anchored=projected.available===true&&projected.kind==='calculated-turbo'&&
   projected.currency==='EUR'&&projected.direction===direction&&
   positive(projected.bidEur)&&positive(projected.askEur)&&projected.askEur>=projected.bidEur&&
   positive(projected.goldUsd)&&positive(projected.usdEur)&&
   Math.abs(projected.goldUsd-gold)<=.10&&Math.abs(projected.usdEur-rate)<=.0002&&
   projected.ratio===m.ratio&&projected.strikeUsd===m.strike&&
   aligned&&Number.isFinite(anchorAge)&&0<=anchorAge&&anchorAge<=anchorBound;
 const modelStop=anchored?projected.bidEur+sign*m.ratio*rate*(plan.stop-gold):intrinsicStop;
 const modelTarget=anchored?projected.bidEur+sign*m.ratio*rate*(plan.target-gold):intrinsicTarget;
 const modelEntry=anchored?projected.askEur:intrinsic(gold);
 if(![modelStop,modelTarget,modelEntry].every(positive)||modelStop>=modelEntry||modelTarget<=modelEntry)
   return fail('Berechneter EUR-Produktkorridor unplausibel; keine Stückzahl oder Freigabe');
 const mode=anchored?'anchored-estimate':'intrinsic-only';
 const referenceAt=anchored?projected.referenceAt:spots.spot_price_as_of;
 return {available:true,mode,modelOnly:true,simulationPlanningUsable:true,
   simulationFillAllowed:false,entryApproved:false,productApproved:false,
   copyAllowed:false,executable:false,productIsin:quote.isin,currency:'EUR',
   direction,modelEntry:Math.round(modelEntry*10000)/10000,
   modelStop:Math.round(modelStop*10000)/10000,
   modelTarget:Math.round(modelTarget*10000)/10000,
   goldEntry:gold,goldStop:plan.stop,goldTarget:plan.target,
   originalGoldAt:spots.spot_price_as_of,fxAt:fxTime,
   referenceAt,calculatedAt:new Date(now).toISOString(),
   inputAgeSeconds:Math.round((now-Math.min(clock(spots.spot_price_as_of),clock(fxTime)))/1000),
   anchorAgeSeconds:anchored?Math.round(anchorAge/1000):null,
   validationReady:anchored&&projected.validation?.ready===true,
   errorBoundEur:anchored&&positive(projected.comparisonErrorEur)?projected.comparisonErrorEur:null,
   reason:anchored?'Aus datiertem Original-Geld/Brief und aktuellem Gold/FX hochgerechnete Modellreferenz':
     'Nur innerer Vertragswert; Aufgeld und Geld/Brief-Spread nicht beobachtet',
   warning:'Nur Modell-Stopp/Ziel, kein ausführbarer Kurs, kein DEGIRO-Einstieg. '+
     'Originalangebot vor einer Kaufentscheidung separat bestätigen.'};
}
module.exports={calculate};
