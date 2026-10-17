"""DEGIRO tab: explicitly offline integration test, no account access."""
PANEL = r'''
<section id="bobDegiroSandbox" class="card" style="padding:16px">
<h3>DEGIRO · Automatik entwickeln und testen</h3>
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
<p>degiro-connector ist noch nicht eingebunden. Anmeldung, Depotabruf und Orderfunktionen bei DEGIRO sind nicht getestet. Die ausstehende E-Mail-Antwort ist keine Genehmigung. Echtgeldhandel ist nicht aktiviert.</p>
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
