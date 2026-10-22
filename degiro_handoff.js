/* Manual order planning only. No brokerage requests or accessibility automation. */
(function(root){
'use strict';
const KEY='bob.degiro2.plan.v1';
function day(date=new Date()){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);}
function cents(value){const s=String(value).trim().replace(',','.');if(!/^\d{1,9}(\.\d{1,2})?$/.test(s))throw Error('Geldbeträge mit höchstens zwei Nachkommastellen eingeben.');const n=Math.round(Number(s)*100);if(!Number.isSafeInteger(n))throw Error('Betrag zu groß.');return n;}
function isin(value){const s=String(value).trim().toUpperCase();if(!/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(s))throw Error('Bitte eine gültige ISIN eingeben.');const digits=s.replace(/[A-Z]/g,c=>String(c.charCodeAt(0)-55));let sum=0;[...digits].reverse().forEach((c,i)=>{let n=Number(c)*(i%2?2:1);sum+=n>9?n-9:n;});if(sum%10)throw Error('ISIN-Prüfziffer stimmt nicht.');return s;}
function reserve(state,input,today=day()){
 const budget=cents(input.budget),fees=cents(input.fees),price=cents(input.price),qty=Number(input.qty);
 if(budget<=0||price<=0||!/^\d+$/.test(String(input.qty))||!Number.isSafeInteger(qty)||qty<1)throw Error('Budget, Stückzahl und Limit müssen positiv sein.');
 if(!['EUR','CHF'].includes(input.currency)||!['Kauf','Verkauf'].includes(input.side))throw Error('Ungültige Währung oder Richtung.');
 const orders=state&&state.day===today?state.orders:[];
 if(!Array.isArray(orders))throw Error('Gespeicherte Planung ist ungültig.');
 if(orders.length&&state.currency!==input.currency)throw Error('Bestehende Tagesentwürfe zuerst entfernen, bevor du die Währung wechselst.');
 const cost=qty*price+fees;if(!Number.isSafeInteger(cost))throw Error('Orderbetrag zu groß.');
 const used=orders.reduce((n,o)=>{if(!Number.isSafeInteger(o.cost)||o.cost<0||!['Kauf','Verkauf'].includes(o.side))throw Error('Gespeicherte Planung ist ungültig.');return n+(o.side==='Kauf'?o.cost:0);},0);
 if(used+(input.side==='Kauf'?cost:0)>budget)throw Error('Die geplanten Käufe überschreiten dein Tagesbudget.');
 const stop=input.stop?cents(input.stop):null,target=input.target?cents(input.target):null;
 if(input.side==='Verkauf'&&(stop!==null||target!==null))throw Error('Stopp und Ziel gehören nicht zum Verkaufsentwurf.');
 if(input.side==='Kauf'&&((stop!==null&&!(stop>0&&stop<price))||(target!==null&&target<=price)))throw Error('Stopp muss unter dem Kauflimit und Ziel darüber liegen (Produktkurs).');
 if(input.side==='Verkauf'&&qty*price<fees)throw Error('Verkaufsgebühren überschreiten den Bruttoerlös.');
 const order={isin:isin(input.isin),side:input.side,qty,price,fees,cost,stop,target};
 return {day:today,currency:input.currency,budget,orders:[...orders,order]};
}
function maxQuantity(state,input,today=day()){
 const budget=cents(input.budget),price=cents(input.price),fees=cents(input.fees);
 if(price<=0)throw Error('Zuerst ein positives Limit eingeben.');
 const current=state&&state.day===today?state:null;
 if(current&&current.orders.length&&current.currency!==input.currency)throw Error('Währung passt nicht zur Tagesplanung.');
 const used=current?current.orders.filter(o=>o.side==='Kauf').reduce((n,o)=>n+o.cost,0):0;
 return Math.max(0,Math.floor((budget-used-fees)/price));
}
function money(c){return (c/100).toFixed(2).replace('.',',');}
function snapPositions(data,now=Date.now()){
 if(!data||data.code!=='READ_OK'||data.readOnly!==true||!Array.isArray(data.snapshot?.accounts))return [];
 const found=[];
 data.snapshot.accounts.forEach((a,index)=>{
  const at=Date.parse(a?.positionsSourceAt||'');
  const current=data.fresh===true&&a?.freshnessMode==='realtime'&&Number.isFinite(at)&&now>=at&&now-at<=690000;
  for(const p of Array.isArray(a?.positions)?a.positions:[]){
   let id;try{id=isin(p.isin);}catch(_){continue;}
   if(p.csvLinkConflict||p.cashEquivalent||!['EUR','CHF'].includes(p.currency))continue;
   const quantity=Number(p.units);
   if(!Number.isSafeInteger(quantity)||quantity<=0)continue;
   const mapped=!!(p.csvEvidence&&p.csvEvidence.currency===p.currency&&p.isinSource&&
    ['provider-isin','provider-wkn','figi-verified','user-confirmed'].includes(p.isinSource));
   const provider=p.providerIsin===id;
   const confirmed=mapped||provider;
   found.push({isin:id,currency:p.currency,quantity,account:index+1,name:String(p.name||p.symbol||'Position').slice(0,70),
    sourceAt:a.positionsSourceAt||null,identityConfirmed:confirmed,current:current&&confirmed,
    note:!confirmed?'ISIN-Zuordnung nicht bestätigt':!current?'Depotstand verzögert oder nicht aktuell bestätigt':'Depotstand laut SnapTrade; bei DEGIRO überprüfen'});
  }
 });
 return found;
}
function summary(o,c){
 const gross=o.qty*o.price;
 let out=`ORDERENTWURF – nicht übermittelt\n${o.side}: ${o.isin}\nStückzahl: ${o.qty}\nLimit je Stück: ${money(o.price)} ${c}\nGeschätzte Gebühren: ${money(o.fees)} ${c}`;
 out+=o.side==='Kauf'?`\nGeplanter Kaufbetrag inkl. Gebühren: ${money(o.cost)} ${c}`:
  `\nBruttoerlös: ${money(gross)} ${c}\nGeschätzter Nettoerlös nach Gebühren: ${money(gross-o.fees)} ${c}`;
 if(o.proposal?.sourceAt)out+='\nQuellbeobachtung (keine DEGIRO-Ausführung): '+o.proposal.source+' · '+o.proposal.sourceAt+
  (o.proposal.modelAt?' · Goldanalyse '+o.proposal.modelAt:'')+
  '\nAchtung: Nach Speicherung sind Kurs und Modell nicht automatisch aktualisiert.';
 if(o.side==='Kauf'){
  if(o.stop!==null&&o.stop!==undefined)out+=`\nSeparater geplanter Produkt-Stopp: ${money(o.stop)} ${c} (nur Planung)\nRechnerischer Verlust bis Stopp ohne Gebühren/Slippage: ${money((o.price-o.stop)*o.qty)} ${c}`;
  if(o.target!==null&&o.target!==undefined)out+=`\nSeparates geplantes Produkt-Ziel: ${money(o.target)} ${c} (nur Planung)`;
 }
 return out+'\nOriginalkurs, Datenalter, Handelsplatz, KO, Produkttyp, Orderart, Verfügbarkeit, Gültigkeit und Gebühren direkt in DEGIRO prüfen. Stopp ist keine Verlustgarantie. Du musst alle Werte in DEGIRO selbst eingeben und die Order selbst bestätigen.';
}

/* Read-only, evidence-gated proposal. No trade approval, broker requests or order submission. */
function calculateProposal(p,input,market={},state=null,now=Date.now()){
 const partial=(reason,extra={})=>({ok:false,reason,tradeable:false,automaticOrder:false,...extra});
 let id;try{id=isin(input.isin);}catch(e){return partial(e.message);}
 if(!p||p.isin!==id)return partial('Produktidentität passt nicht zur Auswahl.');
 const side=input.side;if(!['Kauf','Verkauf'].includes(side))return partial('Kauf oder Verkauf wählen.');
 const q=p.quote;
 if(!q||q.isin!==id||q.found!==true||q.productVerified!==true||q.estimated===true||q.isEstimated===true||q.paperSelectionOnly===true||q.paperQuoteAccepted===true||/estimate|calculated|simulation|paper/i.test(String(q.priceKind||'')))
  return partial('Kein bestätigtes Produktkurspaar für diese ISIN. Bob erfindet kein Limit.');
 if(q.metadata?.status!==1||q.metadata?.tradingHalted===true||q.metadata?.underlyingType==='FUTURE'||
    q.marketOpen===false||q.sourceDisabled===true||q.eligible===false)
  return partial('Emittent bestätigt keine aktive, passende Produktnotierung (gesperrt, geschlossen oder Future).');
 const currency=q.currency||q.metadata?.currency;
 if(!['EUR','CHF'].includes(currency)||currency!==input.currency||q.metadata?.currency&&q.metadata.currency!==currency||
     p.reference?.currency&&p.reference.currency!==currency)
  return partial('Produktwährung nicht eindeutig zugeordnet; keine automatische Preisübernahme.');
 const direction=q.metadata?.direction||p.direction;
 if(!['LONG','SHORT'].includes(direction)||p.direction&&direction!==p.direction)
  return partial('Long-/Short-Richtung nicht eindeutig.');
 const field=side==='Kauf'?'ask':'bid',atField=side==='Kauf'?'askAt':'bidAt';
 const stamp=q[atField];const at=typeof stamp==='string'&&/(Z|[+-]\d{2}:\d{2})$/i.test(stamp)?Date.parse(stamp):NaN;
 if(!Number.isFinite(at)||now-at<0||now-at>90000)return partial('Originalzeit des '+(side==='Kauf'?'Briefkurses':'Geldkurses')+' fehlt oder ist älter als 90 Sekunden.');
 const raw=Number(q[field]);
 if(!(raw>0&&Number.isFinite(raw)))return partial('Kein positiver originaler '+field+'-Kurs verfügbar.');
 const opposite=field==='ask'?'bid':'ask',other=Number(q[opposite]),otherStamp=q[opposite+'At'];
 const otherAt=typeof otherStamp==='string'&&/(Z|[+-]\d{2}:\d{2})$/i.test(otherStamp)?Date.parse(otherStamp):NaN;
 if(!(other>0&&Number.isFinite(other)&&Number(q.ask)>=Number(q.bid)&&Number.isFinite(otherAt)&&
       now-otherAt>=0&&now-otherAt<=90000&&Math.abs(otherAt-at)<=90000))
  return partial('Originales zeitgleiches Geld-/Brief-Paar fehlt oder hat einen Widerspruch.');
 const price=Math[side==='Kauf'?'ceil':'floor'](raw*100+ (side==='Kauf'?-1e-8:1e-8));
 if(!Number.isSafeInteger(price)||price<=0)return partial('Kurs nicht zuverlässig auf zwei Nachkommastellen darstellbar.');
 const evidence={source:String(q.source||'Emittentenbeobachtung').slice(0,120),at:stamp,side:field,currency,price:money(price),
  kind:'Emittentenkurs, NICHT DEGIRO-Ausführung'};
 if(side==='Verkauf')return {ok:true,side,isin:id,currency,price:money(price),qty:null,stop:null,target:null,
  note:'Beobachteter Geldkurs als unverbindliche Verkaufslimit-Vorlage. Stückzahl nur aus geprüftem Bestand.',
  source:evidence,tradeable:false,automaticOrder:false};
 let budget,fees,maxLoss,minRR;
 try{
  budget=cents(input.budget);fees=cents(input.fees||'0');
  maxLoss=input.maxLoss?cents(input.maxLoss):Math.floor(budget/100);
  minRR=Number(String(input.minRR||'2').replace(',','.'));
 }catch(e){return partial('Budget oder Gebühren ungültig: '+e.message,{source:evidence,price:money(price)});}
 if(!(budget>0&&maxLoss>0&&Number.isFinite(minRR)&&minRR>=1&&minRR<=20))
  return partial('Tagesbudget, Verlustbudget oder Mindest-CRV fehlt bzw. ist ungültig.',{source:evidence,price:money(price)});
 if(!market.available||!market.stopModel||!market.targetModel||!market.exitModel)
  return partial('Technische Gold-Stopp-/Zielanalyse oder geprüftes Produktmodell fehlt. Nur Kursbeobachtung verfügbar.',{source:evidence,price:money(price)});
 const ref=p.reference,model=q.productModel;
 const refAt=typeof ref?.referenceAt==='string'&&/(Z|[+-]\d{2}:\d{2})$/i.test(ref.referenceAt)?Date.parse(ref.referenceAt):NaN;
 if(model?.verifiedSimpleTurbo!==true||model.isin!==id||model.underlying!=='XAU/USD'||
   !Number.isFinite(refAt)||Math.abs(refAt-at)>90000||
   !(Number(ref?.bid)>0&&Number(ref?.ko)>0&&Number(ref?.ratio)>0&&Number(ref?.strike)>0&&
     Number(ref?.goldReference)>0&&Number(ref?.fxReference)>0&&Number(ref?.fxScenario)>0))
  return partial('Passende zeitgleiche Gold-/FX- und KO-Produktreferenz fehlt. Keine rechnerische Stopp-Freigabe.',{source:evidence,price:money(price)});
 const stopGold=market.stopModel(direction,market.gold,market.atr,1.5)?.stop;
 const targetGold=market.targetModel(direction,market.gold,stopGold,2)?.target;
 if(!(stopGold>0&&targetGold>0))return partial('Markt-Stopp oder Ziel nicht berechenbar.',{source:evidence,price:money(price)});
 const scenario=market.exitModel({
  ...ref,isin:id,currency,direction,simpleSpotTurbo:true,referenceConfirmed:true,
  entry:price/100,quantity:1,planGold:market.gold,stopGold,targetGold,fxScenario:ref.fxScenario,
 });
 if(!scenario||scenario.reasons?.length||scenario.available!==true)
  return partial('Produkt-KO-/Ausstiegsmodell verwirft das technische Szenario.',{source:evidence,price:money(price)});
 const stopRow=scenario.rows?.find(x=>x.label==='Am Stop');
 const targetRow=scenario.rows?.find(x=>x.label==='Am Ziel');
 if(!stopRow?.available||!targetRow?.available)
  return partial('Stopp oder Ziel erreicht KO oder liefert keinen gültigen Modellkurs.',{source:evidence,price:money(price)});
 // Round conservatively: buy price UP; stop and target DOWN; no false precision.
 const stop=Math.floor(stopRow.price*100+1e-8);
 const target=Math.floor(targetRow.price*100+1e-8);
 if(!Number.isSafeInteger(stop)||!Number.isSafeInteger(target)||stop<=0||stop>=price||target<=price)
  return partial('Technische Produktmarken passen nicht zu einem neuen Kauf.',{source:evidence,price:money(price)});
 const rr=(target-price)/(price-stop);
 if(rr+1e-9<minRR)return partial('Chance-Risiko-Verhältnis von '+rr.toFixed(2)+':1 unterschreitet den gewählten Mindestwert '+minRR+':1.',{source:evidence,price:money(price)});
 const today=day(new Date(now));
 const used=state&&state.day===today?(state.orders||[]).filter(x=>x.side==='Kauf').reduce((n,x)=>n+x.cost,0):0;
 if(state&&state.day===today&&state.currency!==currency&&state.orders?.length)
  return partial('Bestehende Tagesplanung nutzt andere Währung; zuerst bereinigen.',{source:evidence,price:money(price)});
 const left=Math.max(0,budget-used-fees);
 const perUnit=price-stop;
 const qty=Math.max(0,Math.min(Math.floor(left/price),Math.floor((maxLoss-fees)/perUnit)));
 if(qty<1)return partial('Unter Tagesbudget und Verlustbudget lässt sich kein ganzes Stück sicher planen.',{source:evidence,price:money(price)});
 const loss=perUnit*qty+fees,gain=(target-price)*qty-fees,netRR=gain/loss;
 if(!(gain>0&&netRR>=minRR))return partial('Nach den eingegebenen Einstiegsgebühren bleibt das Modell-CRV unter dem Mindestwert.',{source:evidence,price:money(price)});
 return {ok:true,side,isin:id,currency,price:money(price),qty,stop:money(stop),target:money(target),
  loss:money(loss),gain:money(gain),rr:netRR.toFixed(2),
  source:{...evidence,marketAt:market.at,marketSource:market.source,historyAt:market.historyAt},
  note:'Indikatives Produktmodell aus Bobs technischem Gold-Stopp/Ziel und zeitlich abgeglichenen Produktreferenzen; nur eingegebene Einstiegsgebühren berücksichtigt, Verkaufsgebühren/Slippage/Finanzierung noch offen. KO-/Gap-Risiko: Verlustbudget ist keine Verlustgrenze.',
  tradeable:false,automaticOrder:false};
}

const api={day,cents,isin,reserve,summary,maxQuantity,snapPositions,calculateProposal};if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
function mount(){
 const host=document.getElementById('bob-view-degiro2');if(!host)return;
 const box=document.createElement('section');box.className='card';box.style.padding='16px';
 box.innerHTML=`<h3>Handy-Assistent · manuelle Bestätigung</h3>
 <p>Bob bereitet ISIN, Menge, Limit, geschätzte Kosten und optionale Produkt-Stopp-/Zielmarken als Kopiervorlage vor. In DEGIRO sind die Angaben weiterhin manuell einzugeben und von dir zu bestätigen. Keine Order-API und keine Fernbedienung der App.</p>
 <p>Das Tagesbudget begrenzt nur hier geplante Käufe, nicht tatsächliche Trades oder Verluste. Verkäufe geben kein Planbudget frei. SnapTrade liefert ausschließlich lesbare Bestandsinformationen, niemals Handelsfreigaben oder aktuelle DEGIRO-Orderkurse.</p>
 <p><button type="button" id="dg2-snap-read">SnapTrade-Depotstatus lesen</button></p>
 <label>SnapTrade-Position für Verkauf <select id="dg2-snap-position"><option value="">Keine ausgewählt</option></select></label>
 <p class="small" id="dg2-snap-status" role="status" aria-live="polite">Nur bestätigte, aktuelle Depotmengen können automatisch übernommen werden. Auch diese vor einem Verkauf bei DEGIRO prüfen.</p>
 <form id="dg2-form"><label>Tagesbudget <input name="budget" inputmode="decimal" required></label>
 <label>Währung <select name="currency"><option>EUR</option><option>CHF</option></select></label>
 <label>Vorhandenes Bob-Produkt <select id="dg2-product"><option value="">Manuell eingeben</option></select></label><button type="button" id="dg2-refresh">Produktliste übernehmen</button>
 <label>ISIN <input name="isin" maxlength="12" autocapitalize="characters" required></label>
 <label>Richtung <select name="side"><option>Kauf</option><option>Verkauf</option></select></label>
 <label>Stückzahl <input name="qty" inputmode="numeric" required></label>
 <label>Limit je Stück (max. 2 Nachkommastellen) <input name="price" inputmode="decimal" required></label>
 <label>Geschätzte Gebühren (0 = ungeprüfter Platzhalter) <input name="fees" inputmode="decimal" value="0" required></label>
 <label>Verlustbudget je Entwurf (optional, leer = 1 % Tagesbudget als Rechenannahme) <input name="maxLoss" inputmode="decimal"></label>
 <label>Mindest-Chance/Risiko (Rechenvorgabe) <input name="minRR" inputmode="decimal" value="2"></label>
 <label>Optional: Produkt-Stopp (nur Kaufplanung, nicht an DEGIRO übertragen) <input name="stop" inputmode="decimal"></label>
 <label>Optional: Produkt-Ziel (nur Kaufplanung, nicht an DEGIRO übertragen) <input name="target" inputmode="decimal"></label>
 <button type="button" id="dg2-propose">Vorschlag aus Bob berechnen</button>
 <p id="dg2-proposal" role="status" aria-live="polite" class="small">Bob nutzt nur aktuelle bestätigte Emittenten-Kurse und – soweit vollständig – das bestehende Gold-/KO-Szenario. Ohne technische Belege bleiben Stopp, Ziel und Risiko-Stückzahl offen.</p>
 <button type="button" id="dg2-size">Maximale Kaufstückzahl berechnen</button><p>Rechnerische Budgetobergrenze, keine Empfehlung zur vollständigen Ausschöpfung.</p>
 <button type="submit">Entwurf speichern</button></form>
 <p role="status" aria-live="polite" id="dg2-status"></p><p id="dg2-budget"></p><div id="dg2-orders"></div>
 <p><a id="dg2-open">DEGIRO öffnen</a></p>
 <p>Falls sich nur die Webseite öffnet, starte die DEGIRO-App über ihr Symbol. ISIN dort selbst suchen. Es werden keine Eingaben oder Bestätigungen in der App automatisiert.</p>
 <p>Planung nur auf diesem Gerät und in diesem Browser. Tageswechsel: Schweizer Zeit. Andere Geräte, gelöschte Browserdaten und echte Orders werden nicht abgeglichen. Keine zusätzliche Softwarelizenz oder API-Gebühr; bestehende Hosting- und Handelskosten bleiben bestehen.</p>`;
 host.append(box);box.querySelectorAll('label').forEach(el=>{el.style.display='block';el.style.margin='12px 0';});box.querySelectorAll('input,select').forEach(el=>{el.style.display='block';el.style.padding='10px';el.style.maxWidth='100%';});
 const form=box.querySelector('form'),status=box.querySelector('#dg2-status');let state=null;
 const products=box.querySelector('#dg2-product');
 const snap=box.querySelector('#dg2-snap-position'),snapStatus=box.querySelector('#dg2-snap-status');
 let sellPositions=[];let lastProposal=null;
 const output=box.querySelector('#dg2-proposal');
 box.querySelector('#dg2-propose').onclick=()=>{
  const v=Object.fromEntries(new FormData(form));
  const p=(root.BobDegiro?.tradeTestProducts?.()||[]).find(x=>x.isin===String(v.isin||'').trim().toUpperCase());
  // No browser trading: calls only existing local analysis/model functions.
  const plan=root.BobExitEstimate?.planInput?.(root.liveBundleCache,root.A,root.C,p?.direction);
  const r=calculateProposal(p,v,{
    ...(plan||{}),stopModel:root.stopModel,targetModel:root.targetModel,
    exitModel:root.BobExitEstimate?.calculate
  },read());
  lastProposal=null;
  if(!r.ok){
   output.textContent='Vorschlag unvollständig: '+r.reason+
    (r.price?' Beobachteter Preis ≈ '+r.price+' '+r.source.currency+
     ' · '+r.source.at+' ('+r.source.kind+').':'')+
    ' Bestehende Handels-/KO-Regeln bleiben unverändert.';
   return;
  }
  form.elements.price.value=r.price;
  if(r.side==='Kauf'){
   form.elements.qty.value=String(r.qty);form.elements.stop.value=r.stop;form.elements.target.value=r.target;
   output.textContent='Rechenvorschlag: '+r.qty+' Stück × '+r.price+' '+r.currency+
    ' · Stopp ≈ '+r.stop+' · Ziel ≈ '+r.target+
    ' · Verlust am Modellstopp inkl. eingegebener Einstiegsgebühren ≈ '+r.loss+
    ' · Modell-CRV '+r.rr+':1. '+r.note+' Quelle '+r.source.source+' · '+r.source.at+'.';
  }else{
   form.elements.stop.value='';form.elements.target.value='';
   output.textContent='Vorläufiger Verkaufs-Geldkurs ≈ '+r.price+' '+r.currency+
    ' · '+r.source.at+'. Stückzahl und aktuelle Handelbarkeit in DEGIRO prüfen. Keine Verkaufsausführung.';
  }
  lastProposal={...r,signature:JSON.stringify([v.isin,v.side,String(r.qty||form.elements.qty.value),r.price,
    r.stop||'',r.target||'',v.fees,v.currency])};
 };
 form.addEventListener('input',()=>{lastProposal=null;output.textContent='Eingaben geändert. Automatischen Vorschlag erneut prüfen.';});
 form.addEventListener('change',()=>{lastProposal=null;output.textContent='Eingaben geändert. Automatischen Vorschlag erneut prüfen.';});
 box.querySelector('#dg2-snap-read').onclick=async()=>{
  const button=box.querySelector('#dg2-snap-read');button.disabled=true;snapStatus.textContent='Depotstatus abfragen …';
  sellPositions=[];snap.replaceChildren(new Option('Keine ausgewählt',''));
  try{
   const response=await fetch('/api/snaptrade/status',{credentials:'same-origin',cache:'no-store'});
   if(!response.ok)throw Error('Status nicht erreichbar');
   const data=await response.json();
   sellPositions=snapPositions(data);
   for(const [i,p] of sellPositions.entries())snap.append(new Option('Depot '+p.account+' · '+p.isin+' · '+p.quantity+' Stück · '+p.currency+(p.current?' · aktuell':' · prüfen'),String(i)));
   snapStatus.textContent=sellPositions.length?
    sellPositions.length+' Positionen gelesen. Bestandszeit, ISIN und Menge sind keine aktuelle Handelsfreigabe.':
    'Keine eindeutig auslesbaren positiven ISIN-Positionen. SnapTrade-Abgleich oder CSV-Zuordnung prüfen; manuelle Planung bleibt möglich.';
  }catch(e){snapStatus.textContent='SnapTrade nicht erreichbar. Keine Mengenübernahme; manuelle Planung möglich.';}
  finally{button.disabled=false;}
 };
 snap.onchange=()=>{lastProposal=null;
  if(snap.value==='')return;
  const p=sellPositions[Number(snap.value)];if(!p)return;
  form.elements.side.value='Verkauf';form.elements.isin.value=p.isin;form.elements.currency.value=p.currency;
  form.elements.qty.value=p.current?String(p.quantity):'';
  form.elements.price.value='';form.elements.stop.value='';form.elements.target.value='';
  snapStatus.textContent='Depot '+p.account+' · Stand '+(p.sourceAt||'ohne Originalzeit')+' · '+p.note+
   (p.current?' · Menge als Entwurf übernommen.':' · Menge bewusst nicht übernommen. Bitte in DEGIRO nachsehen.');
  status.textContent='Verkauf vorbereitet. Verkaufs-Limit (DEGIRO-Geldkurs), Stückzahl und Handelsplatz vor Ausführung prüfen.';
 };
 function refreshProducts(){lastProposal=null;products.replaceChildren(new Option('Manuell eingeben',''));const items=root.BobDegiro?.tradeTestProducts?.()||[];for(const p of items){try{products.append(new Option(p.isin+' · '+(p.name||''),isin(p.isin)));}catch(e){}}}
 box.querySelector('#dg2-refresh').onclick=()=>{refreshProducts();status.textContent='Produktidentitäten aus Bob geladen. Das aktuelle Limit bitte in DEGIRO prüfen.';};
 products.onchange=()=>{lastProposal=null;if(products.value){
  form.elements.side.value='Kauf';form.elements.isin.value=products.value;
  const p=(root.BobDegiro?.tradeTestProducts?.()||[]).find(x=>x.isin===products.value);
  const c=p?.reference?.currency||p?.quote?.currency;
  if(['EUR','CHF'].includes(c))form.elements.currency.value=c;
  form.elements.price.value='';form.elements.qty.value='';form.elements.stop.value='';form.elements.target.value='';
  snap.value='';
  status.textContent='ISIN aus Bob übernommen'+(p?.direction?' · '+p.direction:'')+'. Anbieter-/Modellkurse sind keine ausführbaren DEGIRO-Limits. Limit und Stückzahl dort prüfen.';
 }};
 box.querySelector('#dg2-size').onclick=()=>{lastProposal=null;try{if(form.elements.side.value!=='Kauf')throw Error('Verkaufsstückzahl anhand deines echten Bestands selbst eingeben.');const qty=maxQuantity(read(),Object.fromEntries(new FormData(form)));form.elements.qty.value=qty||'';status.textContent=qty?'Rechnerische maximale Stückzahl eingetragen. Du kannst sie reduzieren.':'Kein Budget für ein weiteres Stück verfügbar.';}catch(e){status.textContent=e.message;}};
 refreshProducts();
 function read(){const raw=localStorage.getItem(KEY);return raw?JSON.parse(raw):null;}
 function render(){const current=state&&state.day===day()?state:null;const orders=current?current.orders:[];if(!Array.isArray(orders))throw Error('Ungültige gespeicherte Planung.');
 box.querySelector('#dg2-budget').textContent=current?`${current.day} · Geplante Käufe: ${money(orders.filter(o=>o.side==='Kauf').reduce((n,o)=>n+o.cost,0))} / ${money(current.budget)} ${current.currency}`:'Heute noch keine Entwürfe.';
 const list=box.querySelector('#dg2-orders');list.replaceChildren();orders.forEach((order,i)=>{
 const article=document.createElement('article'),text=document.createElement('textarea');text.readOnly=true;text.rows=8;text.style.width='100%';text.style.boxSizing='border-box';text.value=summary(order,current.currency);text.setAttribute('aria-label','Orderentwurf');article.append(text);
 function button(label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=fn;article.append(b);}
 async function copy(value){try{await navigator.clipboard.writeText(value);status.textContent='Kopiert. Bitte in DEGIRO prüfen.';}catch(e){text.focus();text.select();status.textContent='Bitte den markierten Entwurf manuell kopieren.';}}
 button('ISIN kopieren',()=>copy(order.isin));button('Entwurf kopieren',()=>copy(text.value));
 button('Entwurf entfernen',()=>{try{const latest=read();if(JSON.stringify(latest)!==JSON.stringify(state))throw Error('Planung wurde in einem anderen Fenster geändert. Seite neu laden.');const next={...state,orders:state.orders.filter((_,j)=>j!==i)};localStorage.setItem(KEY,JSON.stringify(next));state=next;render();status.textContent='Entwurf entfernt. Dies storniert keine Order bei DEGIRO.';}catch(e){status.textContent=e.message;}});list.append(article);
 });}
 try{state=read();if(state&&state.day===day()){form.elements.budget.value=money(state.budget);form.elements.currency.value=state.currency;}render();}catch(e){status.textContent='Planung konnte nicht geladen werden: '+e.message;form.querySelector('button').disabled=true;}
 form.addEventListener('submit',e=>{e.preventDefault();try{const latest=read();const values=Object.fromEntries(new FormData(form));
 const next=reserve(latest,values);
 // Explicitly preserve observation provenance only for an unchanged, current proposal.
 if(lastProposal){
  const sig=JSON.stringify([values.isin,values.side,values.qty,values.price,values.stop||'',values.target||'',values.fees,values.currency]);
  if(sig===lastProposal.signature&&Date.now()-Date.parse(lastProposal.source.at)<=90000){
   const order=next.orders[next.orders.length-1];
   order.proposal={source:lastProposal.source.source,sourceAt:lastProposal.source.at,kind:lastProposal.source.kind,
    modelAt:lastProposal.source.marketAt||null,verifiedOrder:false};
  }
 }
 localStorage.setItem(KEY,JSON.stringify(next));lastProposal=null;state=next;render();status.textContent='Entwurf gespeichert – keine Order übermittelt.';}catch(err){status.textContent=err.message;}});
 const web='https://trader.degiro.nl/';const link=box.querySelector('#dg2-open');link.href=/Android/i.test(navigator.userAgent||'')?'intent://trader.degiro.nl/#Intent;scheme=https;package=nl.degiro.trader;S.browser_fallback_url='+encodeURIComponent(web)+';end':web;
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){try{state=read();render();}catch(e){status.textContent=e.message;}}});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof window==='undefined'?globalThis:window);
