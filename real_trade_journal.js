(function(){
 const storage='bobRealTradeJournalQueueV1';let queue=[],busy=false;let preparing=false;
 try{queue=JSON.parse(localStorage.getItem(storage)||'[]');if(!Array.isArray(queue))queue=[];}catch(e){}
 const el=id=>document.getElementById(id),time=x=>new Date(x).toLocaleString('de-CH',{timeZone:'Europe/Zurich'});
 function status(text){if(el('realTradeStatus'))el('realTradeStatus').textContent=text;}
 async function request(action,payload){const r=await fetch('/api/real-trades/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Server antwortet mit '+r.status);return r.json();}
 async function flush(){if(busy||!queue.length)return;busy=true;try{while(queue.length){await request('write',queue[0]);queue.shift();localStorage.setItem(storage,JSON.stringify(queue));}status('Echter Trade: Protokoll mit Server synchronisiert.');}catch(e){status('Protokoll noch nicht synchronisiert: '+e.message+'. Lokale Einträge warten auf erneuten Versuch; Hintergrundaufzeichnung erst nach Serverbestätigung.');}finally{busy=false;}}
 function capture(trade,extra){if(!trade?.tradeId||trade.test)return;const data=JSON.parse(JSON.stringify({trade,timeframe:'15m',event:extra||null}));const last=queue.at(-1);if(JSON.stringify(last)===JSON.stringify(data))return;queue.push(data);try{localStorage.setItem(storage,JSON.stringify(queue));}catch(e){status('Lokale Sicherung fehlgeschlagen; Server-Synchronisierung wird versucht.');}flush();}
 function details(title,value){const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');s.textContent=title;p.textContent=JSON.stringify(value,null,2);p.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px';d.append(s,p);return d;}
 async function history(id,root,before){try{const r=await request('read',{tradeId:id,before});if(!before)root.replaceChildren();for(const e of r.events){root.append(details(time(e.at)+' · '+({'observation':'Markt und Empfehlungen','trade-opened':'Beginn der Aufzeichnung','trade-updated':'Trade-Plan aktualisiert','trade-closed-in-bob':'In Bob beendet','push-delivery':'Push-Versand','browser-event':'App-Ereignis','observation-error':'Aufzeichnungslücke'}[e.kind]||e.kind),e.payload));}if(r.more){const b=document.createElement('button');b.textContent='Ältere Einträge laden';b.onclick=()=>{b.remove();history(id,root,r.nextBefore);};root.append(b);}if(!r.events.length)root.textContent='Noch keine Einträge.';}catch(e){root.textContent='Verlauf nicht abrufbar: '+e.message;}}
 function executionForm(t){
 const form=document.createElement('form'),heading=document.createElement('p'),fields={};heading.textContent='Tatsächliche Ausführung in EUR erfassen (Gesamtverkauf; Teilverkäufe hier noch nicht abbildbar).';form.append(heading);
 for(const [key,label] of Object.entries({entryEUR:'Kaufkurs je Stück',exitEUR:'Verkaufskurs je Stück',quantity:'Stückzahl',feesEUR:'Gesamte Gebühren und Kosten in EUR'})){const l=document.createElement('label'),i=document.createElement('input');l.textContent=label;i.type='number';i.step='any';i.min=key==='feesEUR'?'0':'0.000001';i.required=true;i.value=t.snapshot.actualExecution?.[key]??({entryEUR:t.snapshot.product?.entry,quantity:t.snapshot.product?.quantity}[key]??'');l.append(i);form.append(l);fields[key]=i;}
 const extra={},saved=t.snapshot.settlement||{},box=document.createElement('details'),summary=document.createElement('summary');summary.textContent='DEGIRO-Abrechnung und Ausstiegsgrund';box.append(summary);
 for(const [key,label] of Object.entries({purchaseTransactionId:'Kauf-Order-ID',saleTransactionId:'Verkauf-Order-ID',purchasedAt:'Kaufzeit mit Zeitzone',soldAt:'Verkaufszeit mit Zeitzone',purchaseTotalCHF:'Gesamtbelastung Kauf CHF',saleTotalCHF:'Gesamterlös Verkauf CHF',purchaseFeesCHF:'Kaufkosten CHF',saleFeesCHF:'Verkaufskosten CHF',purchaseFX:'Kauf-Wechselkurs EUR/CHF',saleFX:'Verkauf-Wechselkurs EUR/CHF'})){const l=document.createElement('label'),i=document.createElement('input');l.textContent=label;i.type=/CHF|FX/.test(key)?'number':'text';i.step='any';i.value=saved[key]??'';l.append(i);box.append(l);extra[key]=i;}
 const rl=document.createElement('label'),reason=document.createElement('select');rl.textContent='Ausstiegsgrund';for(const [v,label] of [['stop-loss-user-confirmed','Stop-Loss · vom Nutzer bestätigt'],['manual','Manueller Verkauf'],['other','Anderer Ausstieg']]){const o=document.createElement('option');o.value=v;o.textContent=label;reason.append(o);}reason.value=saved.exitReason||'other';rl.append(reason);box.append(rl);form.append(box);
 const result=document.createElement('p');if(saved.netCHF!==undefined)result.textContent='Ergebnis nach Kosten: '+(saved.netCHF>=0?'+':'')+saved.netCHF.toFixed(2)+' CHF · Verkauf '+time(saved.soldAt);form.prepend(result);
 const b=document.createElement('button'),note=document.createElement('p');b.type='submit';b.textContent='Ausführung speichern';form.append(b,note);
 form.onsubmit=async e=>{e.preventDefault();b.disabled=true;try{const actualExecution=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,Number(v.value)]));const settlement=Object.values(extra).some(i=>i.value.trim())?{...Object.fromEntries(Object.entries(extra).map(([k,i])=>[k,/CHF|FX/.test(k)?Number(i.value):i.value.trim()])),exitReason:reason.value}:undefined;await request('write',{trade:{...t.snapshot,actualExecution,...(settlement?{settlement}:{})},timeframe:'15m'});if(settlement){result.textContent='Ergebnis nach Kosten: '+(settlement.saleTotalCHF-settlement.purchaseTotalCHF).toFixed(2)+' CHF · Verkauf '+time(settlement.soldAt);}note.textContent='Gespeichert · Ergebnis nach eingetragenen Kosten: '+((actualExecution.exitEUR-actualExecution.entryEUR)*actualExecution.quantity-actualExecution.feesEUR).toFixed(2)+' EUR. Angaben nicht mit DEGIRO abgeglichen.';}catch(err){note.textContent='Nicht gespeichert: '+err.message;}finally{b.disabled=false;}};return form;
 }
 async function load(){await flush();try{const r=await request('read',{}),root=el('realTradeList');root.replaceChildren();for(const t of r.trades){const d=document.createElement('details'),s=document.createElement('summary'),body=document.createElement('div');s.textContent=time(t.openedAt)+' · '+(t.snapshot.product?.isin||'Goldreferenz ohne Produktdaten')+' · '+t.snapshot.dir+' · '+(t.snapshot.consumed?'Kaufbeleg · abgeschlossener Trade':t.snapshot.recordOnly?'Kauf erfasst · Überwachung offen':t.active?'aktiv':'in Bob beendet');d.append(s,details('Erfasster Trade und Produktwerte',t.snapshot));if(t.active){const note=document.createElement('p');note.textContent=t.pushDevices>0?'Server-Push: '+t.pushDevices+' registrierte Geräte mit diesem Trade verbunden. Empfang am Handy erst durch Test bestätigt.':'Serverüberwachung aktiv. Kein Gerät für diesen Trade verbunden: Auf dem Handy Trade-Push einschalten und Gerät registrieren.';d.append(note);}if(!t.active&&!t.snapshot.recordOnly)d.append(executionForm(t));d.append(body);d.addEventListener('toggle',()=>{if(d.open&&!body.childNodes.length)history(t.id,body);});root.append(d);}if(!r.trades.length)root.textContent='Noch kein echter Trade protokolliert. Nach deinem Kauf den Trade unter „Mein Trade“ erfassen und aktivieren.';}catch(e){status('Echte Trades nicht abrufbar: '+e.message);}}

 function purchasePanel(){
  const parent=el('bobExitEstimate'),existing=el('bobPurchaseRecord'),viewNow=el('bob-view-trade');if(existing){if(viewNow&&existing.parentElement!==viewNow){const h=viewNow.querySelector('h2');if(h)h.after(existing);else viewNow.prepend(existing);}return;}if(!parent)return;
  const box=document.createElement('section');box.id='bobPurchaseRecord';box.className='card';
  box.innerHTML='<h3>Bestätigten Kauf geräteübergreifend speichern</h3><p>Kaufkurs, Stückzahl und Richtung werden aus dem Formular oben übernommen. Die Speicherung benötigt keine Gold-/FX-Referenz. Stopp-, Ziel- und KO-Überwachung bleiben bis zur vollständigen Einrichtung offen.</p><form id="purchaseForm"><label>DEGIRO-Transaktions-ID<input id="purchaseTx" required maxlength="80"></label><label>Kaufzeit mit Zeitzone<input id="purchaseAt" required placeholder="2026-10-14T10:54:59+02:00"></label><label>Gesamtgebühren CHF<input id="purchaseFees" type="number" min="0" step="0.01" required></label><label>Gesamtbelastung CHF<input id="purchaseTotal" type="number" min="0" step="0.01" required></label><button type="submit">Bestätigten Kauf auf Server speichern</button></form><p id="purchaseStatus" role="status"></p><button id="purchaseReload">Gespeicherte Käufe laden</button><div id="purchaseList"></div>';
  const view=el('bob-view-trade');
  if(view){const heading=view.querySelector('h2');if(heading)heading.after(box);else view.prepend(box);}else parent.after(box);
  box.querySelector('h3').textContent='Dein gespeicherter Kauf';
  box.querySelector('p').textContent='Kauf gespeichert → Daten automatisch prüfen → Überwachung automatisch starten.';
  const manual=document.createElement('details'),label=document.createElement('summary');label.textContent='Weiteren Kauf manuell erfassen';manual.append(label,el('purchaseForm'));box.append(manual);
  el('purchaseReload').textContent='Käufe aktualisieren';
  const review=document.createElement('button');review.textContent='Datenprüfung öffnen';review.onclick=()=>{for(let n=parent;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;parent.scrollIntoView({behavior:'smooth',block:'start'});};el('purchaseList').after(review);
  el('purchaseForm').onsubmit=async event=>{event.preventDefault();const b=event.submitter;b.disabled=true;
   try{const field=k=>parent.querySelector('[data-exit="'+k+'"]').value;
    const trade={recordOnly:true,active:false,dir:field('direction'),product:{isin:field('isin').trim().toUpperCase(),entry:Number(field('entry')),quantity:Number(field('quantity'))},purchase:{transactionId:el('purchaseTx').value.trim(),at:el('purchaseAt').value.trim(),feesCHF:Number(el('purchaseFees').value),totalCHF:Number(el('purchaseTotal').value)}};
    await request('write',{trade});el('purchaseStatus').textContent='Kauf auf dem Server gespeichert. Auf anderen Geräten abrufbar. Überwachung noch offen.';await loadPurchases();
   }catch(e){el('purchaseStatus').textContent='Nicht gespeichert: '+e.message;}finally{b.disabled=false;}
  };
  el('purchaseReload').onclick=loadPurchases;loadPurchases();
 }
 async function loadPurchases(){
  const root=el('purchaseList');if(!root)return;
  try{await flush();if(queue.length||busy)return;const r=await request('read',{});root.replaceChildren();
   const current=window.BobTradeSync?.current();
   const closed=r.trades.find(t=>!t.active&&!t.snapshot.recordOnly&&t.id===current?.tradeId);
   if(closed&&window.BobTradeSync?.close({...closed.snapshot,active:false})){el('purchaseStatus').textContent='Trade geschlossen · Trade-Push und Überwachung beendet. Verlauf unter Lernen → Echter Trade.';}
   const active=r.trades.filter(t=>t.active&&!t.snapshot.recordOnly);
   if(active.length===1&&window.BobTradeSync?.restore(active[0].snapshot)){el('purchaseStatus').textContent='Überwachung vom Server übernommen · Stopp und Ziel werden automatisch aktualisiert.';return;}
   for(const t of r.trades.filter(t=>t.snapshot.recordOnly&&!t.snapshot.consumed)){
    const p=t.snapshot.product,e=t.snapshot.purchase,line=document.createElement('p'),b=document.createElement('button');
    line.textContent=p.isin+' · '+t.snapshot.dir+' · '+p.quantity+' Stück zu '+p.entry+' EUR · '+time(e.at)+' · Kauf gespeichert, Überwachung offen. ';
    b.textContent='Kauf vorbereiten · Daten automatisch laden';b.onclick=()=>preparePurchase(t);line.append(b);root.append(line);
   }
   if(!root.childNodes.length)root.textContent='Noch kein gespeicherter Kauf. E-Mail-Eingang unten prüfen oder Kauf manuell erfassen.';
   const pending=r.trades.filter(t=>t.snapshot.recordOnly&&!t.snapshot.consumed),field=k=>document.querySelector('[data-exit="'+k+'"]');
   if(pending.length===1&&!r.trades.some(t=>t.active)&&!window.BobTradeSync?.current()?.active&&['isin','entry','quantity','direction'].every(k=>field(k)&&((k==='direction'&&!field('isin').value.trim())||!field(k).value.trim()||String(field(k).value).trim()===String(k==='direction'?pending[0].snapshot.dir:pending[0].snapshot.product[k]))))await preparePurchase(pending[0]);
  }catch(e){el('purchaseStatus').textContent='Serverkäufe nicht abrufbar: '+e.message;}
 }
 async function preparePurchase(t){
  if(preparing)return;
  const p=t.snapshot.product,e=t.snapshot.purchase;
  for(const [k,v] of Object.entries({isin:p.isin,entry:p.entry,quantity:p.quantity,direction:t.snapshot.dir})){
   const input=document.querySelector('[data-exit="'+k+'"]');if(!input)return;input.value=v;input.dispatchEvent(new Event('input',{bubbles:true}));
  }
  el('purchaseTx').value=e.transactionId;el('purchaseAt').value=e.at;el('purchaseFees').value=e.feesCHF;el('purchaseTotal').value=e.totalCHF;
  el('purchaseStatus').textContent='Kauf übernommen. Produkt- und Gold-/FX-Daten werden automatisch ergänzt …';
  preparing=true;
  try{if(!window.BobExitEstimate?.automaticTradeReference)throw Error('Bitte nach dem vollständigen Laden erneut versuchen.');const values=await window.BobExitEstimate.automaticTradeReference();
   if(!values)throw Error('Produkt- oder zeitlich passende Referenzdaten fehlen noch. Automatischer Wiederholungsversuch folgt.');
   if(values.isin!==p.isin||Number(values.entry)!==p.entry||Number(values.quantity)!==p.quantity||values.direction!==t.snapshot.dir)throw Error('Kaufdaten wurden während der Prüfung geändert.');
   if(typeof window.loadData==='function')await window.loadData(true);
   await window.activateProductTrade(values,t);
   await flush();
   el('purchaseStatus').textContent=queue.length?'Überwachung lokal vorbereitet; Serverspeicherung wird erneut versucht.':'Überwachung automatisch gestartet und gespeichert · Stopp und Ziel in EUR pro Stück (geschätzt).';
  }catch(err){el('purchaseStatus').textContent='Kauf übernommen; Datenabruf noch offen: '+err.message;}finally{preparing=false;}
 }
 window.BobRealTrades={capture,load};
 document.addEventListener('DOMContentLoaded',()=>{el('realTradeLoad')?.addEventListener('click',load);flush();purchasePanel();});
 document.addEventListener('click',e=>{if(e.target.closest?.('[data-view="learning"]'))load();purchasePanel();});
 window.addEventListener('online',()=>{flush();loadPurchases();});setInterval(()=>{flush();if(!preparing)loadPurchases();},30000);
})();
