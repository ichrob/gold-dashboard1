"""DEGIRO tab: explicitly offline integration test, no account access."""
PANEL = r'''
<section id="bobDegiroSandbox" class="card" style="padding:16px">
<h3>DEGIRO · Verbindung und Automatik</h3>
<section aria-label="DEGIRO Lesetest">
<h4>Verbindung prüfen · nur lesen</h4>
<p id="dgConnectionStatus" role="status">Einrichtung wird geprüft …</p>
<label for="dgConnectionOtp">Einmalcode aus deiner Authenticator-App, falls erforderlich</label>
<input id="dgConnectionOtp" type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="off" style="width:100%;box-sizing:border-box;padding:12px">
<button id="dgConnectionTest" type="button" disabled>DEGIRO-Lesetest starten</button>
<p class="small">Einmaliger Anmelde- und Depot-Lesetest. Kein Kauf, Verkauf oder Ändern einer Order. Keine dauerhafte Sitzung. Zugangsdaten gehören ausschließlich in die geschützten Server-Einstellungen, nicht in den Chat.</p>
<details><summary>Einmalige Einrichtung</summary>
<p>Der Server benötigt <code>pip install -r requirements-degiro.txt</code> als Build-Befehl. In Render beim bestehenden Bob-Dienst die Umgebungsvariablen <code>BOB_DEGIRO_USERNAME</code> und <code>BOB_DEGIRO_PASSWORD</code> sicher hinterlegen. Anschließend neu veröffentlichen. Dafür ist kein zusätzlicher Dienst nötig.</p>
<p>Inoffizielle Bibliothek: DEGIRO unterstützt diesen Zugang nicht. Eine ausstehende Genehmigung ist keine Zustimmung. Der Lesetest beweist keine Handelsfreigabe. App-Bestätigung und CAPTCHA sind in diesem Stand nicht unterstützt; eine solche Anmeldeanforderung wird nicht umgangen.</p>
</details>
</section>
<hr>
<h4>Automatischer Simulationslauf</h4>
<p><b>Simulation bereit · DEGIRO nicht verbunden</b></p>
<p class="small">Dieser Test öffnet und schließt eine virtuelle Position automatisch und zieht den Stop nach. Die Kurse sind künstlich. Er bestätigt keine funktionierende DEGIRO-Anbindung.</p>
<label for="dgSandboxScenario">Test auswählen</label>
<select id="dgSandboxScenario" style="width:100%;padding:12px;margin:8px 0">
<option value="target">Kaufen → Gewinnziel → Verkaufen</option>
<option value="stop_gap">Kaufen → Kurslücke → Stop-Verkauf</option>
<option value="trailing">Kaufen → Stop nachziehen → Verkaufen</option>
<option value="stale">Veralteter Kurs → Kauf sperren</option>
</select>
<button id="dgSandboxRun" type="button" class="bob-primary">Automatischen Simulationslauf testen</button>
<p id="dgSandboxStatus" role="status">Noch kein Test gestartet.</p>
<ol id="dgSandboxLog"></ol>
<details><summary>Verbindung und Kosten</summary>
<p>Keine Zugangsdaten erforderlich. Keine zusätzliche Softwarelizenz oder API-Gebühr für diesen internen Test; bestehende Hostingkosten bleiben bestehen.</p>
<p>Der optionale degiro-connector-Lesetest ist vorbereitet. Erst ein erfolgreicher Lesetest bestätigt den Depotabruf. Orderfunktionen sind nicht angebunden. Die ausstehende E-Mail-Antwort ist keine Genehmigung. Echtgeldhandel ist nicht aktiviert.</p>
<p>Der Test läuft einmal nach dem Antippen. Kein fortlaufender Hintergrundhandel. Ergebnisse werden nicht dauerhaft gespeichert.</p>
</details>
</section>
<script>
(function(){
function mount(){
 const panel=document.getElementById('bobDegiroSandbox');
 const target=document.getElementById('bob-view-degiro');
 if(!target || !panel)return;
 target.append(panel);
 const connectionStatus=document.getElementById('dgConnectionStatus'),test=document.getElementById('dgConnectionTest'),otp=document.getElementById('dgConnectionOtp');
 fetch('/api/degiro/connection-status',{credentials:'same-origin',cache:'no-store'}).then(async response=>{
  if(!response.ok)throw new Error('Status nicht erreichbar');
  const data=await response.json();
  test.disabled=!data.ready;
  connectionStatus.textContent=data.ready?'Bibliothek und Zugangsdaten eingerichtet. Verbindung noch nicht getestet.':(!data.sdkReady?'Bibliothek fehlt oder Version passt nicht. ':'')+(!data.credentialsConfigured?'DEGIRO-Zugangsdaten noch nicht eingerichtet. ':'');
 }).catch(()=>{connectionStatus.textContent='Einrichtungsstatus nicht erreichbar.';});
 test.addEventListener('click',async()=>{
  if(otp.value&&!/^[0-9]{6}$/.test(otp.value)){connectionStatus.textContent='Einmalcode muss sechs Ziffern haben.';return;}
  test.disabled=true;connectionStatus.textContent='Lesetest läuft … maximal 45 Sekunden.';
  const body=JSON.stringify({otp:otp.value});otp.value='';
  try{
   const response=await fetch('/api/degiro/connection-test',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body});
   if(!response.ok)throw new Error('HTTP '+response.status);
   const data=await response.json();
   const messages={READ_OK:'✓ Anmeldung und Depotabruf erfolgreich. Keine Order gesendet.',AUTH_REQUIRED:'Anmeldung nicht bestätigt. Zugangsdaten, Einmalcode oder zusätzliche App-Bestätigung prüfen.',SETUP_REQUIRED:'Bibliothek oder Zugangsdaten fehlen.',BUSY:'Ein Lesetest läuft bereits.',COOLDOWN:'Bitte mindestens 60 Sekunden zwischen Anmeldeversuchen warten.',TIMEOUT:'Zeitlimit erreicht. Verbindung nicht bestätigt.',SDK_ERROR:'Lesetest fehlgeschlagen. Keine Verbindung bestätigt.',INVALID_RESPONSE:'Antwortformat nicht erkannt. Depotabruf nicht bestätigt.',INVALID_INPUT:'Eingabe ungültig.'};
   connectionStatus.textContent=(messages[data.code]||'Unbekanntes Testergebnis.')+(data.code==='READ_OK'&&!data.logoutConfirmed?' Abmeldung nicht bestätigt; Sitzung in DEGIRO prüfen.':'');
  }catch(error){connectionStatus.textContent='Lesetest nicht bestätigt: '+error.message;}finally{test.disabled=false;}
 });

 const run=document.getElementById('dgSandboxRun'),status=document.getElementById('dgSandboxStatus'),log=document.getElementById('dgSandboxLog');
 run.addEventListener('click',async()=>{
  run.disabled=true;log.replaceChildren();status.textContent='Interner Test läuft …';
  try{
   const scenario=document.getElementById('dgSandboxScenario').value;
   const response=await fetch('/api/degiro/sandbox?scenario='+encodeURIComponent(scenario),{credentials:'same-origin',cache:'no-store'});
   if(!response.ok)throw new Error('HTTP '+response.status);
   const data=await response.json();
   if(data.mode!=='OFFLINE_SIMULATION'||data.brokerConnected!==false||data.liveOrdersEnabled!==false)throw new Error('Unerwarteter Testmodus');
   const names={BUY_PAPER:'Virtueller Kauf',SELL_PAPER:'Virtueller Verkauf',TRAIL_PAPER:'Stop nachgezogen',BLOCKED:'Kauf gesperrt',STALE_FEED:'Kurs veraltet'};
   for(const event of data.simulation.events){
    const li=document.createElement('li');
    li.textContent=(names[event.event]||event.event)+(event.quantity?' · '+event.quantity+' Stück':'')+(typeof event.price_eur==='number'?' · '+event.price_eur.toFixed(4)+' €':'')+(typeof event.stop_eur==='number'?' · Stop '+event.stop_eur.toFixed(4)+' €':'')+(event.reason?' · '+event.reason:'');log.append(li);
   }
   status.textContent='✓ Interner Test abgeschlossen · '+data.duplicateRetriesChecked+' Wiederholungen ohne Doppelauftrag geprüft. DEGIRO-Verbindung weiterhin nicht getestet.';
  }catch(error){status.textContent='Test fehlgeschlagen: '+error.message;}finally{run.disabled=false;}
 });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
</script>
'''
