/* Two-stage, read-only product stop assistant. Never issues broker orders or approves trades. */
(function(root){
 'use strict';
 const positive=v=>typeof v==='number'&&Number.isFinite(v)&&v>0;
 const atMs=v=>typeof v==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(v)?Date.parse(v):NaN;
 const recent=(v,now,age)=>Number.isFinite(atMs(v))&&now>=atMs(v)&&now-atMs(v)<=age;
 const side=x=>x==='LONG'||x==='SHORT';
 function selectQuote(q,isin,now=Date.now()){
  if(!q||q.isin!==isin||q.productVerified!==true||q.sourceDisabled
    ||q.metadata?.status!==1||q.metadata?.tradingHalted===true) return null;
  const candidates=[];
  for(const [origin,row] of [['issuer',q],['comdirect',q.secondaryQuote],
    ['analysis',q.analysisQuote],['swissquote',q.thirdQuote]]){
   if(!row||row.isin!==isin||row.currency!=='EUR'||!positive(row.bid)
      ||!positive(row.ask)||row.ask<row.bid||!recent(row.bidAt,now,90000)
      ||!recent(row.askAt,now,90000)||row.delayed===true||row.estimated===true
      ||!String(row.source||'').trim()||['calculated','unavailable'].includes(row.priceKind)) continue;
   // A native issuer orderable quote and a secondary market observation are
   // different evidence. Neither is an authenticated DEGIRO execution.
   if(origin==='issuer'&&q.found!==true) continue;
   const issuer=origin==='issuer'&&q.found===true&&row.isExecutableQuote===true
     &&!q.sourceFailure&&!q.quoteFailureCode&&!q.sourceFailureCode
     &&row.priceKind!=='issuer-chart'&&row.priceKind!=='research'&&row.researchOnly!==true;
   if(origin!=='issuer'&&(row.isExecutableQuote!==false||row.degiroExecutable!==false)) continue;
   if(origin==='issuer'&&!issuer&&row.isExecutableQuote!==false) continue;
   candidates.push({isin,bid:row.bid,ask:row.ask,at:row.bidAt,askAt:row.askAt,
     source:row.source,origin,kind:issuer?'issuer':'research',chart:row.priceKind==='issuer-chart',
     delayed:false,error:false,degiroExecutable:false});
  }
  // Latest original bid clock wins; prefer a native issuer quote on equal time.
  candidates.sort((a,b)=>atMs(b.at)-atMs(a.at)||
    Number(b.kind==='issuer')-Number(a.kind==='issuer'));
  return candidates[0]||null;
 }
 function evaluate({product,stopGold,targetGold,spots,quote,now=Date.now()}={}){
  const unavailable=(reason)=>({available:false,stage:'unavailable',reason,
    model:null,observed:null,degiroExecutable:false,automaticOrder:false});
  if(!product||!side(product.direction)||product.currency!=='EUR'
    ||product.simpleSpotTurbo!==true||product.referenceConfirmed!==true
    ||!positive(stopGold)||!positive(targetGold))
    return unavailable('Bestätigtes einfaches EUR-Gold-Spot-Turbo und Gold-Stopp-/Zielplan fehlen.');
  const calc=root.BobTradeProduct;
  if(!calc)return unavailable('Produktrechner nicht geladen.');
  const stop=calc.price(product,stopGold),target=calc.price(product,targetGold);
  if(!stop?.available||!target?.available||!(stop.price<target.price)
    ||!(stop.price<product.entry&&target.price>product.entry))
    return unavailable('Stopp/Ziel im Produktkurs nicht verlässlich berechenbar (Produktbedingungen oder KO prüfen).');
  const result={available:true,stage:'waiting-market',reason:'Aktuelle Gold-/FX-Referenz fehlt.',
    stopEur:stop.price,targetEur:target.price,currency:'EUR',
    model:null,observed:null,degiroExecutable:false,automaticOrder:false};
  const fx=spots?.usd_eur_meta,stamp=spots?.spot_price_as_of;
  if(spots?.is_genuine_xauusd_spot===true&&!spots?.spot_error
     &&recent(stamp,now,60000)&&positive(spots.xaus)
     &&positive(fx?.rate)&&!fx?.error&&recent(fx?.fetchedAt,now,90000)){
   const updated=calc.withFx(product,spots,now);
   if(updated?.fxDetails?.delayed===false){
    const st=calc.price(updated,stopGold),tg=calc.price(updated,targetGold),
      current=calc.price(updated,spots.xaus);
    if(st.available&&tg.available&&current.available&&st.price<tg.price){
     const room=Math.max(0,product.entry-st.price);
     const boundary=Math.max(room*0.2,0.01);
     const signal=current.price<=st.price?'model-stop-zone':
       current.price-st.price<=boundary?'model-stop-near':
       current.price>=tg.price?'model-target-zone':'model-ok';
     result.model={signal,price:current.price,stopEur:st.price,targetEur:tg.price,
       spotAt:stamp,fxFetchedAt:fx.fetchedAt,
       note:'Nur theoretisch: gleicher Gold-Spot-Datensatz, aktuelle FX-Abrufzeit, konstante Produktannahmen. Keine bestätigte Ausführung.'};
     result.stopEur=st.price;result.targetEur=tg.price;
     result.stage=signal;
     result.reason='Produktwert aus Gold und FX geschätzt; keine Orderauslösung.';
    }
   }
  }
  if(quote?.isin===product.isin&&quote.kind==='issuer'&&
     positive(quote.bid)&&positive(quote.ask)&&quote.ask>=quote.bid
     &&recent(quote.at,now,90000)&&recent(quote.askAt,now,90000)
     &&quote.error!==true&&quote.delayed!==true){
   // Only compare the issuer bid against stop/target levels when current
   // Spot AND FX have independently qualified this scenario. An old FX
   // assumption must never transform an issuer price into a stop alert.
   const signal=!result.model?'issuer-price-only':
     quote.bid<=result.stopEur?'issuer-stop-observed':
     quote.bid>=result.targetEur?'issuer-target-observed':'issuer-ok';
   result.observed={signal,bid:quote.bid,at:quote.at,source:quote.source,
     note:'Datierte Anbieterbeobachtung, kein DEGIRO-Brokerkurs und keine garantierte Orderausführung.'};
   result.stage=signal;
   result.reason=result.model?
     'Originalanbieter-Kurs gegen den aktuellen Modellstopp geprüft; bei Schwellenüberschreitung DEGIRO selbst kontrollieren.':
     'Originalanbieter-Geldkurs vorhanden, aber ohne aktuellen Gold-/FX-Modellstopp keine Schwellenbestätigung.';
  }
  // Research-only quotes deliberately never promote to "issuer observed".
  return result;
 }
 function instructions({isin,quantity,stopEur,currency='EUR'}={}){
  if(!/^[A-Z]{2}[A-Z0-9]{10}$/.test(isin||'')||
     !Number.isSafeInteger(quantity)||quantity<=0||!positive(stopEur)||currency!=='EUR')
     return {available:false,reason:'ISIN, ganze Stückzahl und bestätigter EUR-Modell-Stopp fehlen. Brokerkurs separat prüfen.'};
  return {available:true,isin,quantity,stopEur,currency,
   steps:[
    '1. DEGIRO öffnen, im Portfolio die exakt gleiche ISIN und die gehaltene Stückzahl prüfen.',
    '2. Falls für dieses Produkt unterstützt: VERKAUFEN wählen und den verfügbaren Stopp-Ordertyp prüfen.',
    '3. Produkt-Stopp als Orientierung verwenden. Den aktuellen DEGIRO-Geldkurs, Trigger und ggf. Stop-Limit selbst prüfen; ein Stop-Limit kann unausgeführt bleiben.',
    '4. Stückzahl, Währung, Börsenplatz und Orderbedingungen kontrollieren und den Auftrag ausschließlich selbst bestätigen.',
    '5. Im DEGIRO-Orderstatus prüfen, ob der Schutzauftrag tatsächlich angenommen wurde. Bob kann dies nicht bestätigen.'
   ],note:'Modellpreis ist kein ausführbarer Kurs. Knock-out, Handelsunterbrechung und Kurslücken können die Ausführung verhindern.'};
 }
 let panel=null;
 function update(info){
  if(typeof document==='undefined')return;
  const stopPanel=document.getElementById('stopPanel');
  if(!stopPanel)return;
  const {product,stopGold,targetGold,spots,quote,now=Date.now()}=info||{};
  if(!panel){
   panel=document.createElement('section');panel.id='bobTwoStageStop';panel.style.cssText='border:1px solid #cbd5e1;border-radius:12px;padding:12px;margin:12px 0;';
   panel.innerHTML='<h4>Zweistufiger Produkt-Stopp · ohne automatische Orders</h4><p data-stop-stage role="status"></p><p data-stop-model></p><p data-stop-issuer></p><details><summary>Manuellen DEGIRO-Schutzstopp vorbereiten</summary><p data-stop-instructions style="white-space:pre-line"></p><p><button type="button" data-copy-isin>ISIN kopieren</button> <button type="button" data-copy-stop>Modell-Stopp kopieren</button></p><p data-copy-status role="status"></p></details>';
   stopPanel.insertAdjacentElement('afterend',panel);
   panel.addEventListener('click',async e=>{
    const key=e.target?.dataset?.copyIsin!==undefined?'isin':
      e.target?.dataset?.copyStop!==undefined?'stop':null;
    if(!key)return;
    const value=panel.dataset[key];
    const message=panel.querySelector('[data-copy-status]');
    if(!value){message.textContent='Für diese Eingabe fehlt ein geprüfter Wert.';return;}
    try{
     if(!navigator?.clipboard?.writeText)throw Error('not-supported');
     await navigator.clipboard.writeText(value);
     message.textContent='Wert kopiert. Bei DEGIRO selbst einfügen und prüfen.';
    }catch(_){message.textContent='Kopieren nicht möglich; Wert bitte manuell prüfen.';}
   });
  }
  const v=evaluate({product,stopGold,targetGold,spots,quote,now});
  const fmt=n=>positive(n)?n.toFixed(4)+' EUR/Stück':'nicht verfügbar';
  panel.dataset.isin=product?.isin||'';
  panel.dataset.stop=v.model?String(Number(v.model.stopEur.toFixed(4))):'';
  const stage=panel.querySelector('[data-stop-stage]');
  stage.textContent=v.available?'Status: '+v.stage+' · '+v.reason:'Nicht verfügbar: '+v.reason;
  panel.querySelector('[data-stop-model]').textContent=v.model?
   'Stufe A · Modell: '+fmt(v.model.price)+' · Stopp '+fmt(v.model.stopEur)+
   ' · Ziel '+fmt(v.model.targetEur)+' · '+v.model.note:
   'Stufe A: aktueller Modellkurs nicht belastbar (frischen Gold-Spot, FX-Abruf und Produktbedingungen prüfen).';
  panel.querySelector('[data-stop-issuer]').textContent=v.observed?
   'Stufe B · Anbieter-Geldkurs '+fmt(v.observed.bid)+' · '+v.observed.at+
   ' · '+v.observed.source+' · '+v.observed.note:
   'Stufe B: kein vollständig datierter originaler Anbieter-Geld-/Briefkurs. Kein bestätigtes Stop-/Zielereignis.';
  const guide=instructions({isin:product?.isin,quantity:product?.quantity,
    stopEur:v.model?.stopEur,currency:product?.currency});
  panel.querySelector('[data-stop-instructions]').textContent=guide.available?
    guide.steps.join('\n')+'\n'+guide.note:guide.reason;
  panel.querySelector('[data-copy-stop]').disabled=!guide.available;
  panel.querySelector('[data-copy-isin]').disabled=!product?.isin;
 }
 root.BobStopAssistant={selectQuote,evaluate,instructions,update};
 if(typeof module!=='undefined')module.exports=root.BobStopAssistant;
})(typeof window!=='undefined'?window:globalThis);
