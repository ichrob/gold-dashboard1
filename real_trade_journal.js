(function(){
 const storage='bobRealTradeJournalQueueV1';let queue=[],busy=false;
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
 const b=document.createElement('button'),note=document.createElement('p');b.type='submit';b.textContent='Ausführung speichern';form.append(b,note);
 form.onsubmit=async e=>{e.preventDefault();b.disabled=true;try{const actualExecution=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,Number(v.value)]));await request('write',{trade:{...t.snapshot,actualExecution},timeframe:'15m'});note.textContent='Gespeichert · Ergebnis nach eingetragenen Kosten: '+((actualExecution.exitEUR-actualExecution.entryEUR)*actualExecution.quantity-actualExecution.feesEUR).toFixed(2)+' EUR. Angaben nicht mit DEGIRO abgeglichen.';}catch(err){note.textContent='Nicht gespeichert: '+err.message;}finally{b.disabled=false;}};return form;
 }
 async function load(){await flush();try{const r=await request('read',{}),root=el('realTradeList');root.replaceChildren();for(const t of r.trades){const d=document.createElement('details'),s=document.createElement('summary'),body=document.createElement('div');s.textContent=time(t.openedAt)+' · '+(t.snapshot.product?.isin||'Goldreferenz ohne Produktdaten')+' · '+t.snapshot.dir+' · '+(t.snapshot.recordOnly?'Kauf erfasst · Überwachung offen':t.active?'aktiv':'in Bob beendet');d.append(s,details('Erfasster Trade und Produktwerte',t.snapshot));if(t.active){const note=document.createElement('p');note.textContent=t.pushDevices>0?'Server-Push: '+t.pushDevices+' registrierte Geräte mit diesem Trade verbunden. Empfang am Handy erst durch Test bestätigt.':'Serverüberwachung aktiv. Kein Gerät für diesen Trade verbunden: Auf dem Handy Trade-Push einschalten und Gerät registrieren.';d.append(note);}if(!t.active&&!t.snapshot.recordOnly)d.append(executionForm(t));d.append(body);d.addEventListener('toggle',()=>{if(d.open&&!body.childNodes.length)history(t.id,body);});root.append(d);}if(!r.trades.length)root.textContent='Noch kein echter Trade protokolliert. Nach deinem Kauf den Trade unter „Mein Trade“ erfassen und aktivieren.';}catch(e){status('Echte Trades nicht abrufbar: '+e.message);}}

 function purchasePanel(){
  const parent=el('bobExitEstimate');if(!parent||el('bobPurchaseRecord'))return;
  const box=document.createElement('section');box.id='bobPurchaseRecord';box.className='card';
  box.innerHTML='<h3>Bestätigten Kauf geräteübergreifend speichern</h3><p>Kaufkurs, Stückzahl und Richtung werden aus dem Formular oben übernommen. Die Speicherung benötigt keine Gold-/FX-Referenz. Stopp-, Ziel- und KO-Überwachung bleiben bis zur vollständigen Einrichtung offen.</p><form id="purchaseForm"><label>DEGIRO-Transaktions-ID<input id="purchaseTx" required maxlength="80"></label><label>Kaufzeit mit Zeitzone<input id="purchaseAt" required placeholder="2026-10-14T10:54:59+02:00"></label><label>Gesamtgebühren CHF<input id="purchaseFees" type="number" min="0" step="0.01" required></label><label>Gesamtbelastung CHF<input id="purchaseTotal" type="number" min="0" step="0.01" required></label><button type="submit">Bestätigten Kauf auf Server speichern</button></form><p id="purchaseStatus" role="status"></p><button id="purchaseReload">Gespeicherte Käufe laden</button><div id="purchaseList"></div>';
  parent.after(box);
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
  try{const r=await request('read',{});root.replaceChildren();
   for(const t of r.trades.filter(t=>t.snapshot.recordOnly)){
    const p=t.snapshot.product,e=t.snapshot.purchase,line=document.createElement('p'),b=document.createElement('button');
    line.textContent=p.isin+' · '+t.snapshot.dir+' · '+p.quantity+' Stück zu '+p.entry+' EUR · '+time(e.at)+' · Kauf gespeichert, Überwachung offen. ';
    b.textContent='Kauf ins Formular übernehmen';b.onclick=()=>{for(const [k,v] of Object.entries({isin:p.isin,entry:p.entry,quantity:p.quantity,direction:t.snapshot.dir})){const input=document.querySelector('[data-exit="'+k+'"]');input.value=v;input.dispatchEvent(new Event('input',{bubbles:true}));}el('purchaseTx').value=e.transactionId;el('purchaseAt').value=e.at;el('purchaseFees').value=e.feesCHF;el('purchaseTotal').value=e.totalCHF;window.BobExitEstimate?.automaticTradeReference();};line.append(b);root.append(line);
   }
   if(!root.childNodes.length)root.textContent='Noch keine separat erfassten Käufe.';
  }catch(e){el('purchaseStatus').textContent='Serverkäufe nicht abrufbar: '+e.message;}
 }
 window.BobRealTrades={capture,load};
 document.addEventListener('DOMContentLoaded',()=>{el('realTradeLoad')?.addEventListener('click',load);flush();purchasePanel();});
 document.addEventListener('click',e=>{if(e.target.closest?.('[data-view="learning"]'))load();purchasePanel();});
 window.addEventListener('online',flush);setInterval(flush,30000);
})();
