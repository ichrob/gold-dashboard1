"""Personal setup in the existing DEGIRO tab; no broker credentials collected."""
PANEL = r'''
<section id="bobSnapTrade" class="card" style="padding:16px;overflow-wrap:anywhere">
<h3>DEGIRO über SnapTrade Personal</h3>
<p>Kostenloser Personal-Zugang für dein eigenes Depot. Bob liest Bestände und Bargeld höchstens alle zehn Minuten, auch wenn diese Ansicht geschlossen ist. Kein 30-Sekunden-Kursfeed.</p>
<p id="snapStatus" role="status">Einrichtung wird geprüft …</p>
<ol>
<li><a href="https://snaptrade.com/personal" target="_blank" rel="noopener noreferrer">SnapTrade Personal kostenlos öffnen</a>, Konto erstellen und E-Mail bestätigen.</li>
<li>Im SnapTrade-Dashboard DEGIRO zum Lesen verbinden. Die DEGIRO-Anmeldung erfolgt dort. Bob benötigt kein DEGIRO-Passwort und keinen Authenticator-Hauptschlüssel.</li>
<li>In SnapTrade die Zwei-Faktor-Anmeldung einrichten und unter <a href="https://dashboard.snaptrade.com/" target="_blank" rel="noopener noreferrer">API Keys</a> deinen persönlichen API-Schlüssel erstellen. Die beiden Werte hier einfügen.</li>
</ol>
<p class="small">Falls SnapTrade einen dauerhaften Authenticator-Hauptschlüssel verlangt, lass diesen Schritt offen. Für Bob wird die bestehende Zwei-Faktor-Absicherung nicht geändert.</p>
<details id="snapSetup"><summary>Persönlichen Schlüssel in Bob hinterlegen</summary>
<form id="snapForm" autocomplete="off">
<p><label for="snapClient">Personal Client ID</label><br><input id="snapClient" type="password" autocomplete="off" spellcheck="false" required minlength="8" maxlength="256" style="width:100%;box-sizing:border-box;padding:12px"></p>
<p><label for="snapKey">Personal Consumer Key</label><br><input id="snapKey" type="password" autocomplete="off" spellcheck="false" required minlength="8" maxlength="256" style="width:100%;box-sizing:border-box;padding:12px"></p>
<label><input id="snapFree" type="checkbox" required> Das ist mein kostenloser Personal-Zugang für mein eigenes Depot.</label>
<p><button id="snapSave" type="submit">Schlüssel speichern und Lesetest starten</button></p>
<p id="snapFormStatus" role="status" aria-live="polite" style="font-weight:600;overflow-wrap:anywhere"></p>
</form>
<p class="small">Der Schlüssel wird verschlüsselt auf Bobs bestehendem Server gespeichert. Er wird nicht im Browser gespeichert oder zurück angezeigt. Keine Zahlungskarte und keinen kostenpflichtigen Tarif einrichten. Das Löschen unten entfernt den Schlüssel aus Bob; die Verbindung bei SnapTrade verwaltest du dort.</p>
</details>
<p id="snapFeedback" role="status" aria-live="polite"></p>
<p><button id="snapCheck" type="button" disabled>Verbindung prüfen</button> <button id="snapRemove" type="button" disabled>Schlüssel aus Bob löschen</button></p>
<p id="snapClock" class="small"></p><div id="snapHoldings"></div>
<p class="small">Die Daten zeigen nur den vom Anbieter gelieferten Depotstand. Vollständige ISINs, Schweizer Gold-Knock-outs, aktuelle Geld-/Briefkurse, Hebel und KO-Nachweise sind noch nicht bestätigt. Keine Übernahme in die Top 3 oder in Mein Trade. Keine Orders. CSV-Import und bisherige Produktquellen bleiben verfügbar.</p>
</section>
<script>
(function(){
function mount(){
 const panel=document.getElementById('bobSnapTrade'),target=document.getElementById('bob-view-degiro');if(!panel||!target)return;
 target.prepend(panel);
 const status=document.getElementById('snapStatus'),clock=document.getElementById('snapClock'),list=document.getElementById('snapHoldings');
 const client=document.getElementById('snapClient'),key=document.getElementById('snapKey'),free=document.getElementById('snapFree');
 const save=document.getElementById('snapSave'),check=document.getElementById('snapCheck'),remove=document.getElementById('snapRemove');
 let busy=false,lastData=null;
 function feedback(message){const inline=document.getElementById('snapFormStatus'),outside=document.getElementById('snapFeedback');inline.textContent=message;outside.textContent=message;(document.getElementById('snapSetup').open?inline:outside).scrollIntoView({block:'nearest'});}
 function controls(){check.disabled=busy||!lastData?.configured||lastData.nextCheckSeconds>0;remove.disabled=busy||!lastData?.configured;}
 const messages={SETUP_REQUIRED:'Noch nicht verbunden. Einmalige Einrichtung oben durchführen.',READY:'Schlüssel gespeichert. Lesetest wird gestartet.',CHECKING:'Depot-Lesetest läuft …',READ_OK:'✓ Depotdaten empfangen. Goldprodukt-Abdeckung noch nicht bestätigt.',CONNECT_DEGIRO:'Personal-Zugang erreichbar. DEGIRO im SnapTrade-Dashboard verbinden.',READ_CONNECTION_REQUIRED:'DEGIRO-Verbindung bei SnapTrade muss auf Lesen stehen.',AUTH_REQUIRED:'Anmeldung nicht bestätigt oder Verbindung abgelaufen. Im SnapTrade-Dashboard prüfen.',ACCESS_DENIED:'Anbieter verweigert den Zugriff. Personal-Zugang und Berechtigungen prüfen.',PLAN_REQUIRED:'Anbieter verlangt einen anderen Tarif. Kein kostenpflichtiger Abruf wird ausgelöst.',RATE_LIMITED:'Anbieter begrenzt die Abrufe. Nächster Versuch frühestens nach zehn Minuten.',PROVIDER_UNAVAILABLE:'Anbieter momentan nicht erreichbar. Letzter Stand ist nicht als aktuell bestätigt.',INVALID_RESPONSE:'Datenformat nicht vollständig erkannt. Kein vollständiger Abgleich bestätigt.',STORE_UNAVAILABLE:'Geschützter Schlüsselspeicher momentan nicht erreichbar.',SETTINGS_UNREADABLE:'Gespeicherter Schlüssel kann nicht gelesen werden. Personal-Schlüssel erneut speichern.',NO_ACCOUNTS:'Noch kein lesbares DEGIRO-Depot gefunden.',TOO_MANY_ACCOUNTS:'Mehr als drei DEGIRO-Depots/Verbindungen. Abgleich zur Prüfung angehalten.'};
 function stamp(value){const d=new Date(value);return value&&Number.isFinite(d.getTime())?d.toLocaleString('de-CH'):'nicht geliefert';}
 function render(data){
  lastData=data;
  status.textContent=messages[data.code]||'Verbindung nicht bestätigt.';
  controls();
  document.getElementById('snapSetup').open=!data.configured;
  clock.textContent=(data.checkedAt?'Letzte Prüfung: '+stamp(data.checkedAt)+'. ':'')+(data.configured?'Nächster möglicher Abruf in '+data.nextCheckSeconds+' Sekunden. ':'')+(data.snapshot?(data.fresh?'Quellenstand innerhalb des Depotintervalls.':'Quellenstand nicht als aktuell bestätigt. '):'');
  list.replaceChildren();
  for(const [i,account] of (data.snapshot?.accounts||[]).entries()){
   const box=document.createElement('section'),title=document.createElement('h4'),meta=document.createElement('p');
   title.textContent='DEGIRO-Depot '+(i+1)+' · '+account.positions.length+' gelieferte Positionen';box.append(title);
   meta.textContent='Bestandsquelle: '+stamp(account.positionsSourceAt)+' · Bargeldquelle: '+stamp(account.cashSourceAt)+' · '+(account.freshnessMode==='realtime'?'Anbieter meldet aktuellen Abruf':'verzögert oder unbekannt');box.append(meta);
   for(const cash of account.cash){const p=document.createElement('p');p.textContent='Bargeld: '+(cash.amount??'unbekannt')+' '+cash.currency;box.append(p);}
   for(const item of account.positions){const p=document.createElement('p');p.textContent=(item.name||item.symbol||'Unbenannte Position')+' · Menge '+(item.units??'unbekannt')+' · ISIN nicht nachgewiesen';box.append(p);}
   list.append(box);
  }
  for(const note of data.snapshot?.limitations||[]){const p=document.createElement('p');p.textContent=note;list.append(p);}
 }
 async function call(action,payload){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try{
   const response=await fetch('/api/snaptrade/'+action,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify(payload||{})});
   if(response.status===401)throw Error('Bob-Anmeldung abgelaufen. Erneut in Bob anmelden; anschließend den Speicherstatus prüfen.');
   if(response.status===403)throw Error('Speichern nicht erlaubt. Bob in diesem Browser neu öffnen und erneut anmelden.');
   let data;try{data=await response.json();}catch(_){throw Error('Bob hat keine gültige Antwort geliefert. Speichern nicht bestätigt.');}
   if(!response.ok){
    const reason=data.code==='CRYPTO_UNAVAILABLE'?'Verschlüsselung auf Bobs Server nicht verfügbar.':messages[data.code]||'Eingabe oder Server prüfen.';
    throw Error('Nicht gespeichert: '+reason);
   }
   if(typeof data.configured!=='boolean')throw Error('Speichern nicht bestätigt: unvollständige Serverantwort.');
   render(data);return data;
  }catch(error){
   if(error.name==='AbortError')throw Error('Zeitüberschreitung. Speicherstatus nicht bestätigt; Ansicht neu öffnen, bevor du erneut speicherst.');
   if(error instanceof TypeError)throw Error('Verbindung zu Bob unterbrochen. Speichern nicht bestätigt.');
   throw error;
  }finally{clearTimeout(timer);}
 }
 async function refresh(){if(busy)return;try{const r=await fetch('/api/snaptrade/status',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw Error();render(await r.json());}catch(_){status.textContent='Einrichtungsstatus nicht erreichbar.';}}
 document.getElementById('snapForm').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!free.checked)return;busy=true;save.disabled=true;controls();feedback('Schlüssel werden verschlüsselt gespeichert …');
  const payload={clientId:client.value.trim(),consumerKey:key.value.trim(),personalFreeConfirmed:true};client.value='';key.value='';
  try{const data=await call('configure',payload);feedback(data.configured?'✓ Schlüssel gespeichert. Die Eingabefelder wurden geleert. '+(messages[data.code]||'Lesetest wird gestartet.'):'Speichern nicht bestätigt.');}catch(error){feedback(error.message);status.textContent=error.message;}finally{payload.clientId='';payload.consumerKey='';busy=false;save.disabled=false;controls();}
 });
 for(const [button,action] of [[check,'check'],[remove,'disconnect']])button.addEventListener('click',async()=>{if(busy)return;busy=true;controls();try{const data=await call(action);feedback(messages[data.code]||'Status aktualisiert.');}catch(error){feedback(error.message);}finally{busy=false;controls();await refresh();}});
 refresh();setInterval(()=>{if(!document.hidden)refresh();},10000);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
</script>
'''
