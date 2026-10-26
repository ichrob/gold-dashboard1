"""DEGIRO tab: explicitly offline integration test, no account access."""
PANEL = r'''
<section id="bobDegiroSandbox" class="card" style="padding:16px">
<h3>DEGIRO · Verbindung und Automatik</h3>
<section aria-label="DEGIRO Depotabgleich über SnapTrade">
<h4>DEGIRO-Depotabgleich über SnapTrade · nur lesen</h4>
<p id="dgSnaptradeSyncStatus" role="status">Gespeicherten Lese-Status prüfen …</p>
<p id="dgSnaptradeSyncDetail" class="small">Keine neuen Brokerzugriffe durch diese Statusanzeige.</p>
<p class="small">Dieser Abgleich zeigt nur die über SnapTrade gelieferten Depotpositionen, keine vollständige bei DEGIRO handelbare Goldproduktliste und keine ausführbaren Geld-/Briefkurse. Originalzeiten und Produktfreigaben werden nicht verändert.</p>
</section>
<hr>
<details id="dgOptionalSdk"><summary>Separater inoffizieller DEGIRO-SDK-Test (für SnapTrade nicht erforderlich)</summary>
<p class="small">Dies ist NICHT der SnapTrade-Abgleich. DEGIRO unterstützt diese inoffizielle Schnittstelle nicht; ein erfolgreicher SnapTrade-Lesezugriff startet den SDK-Test nicht.</p>
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
<section aria-label="DEGIRO Ordervorprüfung">
<h4>Orderentwurf bei DEGIRO prüfen · ohne Bestätigung</h4>
<p>Einzelner inoffizieller Praxistest. Noch kein automatischer Dauerbetrieb. DEGIRO unterstützt diese Automatisierung nicht. Der Broker prüft nur die eingegebenen Angaben zum Prüfzeitpunkt; eine Ausführung wird nicht garantiert.</p>
<label>ISIN<input id="dgPreviewIsin" maxlength="12" autocomplete="off"></label>
<label>Kauf oder Verkauf<select id="dgPreviewSide"><option value="BUY">Kauf prüfen</option><option value="SELL">Verkauf prüfen</option></select></label>
<label>Stückzahl<input id="dgPreviewQuantity" type="number" min="1" step="1"></label>
<label>Limitpreis je Stück<input id="dgPreviewPrice" type="number" min="0.0001" step="any"></label>
<label>Währung<select id="dgPreviewCurrency"><option>EUR</option><option>CHF</option></select></label>
<button id="dgPreviewRun" type="button">Nur Ordervorprüfung starten</button>
<p id="dgPreviewResult" role="status">Noch keine Vorprüfung durchgeführt. Nutzt den Einmalcode oben, falls erforderlich.</p>
<p class="small">Es wird keine Order bestätigt, geändert oder gelöscht. Ein laufender direkter Leseabgleich muss zuvor beendet werden. Ergebnisse ändern weder Bobs Rangliste noch die Handelsfreigabe.</p>
</section><hr>
<section aria-label="DEGIRO automatischer Leseabgleich">
<h4>Depot automatisch abgleichen</h4>
<p>Alle 30 Sekunden während der angemeldeten Sitzung, auch bei geschlossener App. Der Einmalcode oben wird auch für diesen Start verwendet.</p>
<button id="dgSyncStart" type="button">Leseabgleich starten</button>
<button id="dgSyncStop" type="button">Abgleich beenden</button>
<p id="dgSyncStatus" role="status">Noch kein Abgleich gestartet.</p>
<div id="dgSyncHoldings"></div>
<p class="small">Depotbewertungen sind keine aktuellen Geld-/Briefkurse. SG, BNP, comdirect und Swissquote bleiben für Produktdaten zuständig. Nach Serverneustart, spätestens nach acht Stunden oder bei abgelaufener Sitzung erneut anmelden. Zugangssitzungen werden nicht dauerhaft gespeichert.</p>
</section>
</details>
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
 const sourceStatus=document.getElementById('dgSnaptradeSyncStatus'),sourceDetail=document.getElementById('dgSnaptradeSyncDetail');
 async function refreshSnaptradeSource(){
  try{
   // Status is process-local and authenticated; unlike /api/snaptrade/check it does not contact the provider.
   const response=await fetch('/api/snaptrade/status',{credentials:'same-origin',cache:'no-store'});
   if(!response.ok)throw Error('status unavailable');
   const data=await response.json();
   if(!data||typeof data!=='object'||data.configured!==true){
    sourceStatus.textContent='SnapTrade in Bob nicht eingerichtet. Kein automatischer Depotabgleich bestätigt.';
    sourceDetail.textContent='Der separate DEGIRO-SDK-Test ist keine Ersatzverbindung.';
    return;
   }
   const accounts=Array.isArray(data.snapshot?.accounts)?data.snapshot.accounts:[];
   const positions=accounts.reduce((n,account)=>n+(Array.isArray(account?.positions)?account.positions.length:0),0);
   const isRead=data.code==='READ_OK';
   sourceStatus.textContent=isRead&&data.fresh===true?'✓ SnapTrade-Depotlesung aktuell bestätigt.':
     isRead?'Letzter SnapTrade-Depotlesestand vorhanden, aber nicht als aktuell bestätigt.':
     'SnapTrade eingerichtet; laufende Depotlesung nicht bestätigt.';
   sourceDetail.textContent=(isRead?accounts.length+' Konto/Konten · '+positions+' Positionen im gespeicherten Lesestand. ':'Noch kein bestätigter Depotlesestand. ')+
     'Keine vollständige DEGIRO-Produktliste, keine Broker-Geld-/Briefkurse und keine Orderfreigabe.';
  }catch(_){
   sourceStatus.textContent='SnapTrade-Status nicht erreichbar. Keine aktuelle Depotverbindung bestätigt.';
   sourceDetail.textContent='Die Statusprüfung sendet keine neue Anfrage an DEGIRO oder SnapTrade.';
  }
 }
 refreshSnaptradeSource();setInterval(()=>{if(!document.hidden)refreshSnaptradeSource();},30000);
 const connectionStatus=document.getElementById('dgConnectionStatus'),test=document.getElementById('dgConnectionTest'),otp=document.getElementById('dgConnectionOtp');
 const authReasons={TOTP_REQUIRED:'DEGIRO verlangt einen Einmalcode aus einer bereits eingerichteten Authenticator-App.',APP_APPROVAL_REQUIRED:'DEGIRO verlangt eine Bestätigung in der DEGIRO-App. Diesen Anmeldeablauf unterstützt Bob derzeit nicht.',CAPTCHA_REQUIRED:'DEGIRO verlangt ein CAPTCHA. Bob kann es nicht bearbeiten; im offiziellen DEGIRO-Browserzugang prüfen.',RATE_LIMITED:'DEGIRO begrenzt die Anmeldeversuche. Bitte vorerst keine weiteren Versuche starten.',ACCESS_DENIED:'Der DEGIRO-Server verweigert den Zugriff dieses Servers. Ein falsches Passwort ist damit nicht nachgewiesen.',SERVICE_UNAVAILABLE:'Der DEGIRO-Anmeldedienst ist derzeit nicht verfügbar.',INVALID_LOGIN_RESPONSE:'Die DEGIRO-Anmeldeantwort hat ein unerwartetes Format. Technische Prüfung erforderlich.',LOGIN_REJECTED:'DEGIRO hat keine Sitzung erteilt. Die Antwort bestätigt weder ein falsches Passwort noch einen fehlenden Einmalcode.'};
 function authDetail(data){
  const detail=data.authReason==='LOGIN_REDIRECT'?'DEGIRO leitet die Serveranmeldung weiter. Bob hat die Weiterleitung angehalten; die Anmeldung ist nicht bestätigt.':authReasons[data.authReason]||'',r=data.loginResponse;
  if(!detail||!r)return detail;
  const kind={html:'HTML-Seite',empty:'leere Antwort',json:'JSON-Antwort',other:'anderes Antwortformat'};
  const routes={'login-page':'Anmeldeseite','login-api':'Anmelde-API','totp-api':'Einmalcode-API','trader-page':'Handelsoberfläche',captcha:'CAPTCHA-Seite',challenge:'Prüfseite',maintenance:'Wartungsseite',blocked:'Sperrseite',denied:'Zugriff verweigert',error:'Fehlerseite',other:'anderer Pfad'};
  const redirect=r.redirectHost?' Weiterleitungsziel: '+(r.redirectHost==='other'?'nicht freigegebener oder unbekannter Host':r.redirectHost)+' · '+(routes[r.redirectRoute]||'unbekannt')+'.':'';
  return detail+' Technischer Befund: HTTP '+r.httpStatus+' · '+(kind[r.responseFormat]||'Format unbekannt')+(r.challengePage?' · Prüfseite erkannt. Bob umgeht diese Prüfung nicht.':'.')+redirect;
 }
 fetch('/api/degiro/connection-status',{credentials:'same-origin',cache:'no-store'}).then(async response=>{
  if(!response.ok)throw new Error('Status nicht erreichbar');
  const data=await response.json();
  test.disabled=!data.ready;
  connectionStatus.textContent=data.ready?'Bibliothek und Zugangsdaten eingerichtet. Verbindung noch nicht getestet.':(!data.sdkReady?'Bibliothek fehlt oder Version passt nicht. ':'')+(!data.credentialsConfigured?'DEGIRO-Zugangsdaten noch nicht eingerichtet. ':'');
  if(data.lastTest)connectionStatus.textContent='Letzter Lesetest: '+new Date(data.lastTest.checkedAt).toLocaleString()+' · '+(authDetail(data.lastTest)||(data.lastTest.code==='READ_OK'?'Anmeldung und Depotabruf erfolgreich.':'Keine Verbindung bestätigt ('+data.lastTest.code+').'));
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
   if(authDetail(data))connectionStatus.textContent=authDetail(data);
  }catch(error){connectionStatus.textContent='Lesetest nicht bestätigt: '+error.message;}finally{test.disabled=false;}
 });

 const previewButton=document.getElementById('dgPreviewRun');
 previewButton.addEventListener('click',async()=>{
  const out=document.getElementById('dgPreviewResult'),read=id=>document.getElementById(id).value;
  const payload={isin:read('dgPreviewIsin').trim().toUpperCase(),side:read('dgPreviewSide'),quantity:Number(read('dgPreviewQuantity')),price:Number(read('dgPreviewPrice')),currency:read('dgPreviewCurrency'),otp:read('dgConnectionOtp').trim()};
  if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(payload.isin)||!Number.isInteger(payload.quantity)||payload.quantity<1||!Number.isFinite(payload.price)||payload.price<=0){out.textContent='ISIN, ganze Stückzahl und positiven Limitpreis ergänzen.';return;}
  document.getElementById('dgConnectionOtp').value='';previewButton.disabled=true;out.textContent='Anmeldung und einzelne Vorprüfung laufen …';
  try{
   const r=await fetch('/api/degiro/preflight',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   if(!r.ok)throw Error();const data=await r.json();
   const labels={PRECHECK_RESPONSE:'DEGIRO hat eine Vorprüfungsantwort geliefert. Keine Order bestätigt; keine Ausführungsgarantie.',BROKER_REJECTED:'DEGIRO hat diesen Entwurf abgelehnt. Kein allgemeines Urteil über die ISIN.',UNVERIFIED_RESPONSE:'Brokerantwort nicht eindeutig bestätigt.',IDENTITY_UNCONFIRMED:'ISIN, Handelsplatzzuordnung oder Währung nicht eindeutig. Keine Vorprüfung gesendet.',AUTH_REQUIRED:'Direkte DEGIRO-Anmeldung nicht bestätigt. Einmalcode oder App-Anforderung prüfen.',BUSY:'Direkter Leseabgleich oder anderer Test läuft. Zuerst beenden.',SETUP_REQUIRED:'Direkte DEGIRO-Zugangsdaten oder passende Bibliothek fehlen. Einmalige Einrichtung oben prüfen.',COOLDOWN:'Zwischen Anmeldeversuchen mindestens 60 Sekunden warten.',TIMEOUT:'Zeitlimit erreicht. Keine bestätigte Vorprüfung.',SDK_ERROR:'Vorprüfung technisch nicht bestätigt.',INVALID_INPUT:'Eingaben ungültig.'};
   out.textContent=(labels[data.code]||'Ergebnis unbekannt.')+(data.checkedAt?' Prüfzeit: '+new Date(data.checkedAt).toLocaleString():'')+(data.logoutConfirmed===false?' Abmeldung nicht bestätigt.':'');
  }catch(_){out.textContent='Vorprüfung nicht bestätigt. Keine automatische Wiederholung.';}finally{previewButton.disabled=false;}
 });
 const syncStatus=document.getElementById('dgSyncStatus'),holdings=document.getElementById('dgSyncHoldings');
 const syncStart=document.getElementById('dgSyncStart'),syncStop=document.getElementById('dgSyncStop');
 function drawSync(data){
  const names={NOT_STARTED:'Noch nicht gestartet.',STARTING:'Anmeldung läuft …',READ_OK:'Depot gelesen.',SETUP_REQUIRED:'Bibliothek oder Zugangsdaten fehlen.',AUTH_REQUIRED:'Erneut anmelden; gegebenenfalls Einmalcode eingeben.',SDK_ERROR:'Abgleich unterbrochen. Erneut anmelden.',INVALID_RESPONSE:'Datenantwort unvollständig. Letzter Stand bleibt erhalten.',DISCONNECTED:'Verbindung beendet. Erneut anmelden.',TIMEOUT:'Abgleich antwortet nicht. Sitzung beendet; erneut anmelden.',STOPPING:'Abgleich wird beendet …',STOPPED:'Abgleich beendet.',COOLDOWN:'Bitte 60 Sekunden zwischen Anmeldeversuchen warten.'};
  syncStatus.textContent=(names[data.code]||'Status unbekannt.')+(data.snapshot?' Letzter Abruf: '+new Date(data.snapshot.observedAt).toLocaleString()+' · '+(data.fresh?'aktuell abgeglichen':'nicht aktuell bestätigt'):'');
  if(authDetail(data))syncStatus.textContent=authDetail(data);
  syncStart.disabled=data.running===true;syncStop.disabled=data.running!==true;
  holdings.replaceChildren();
  for(const row of data.snapshot?.holdings||[]){
   const card=document.createElement('p');
   card.textContent=(row.name||row.isin||'Produkt '+row.productId)+' · '+(row.isin||'ISIN nicht geliefert')+' · '+row.quantity+' Stück · Depotbewertung je Stück: '+(row.valuationPrice??'nicht geliefert')+' '+row.currency+' (Kurszeit nicht geliefert)';
   holdings.append(card);
  }
  if(data.snapshot&&!data.snapshot.holdings.length)holdings.textContent='Keine offenen Produktpositionen im gelesenen Depot.';
 }
 async function refreshSync(){
  try{const r=await fetch('/api/degiro/sync',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw Error();drawSync(await r.json());}
  catch(_){syncStatus.textContent='Abgleichstatus nicht erreichbar; Aktualität nicht bestätigt.';}
 }
 async function controlSync(action){
  if(action==='start'&&otp.value&&!/^[0-9]{6}$/.test(otp.value)){syncStatus.textContent='Einmalcode muss sechs Ziffern haben.';return;}
  const body=JSON.stringify(action==='start'?{otp:otp.value}:{});otp.value='';
  syncStart.disabled=true;syncStop.disabled=true;
  try{const r=await fetch('/api/degiro/sync/'+action,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body});if(!r.ok)throw Error();drawSync(await r.json());}
  catch(_){syncStatus.textContent='Anfrage fehlgeschlagen. Status erneut prüfen.';syncStart.disabled=false;}
 }
 syncStart.addEventListener('click',()=>controlSync('start'));syncStop.addEventListener('click',()=>controlSync('stop'));
 refreshSync();setInterval(()=>{if(!document.hidden)refreshSync();},5000);

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

