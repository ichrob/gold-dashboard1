(function(){
 const storage='bobRealTradeJournalQueueV1';let queue=[],busy=false;let preparing=false;
 try{queue=JSON.parse(localStorage.getItem(storage)||'[]');if(!Array.isArray(queue))queue=[];}catch(e){}
 const el=id=>document.getElementById(id),time=x=>new Date(x).toLocaleString('de-CH',{timeZone:'Europe/Zurich'});
 function status(text){if(el('realTradeStatus'))el('realTradeStatus').textContent=text;}
 async function request(action,payload){const r=await fetch('/api/real-trades/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Server antwortet mit '+r.status);return r.json();}
 async function flush(){if(busy||!queue.length)return;busy=true;try{while(queue.length){await request('write',queue[0]);queue.shift();localStorage.setItem(storage,JSON.stringify(queue));}status('Echter Trade: Protokoll mit Server synchronisiert.');}catch(e){status('Protokoll noch nicht synchronisiert: '+e.message+'. Lokale Einträge warten auf erneuten Versuch; Hintergrundaufzeichnung erst nach Serverbestätigung.');}finally{busy=false;}}
 function capture(trade,extra){if(!trade?.tradeId||trade.test)return;const data=JSON.parse(JSON.stringify({trade,timeframe:'15m',event:extra||null}));const last=queue.at(-1);if(JSON.stringify(last)===JSON.stringify(data))return;queue.push(data);try{localStorage.setItem(storage,JSON.stringify(queue));}catch(e){status('Lokale Sicherung fehlgeschlagen; Server-Synchronisierung wird versucht.');}flush();}
 function details(title,value){const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');s.textContent=title;p.textContent=JSON.stringify(value,null,2);p.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px';d.append(s,p);return d;}
 function reviewLines(e){
  if(!e)return [];
  const lines=['Trade-Auswertung'];
  if(Number.isFinite(e.realizedNetCHF))lines.push('Netto laut erfasster Abrechnung: '+e.realizedNetCHF.toFixed(2)+' CHF');
  else if(Number.isFinite(e.realizedNetProduct))lines.push('Netto laut erfasster Ausführung: '+e.realizedNetProduct.toFixed(2)+' '+(e.currency||''));
  else lines.push('Nettoergebnis offen: Abrechnung unvollständig.');
  if(e.windowNote)lines.push(e.windowNote);
  if(e.trace)lines.push(e.trace.observations+' Beobachtungen innerhalb der Haltedauer · '+e.trace.recommendations+' Empfehlungen · '+e.trace.adverseObservations+' Gegenrichtungs-Signale · '+e.trace.stopLoosenings+' Stopp-Lockerungen. Keine bestätigte Broker-Ausführung.');
  if(e.modelObservations)lines.push(e.modelObservations+' berechnete Produktwerte · größte beobachtete Bewegung ab Einstieg: '+e.modelMaePct+' % bis +'+e.modelMfePct+' %. Modellverlauf, keine ausführbaren Kurse.');
  lines.push(...(e.lessons||[]));
  if(e.learning)lines.push(e.learning.note+' Der bestehende Vorwärtstest prüft Referenzstrategien; ein Produkt-Nettovorteil ist damit noch nicht belegt.');
  return lines;
 }
 function renderEvaluation(e){const box=document.createElement('section');for(const line of reviewLines(e)){const p=document.createElement('p');p.textContent=line;box.append(p);}return box;}
 function renderStopReview(review,id){
  const box=document.createElement('details'),head=document.createElement('summary');
  head.textContent='Stopp-Wirkung · Vorschlag → Brokerbestätigung';box.append(head);
  const note=document.createElement('p');note.textContent='Die Bestätigung dokumentiert deine Angabe. Sie setzt keinen Stopp bei DEGIRO und beendet keinen Trade in Bob.';box.append(note);
  if(review.truncated){const p=document.createElement('p');p.textContent='Ansicht gekürzt; weitere Einträge bleiben im Journal.';box.append(p);}
  if(!review.rows?.length){const p=document.createElement('p');p.textContent='Noch kein auswertbarer Stopp-Vorschlag gespeichert.';box.append(p);}
  for(const row of review.rows||[]){
   const item=document.createElement('details'),title=document.createElement('summary');
   title.textContent=time(row.at)+' · Stopp '+(Number.isFinite(row.productStop)?'≈ '+row.productStop.toFixed(4)+' '+row.currency:row.goldStop.toFixed(2)+' USD/oz · damaliger Produktwert nicht belegt');
   item.append(title);
   const context=document.createElement('p');context.textContent=Number.isFinite(row.productPrice)?'Produktkurs beim Vorschlag: ≈ '+row.productPrice.toFixed(4)+' '+row.currency+' · Quellzeit '+time(row.sourceAt)+' · FX '+time(row.fxAt)+' · berechnet':'Für diesen älteren Vorschlag fehlt ein gleichzeitig gespeicherter Produktkurs.';item.append(context);
   for(const action of row.confirmations||[]){const p=document.createElement('p');p.textContent=(action.action==='set'?'Bei DEGIRO gesetzt':'Ausgeführt')+' laut Nutzer · '+action.price+' '+action.currency+' · '+time(action.at)+' · '+Math.round(action.reactionSeconds)+' Sekunden nach Vorschlag'+(Number.isFinite(action.differenceFromProposal)?' · Abweichung zum Modell-Stopp '+action.differenceFromProposal.toFixed(4)+' '+action.currency:'');item.append(p);}
   const form=document.createElement('form'),action=document.createElement('select');
   action.setAttribute('aria-label','Stopp-Status');
   for(const [v,label] of [['set','Bei DEGIRO gesetzt'],['filled','Bei DEGIRO ausgeführt']]){const o=document.createElement('option');o.value=v;o.textContent=label;action.append(o);}
   const price=document.createElement('input');price.type='number';price.step='any';price.min='0.000001';price.required=true;price.placeholder='Tatsächlicher Produktkurs';price.setAttribute('aria-label','Bestätigter Stopp- oder Ausführungskurs');
   const at=document.createElement('input');at.type='datetime-local';at.step='1';at.required=true;at.setAttribute('aria-label','Brokerzeit (Schweizer Zeit)');
   const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.required=true;label.append(check,document.createTextNode(' Ich bestätige diese Angaben aus DEGIRO.'));
   const button=document.createElement('button');button.type='submit';button.textContent='Bestätigung dokumentieren';const result=document.createElement('p');
   const timeLabel=document.createElement('label');timeLabel.textContent='Brokerzeit (Schweizer Zeit)';timeLabel.append(at);form.append(action,price,timeLabel,label,button,result);
   form.onsubmit=async e=>{e.preventDefault();button.disabled=true;try{
    const currency=row.currency||latestTrades.find(t=>t.id===id)?.snapshot.product?.currency||'EUR';
    await request('write',{stopConfirmation:{tradeId:id,recommendationSeq:row.seq,action:action.value,price:Number(price.value),currency,localAt:at.value.trim(),timezone:'Europe/Zurich',userConfirmed:check.checked}});
    result.textContent='Gespeichert als Nutzerbestätigung. Keine Order ausgelöst.';button.textContent='Dokumentiert';
   }catch(err){result.textContent=err.message;button.disabled=false;}};
   item.append(form);box.append(item);
  }
  return box;
 }
 async function history(id,root,before){try{const r=await request('read',{tradeId:id,before});if(!before){root.replaceChildren();if(r.evaluation)root.append(renderEvaluation(r.evaluation));if(r.stopReview)root.append(renderStopReview(r.stopReview,id));}for(const e of r.events){root.append(details(time(e.at)+' · '+({'observation':'Markt und Empfehlungen','trade-opened':'Beginn der Aufzeichnung','trade-updated':'Trade-Plan aktualisiert','trade-closed-in-bob':'In Bob beendet','push-delivery':'Push-Versand','browser-event':'App-Ereignis','observation-error':'Aufzeichnungslücke'}[e.kind]||e.kind),e.payload));}if(r.more){const b=document.createElement('button');b.textContent='Ältere Einträge laden';b.onclick=()=>{b.remove();history(id,root,r.nextBefore);};root.append(b);}if(!r.events.length&&!r.evaluation&&!r.stopReview)root.textContent='Noch keine Einträge.';}catch(e){root.textContent='Verlauf nicht abrufbar: '+e.message;}}
 function executionForm(t){
 const currency=t.snapshot.product?.currency||'EUR',entryKey='entry'+currency,exitKey='exit'+currency,feesKey='fees'+currency;
 const form=document.createElement('form'),heading=document.createElement('p'),fields={};heading.textContent='Tatsächliche Ausführung in '+currency+' erfassen (Gesamtverkauf; Teilverkäufe hier noch nicht abbildbar).';form.append(heading);
 for(const [key,label] of Object.entries({[entryKey]:'Kaufkurs je Stück', [exitKey]:'Verkaufskurs je Stück',quantity:'Stückzahl',[feesKey]:'Gesamte Gebühren und Kosten in '+currency})){const l=document.createElement('label'),i=document.createElement('input');l.textContent=label;i.type='number';i.step='any';i.min=key===feesKey?'0':'0.000001';i.required=true;i.value=t.snapshot.actualExecution?.[key]??({[entryKey]:t.snapshot.product?.entry,quantity:t.snapshot.product?.quantity}[key]??'');l.append(i);form.append(l);fields[key]=i;}
 const extra={},saved=t.snapshot.settlement||{},box=document.createElement('details'),summary=document.createElement('summary');summary.textContent='DEGIRO-Abrechnung und Ausstiegsgrund';box.append(summary);
 for(const [key,label] of Object.entries({purchaseTransactionId:'Kauf-Order-ID',saleTransactionId:'Verkauf-Order-ID',purchasedAt:'Kaufzeit mit Zeitzone',soldAt:'Verkaufszeit mit Zeitzone',purchaseTotalCHF:'Gesamtbelastung Kauf CHF',saleTotalCHF:'Gesamterlös Verkauf CHF',purchaseFeesCHF:'Kaufkosten CHF',saleFeesCHF:'Verkaufskosten CHF',purchaseFX:'Kauf-Wechselkurs EUR/CHF',saleFX:'Verkauf-Wechselkurs EUR/CHF'})){const l=document.createElement('label'),i=document.createElement('input');l.textContent=label;i.type=/CHF|FX/.test(key)?'number':'text';i.step='any';i.value=saved[key]??'';l.append(i);box.append(l);extra[key]=i;}
 const rl=document.createElement('label'),reason=document.createElement('select');rl.textContent='Ausstiegsgrund';for(const [v,label] of [['stop-loss-user-confirmed','Stop-Loss · vom Nutzer bestätigt'],['manual','Manueller Verkauf'],['other','Anderer Ausstieg']]){const o=document.createElement('option');o.value=v;o.textContent=label;reason.append(o);}reason.value=saved.exitReason||'other';rl.append(reason);box.append(rl);if(currency==='EUR')form.append(box);
 const result=document.createElement('p');if(saved.netCHF!==undefined)result.textContent='Ergebnis nach Kosten: '+(saved.netCHF>=0?'+':'')+saved.netCHF.toFixed(2)+' CHF · Verkauf '+(saved.soldAt?time(saved.soldAt):(saved.saleExecutedLocal||'Zeit nicht belegt'));form.prepend(result);
 const b=document.createElement('button'),note=document.createElement('p');b.type='submit';b.textContent='Ausführung speichern';form.append(b,note);
 form.onsubmit=async e=>{e.preventDefault();b.disabled=true;try{const actualExecution=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,Number(v.value)]));const settlement=Object.values(extra).some(i=>i.value.trim())?{...Object.fromEntries(Object.entries(extra).map(([k,i])=>[k,/CHF|FX/.test(k)?Number(i.value):i.value.trim()])),exitReason:reason.value}:undefined;await request('write',{trade:{...t.snapshot,actualExecution,...(settlement?{settlement}:{})},timeframe:'15m'});if(settlement){result.textContent='Ergebnis nach Kosten: '+(settlement.saleTotalCHF-settlement.purchaseTotalCHF).toFixed(2)+' CHF · Verkauf '+time(settlement.soldAt);}note.textContent='Gespeichert · Ergebnis nach eingetragenen Kosten: '+((actualExecution[exitKey]-actualExecution[entryKey])*actualExecution.quantity-actualExecution[feesKey]).toFixed(2)+' '+currency+'. Angaben nicht mit DEGIRO abgeglichen.';}catch(err){note.textContent='Nicht gespeichert: '+err.message;}finally{b.disabled=false;}};return form;
 }
 async function load(){await flush();try{const r=await request('read',{}),root=el('realTradeList');root.replaceChildren();if(r.automaticMonitor){const p=document.createElement('p');p.textContent='Automatischer Überwachungsstart: '+r.automaticMonitor.message+(r.automaticMonitor.checkedAt?' · Stand '+time(r.automaticMonitor.checkedAt):'');root.append(p);}for(const t of r.trades){const d=document.createElement('details'),s=document.createElement('summary'),body=document.createElement('div');s.textContent=time(t.openedAt)+' · '+(t.snapshot.product?.isin||'Goldreferenz ohne Produktdaten')+' · '+t.snapshot.dir+' · '+(t.snapshot.consumed?'Kaufbeleg · abgeschlossener Trade':t.snapshot.recordOnly?'Kauf erfasst · Überwachung offen':t.active?'aktiv':'in Bob beendet');d.append(s,details('Erfasster Trade und Produktwerte',t.snapshot));if(t.monitorTiming){const p=document.createElement('p');p.textContent='Überwachungsbeginn: '+time(t.monitorTiming.startedAt)+' · '+Math.round(t.monitorTiming.delaySeconds/60)+' Minuten nach Kauf'+(t.monitorTiming.timezoneAssumed?' (Belegzeit als Schweizer Ortszeit angenommen)':'');d.append(p);}if(t.active){const note=document.createElement('p');note.textContent=t.pushDevices>0?'Server-Push: '+t.pushDevices+' registrierte Geräte mit diesem Trade verbunden. Empfang am Handy erst durch Test bestätigt.':'Serverüberwachung aktiv. Kein Gerät für diesen Trade verbunden: Auf dem Handy Trade-Push einschalten und Gerät registrieren.';d.append(note);}if(!t.active&&!t.snapshot.recordOnly)d.append(executionForm(t));d.append(body);d.addEventListener('toggle',()=>{if(d.open&&!body.childNodes.length)history(t.id,body);});root.append(d);}if(!r.trades.length)root.textContent='Noch kein echter Trade protokolliert. Nach deinem Kauf den Trade unter „Mein Trade“ erfassen und aktivieren.';}catch(e){status('Echte Trades nicht abrufbar: '+e.message);}}


 let latestTrades=[],emailState='E-Mail-Eingang wird automatisch geprüft.',workflowError='',loadingPurchases=false;
 function workflowState(trades,current,plan){
  const active=trades.find(t=>t.active&&t.id===current?.tradeId)||trades.find(t=>t.active);
  const pending=trades.find(t=>t.snapshot.recordOnly&&!t.snapshot.consumed);
  const closed=trades.find(t=>!t.active&&!t.snapshot.recordOnly&&(t.snapshot.exitReceipt||t.snapshot.actualExecution||t.snapshot.settlement));
  const chosen=active||pending||closed;
  const same=chosen&&chosen.id===current?.tradeId;
  const validPlan=!!(same&&current?.active&&plan?.available);
  return {chosen,active,pending,closed:!active&&!pending?closed:null,validPlan,
   steps:[!!chosen,!!(chosen?.snapshot.product?.referenceConfirmed||validPlan),validPlan,
    !!active,!!(active&&active.pushDevices>0),!!(!active&&!pending&&closed),!!(!active&&!pending&&closed&&(Number.isFinite(closed.evaluation?.realizedNetCHF)||Number.isFinite(closed.evaluation?.realizedNetProduct)||Number.isFinite(closed.snapshot.settlement?.netCHF)))]};
 }
 function renderWorkflow(){
  const root=el('tradeWorkflow');if(!root)return;
  const current=window.BobTradeSync?.current(),plan=window.BobTradeSync?.plan?.();
  const state=workflowState(latestTrades,current,plan),labels=['Kauf erkannt und gespeichert','Produkt- und Referenzdaten ergänzt','Stop-Loss und Ziel berechnet','Hintergrundüberwachung eingerichtet','Trade-Push mit Gerät verbunden','Verkauf erkannt · Überwachung beendet','Ergebnis und Verlauf dokumentiert'];
  root.replaceChildren();const h=document.createElement('h3');h.textContent='Dein Trade · Schritt für Schritt';root.append(h);
  const list=document.createElement('ol');list.style.paddingLeft='26px';
  labels.forEach((label,i)=>{const li=document.createElement('li');li.style.cssText='padding:6px 0;'+(state.steps[i]?'color:#15803d;font-weight:600':'');li.textContent=(state.steps[i]?'✓ Erledigt · ':'○ Offen · ')+label;list.append(li);});root.append(list);
  const note=document.createElement('p');note.setAttribute('role','status');
  note.textContent=workflowError||(!state.chosen?emailState:state.closed?'Verkauf dokumentiert. Kosten und Nettoergebnis nur, soweit belegt.':state.active?'Serverüberwachung eingerichtet. Ein grüner Push-Haken bestätigt die Geräteverbindung, nicht den Empfang jeder Nachricht.':'Kauf gespeichert. Der Server prüft Produkt- und Marktdaten und startet die Überwachung automatisch. Fehlende Nachweise bleiben sichtbar.');root.append(note);
  if(state.closed){const snap=state.closed.snapshot,p=snap.product||{},sale=snap.exitReceipt;const result=document.createElement('p');if(Number.isFinite(snap.settlement?.netCHF))result.textContent='Netto laut abgeglichener Abrechnung: '+snap.settlement.netCHF.toFixed(2)+' CHF';else if(snap.actualExecution?.netCHF!==undefined)result.textContent='Ergebnis nach erfassten Kosten: '+Number(snap.actualExecution.netCHF).toFixed(2)+' CHF';else if(snap.actualExecution?.netEUR!==undefined)result.textContent='Ergebnis nach erfassten Kosten: '+Number(snap.actualExecution.netEUR).toFixed(2)+' EUR';else if((p.currency||'EUR')==='EUR'&&sale&&Number.isFinite(p.entry)&&Number.isFinite(sale.priceEur))result.textContent='Ergebnis vor Kosten: '+((sale.priceEur-p.entry)*sale.quantity).toFixed(2)+' EUR · Nettoergebnis wartet auf vollständige Gebühren/Abrechnung.';else result.textContent='Abrechnung unter Lernen → Echter Trade.';root.append(result);}
  if(state.chosen){const identity=document.createElement('p');identity.textContent=state.chosen.snapshot.product?.isin||'';root.append(identity);}
  if(state.validPlan){
   for(const [key,label] of [['stop','Stop-Loss'],['target','Ziel']]){
    const line=document.createElement('p'),b=document.createElement('button');line.textContent=label+': ≈ '+plan[key].toFixed(4)+' '+plan.currency+' pro Stück (berechnet) ';b.type='button';b.textContent=label+' kopieren';
    b.onclick=async()=>{try{await navigator.clipboard.writeText(plan[key].toFixed(4).replace('.',','));b.textContent='✓ Kopiert';}catch(_){b.textContent='Kopieren nicht möglich · Wert oben markieren';}};line.append(b);root.append(line);
   }
   const note=document.createElement('p');note.textContent='Stop bei DEGIRO selbst eintragen. Bob kann die Übernahme beim Broker nicht bestätigen.';root.append(note);
  }
  if(!state.closed){const b=document.createElement('button');b.type='button';b.textContent=!state.chosen?'Ausführungsbeleg hinzufügen':state.active?'Trade und Push-Status ansehen':'Fehlenden Nachweis ansehen';b.onclick=()=>{const target=!state.chosen?el('bobTradeUpload'):state.active?el('stopPanel'):el('bobExitEstimate');for(let n=target;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;target?.scrollIntoView({behavior:'smooth',block:'start'});};root.append(b);}
 }
 async function importMailPurchase(){
  if(latestTrades.some(t=>t.active||t.snapshot.recordOnly&&!t.snapshot.consumed))return;
  const response=await fetch('/api/trade-email/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('E-Mail-Prüfung: HTTP '+response.status);
  const data=await response.json(),items=data.items||[],today=new Date().toLocaleDateString('en-CA',{timeZone:'Europe/Zurich'});
  const day=r=>r.executedAt?new Date(r.executedAt).toLocaleDateString('en-CA',{timeZone:'Europe/Zurich'}):r.executedLocal?.slice(0,10).split('.').reverse().join('-');
  const candidates=items.filter(x=>x.messageId&&x.result?.status==='pending-review'&&x.result.side==='BUY'&&day(x.result)===today);
  emailState=data.configured?'Warte auf eine eindeutige Kaufbestätigung. Alternativ Ausführungsbeleg hinzufügen.':'E-Mail-Empfang noch nicht verbunden. Bitte den Ausführungsbeleg hinzufügen.';
  if(candidates.length!==1){if(candidates.length>1)emailState='Mehrere Käufe erkannt. Bitte den gewünschten Trade auswählen; Bob überschreibt keine Position.';return;}
  const item=candidates[0],r=item.result;
  if(latestTrades.some(t=>t.snapshot.product?.isin===r.isin&&t.snapshot.product?.entry===r.priceEur&&t.snapshot.product?.quantity===r.quantity))return;
  const q=await fetch('/api/degiro/enrich?isin='+encodeURIComponent(r.isin),{signal:AbortSignal.timeout(65000)});if(!q.ok)throw Error('Produktdaten für Kauf-Mail noch nicht erreichbar');
  const quote=await q.json(),fields=window.BobExitEstimate.issuerTradeFields(quote,r.isin);
  if(fields.currency==='CHF')throw Error('CHF-Kauf über das Formular in CHF erfassen; EUR-Mailkurs nicht als CHF übernehmen');
  if(quote.productVerified!==true||!['LONG','SHORT'].includes(fields.direction))throw Error('Produktrichtung der Kauf-Mail noch nicht bestätigt');
  await request('write',{emailReceiptId:item.messageId,direction:fields.direction});
  emailState='Kauf aus E-Mail gespeichert. Produktprüfung folgt automatisch.';
 }
 function purchasePanel(){
  const parent=el('bobExitEstimate'),existing=el('bobPurchaseRecord'),viewNow=el('bob-view-trade');if(existing){if(viewNow&&existing.parentElement!==viewNow){const h=viewNow.querySelector('h2');if(h)h.after(existing);else viewNow.prepend(existing);}return;}if(!parent)return;
  const box=document.createElement('details');box.id='bobPurchaseRecord';box.className='card';
  box.innerHTML='<summary>Gespeicherte Käufe und Überwachungsdetails</summary><div id="tradeWorkflow"></div><h3>Bestätigten Kauf geräteübergreifend speichern</h3><p>Kaufkurs, Stückzahl und Richtung werden aus dem Formular oben übernommen. Die Speicherung benötigt keine Gold-/FX-Referenz. Stopp-, Ziel- und KO-Überwachung bleiben bis zur vollständigen Einrichtung offen.</p><form id="purchaseForm"><label>DEGIRO-Transaktions-ID<input id="purchaseTx" required maxlength="80"></label><label>Kaufzeit mit Zeitzone<input id="purchaseAt" required placeholder="2026-10-14T10:54:59+02:00"></label><label>Gesamtgebühren CHF<input id="purchaseFees" type="number" min="0" step="0.01" required></label><label>Gesamtbelastung CHF<input id="purchaseTotal" type="number" min="0" step="0.01" required></label><button type="submit">Bestätigten Kauf auf Server speichern</button></form><p id="purchaseStatus" role="status"></p><button id="purchaseReload">Gespeicherte Käufe laden</button><div id="purchaseList"></div>';
  const view=el('bob-view-trade');
  if(view){const heading=view.querySelector('h2');if(heading)heading.after(box);else view.prepend(box);}else parent.after(box);
  box.querySelector('h3').textContent='Dein gespeicherter Kauf';
  box.querySelector('p').textContent='Kauf gespeichert → Daten automatisch prüfen → Überwachung automatisch starten.';
  const manual=document.createElement('details'),label=document.createElement('summary');label.textContent='Weiteren Kauf manuell erfassen';manual.append(label,el('purchaseForm'));box.append(manual);
  el('purchaseReload').textContent='Käufe aktualisieren';
  const review=document.createElement('button');review.textContent='Datenprüfung öffnen';review.onclick=()=>{for(let n=parent;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;parent.scrollIntoView({behavior:'smooth',block:'start'});};el('purchaseList').after(review);
  el('purchaseForm').onsubmit=async event=>{event.preventDefault();const b=event.submitter;b.disabled=true;
   try{const field=k=>parent.querySelector('[data-exit="'+k+'"]').value;
    const trade={recordOnly:true,active:false,dir:field('direction'),product:{isin:field('isin').trim().toUpperCase(),currency:field('currency')||'EUR',entry:Number(field('entry')),quantity:Number(field('quantity'))},purchase:{transactionId:el('purchaseTx').value.trim(),at:el('purchaseAt').value.trim(),feesCHF:Number(el('purchaseFees').value),totalCHF:Number(el('purchaseTotal').value)}};
    await request('write',{trade});el('purchaseStatus').textContent='Kauf auf dem Server gespeichert. Auf anderen Geräten abrufbar. Überwachung noch offen.';await loadPurchases();
   }catch(e){el('purchaseStatus').textContent='Nicht gespeichert: '+e.message;}finally{b.disabled=false;}
  };
  el('purchaseReload').onclick=loadPurchases;loadPurchases();
 }
 async function loadPurchases(){
  const root=el('purchaseList');if(!root||loadingPurchases)return;loadingPurchases=true;
  try{let r=await request('read',{});latestTrades=r.trades;try{await importMailPurchase();r=await request('read',{});latestTrades=r.trades;workflowError='';}catch(err){workflowError=err.message;}renderWorkflow();reconcileClosed(r.trades);await flush();if(queue.length||busy)return;root.replaceChildren();
   const active=r.trades.filter(t=>t.active&&!t.snapshot.recordOnly);
   if(active.length===1&&window.BobTradeSync?.restore(active[0].snapshot)){el('purchaseStatus').textContent='Überwachung vom Server übernommen · Stopp und Ziel werden automatisch aktualisiert.';return;}
   for(const t of r.trades.filter(t=>t.snapshot.recordOnly&&!t.snapshot.consumed)){
    const p=t.snapshot.product,e=t.snapshot.purchase,line=document.createElement('p'),b=document.createElement('button');
    line.textContent=p.isin+' · '+t.snapshot.dir+' · '+p.quantity+' Stück zu '+p.entry+' '+(p.currency||'EUR')+' · '+(e.at?time(e.at):e.executedLocal+' (Quellenzeit)')+' · Kauf gespeichert, Überwachung offen. ';
    b.textContent='Kauf vorbereiten · Daten automatisch laden';b.onclick=()=>preparePurchase(t);line.append(b);root.append(line);
   }
   if(!root.childNodes.length)root.textContent='Noch kein gespeicherter Kauf. E-Mail-Eingang unten prüfen oder Kauf manuell erfassen.';
   const pending=r.trades.filter(t=>t.snapshot.recordOnly&&!t.snapshot.consumed),field=k=>document.querySelector('[data-exit="'+k+'"]');
   if(pending.length===1&&!r.trades.some(t=>t.active)&&!window.BobTradeSync?.current()?.active&&['isin','entry','quantity','direction'].every(k=>field(k)&&((k==='direction'&&!field('isin').value.trim())||!field(k).value.trim()||String(field(k).value).trim()===String(k==='direction'?pending[0].snapshot.dir:pending[0].snapshot.product[k])||String(field(k).value).trim()===String(k==='direction'?window.BobTradeSync?.current()?.dir:window.BobTradeSync?.current()?.product?.[k]))))await preparePurchase(pending[0]);
  }catch(e){workflowError='Serverkäufe nicht abrufbar: '+e.message;el('purchaseStatus').textContent=workflowError;}finally{loadingPurchases=false;renderWorkflow();}
 }
 function reconcileClosed(trades){
  const closed=new Map(trades.filter(t=>!t.active&&!t.snapshot.recordOnly).map(t=>[t.id,t.snapshot]));
  const current=window.BobTradeSync?.current(),snapshot=closed.get(current?.tradeId);
  if(snapshot&&window.BobTradeSync?.close({...snapshot,active:false})&&el('purchaseStatus'))el('purchaseStatus').textContent='Trade geschlossen · Trade-Push und Überwachung beendet. Verlauf unter Lernen → Echter Trade.';
  // An old device may have queued plan updates. Keep their evidence in the
  // closed journal without trying to reopen the position and blocking sync.
  queue=queue.map(item=>item.trade?.active&&closed.has(item.trade.tradeId)?{
   ...item,trade:{...closed.get(item.trade.tradeId),active:false},
   event:{...item.event,staleClientTrade:item.trade}
  }:item);
  localStorage.setItem(storage,JSON.stringify(queue));
 }
 async function preparePurchase(t){
  if(preparing)return;
  const p=t.snapshot.product,e=t.snapshot.purchase;
  for(const [k,v] of Object.entries({isin:p.isin,currency:p.currency||'EUR',entry:p.entry,quantity:p.quantity,direction:t.snapshot.dir})){
   const input=document.querySelector('[data-exit="'+k+'"]');if(!input)return;input.value=v;input.dispatchEvent(new Event('input',{bubbles:true}));
  }
  el('purchaseTx').value=e.transactionId;el('purchaseAt').value=e.at||'';el('purchaseFees').value=e.feesCHF??'';el('purchaseTotal').value=e.totalCHF??'';
  el('purchaseStatus').textContent='Kauf übernommen. Produkt- und Gold-/FX-Daten werden automatisch ergänzt …';
  preparing=true;
  try{if(!window.BobExitEstimate?.automaticTradeReference)throw Error('Bitte nach dem vollständigen Laden erneut versuchen.');const values=await window.BobExitEstimate.automaticTradeReference();
   if(!values)throw Error(document.querySelector('[data-exit-output]')?.textContent||'Produkt- oder zeitlich passende Referenzdaten fehlen noch. Automatischer Wiederholungsversuch folgt.');
   if((values.currency||'EUR')!==(p.currency||'EUR')||values.isin!==p.isin||Number(values.entry)!==p.entry||Number(values.quantity)!==p.quantity||values.direction!==t.snapshot.dir)throw Error('Kaufdaten wurden während der Prüfung geändert.');
   if(typeof window.loadData==='function')await window.loadData(true);
   const activation=await window.activateProductTrade(values,t);
   if(!window.BobTradeSync?.current()?.active)throw Error(activation);
   await flush();
   el('purchaseStatus').textContent=queue.length?'Überwachung lokal vorbereitet; Serverspeicherung wird erneut versucht.':'Überwachung automatisch gestartet und gespeichert · Stopp und Ziel in '+(p.currency||'EUR')+' pro Stück (geschätzt).';
  }catch(err){workflowError='Datenabruf noch offen: '+err.message;el('purchaseStatus').textContent=workflowError;}finally{preparing=false;}
 }
 window.BobRealTrades={capture,load,reconcileClosed,workflowState,renderWorkflow};
 document.addEventListener('DOMContentLoaded',()=>{el('realTradeLoad')?.addEventListener('click',load);flush();purchasePanel();});
 document.addEventListener('click',e=>{if(e.target.closest?.('[data-view="learning"]'))load();purchasePanel();});
 if(typeof navigator!=='undefined'&&navigator.serviceWorker)navigator.serviceWorker.addEventListener('message',event=>{if(event.data?.type==='BOB_PUSH_CLICK'&&event.data.data?.kind==='trade'){location.hash='trade';loadPurchases();}});
 window.addEventListener('online',()=>{flush();loadPurchases();});setInterval(()=>{flush();if(!preparing)loadPurchases();},30000);
})();
