/* Bob: manual-only Top-3 order preparation. No broker control, order or quote fetch. */
(function(root){
'use strict';
const MAX_QUOTE_AGE=90000,MAX_FX_AGE=90000;
// Retain a read-only evidence draft across a complete multi-product run.
// This is not the live quote validity window used by evaluate/reconcile.
const MAX_HANDSET_EVIDENCE_AGE=14*60*60*1000;
const positive=n=>typeof n==='number'&&Number.isFinite(n)&&n>0;
const nonnegative=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
const stamp=s=>typeof s==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(s)?Date.parse(s):NaN;
const fresh=(s,now,limit)=>Number.isFinite(stamp(s))&&now>=stamp(s)&&now-stamp(s)<=limit;
const validSide=s=>s==='LONG'||s==='SHORT';
const fmt=(n,d=2)=>Number.isFinite(n)?n.toLocaleString('de-CH',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const seenAt=s=>Number.isFinite(stamp(s))?new Date(stamp(s)).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'unbekannt';
function readChfFx(spots,now=Date.now(),currency='EUR'){
 if(currency==='CHF')return {available:true,rate:1,note:'Produkt direkt in CHF'};
 if(currency!=='EUR')return {available:false,reason:'Nur EUR-/CHF-Produkte unterstützt'};
 const chf=spots?.usd_chf_meta,eur=spots?.usd_eur_meta;
 if(chf?.error||eur?.error||!positive(Number(chf?.rate))||!positive(Number(eur?.rate))||
   !fresh(chf?.fetchedAt,now,MAX_FX_AGE)||!fresh(eur?.fetchedAt,now,MAX_FX_AGE))
  return {available:false,reason:'Aktuelle, datierte USD/CHF- und USD/EUR-Umrechnung fehlt'};
 return {available:true,rate:Number(chf.rate)/Number(eur.rate),
   note:'EUR/CHF aus USD/CHF ÷ USD/EUR; FX-Quellenzeit '+seenAt(chf.fetchedAt)+' / '+seenAt(eur.fetchedAt)};
}
// Versioned official CH tariff, checked 2026-11-13. No account/profile inference
// from residence, issuer, ISIN or quote provider. This is a planning reserve,
// never an actual broker charge or execution permission.
function resolveFees({config={},report,isin,spots,now=Date.now()}={}){
 const source='https://www.degiro.ch/data/pdf/ch-de/DE-CH_Preis_und_Leistungsverzeichnis.pdf';
 const base={source,tariffDate:'2026-01-01',checkedAt:'2026-11-13',estimated:true,
  rankingPenalty:false,realOrders:false};
 const fail=reason=>({...base,available:false,feesCHF:null,reason});
 if(nonnegative(config.feesCHF))return {available:true,feesCHF:config.feesCHF,
  estimated:false,source:'Nutzereingabe',reason:'Manuell angegebene Gesamtgebühren'};
 if(config.feesCHF!==null&&config.feesCHF!==undefined)return fail('Ungültige manuelle Gebührenangabe');
 if(config.feeProfile!=='CH_STANDARD')return fail('Gebühren: Schweizer Standardtarif (Basic/Active/Trader) noch nicht bestätigt.');
 if(!Number.isFinite(now)||now<Date.parse('2026-11-13T00:00:00Z')||now>=Date.parse('2026-12-13T00:00:00Z'))
  return fail('Gebührentarif muss anhand des offiziellen Preisverzeichnisses erneut geprüft werden.');
 const imported=importHandsetReport(report,isin,now);
 if(!imported.available)return fail('Gebühren: aktueller zugeordneter DEGIRO-Handelsplatzbeleg fehlt.');
 const venue=String(imported.values?.venue||'').trim().toUpperCase().replace(/\s+/g,' ');
 // Exact route names only; Société Générale as issuer alone proves no venue.
 const routes={ 'SG OTC':.5,'OTC SOCIÉTÉ GÉNÉRALE':.5,'OTC SOCIETE GENERALE':.5,
  'SOCIETE GENERALE OTC':.5,'SOCIÉTÉ GÉNÉRALE OTC':.5,
  'OTC BNP PARIBAS':.5,'BNP PARIBAS OTC':.5,'BNP OTC':.5,'ZERTIFIKATE-BÖRSE FRANKFURT':3,
  'EURONEXT ACCESS PARIS':3 };
 if(!Object.prototype.hasOwnProperty.call(routes,venue))return fail('Gebühren: kein eindeutig unterstützter DEGIRO-Handelsplatz ('+(venue||'fehlt')+').');
 const fx=readChfFx(spots,now,'EUR');
 if(!fx.available)return fail('Gebühren in EUR: '+fx.reason);
 const currency=imported.values.currency;
 if(!['AUTO_CHF','NO_CONVERSION'].includes(config.fxMode))return fail('Gebühren: Währungswechsel-Einstellung noch nicht bestätigt.');
 if(!positive(config.budgetCHF))return fail('Gebühren: Einsatzvorgabe fehlt.');
 const commissionCHF=2*routes[venue]*fx.rate;
 // Reserve both legs at the whole capital limit. Valid for the loss-stop
// scenario, not a promise for arbitrary profitable exits or future FX rates.
 const fxReserveCHF=config.fxMode==='AUTO_CHF'&&currency!=='CHF'?config.budgetCHF*.005:0;
 const feesCHF=Math.ceil((commissionCHF+fxReserveCHF)*100-1e-9)/100;
 return {...base,available:true,feesCHF,venue,commissionCHF,fxReserveCHF,fxBasis:fx.note,
  reason:'Automatische Tarifreserve für Kauf und Stopp-Verkauf; '+
   'inkl. Bearbeitung'+(fxReserveCHF?' und AutoFX-Reserve':'')+
   '. Keine Abrechnung; mögliche Steuern und jährliche Börsenanbindung separat. Spread nicht als Gebühr doppelt gezählt.'};
}
// Immutable priority: verified current native issuer -> current dated backup
// observation -> strictly validated product model. Never prefer newer backup
// over a still-valid original. No retrieval time can renew an old quote.
function selectQuoteByPriority(product,now=Date.now()){
 const isin=product?.isin,q=product?.quote;
 if(!isin||q?.isin!==isin||q.productVerified!==true)return null;
 const currency=q.metadata?.currency||q.currency;
 if(!['EUR','CHF'].includes(currency))return null;
 const list=root.BobStopAssistant?.compareQuoteSources(q,isin,now,currency)?.quotes||[];
 const original=list.find(row=>row.kind==='issuer'&&row.origin==='issuer'&&!row.chart);
 if(original)return {quote:original,tier:1,label:'1 · Originalquelle (Emittent)',calculated:false};
 const backup=list.find(row=>row.kind==='research'&&!row.chart)||
  list.find(row=>row.kind==='research');
 if(backup)return {quote:backup,tier:2,label:'2 · Ersatzquelle / Beobachtung',calculated:false};
 const model=root.BobDegiro?.calculatedProductDisplay?.(product,now);
 if(model?.priceKind==='calculated'&&model.isin===isin&&model.currency===currency&&
    positive(model.bid)&&positive(model.ask)&&model.ask>=model.bid&&
    fresh(model.at,now,60000)){
  return {quote:{isin,currency,bid:model.bid,ask:model.ask,
    at:model.at,askAt:model.at,source:model.source,
    kind:'calculated',origin:'model',modelVerified:true,
    validationReady:model.validationReady===true,
    validationSamples:model.validationSamples,
    priceKind:'calculated',degiroExecutable:false},
   tier:3,label:'3 · Berechneter Modellwert',calculated:true};
 }
 return null;
}
function evaluate({candidate,product,quote,stopPlan,fx,budgetCHF,riskCHF,feesCHF,now=Date.now(),direction}={}){
 const item={isin:String(candidate?.isin||''),direction,available:false,entry:null,bid:null,stop:null,
  quantity:null,currency:null,totalCHF:null,investedCHF:null,lossCHF:null,reason:'',
  source:null,quoteAt:null,fxNote:'',priceKind:null,sourceTier:null,sourceLabel:'',copyAllowed:false,warning:'Richtwerte, keine ausführbaren DEGIRO-Kurse'};
 const block=reason=>({...item,reason});
 if(!candidate||!validSide(direction)||candidate.direction!==direction||
    product?.isin!==item.isin||product.productDirection!==direction||
    product.isinConfirmed!==true)return block('Richtung und ISIN müssen zum geprüften Ranking passen.');
 if(!quote||quote.isin!==item.isin||!['EUR','CHF'].includes(quote.currency)||
    !positive(Number(quote.ask))||!positive(Number(quote.bid))||Number(quote.ask)<Number(quote.bid)||
    !fresh(quote.at,now,MAX_QUOTE_AGE)||!fresh(quote.askAt,now,MAX_QUOTE_AGE)||
    Math.abs(stamp(quote.askAt)-stamp(quote.at))>30000||
    !['issuer','research','calculated'].includes(quote.kind)||!String(quote.source||'').trim()||
    (quote.kind==='calculated'&&(quote.modelVerified!==true||quote.validationReady!==true||
     !Number.isInteger(quote.validationSamples)||quote.validationSamples<20)))
  return block('Kein zeitgleich datiertes, aktuelles Geld-/Briefpaar dieser ISIN.');
 item.entry=Number(quote.ask);item.bid=Number(quote.bid);item.currency=quote.currency;item.source=quote.source;
 item.quoteAt=quote.askAt;item.priceKind=quote.kind;
 item.sourceTier=quote.kind==='issuer'?1:quote.kind==='calculated'?3:2;
 item.sourceLabel=item.sourceTier===1?'1 · Originalquelle (Emittent)':
  item.sourceTier===2?'2 · Ersatzquelle / Beobachtung':'3 · Berechneter Modellwert';
 // No calculated or chart-derived number may be copied as a ready order field.
 item.copyAllowed=quote.kind!=='calculated'&&quote.chart!==true;
 if(!stopPlan?.available||stopPlan.currency!==quote.currency||
    !positive(Number(stopPlan.stop))||!(Number(stopPlan.stop)<item.entry)||
    !fresh(stopPlan.referenceAt,now,MAX_QUOTE_AGE)||
    Math.abs(stamp(stopPlan.referenceAt)-stamp(quote.at))>30000)
  return block('Produkt-Stopp fehlt oder passt nicht zur aktuellen Quelle; keine Stückzahl berechnen.');
 item.stop=Number(stopPlan.stop);
 if(!fx?.available||!positive(fx.rate))return block(fx?.reason||'Aktuelle Währungsumrechnung fehlt.');
 item.fxNote=fx.note||'';
 if(!positive(budgetCHF)||!positive(riskCHF)||!nonnegative(feesCHF))
  return block('Maximales Kapital, Verlustrisiko und Gebühren (auch 0 explizit) in CHF eintragen.');
 const costPerUnit=item.entry*fx.rate,lossPerUnit=(item.entry-item.stop)*fx.rate;
 if(!positive(costPerUnit)||!positive(lossPerUnit)||budgetCHF<=feesCHF||riskCHF<=feesCHF)
  return block('Kapital oder Risikobudget reicht nach Gebühren nicht aus.');
 const byBudget=Math.floor((budgetCHF-feesCHF)/costPerUnit);
 const byRisk=Math.floor((riskCHF-feesCHF)/lossPerUnit);
 const quantity=Math.min(byBudget,byRisk);
 if(!Number.isSafeInteger(quantity)||quantity<=0)return block('Kein ganzes Stück innerhalb von Kapital- und Risikogrenze.');
 item.available=true;item.quantity=quantity;item.investedCHF=quantity*costPerUnit;
 item.totalCHF=item.investedCHF+feesCHF;item.lossCHF=quantity*lossPerUnit+feesCHF;
 item.reason=quote.kind==='calculated'
  ?'Nur Modellrechnung für den Vergleich, keine ausführbare Preis-/Ordergrundlage; Werte nicht direkt als DEGIRO-Order übernehmen.'
  :'Manuelle Richtwerte; bei DEGIRO Preis, Menge, Gebühren und separate VERKAUF-Stop-Order prüfen.';
 return item;
}

/* Stage B: a user-transcribed DEGIRO product screen is a *display observation*,
 * never a broker execution or trade approval. Re-evaluate the current Stage A
 * risk plan; do not manufacture a stop/source clock from the screenshot.
 */
function reconcileBrokerDisplay({candidate,product,preliminary,broker,fx,
 budgetCHF,riskCHF,feesCHF,now=Date.now(),direction}={}){
 const empty={available:false,manualFieldsComplete:false,copyAllowed:false,
  brokerExecutionVerified:false,orderSubmitted:false,reason:'',isin:candidate?.isin||'',
  source:'DEGIRO-Anzeige · vom Nutzer abgelesen (keine Ausführung)',
  currency:null,entry:null,stop:null,quantity:null,totalCHF:null,lossCHF:null,
  difference:null,differencePct:null,sourceAt:null,fxRate:null,fxBasis:null,
  stopBasis:'Modellstopp aus Goldplan und zeitnaher Geldkursabweichung; kein DEGIRO-Stoppkurs'};
 const fail=reason=>({...empty,reason});
 if(!candidate||!validSide(direction)||candidate.direction!==direction||
    !product||product.isin!==candidate.isin||product.productDirection!==direction||
    product.isinConfirmed!==true)
  return fail('Produktidentität oder Signalrichtung geändert – Vorauswahl neu prüfen.');
 if(product.quote?.isin&&product.quote.isin!==candidate.isin||
    product.quote?.sourceDisabled===true||
    product.quote?.metadata?.tradingHalted===true||
    product.quote?.metadata?.status!==undefined&&product.quote.metadata.status!==1)
  return fail('Produktstatus oder Identität nicht mehr gültig.');
 if(!preliminary?.available||preliminary.isin!==candidate.isin||
    !fresh(preliminary.quoteAt,now,MAX_QUOTE_AGE)||
    !positive(preliminary.entry)||!positive(preliminary.bid)||!positive(preliminary.stop))
  return fail('Vorläufiger Kurs-/Stoppplan abgelaufen oder unvollständig – mit frischem Gold-/FX-Plan neu berechnen.');
 if(!broker||broker.confirmedByUser!==true)
  return fail('DEGIRO-Bildschirmwerte erst ablesen und durch „Werte neu prüfen“ bestätigen.');
 const currency=product.quote?.metadata?.currency||product.quote?.currency||preliminary.currency;
 if(broker.isin!==candidate.isin||broker.currency!==currency||
    preliminary.currency!==currency||!['EUR','CHF'].includes(currency))
  return fail('DEGIRO-Bildschirm-ISIN oder Produktwährung weicht vom gewählten Produkt ab.');
 const bid=Number(broker.bid),ask=Number(broker.ask);
 if(!positive(bid)||!positive(ask)||ask<bid||!fresh(broker.quoteAt,now,MAX_QUOTE_AGE))
  return fail('Geld/Brief oder originale DEGIRO-Anzeigezeit fehlen, sind widersprüchlich oder älter als 90 Sekunden.');
 if(!positive(preliminary.stop)||preliminary.stop>=ask)
  return fail('Aktueller Briefkurs liegt am/unter dem Modellstopp – neuen Gold-Stopp-/Risiko-Plan prüfen.');
 if(!positive(budgetCHF)||!positive(riskCHF)||!nonnegative(feesCHF))
  return fail('Ausdrücklich eingegebene Kapital-, Verlust- und Gebührenwerte fehlen.');
 let rate=fx?.rate,fxBasis='Frische, unabhängige Markt-FX-Referenz; kein bestätigter DEGIRO-Umrechnungskurs';
 let directFx=false;
 const typedFx=broker.fxRateCHF!==undefined&&broker.fxRateCHF!==null&&
   String(broker.fxRateCHF).trim()!=='';
 if(currency==='CHF'){
  rate=1;fxBasis='Produktkonto / Produktpreis beide CHF';
 }else if(typedFx){
  rate=Number(broker.fxRateCHF);
  if(!positive(rate)||!fresh(broker.fxAt,now,MAX_FX_AGE))
   return fail('Abgelesener DEGIRO-EUR/CHF-Kurs ist ungültig oder zeitlich nicht aktuell.');
  directFx=true;fxBasis='EUR/CHF aus vom Nutzer abgelesener DEGIRO-Anzeige · '+seenAt(broker.fxAt)+' Zürich';
 }else if(!fx?.available||!positive(rate)){
  return fail('Kein frischer EUR/CHF-Referenzkurs vorhanden.');
 }
 const typedFunds=broker.buyingPowerCHF!==undefined&&broker.buyingPowerCHF!==null&&
   String(broker.buyingPowerCHF).trim()!=='';
 const buyingPower=typedFunds?Number(broker.buyingPowerCHF):null;
 if(typedFunds&&!positive(buyingPower))
  return fail('Abgelesene CHF-Kaufkraft fehlt oder ist nicht positiv.');
 const maxCapital=typedFunds?Math.min(budgetCHF,buyingPower):budgetCHF;
 if(!(maxCapital>feesCHF&&riskCHF>feesCHF))
  return fail('Kaufkraft, Kapital oder Risikobudget nach Gebühren zu klein.');
 const typedLot=broker.lotSize!==undefined&&broker.lotSize!==null&&
   String(broker.lotSize).trim()!=='';
 const lot=typedLot?Number(broker.lotSize):1;
 if(typedLot&&(!Number.isSafeInteger(lot)||lot<=0))
  return fail('Die angegebene Mindestlosgröße ist ungültig.');
 // Reanchor only the theoretical pre-entry stop against a comparably fresh
 // displayed bid. Existing confirmed-position stops are never changed here.
 const quoteGapMs=Math.abs(stamp(broker.quoteAt)-stamp(preliminary.quoteAt));
 const sameClock=quoteGapMs<=30000;
 const bidShift=bid-preliminary.bid;
 const modelStop=sameClock?preliminary.stop+bidShift:preliminary.stop;
 if(!positive(modelStop)||modelStop>=ask)
  return fail('Neu an den Geldkurs angepasster Modellstopp ist ungültig – keine Stückzahl berechnen.');
 const costEach=ask*rate,lossEach=(ask-modelStop)*rate;
 if(!positive(costEach)||!positive(lossEach))
  return fail('Einstandspreis und Modellstopp erlauben keine sichere Stückzahlberechnung.');
 const rawQty=Math.min(Math.floor((maxCapital-feesCHF)/costEach),
                       Math.floor((riskCHF-feesCHF)/lossEach));
 const qty=Math.floor(rawQty/lot)*lot;
 if(!Number.isSafeInteger(qty)||qty<1)
  return fail('Keine ganze Stückzahl innerhalb der neu berechneten Kapital-/Risikogrenze.');
 const tick=Number(broker.tickSize);
 const validTick=broker.tickSize!==undefined&&String(broker.tickSize).trim()!==''&&
   positive(tick)&&Math.abs(ask-Math.round(ask/tick)*tick)<=Math.max(1e-8,tick*1e-6);
 const difference=ask-preliminary.entry;
 const deviationPct=100*difference/preliminary.entry;
 // A large deviation makes a new independently sourced product/market review
 // necessary even when the user typed a valid current display price.
 const deviationReview=Math.abs(deviationPct)>5;
 const complete=Boolean(String(broker.venue||'').trim()&&
   broker.orderType==='LIMIT'&&['DAY','GTC'].includes(broker.orderDuration)&&
   validTick&&typedLot&&typedFunds&&(currency==='CHF'||directFx)&&
   sameClock&&!deviationReview);
 return {...empty,available:true,manualFieldsComplete:complete,
  currency,entry:ask,bid,stop:modelStop,quantity:qty,
  totalCHF:qty*costEach+feesCHF,lossCHF:qty*lossEach+feesCHF,
  difference,differencePct:deviationPct,sourceAt:broker.quoteAt,
  referenceClockGapSeconds:quoteGapMs/1000,
  stopShift:sameClock?bidShift:null,
  stopBasis:sameClock?'Rechnerische Neuanpassung an die DEGIRO-Geldkursabweichung (nicht ausführbar)':'Bisheriger Gold-Modellstopp; Zeitabstand der Produktquellen zu groß',
  fxRate:rate,fxBasis,venue:String(broker.venue||''),lotSize:lot,
  reason:complete?
   'Neu berechnete manuelle Vergleichsvorlage. DEGIRO-Kaufkraft, Ordertyp und echte Ausführbarkeit vor jedem Absenden selbst erneut prüfen.':
   'Neu berechnet, aber Broker-Orderbedingungen / Kaufkraft / Tick / unabhängige FX-Anzeige unvollständig'+
   (deviationReview?' oder Modellabweichung über 5 %':'')+
   (!sameClock?' oder Kurszeiten der Vergleichsquellen mehr als 30 Sekunden auseinander':'')+
   '. Keine bestätigte ausführbare Ordervorlage.'};
}

/* Reuse an explicitly shared, read-only Android product-image draft.
 * OCR has no verified quote source clock; the user must supply and recheck
 * the actual displayed quote time before any repricing can occur.
 */
function importAndroidScreenDraft(draft){
 const unavailable=reason=>({available:false,reason});
 if(!draft||draft.verified!==false||draft.tradeApproved!==false||draft.sourceTime!==null)
  return unavailable('Nur eine ungeprüfte, ausdrücklich geteilte DEGIRO-Bildschirmbeobachtung ist zulässig.');
 let row;
 try{row=root.BobAndroidEvidence?.displayedPairStatus?.(draft);}catch(_){return unavailable('DEGIRO-Bildentwurf ist unvollständig oder widersprüchlich.');}
 if(!row||row.state!=='screen-observation'||row.executable!==false||
    row.canTrade!==false||row.sourceTime!==null)
  return unavailable('Kein eindeutiges Geld-/Briefpaar im gespeicherten Bild.');
 return {available:true,displayedTime:row.displayedTime||null,
  values:{isin:row.isin,currency:['EUR','CHF'].includes(draft.currency)?draft.currency:'',
   bid:String(row.bid),ask:String(row.ask),venue:row.venue||'',
   quoteAt:'',confirmedByUser:false},
  note:'Bildwerte nur vorbefüllt. Original-Kurszeit, Währung und sämtliche Brokerbedingungen selbst prüfen; keine Ausführung bestätigt.'};
}

// Consume the existing authenticated audit, without another poll or storage.
// Receipt/observation times are freshness guards, never original quote clocks.
function importHandsetReport(report,isin,now=Date.now()){
 const fail=reason=>({available:false,reason});
 if(!['ok','partial'].includes(report?.status)||!fresh(report.lastCheckedAt,now,120000))
  return fail('Aktueller Handy-Lesebericht nicht verfügbar.');
 const rows=Array.isArray(report.items)?report.items.filter(x=>x?.isin===isin):[];
 if(rows.length!==1)return fail('Kein eindeutig zugeordneter Handy-Lesebeleg.');
 const item=rows[0],o=item.handsetObservation,f=o?.fields;
 if(['terminated','excluded-factor'].includes(item.state)||o?.terminalAtAudit===true||
    o?.researchOnly!==true||o.verified!==false||o.tradeApproved!==false||
    o.executionConfirmed!==false||o.sourceTime!==null||!f||
    !['COMPLETE','PARTIAL'].includes(o.code)||!fresh(o.observedAt,now,MAX_HANDSET_EVIDENCE_AGE))
  return fail('Kein zulässiger gespeicherter Produkt-Lesebeleg (höchstens 14 Stunden).');
 if(!['EUR','CHF'].includes(f['Währung'])||f.Hinweis!=='Keine Aussage zur Handelbarkeit')
  return fail('Produktwährung fehlt oder die Handy-Anzeige meldet verzögerte/eingeschränkte Kurse.');
 const draft={isin,verified:false,tradeApproved:false,sourceTime:null,currency:f['Währung'],
  fields:{bid:f.Geld,ask:f.Brief,venue:f.Handelsplatz,displayedTime:f.Anzeigezeit}};
 const imported=importAndroidScreenDraft(draft);
 if(!imported.available)return imported;
 const number=s=>typeof s==='string'&&/^\d{1,9}(?:[,.]\d{1,4})?$/.test(s)&&positive(Number(s.replace(',','.')))?s:null;
 const captureAgeSeconds=Math.floor((now-stamp(o.observedAt))/1000);
 const historicalOnly=!fresh(o.observedAt,now,MAX_QUOTE_AGE);
 return {...imported,observedAt:o.observedAt,captureAgeSeconds,historicalOnly,
  leverage:number(f.Hebel),ko:number(f['KO-Schwelle']),
  fingerprint:JSON.stringify([isin,o.observedAt,f]),
  note:(historicalOnly?'Gespeicherter Bob-Handy-Beleg · Erfassung älter als 90 Sekunden; kein aktueller Kurs. ':'Bob Handy automatisch übernommen · ungeprüfte Anzeige. ')+
   'Original-Kurszeit mit Zeitzone prüfen und bestätigen; Erfassungszeit ist keine Kurszeit.'};
}

// Automatic what-if calculation: stored display prices + current independent
// model stop/FX. Different clocks are explicit; no source time is invented and
// the result never enters ranking, trade approval, copying or model training.
function compareHandsetModel({report,candidate,product,preliminary,fx,
 budgetCHF,riskCHF,feesCHF,now=Date.now(),direction}={}){
 const empty={available:false,researchOnly:true,copyAllowed:false,
  brokerExecutionVerified:false,orderSubmitted:false,sourceAt:null};
 const fail=reason=>({...empty,reason});
 const imported=importHandsetReport(report,candidate?.isin,now);
 if(!imported.available)return fail(imported.reason);
 if(!validSide(direction)||candidate?.direction!==direction||
    product?.isin!==candidate?.isin||product?.isinConfirmed!==true||
    product?.productDirection!==direction||
    product.quote?.sourceDisabled===true||product.quote?.metadata?.tradingHalted===true||
    product.quote?.metadata?.status!==undefined&&product.quote.metadata.status!==1)
  return fail('Produktidentität, Richtung oder Produktstatus nicht gültig.');
 if(!preliminary?.available||preliminary.isin!==candidate.isin||
    !fresh(preliminary.quoteAt,now,MAX_QUOTE_AGE)||
    !positive(preliminary.entry)||!positive(preliminary.stop))
  return fail('Aktueller unabhängiger Modellplan fehlt.');
 const currency=imported.values.currency;
 if(currency!==preliminary.currency||currency!==(product.quote?.metadata?.currency||product.quote?.currency))
  return fail('Produktwährungen stimmen nicht überein.');
 const bid=Number(imported.values.bid),entry=Number(imported.values.ask),stop=preliminary.stop;
 if(!positive(bid)||!positive(entry)||entry<bid||stop>=entry)
  return fail('Anzeigekurse passen nicht zum aktuellen Modellstopp.');
 const rate=currency==='CHF'?1:fx?.rate;
 if(currency!=='CHF'&&(!fx?.available||!positive(rate)))return fail('Aktuelle EUR/CHF-Referenz fehlt.');
 if(!positive(budgetCHF)||!positive(riskCHF)||!nonnegative(feesCHF)||
    budgetCHF<=feesCHF||riskCHF<=feesCHF)
  return fail('Kapital, Risikobudget und Gebühren in CHF eintragen.');
 const costEach=entry*rate,lossEach=(entry-stop)*rate;
 if(!positive(costEach)||!positive(lossEach))return fail('Kosten oder Modellrisiko nicht berechenbar.');
 const quantity=Math.min(Math.floor((budgetCHF-feesCHF)/costEach),Math.floor((riskCHF-feesCHF)/lossEach));
 if(!Number.isSafeInteger(quantity)||quantity<1)return fail('Kein ganzes Stück innerhalb von Kapital und Risikobudget.');
 const totalCHF=quantity*costEach+feesCHF,lossCHF=quantity*lossEach+feesCHF;
 if(!Number.isFinite(totalCHF)||!Number.isFinite(lossCHF)||totalCHF>budgetCHF||lossCHF>riskCHF)
  return fail('Berechnung überschreitet Kapital oder Risikobudget.');
 return {...empty,available:true,isin:candidate.isin,currency,entry,bid,stop,
  quantity,totalCHF,lossCHF,riskUsagePct:100*lossCHF/riskCHF,
  difference:entry-preliminary.entry,differencePct:100*(entry-preliminary.entry)/preliminary.entry,
  observedAt:imported.observedAt,displayedTime:imported.displayedTime,
  referenceAt:preliminary.quoteAt,historicalOnly:imported.historicalOnly,
  leverage:imported.leverage,ko:imported.ko,
  reason:'Modellszenario: gespeicherter Anzeigekurs mit aktuellem Modellstopp und aktueller FX-Referenz. '+
   'Kurszeiten nicht als zeitgleich bestätigt; kein aktueller ausführbarer Kurs. Keine Anpassung des Stopps aus dieser Zeitdifferenz.'};
}
function handsetRunSummary(report,comparisons,now=Date.now()){
 if(!['ok','partial'].includes(report?.status)||!fresh(report.lastCheckedAt,now,120000))
  return 'Handy-Abschluss: aktueller Prüfbericht fehlt.';
 const items=Array.isArray(report.items)?report.items:[];
 const active=items.filter(x=>!['terminated','excluded-factor'].includes(x.state));
 const complete=active.filter(x=>x.handsetObservation?.code==='COMPLETE').length;
 const partial=active.filter(x=>x.handsetObservation?.code==='PARTIAL').length;
 const ended=items.filter(x=>x.state==='terminated').length;
 const excluded=items.filter(x=>x.state==='excluded-factor').length;
 const results=Array.isArray(comparisons)?comparisons:[];
 const ready=results.filter(x=>x.available).length;
 const reasons=[...new Set(results.filter(x=>!x.available).map(x=>x.reason))];
 return 'Handy-Abschluss: '+complete+' vollständig · '+partial+' teilweise · '+ended+' beendet · '+excluded+
  ' Faktor ausgeschlossen. '+ready+' von '+results.length+' ausgewählten Modellvergleichen berechenbar.'+
  (reasons.length?' Offen: '+reasons.join(' '):'')+
  ' Gespeicherte Serverbelege; keine Ausführungsbestätigung.';
}
function handsetModelText(result){
 if(!result.available)return 'Automatischer Handy-Modellvergleich: '+result.reason;
 return 'Automatischer Handy-Modellvergleich · '+result.quantity+' Stück · '+fmt(result.totalCHF)+
  ' CHF einschließlich Gebühren · Modellrisiko '+fmt(result.lossCHF)+' CHF ('+fmt(result.riskUsagePct,1)+
  ' % des Risikobudgets) · Modellstopp '+fmt(result.stop,4)+' '+result.currency+
  ' · Preisabweichung '+fmt(result.differencePct)+' %. Anzeigezeit: '+(result.displayedTime||'fehlt')+
  ' (Zeitzone unbestätigt); Erfassung '+seenAt(result.observedAt)+' Zürich; Modellquelle '+seenAt(result.referenceAt)+
  ' Zürich. '+result.reason;
}

const emptyBroker=isin=>({isin:isin||'',currency:'',bid:'',ask:'',quoteAt:'',venue:'',
 buyingPowerCHF:'',fxRateCHF:'',fxAt:'',tickSize:'',lotSize:'',orderType:'',
 orderDuration:'',confirmedByUser:false,edited:false,handsetFingerprint:null});
const session={budgetCHF:'',riskCHF:'',feesCHF:'',feeProfile:'unknown',fxMode:'unknown',last:null,broker:emptyBroker('')};
const planningState={loaded:false,revision:null,lastRead:0,busy:false,editVersion:0,dirty:false};
async function planningRequest(body){
 const response=await fetch('/api/degiro/android-observations',{method:'POST',credentials:'same-origin',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data=await response.json();
 if(!response.ok||!data.ok)throw Error(data.error||'Planungsvorgaben konnten nicht verarbeitet werden');
 return data;
}
function showServerPlanning(panel,data){
 const result=data.result,box=panel.querySelector('[data-server-handset-plans]');
 if(!result){box.textContent='Serververgleich: wartet auf den nächsten Hintergrundlauf mit Produkt- und Marktdaten.';return;}
 const sameList=result.listUploadedAt===root.BobProductAuditReport?.listUploadedAt;
 if(!data.resultFresh||!sameList){box.textContent='Serververgleich veraltet oder für eine andere Produktliste. Neue Berechnung wird im Hintergrund geprüft.';return;}
 box.textContent='Serververgleich · '+result.available+' von '+result.items.length+' berechenbar · '+
  new Date(result.calculatedAt).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich'})+' Zürich\n'+
  result.items.map(x=>x.isin+' · '+(x.feeAssessment?.available?'Gebühren '+fmt(x.feeAssessment.feesCHF)+' CHF ('+(x.feeAssessment.estimated?'Tarifreserve':'manuell')+') · ':'')+(x.available?
   x.quantity+' Stück · '+fmt(x.totalCHF)+' CHF inkl. Gebühren · Modellstopp '+fmt(x.stop,4)+' '+x.currency+
   ' · Modellrisiko '+fmt(x.lossCHF)+' CHF ('+fmt(x.riskUsagePct,1)+' %)':
   (x.modelStop!==null?'Modellstopp '+fmt(x.modelStop,4)+' · ':'')+(x.reasons||[]).join(' · '))).join('\n')+
  '\nGespeicherte DEGIRO-Anzeige mit aktuellem unabhängigen Modellplan; keine zeitgleiche Kurs- oder Ausführungsbestätigung.';
}
async function loadPlanning(panel,replace=false){
 if(planningState.busy||(!replace&&Date.now()-planningState.lastRead<30000))return;
 planningState.busy=true;planningState.lastRead=Date.now();
 const version=planningState.editVersion,status=panel.querySelector('[data-planning-status]');
 try{
  const data=await planningRequest({action:'plan-read'});
  if(planningState.revision===null)planningState.revision=data.revision;
  if(version===planningState.editVersion&&(replace||!planningState.dirty)){
   planningState.revision=data.revision;
   if(data.config&&(!planningState.loaded||replace))for(const key of ['budgetCHF','riskCHF','feesCHF','feeProfile','fxMode']){
    session[key]=data.config[key]==null?(['feeProfile','fxMode'].includes(key)?'unknown':''):String(data.config[key]);
    panel.querySelector('#'+({budgetCHF:'bobManualBudget',riskCHF:'bobManualRisk',feesCHF:'bobManualFees',feeProfile:'bobFeeProfile',fxMode:'bobFeeFx'})[key]).value=session[key];
   }
   if(replace)planningState.dirty=false;
  }
  planningState.loaded=true;
  status.textContent=data.config?'CHF-Vorgaben serverseitig gespeichert. Änderungen erst mit „Speichern“ übernehmen.':'Noch keine CHF-Vorgaben gespeichert. Keine Beträge vorbelegt.';
  showServerPlanning(panel,data);
 }catch(e){status.textContent=e.message;}
 finally{planningState.busy=false;}
}
async function savePlanning(panel){
 const status=panel.querySelector('[data-planning-status]');
 if(planningState.busy)return;
 if(planningState.revision===null){status.textContent='Gespeicherten Stand zuerst laden; deine Eingaben bleiben erhalten.';return;}
 const config=Object.fromEntries(['budgetCHF','riskCHF','feesCHF'].map(k=>[k,parseAmount(session[k])]));
 if(session.feesCHF.trim()==='')config.feesCHF=null;
 config.feeProfile=session.feeProfile;config.fxMode=session.fxMode;
 config.trailAtr=Number(document.getElementById('trailAtr')?.value||1.5);
 config.minRR=Number(document.getElementById('minRR')?.value||2);
 if(!['budgetCHF','riskCHF','trailAtr','minRR'].every(k=>Number.isFinite(config[k]))||
    (config.feesCHF!==null&&!Number.isFinite(config.feesCHF))){status.textContent='Kapital und Risiko eingeben. Gebühren leer lassen für automatische Ermittlung.';return;}
 const version=planningState.editVersion;planningState.busy=true;
 try{
  const data=await planningRequest({action:'plan-save',expectedRevision:planningState.revision,config});
  planningState.revision=data.revision;
  if(version===planningState.editVersion)planningState.dirty=false;
  status.textContent='CHF-Vorgaben und aktuelle Stopp-Parameter dauerhaft gespeichert. '+
   (config.feesCHF===null?'Bob ermittelt Gebühren je Produkt; fehlende Tarifdaten werden angezeigt. ':'')+'Hintergrundberechnung folgt; keine Order.';
  showServerPlanning(panel,data);
 }catch(e){status.textContent=e.message;}
 finally{planningState.busy=false;planningState.lastRead=0;}
}
function ensurePanel(){
 if(typeof document==='undefined')return null;
 const anchor=document.getElementById('dgTop3Out');
 if(!anchor)return null;
 let panel=document.getElementById('bobManualTop3');
 if(panel)return panel;
 panel=document.createElement('section');
 panel.id='bobManualTop3';
 panel.className='card';
 panel.style.cssText='border:1px solid #dbe4f0;padding:14px;margin-top:12px;background:#f8fbff';
 panel.innerHTML='<h3>Top 3 · Werte zum manuellen Eintragen</h3>'+
  '<p class="small">Bob verwendet exakt die bestehende LONG-/SHORT-Auswahl. Kein GO, keine Order und kein Klick auf DEGIRO. Aktualisierung mit Bobs bestehender Marktprüfung (im Handelsfenster etwa 30 Sek.); Quellenzeiten bestimmen die Gültigkeit, nicht das Neuladen der Anzeige.</p>'+
  '<div class="grid">'+
   '<div><label for="bobManualBudget">Maximaler Einsatz (CHF)</label><input id="bobManualBudget" type="number" min="0.01" step="0.01" inputmode="decimal" placeholder="selbst festlegen"></div>'+
   '<div><label for="bobManualRisk">Maximaler Verlust bis Stopp (CHF)</label><input id="bobManualRisk" type="number" min="0.01" step="0.01" inputmode="decimal" placeholder="selbst festlegen"></div>'+
   '<div><label for="bobManualFees">Gebühren (CHF) · nur manuelle Korrektur</label><input id="bobManualFees" type="number" min="0" step="0.01" inputmode="decimal" placeholder="leer = automatisch je Produkt"></div>'+
   '<div><label for="bobFeeProfile">Dein DEGIRO-Preisverzeichnis</label><select id="bobFeeProfile"><option value="unknown">Noch nicht bestätigt</option><option value="CH_STANDARD">Schweiz · Basic / Active / Trader</option></select></div>'+
   '<div><label for="bobFeeFx">Währungswechsel für diese Planung</label><select id="bobFeeFx"><option value="unknown">Noch nicht bestätigt</option><option value="AUTO_CHF">CHF-Konto mit AutoFX</option><option value="NO_CONVERSION">Kein Wechsel: vorhandenes Währungsguthaben</option></select></div>'+
  '</div>'+
  '<p class="small">Einsatz und Verlustgrenze sind auch ohne Gebühren speicherbar. Bob übernimmt die Tarifreserve automatisch je Produkt in die Rechnung, sobald Tarif, Handelsplatz und Währungswechsel zugeordnet sind. Custody/andere Tarife und manuelle Wechsel: tatsächliche Gesamtkosten eintragen. Keine pauschale Gebühr für alle Produkte.</p>'+
  '<p class="small"><a href="https://www.degiro.ch/data/pdf/ch-de/DE-CH_Preis_und_Leistungsverzeichnis.pdf" target="_blank" rel="noopener">Offizieller CH-Tarif</a> · geprüft 13.11.2026. Reserve für Kauf und Stopp-Verkauf; mögliche Steuern und jährliche Börsenanbindung separat. Keine bestätigte Broker-Abrechnung.</p>'+
  '<button type="button" data-planning-save>CHF-Vorgaben für Hintergrundvergleich speichern</button> '+
  '<button type="button" data-planning-load>Gespeicherte Vorgaben laden</button>'+
  '<p data-planning-status class="small" role="status"></p>'+
  '<div data-server-handset-plans class="small" style="white-space:pre-line"></div>'+
  '<div data-manual-top3-status class="small" role="status"></div>'+
  '<div data-handset-run-summary class="small" role="status"></div>'+
  '<div data-manual-top3-rows></div>'+

  '<details data-manual-broker-compare><summary>DEGIRO-Anzeigewerte vergleichen und Beträge neu berechnen (keine Order)</summary>'+
  '<p class="small">Einmalig die <b>tatsächlich auf der DEGIRO-Produktseite</b> sichtbaren Werte eingeben. Anzeigezeit mit Datum und Zeitzone übernehmen, keine erfundenen Sekunden. Bob liest oder bedient keine Ordermaske. Das bloße Öffnen eines Kaufdialogs bestätigt keinen Fill.</p>'+
  '<div class="grid">'+
   '<div><label for="bobManualScreenIsin">ISIN im DEGIRO-Bild</label><select id="bobManualScreenIsin"></select></div>'+
   '<div><label for="bobManualScreenCcy">Produktwährung</label><select id="bobManualScreenCcy"><option value="">Bitte ablesen</option><option value="EUR">EUR</option><option value="CHF">CHF</option></select></div>'+
   '<div><label for="bobManualScreenBid">DEGIRO Geldkurs</label><input id="bobManualScreenBid" type="number" min="0" step="any" inputmode="decimal"></div>'+
   '<div><label for="bobManualScreenAsk">DEGIRO Briefkurs</label><input id="bobManualScreenAsk" type="number" min="0" step="any" inputmode="decimal"></div>'+
   '<div><label for="bobManualScreenAt">Angezeigte DEGIRO-Kurszeit inkl. Zeitzone</label><input id="bobManualScreenAt" type="text" placeholder="2026-11-12T14:02:00+01:00" autocomplete="off"></div>'+
   '<div><label for="bobManualScreenVenue">Handelsplatz laut Produktseite</label><input id="bobManualScreenVenue" type="text" placeholder="abgelesener Handelsplatz"></div>'+
   '<div><label for="bobManualScreenFunds">Verfügbare CHF-Kaufkraft laut DEGIRO</label><input id="bobManualScreenFunds" type="number" min="0" step="0.01" inputmode="decimal"></div>'+
   '<div><label for="bobManualScreenFx">DEGIRO EUR/CHF-Umrechnung (nur bei EUR-Produkt)</label><input id="bobManualScreenFx" type="number" min="0" step="any" inputmode="decimal"></div>'+
   '<div><label for="bobManualScreenFxAt">DEGIRO FX-Anzeigezeit inkl. Zeitzone</label><input id="bobManualScreenFxAt" type="text" placeholder="2026-11-12T14:02:00+01:00" autocomplete="off"></div>'+
   '<div><label for="bobManualScreenTick">Zulässiger Preisschritt / Tick</label><input id="bobManualScreenTick" type="number" min="0" step="any" inputmode="decimal"></div>'+
   '<div><label for="bobManualScreenLot">Losgröße / Stück-Schritt</label><input id="bobManualScreenLot" type="number" min="1" step="1" inputmode="numeric"></div>'+
   '<div><label for="bobManualScreenOrderType">Angezeigter Kauf-Ordertyp</label><select id="bobManualScreenOrderType"><option value="">Nicht bestätigt</option><option value="LIMIT">LIMIT</option></select></div>'+
   '<div><label for="bobManualScreenDuration">Angebotene Orderdauer</label><select id="bobManualScreenDuration"><option value="">Nicht bestätigt</option><option value="DAY">Tagesgültig</option><option value="GTC">Unbefristet</option></select></div>'+
  '</div>'+
  '<button type="button" data-manual-screen-import>Geteiltes DEGIRO-Produktbild (ungeprüft) vorbefüllen</button>'+
  '<button type="button" data-manual-screen-confirm>Werte erneut prüfen und berechnen – keine Order</button>'+
  '<div data-manual-handset-status class="small" role="status"></div>'+
  '<div data-manual-broker-result class="small" role="status"></div>'+
  '<p class="small">Ein Nutzer-Abgleich ist keine Broker-API-Prüfung und keine Orderannahme. Der Stopp bleibt ein Gold-basiertes <b>Modell</b>, kein sichtbarer DEGIRO-Verkaufsstopp. Nach einem tatsächlichen Kauf muss die echte Ausführung separat bestätigt werden.</p>'+
  '</details>'+
  '<p class="small">Preisfolge: Originalquelle → Ersatzquelle → Berechnung. Die Berechnung ist kein verbindliches DEGIRO-Limit. Ein Schutzstopp ist eine getrennte VERKAUF-Order nach tatsächlichem Kauf; Stop- und KO-Gaps können höhere Verluste verursachen. Stückzahlen sind Planwerte, keine Brokerbestätigung.</p>';
 anchor.insertAdjacentElement('afterend',panel);
 for(const [id,key] of [['bobManualBudget','budgetCHF'],['bobManualRisk','riskCHF'],['bobManualFees','feesCHF']]){
  const input=panel.querySelector('#'+id);
  input.value=session[key];
  input.addEventListener('input',()=>{session[key]=input.value;planningState.editVersion++;planningState.dirty=true;if(session.last)renderFrom(session.last);});
 }
 panel.querySelector('[data-planning-save]').addEventListener('click',()=>savePlanning(panel));
 panel.querySelector('[data-planning-load]').addEventListener('click',()=>loadPlanning(panel,true));
 for(const [id,key] of [['bobFeeProfile','feeProfile'],['bobFeeFx','fxMode']]){
  const field=panel.querySelector('#'+id);field.value=session[key];
  field.addEventListener('change',()=>{session[key]=field.value;planningState.editVersion++;planningState.dirty=true;if(session.last)renderFrom(session.last);});
 }
 for(const [id,key] of [
  ['bobManualScreenIsin','isin'],['bobManualScreenCcy','currency'],
  ['bobManualScreenBid','bid'],['bobManualScreenAsk','ask'],['bobManualScreenAt','quoteAt'],
  ['bobManualScreenVenue','venue'],['bobManualScreenFunds','buyingPowerCHF'],
  ['bobManualScreenFx','fxRateCHF'],['bobManualScreenFxAt','fxAt'],
  ['bobManualScreenTick','tickSize'],['bobManualScreenLot','lotSize'],
  ['bobManualScreenOrderType','orderType'],['bobManualScreenDuration','orderDuration']]){
  const field=panel.querySelector('#'+id);
  field.value=session.broker[key]||'';
  field.addEventListener(field.tagName==='SELECT'?'change':'input',()=>{
   if(key==='isin'&&field.value!==session.broker.isin){
    session.broker=emptyBroker(field.value);
    for(const [inputId,inputKey] of [
     ['bobManualScreenCcy','currency'],['bobManualScreenBid','bid'],
     ['bobManualScreenAsk','ask'],['bobManualScreenAt','quoteAt'],
     ['bobManualScreenVenue','venue'],['bobManualScreenFunds','buyingPowerCHF'],
     ['bobManualScreenFx','fxRateCHF'],['bobManualScreenFxAt','fxAt'],
     ['bobManualScreenTick','tickSize'],['bobManualScreenLot','lotSize'],
     ['bobManualScreenOrderType','orderType'],['bobManualScreenDuration','orderDuration']]){
     const reset=panel.querySelector('#'+inputId);if(reset)reset.value=session.broker[inputKey];
    }
   }else session.broker[key]=field.value;
   session.broker.edited=key!=='isin';
   session.broker.confirmedByUser=false;
   if(session.last)renderFrom(session.last);
  });
 }
 panel.addEventListener('click',async e=>{
  if(e.target.closest('button[data-manual-screen-import]')){
   const status=panel.querySelector('[data-manual-broker-result]');
   try{
    const saved=root.BobAndroidEvidence?.savedObservations?.(root.localStorage)||[];
    const match=saved.find(row=>row.draft?.isin===session.broker.isin);
    const imported=importAndroidScreenDraft(match?.draft);
    if(!imported.available){status.textContent=imported.reason;return;}
    session.broker={...emptyBroker(imported.values.isin),...imported.values,edited:true};
    for(const input of panel.querySelectorAll('[id^="bobManualScreen"]')){
     if(input.id!=='bobManualScreenIsin')input.value='';
    }
    // Refresh only the visible fields, preserving budgets in memory.
    for(const [id,key] of [
     ['bobManualScreenIsin','isin'],['bobManualScreenCcy','currency'],
     ['bobManualScreenBid','bid'],['bobManualScreenAsk','ask'],
     ['bobManualScreenAt','quoteAt'],['bobManualScreenVenue','venue']]){
     const field=panel.querySelector('#'+id);
     if(field)field.value=session.broker[key]||'';
    }
    if(session.last)renderFrom(session.last);
    panel.querySelector('[data-manual-broker-result]').textContent=
     imported.note+(imported.displayedTime?' Bildanzeige: '+imported.displayedTime+'.':'');
   }catch(_){status.textContent='Geteiltes Produktbild nicht lesbar; Werte bitte manuell prüfen.';}
   return;
  }
  if(e.target.closest('button[data-manual-screen-confirm]')){
   session.broker.confirmedByUser=true;
   if(session.last)renderFrom(session.last);
   return;
  }
  const btn=e.target.closest('button[data-manual-copy]');
  if(!btn||btn.disabled)return;
  const value=btn.dataset.manualCopy;
  const status=panel.querySelector('[data-manual-top3-status]');
  try{
   if(!navigator.clipboard?.writeText)throw Error('clipboard-unavailable');
   await navigator.clipboard.writeText(value);
   status.textContent='Einzelwert kopiert. Bei DEGIRO vor Eingabe und Absenden selbst prüfen.';
  }catch(_){status.textContent='Kopieren auf diesem Gerät nicht möglich. Wert bitte manuell übernehmen.';}
 });
 return panel;
}
function parseAmount(s){return String(s).trim()===''?NaN:Number(s);}

function refreshHandset(){if(session.last)renderFrom(session.last);}
function syncHandset(panel,now){
 const imported=importHandsetReport(root.BobProductAuditReport,session.broker.isin,now);
 const status=panel.querySelector('[data-manual-handset-status]');
 if(!imported.available){status.textContent=imported.reason;return;}
 status.textContent=imported.note+
  (imported.displayedTime?' Angezeigte Kurszeit: '+imported.displayedTime+'.':' Kurszeit fehlt im Lesebeleg.')+
  ' Hebel laut Anzeige: '+(imported.leverage||'fehlt')+' · KO laut Anzeige: '+(imported.ko||'fehlt')+'.';
 // Never overwrite a user's edits, confirmation or a newer manually shared image.
 if(session.broker.edited||session.broker.confirmedByUser||
    session.broker.handsetFingerprint===imported.fingerprint)return;
 session.broker={...emptyBroker(imported.values.isin),...imported.values,
  handsetFingerprint:imported.fingerprint};
 for(const [id,key] of [['Ccy','currency'],['Bid','bid'],['Ask','ask'],['At','quoteAt'],['Venue','venue']]){
  panel.querySelector('#bobManualScreen'+id).value=session.broker[key]||'';
 }
}

function renderBrokerComparison(panel,selected,plans,now){
 const select=panel.querySelector('#bobManualScreenIsin');
 const options=selected.map(c=>'<option value="'+escape(c.isin)+'">'+escape(c.isin)+'</option>').join('');
 if(select._html!==options){select.innerHTML=options;select._html=options;}
 if(!selected.some(c=>c.isin===session.broker.isin)){
  session.broker=emptyBroker(selected[0]?.isin||'');
  for(const input of panel.querySelectorAll('[id^="bobManualScreen"]')){
   if(input.id!=='bobManualScreenIsin')input.value='';
  }
 }
 select.value=session.broker.isin;
 const out=panel.querySelector('[data-manual-broker-result]');
 if(!selected.length){
  panel.querySelector('[data-manual-handset-status]').textContent='';
  out.textContent='Kein aktuelles geeignetes LONG-/SHORT-Produkt für diesen Vergleich ausgewählt.';
  return;
 }
 const row=plans.get(session.broker.isin);
 syncHandset(panel,now);
 const result=reconcileBrokerDisplay({
  ...row,preliminary:row?.preliminary,broker:session.broker,
  budgetCHF:parseAmount(session.budgetCHF),riskCHF:parseAmount(session.riskCHF),
  feesCHF:row?.feesCHF,now,direction:row?.candidate?.direction});
 if(!result.available){
  out.textContent='Noch kein gültiger erneuter Vergleich: '+result.reason;
  return;
 }
 const sign=result.difference>=0?'+':'';
 out.textContent='KAUF-Preis abgelesen '+fmt(result.entry,4)+' '+result.currency+
  ' statt Vorabwert '+fmt(row.preliminary.entry,4)+' '+result.currency+
  ' (Abweichung '+sign+fmt(result.difference,4)+' / '+sign+fmt(result.differencePct,2)+' %). '+
  'NEU: '+result.quantity+' ganze Stück · geschätzte Belastung '+fmt(result.totalCHF)+
  ' CHF einschließlich deiner Gebühren · geschätzter Verlust bis Gold-Modellstopp '+
  fmt(result.lossCHF)+' CHF · Modellstopp '+fmt(result.stop,4)+' '+result.currency+
  '. Stopp-Basis: '+result.stopBasis+' · Kurszeit '+seenAt(result.sourceAt)+' Zürich · FX-Basis: '+result.fxBasis+
  '. '+result.reason+' Kein DEGIRO-Fill, keine automatische Kauf-/Verkaufsorder.';
}
function renderFrom(snapshot){
 const panel=ensurePanel();if(!panel)return;
 void loadPlanning(panel);
 const now=Date.now(),{flow,products,bundle}=snapshot,side=flow?.direction;
 const rows=panel.querySelector('[data-manual-top3-rows]');
 const status=panel.querySelector('[data-manual-top3-status]');
 const selected=flow?.approved&&validSide(side)?
  (flow.groups||[]).flatMap(g=>g.candidates||[]).filter((c,i,all)=>all.findIndex(p=>p.isin===c.isin)===i).slice(0,3):[];
 const budgetCHF=parseAmount(session.budgetCHF),riskCHF=parseAmount(session.riskCHF);
 const market=root.productMarketPlan?.(side,now);
 const planByIsin=new Map();
 const handsetComparisons=[];
 const offers=selected.map((candidate,i)=>{
  const product=(products||[]).find(p=>p.isin===candidate.isin);
  const currency=product?.quote?.metadata?.currency||product?.quote?.currency;
  const selectedQuote=selectQuoteByPriority(product,now);
  const quote=selectedQuote?.quote||null;
  const stopPlan=product&&quote&&market?.available?
   root.BobDegiro?.productRiskPreview(product,market,now,quote):null;
  const fx=readChfFx(bundle?.spots,now,quote?.currency||currency);
  const feeAssessment=resolveFees({config:{budgetCHF,feeProfile:session.feeProfile,fxMode:session.fxMode,
   feesCHF:session.feesCHF.trim()===''?null:parseAmount(session.feesCHF)},
   report:root.BobProductAuditReport,isin:candidate.isin,spots:bundle?.spots,now});
  const feesCHF=feeAssessment.available?feeAssessment.feesCHF:null;
  const plan=evaluate({candidate,product,quote,stopPlan,fx,budgetCHF,riskCHF,feesCHF,now,direction:side});
  const handsetComparison=compareHandsetModel({report:root.BobProductAuditReport,
   candidate,product,preliminary:plan,fx,budgetCHF,riskCHF,feesCHF,now,direction:side});
  handsetComparisons.push(handsetComparison);
  planByIsin.set(candidate.isin,{candidate,product,preliminary:plan,fx,stopPlan,feesCHF});
  const line=(label,value,copy)=>'<div style="margin:5px 0"><b>'+label+':</b> '+escape(value)+
   (copy!==null&&copy!==undefined?'<button type="button" data-manual-copy="'+escape(copy)+'" style="width:auto;margin-left:8px;padding:5px 9px;font-size:12px;background:#334155">Kopieren</button>':'')+'</div>';
  const entry=plan.entry!==null?fmt(plan.entry,4)+' '+plan.currency+'/Stück':'—';
  const stop=plan.stop!==null?'≈ '+fmt(plan.stop,4)+' '+plan.currency+'/Stück':'—';
  const orderCopy=plan.available&&plan.copyAllowed;
  const sourceLine=selectedQuote?.label||'Keine aktuelle belegte Quelle';
  const calculationNote=selectedQuote?.calculated?
   '<div class="small" style="color:#92400e"><b>Berechnet – NICHT als DEGIRO-Kaufpreis übernehmen.</b> Stückzahl und Stopp sind nur ein rechnerisches Szenario; keine Kopierfreigabe.</div>':'';

  return '<article style="padding:12px;border:1px solid #dde5ef;border-radius:12px;margin-top:10px;background:white">'+
   '<b>Platz '+(i+1)+' · '+escape(candidate.isin)+' · '+escape(side)+'</b>'+
   line('ISIN',candidate.isin,candidate.isin)+
   '<div class="small"><b>Preis-Herkunft:</b> '+escape(sourceLine)+'</div>'+
   line('KAUF · Briefkurs als Limit-Richtwert',entry,orderCopy?String(plan.entry):null)+
   line('STOP-LOSS · Modell für späteren VERKAUF',stop,orderCopy?String(Number(plan.stop.toFixed(4))):null)+
   line('Stückzahl',plan.available?String(plan.quantity):'—',orderCopy?String(plan.quantity):null)+
   line('Geschätzter Gesamtbetrag',plan.available?fmt(plan.totalCHF)+' CHF':'—',orderCopy?String(Number(plan.totalCHF.toFixed(2))):null)+
   line('Kauf-/Verkaufsgebühren',feeAssessment.available?fmt(feesCHF)+' CHF · '+feeAssessment.reason:feeAssessment.reason,null)+
   calculationNote+
   '<div class="small" data-handset-model-result>'+escape(handsetModelText(handsetComparison))+'</div>'+
   (plan.available?'<div class="small">Modellverlust bei Stopp einschließlich eingegebener Gebühren: ≈ '+fmt(plan.lossCHF)+' CHF. Tatsächlicher Verlust kann durch Gaps, KO oder fehlende Ausführung größer sein.</div>':'')+
   '<div class="small" style="margin-top:7px">'+escape(plan.source?'Quelle: '+plan.source+' · Original-Briefkurszeit '+seenAt(plan.quoteAt)+' Zürich. '+plan.fxNote:'Keine aktuelle Original-Kursquelle.')+'</div>'+
   '<div class="small" style="margin-top:5px;color:'+(plan.available?'#166534':'#9a3412')+'">'+escape(plan.reason)+'</div></article>';
 });
 status.textContent=selected.length?
  'Richtung '+side+' · '+selected.length+' Ranking-Produkte · geprüft '+new Date(now).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich'})+' · keine DEGIRO-Ausführungszusage':
  'ABWARTEN · keine aktuellen freigegebenen Ranking-Produkte, daher keine Kauf-/Stop-/Stückzahlwerte.';
 const output=offers.length?offers.join(''):'<p class="small">Keine drei Kandidaten erzwingen. Erst bestätigtes Markt- und Produktsignal abwarten.</p>';
 if(rows._html!==output){rows.innerHTML=output;rows._html=output;}
 panel.querySelector('[data-handset-run-summary]').textContent=handsetRunSummary(root.BobProductAuditReport,handsetComparisons,now);
 renderBrokerComparison(panel,selected,planByIsin,now);
}
function render(flow,products,bundle){
 session.last={flow,products,bundle};
 renderFrom(session.last);
}
const api={resolveFees,handsetRunSummary,compareHandsetModel,evaluate,reconcileBrokerDisplay,importAndroidScreenDraft,importHandsetReport,refreshHandset,readChfFx,selectQuoteByPriority,render};
root.BobManualTop3=api;
if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
