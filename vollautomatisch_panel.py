"""Isolated UI for an authenticated, fixed-quote PAPER-ONLY regression demo.

Existing mobile navigation in Bob.html provides the Vollautomatisch workspace.
This panel adds an actual executable prototype without duplicate navigation.
"""
PANEL = r"""
<section id="bob-broker-route-status" class="card" style="margin:12px 0;padding:15px;border:1px solid #cbd5e1;border-radius:14px;background:#fff;color:#17263a">
 <h3>Broker &amp; Ausführung · Status</h3>
 <p class="small"><b>DEGIRO:</b> Bob analysiert LONG/SHORT und unterstützt deine manuelle Kauf- oder Verkaufsentscheidung. Keine API-Verbindung, keine automatische Order. Den angebotenen Preis prüfst du im DEGIRO-Orderfenster.</p>
 <p class="small"><b>Andere Broker:</b> Interactive Brokers und IG Bank Schweiz sind als zukünftige API-Routen vorbereitet. Erst offizielle Konto-/Instrumentenprüfung, dann Demo-/Paper-Tests, anschließend nur nach gesonderter Zustimmung eine mögliche Live-Anbindung.</p>
 <p id="bob-broker-route-confirmation" class="small" role="status">Automatische Brokerorders deaktiviert · keine Zugangsdaten erforderlich.</p>
 <button type="button" id="bob-broker-route-refresh">Brokermodus prüfen</button>
</section>
<section id="bob-vollautomatisch-demo" class="card" style="margin:12px 0;padding:16px;border:1px solid #b6c3d2;border-radius:14px;background:#fff;color:#16263c">
 <h3>100 € · Simulations-Probelauf</h3>
 <p class="small" style="color:#475569">Getrennter Rechenkern mit synthetischen Produktkursen in Euro. Er testet Kauf, Positionsgrösse, Stop-Loss, Gewinnziel, Trailing-Stop und Kostenannahmen. Noch kein automatischer Handel mit Marktdaten.</p>
 <label for="bobAutoDemoScenario"><b>Testszenario</b></label>
 <select id="bobAutoDemoScenario" style="display:block;margin:8px 0 12px;max-width:100%;width:100%;padding:10px;border-radius:8px">
  <option value="target">Gewinnziel erreicht</option>
  <option value="stop_gap">Kurslücke und Stop-Verlust</option>
  <option value="trailing">Nachgezogener Stop</option>
  <option value="stale">Veralteter Kurs blockiert Einstieg</option>
 </select>
 <button type="button" id="bobAutoDemoRun" class="bob-primary">Probelauf mit Beispieldaten starten</button>
 <p class="small" id="bobAutoDemoStatus" role="status">Noch nicht ausgeführt · keine Echtgeld-Orders möglich.</p>
 <div id="bobAutoDemoResults" hidden>
  <div id="bobAutoDemoNumbers" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0"></div>
  <details open><summary><b>Simulierter Orderverlauf</b></summary>
   <ol id="bobAutoDemoEvents" style="padding-left:22px;line-height:1.7"></ol>
  </details>
  <p class="small">Die Kurse sind frei erfunden und nachträglich festgelegt. Der Probelauf ist ein Funktionstest, kein Erfolgsnachweis. Einstieg zum Briefkurs, Ausstieg zum Geldkurs, zusätzliche Slippage; Gebühren im Probelauf auf 0 € gesetzt.</p>
 </div>
</section>
<section class="card" id="bob-portfolio-comparison" style="margin:12px 0;padding:15px;border:1px solid #cbd5e1;border-radius:14px;background:#fff;color:#17263a">
 <h3>Fünf unabhängige Geldsimulationen</h3>
 <p class="small">Vier 100-€-Testkonten und ein 800-€-Trendfolgekonto. Die ersten vier bisherigen Konten starten wie bisher am Montag, 12.10.2026 um 08:00 Uhr (Zürich); das neue Frühimpuls-Testkonto erst ab seiner Aktivierung. Keine echten Orders, kein DEGIRO-Zugriff. Alle fünf Konten nutzen dieselben beobachteten Kurse. Der bestehende manuelle 800-Euro-Test unter Mein Trade bleibt vollständig unangetastet.</p>
 <button type="button" id="bobProfilesRefresh" class="bob-primary">Fünf Simulationen prüfen</button>
 <p id="bobProfilesStatus" class="small" role="status">Prüfstand wird geladen …</p>
 <div id="bobProfilesCards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:12px"></div>
 <p class="small">Bruttoergebnisse: Spread ist im Brief-/Geldkurs enthalten. Gebühren, Finanzierung und Slippage sind nicht vollständig belegt. Erfolgsquote zählt nur mit frischem Produktkurs bewertete Trades; Drawdown nur beobachtete Kurse, keine unbekannten Kurslücken.</p>
  <details><summary>Grenzen des Tests</summary><p class="small">Konservativ: bestätigter Trend, Richtungswert 80/20, bis 35 % Kapitaleinsatz, 1 % Tages-Einstiegssperre. Ausgewogen: 70/30, bis 65 %, 3 %. Offensiv: 65/35, bis 95 %, 5 %. 800 € · Bob-Stopp & Wiedereinstieg: Trend bestätigt, 70/30, bis 65 %, 3 %. Dieselbe Bob-Stopp-/Zielverwaltung wie die Haupt-Testkonten: Stoppvorschläge übernehmen, niemals lockern, am beobachteten Stopp beenden. Danach neues bestätigtes Setup und vollständige Produktfreigabe vor dem Wiedereinstieg. Teilgewinn und Zielverlängerung bleiben Teil von Bobs gemeinsamer Verwaltung. Höchstens vier Stunden pro neuem Trade beziehungsweise bis 21:45 Uhr Zürich. Keine Nachtposition. Prozentuale Rendite statt absoluter Eurogewinne vergleichen. Frühimpuls 100 €: eigenständiger früher 5m/15m-LONG/SHORT-Einstiegsversuch, ohne Änderung der Hauptrichtung und nur mit gültigem Euro-Produktkurs, verifiziertem KO und Gold-Stop/Ziel-Plan. Fehlende Nachweise blockieren auch den virtuellen Einstieg. Die Tagesgrenzen stoppen nur weitere Einstiege. Alle Varianten verwenden dieselben Produktnachweise. Bruttomodell ohne vollständig belegte Gebühren, Finanzierung und Slippage; Stopps sind wegen Kurslücken keine garantierten Verlustgrenzen.</p></details>
</section>
<script>
(function(){
 function mount(){
  const root=document.getElementById('bob-vollautomatisch-demo');
  if(!root)return;
  const auto=document.getElementById('bob-view-auto');
  const brokerPanel=document.getElementById('bob-broker-route-status');
  if(auto&&brokerPanel)auto.append(brokerPanel);
  if(auto)auto.append(root);
  const brokerStatus=document.getElementById('bob-broker-route-confirmation');
  const brokerRefresh=document.getElementById('bob-broker-route-refresh');
  async function refreshBrokerStatus(){
    if(!brokerStatus||!brokerRefresh)return;
    brokerRefresh.disabled=true;
    try{
      const response=await fetch('/api/zukunft/research',{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)throw Error('not available');
      const readiness=(await response.json()).brokerReadiness;
      if(!readiness||readiness.defaultManualBroker!=='degiro'||readiness.executionEnabled!==false||
         readiness.liveOrders!==false||readiness.paperOrders!==false||
         readiness.manualBroker?.mode!=='MANUAL_ONLY')throw Error('unexpected policy');
      brokerStatus.textContent='Bestätigt: DEGIRO nur manuell · API-Broker nicht verbunden · Paper- und Echtgeldorders deaktiviert.';
    }catch(_){
      brokerStatus.textContent='Aktueller Brokerstatus nicht abrufbar. Keine automatische Orderfreigabe.';
    }finally{brokerRefresh.disabled=false;}
  }
  if(brokerRefresh)brokerRefresh.addEventListener('click',refreshBrokerStatus);

  const comparison=document.getElementById('bob-portfolio-comparison');
  if(auto&&comparison)auto.insertBefore(comparison,root);
  const profilesStatus=document.getElementById('bobProfilesStatus');
  const profilesCards=document.getElementById('bobProfilesCards');
  const money=new Intl.NumberFormat('de-CH',{style:'currency',currency:'EUR'});
  const time=v=>v?new Date(v).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch kein Hintergrundzyklus';
  let profileBusy=false;
  async function refreshProfiles(){
   if(profileBusy)return;
   profileBusy=true;
   profilesStatus.textContent='Alle fünf Testkonten werden geprüft …';
   try{
    const day=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich'}).format(new Date());
    const response=await fetch('/api/audit/read',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json'},cache:'no-store',
      body:JSON.stringify({mode:'simulation-profiles',day})});
    if(!response.ok)throw Error('HTTP '+response.status);
    const data=await response.json();
    if(data.mode!=='five-independent-paper-accounts'||data.realOrders!==false||
       !Array.isArray(data.accounts)||data.accounts.length!==5)throw Error('Fünf-Konten-Auswertung ungültig');
    profilesCards.replaceChildren();
    const names={conservative:'Konservativ',balanced:'Ausgewogen',offensive:'Offensiv',trend800:'800 € · Bob-Stopp & Wiedereinstieg',early100:'Frühimpuls 100 € (LONG/SHORT)'};
    for(const acc of data.accounts){
     const c=acc.control||{},p=acc.riskPolicy||{},st=acc.stats||{},perf=acc.performance||{};
     const card=document.createElement('div');card.style='padding:12px;border:1px solid #cbd5e1;border-radius:12px;min-width:0';
     const heading=document.createElement('h4');heading.style='margin:0 0 8px';heading.textContent=names[acc.profile]||acc.profile;card.append(heading);
     const lines=[
      'Fiktiver Anfang: '+money.format(c.initialCapital??100),
      'Kapital: '+(Number.isFinite(c.equity)?money.format(c.equity):'Bewertung offen'),
      'Bargeld: '+(Number.isFinite(c.cash)?money.format(c.cash):'unbekannt'),
      'Rendite seit Start (brutto): '+(Number.isFinite(c.equity)&&Number.isFinite(c.initialCapital)&&c.initialCapital>0?((c.equity/c.initialCapital-1)*100).toFixed(2)+' %':'Bewertung offen'),
      'Grösster beobachteter Kapitalrückgang: '+(Number.isFinite(perf.observedMaxDrawdownPct)?perf.observedMaxDrawdownPct.toFixed(2)+' %':'noch kein belegter Wert'),
      'Positive vollständig bepreiste Trades: '+(perf.pricedTrades>0?(perf.positivePricedTrades+'/'+perf.pricedTrades+' · '+perf.productPositiveRatePct.toFixed(1)+' %'):'noch keine'),
      'Nicht auswertbare Fälle: '+(perf.inconclusiveTrades??0),
      'Preisprüfungen ohne gültigen Kurs: '+(perf.quoteMissingChecks??0)+' (seit Start)',
      'Preisprüfungen mit gültigem Kurs: '+(perf.quoteConfirmedChecks??0)+' (seit Start)',
      'Produktbewertung: '+(perf.quoteStatus==='missing-or-stale'?'Geldkurs fehlt oder ist veraltet':perf.quoteStatus==='confirmed'?'bestätigter Geldkurs':perf.quoteStatus==='no-open-units'?'keine offenen Stücke':'noch keine Beobachtung'),
      'Heute realisiert (brutto): '+(Number.isFinite(st.dayRealizedProfit)?money.format(st.dayRealizedProfit):'noch unbekannt'),
      'Offene Stücke: '+(c.openUnits??0),
      'Tagesverlustgrenze: '+Math.round((p.daily_loss_fraction||0)*100)+' %',
      'Max. Kapitaleinsatz: '+Math.round((p.exposure_fraction||0)*100)+' %',
      'Strategie: '+(acc.profile==='early100'?'Frühimpuls LONG/SHORT · nur virtuell':'bestätigte Hauptrichtung') ,
      'Beginn der Konto-Historie: '+time(c.startAt),
      'Ausstiegsmodell: '+(acc.exitPolicy==='bob-stop-reentry-v1'?'Bobs Stopp übernehmen → am Stopp beenden → bei neuem bestätigtem Setup wieder einsteigen':acc.exitPolicy==='trend-follow-v1'?'Längeren Trend halten · kein Teilverkauf am 1. Ziel':'Bob: Teilgewinn und Zielverlängerung'),
      'Abgeschlossene Fälle heute: '+(st.closed||0),
      'Status: '+(c.status||'nicht bestätigt'),
      'Letzte Prüfung: '+time(c.checkedAt),
      'Grund: '+(c.reason||'Noch kein protokollierter Durchlauf')
     ];
     const detail=document.createElement('p');detail.className='small';detail.style='white-space:pre-line;overflow-wrap:anywhere';
     detail.textContent=lines.join('\n');card.append(detail);
     const cr=acc.costReview;
     if(cr){
      const costs=document.createElement('details'),title=document.createElement('summary'),body=document.createElement('p');
      title.textContent='Ergebnis nach Beispielkosten · gewählter Tag';body.className='small';body.style='white-space:pre-line;overflow-wrap:anywhere';
      const costLines=[];
      for(const m of cr.scenarios||[])costLines.push(m.name+': '+m.evaluated+' bepreiste Fälle · '+m.excluded+' ausgeschlossen · Ergebnis nach Beispielkosten '+(Number.isFinite(m.modelNetEur)?money.format(m.modelNetEur):'offen')+' · mittlerer Gewinn '+(Number.isFinite(m.averageWinEur)?money.format(m.averageWinEur):'offen')+' / Verlust '+(Number.isFinite(m.averageLossEur)?money.format(m.averageLossEur):'offen')+' · Annahmen: '+m.feeEurPerOrder+' EUR je Kauf/Teilverkauf, '+m.slippageBpsPerSide+' Basispunkte schlechtere Ausführung je Seite, '+m.extraHoldingBpsPerDay+' Basispunkte zusätzliche Haltekosten pro Tag.');
      costLines.push(cr.note);body.textContent=costLines.join('\n\n');costs.append(title,body);card.append(costs);
     }
     const blocks=document.createElement('details'),blockTitle=document.createElement('summary');
     blockTitle.textContent='Einstiegssperren · Tagesprotokoll';blocks.append(blockTitle);
     const blockText=document.createElement('p');blockText.className='small';blockText.style='white-space:pre-line';
     blockText.textContent=[
      ...(Object.entries(st.entryBlockCounts||{}).map(([reason,count])=>count+' Prüfungen: '+reason)),
      ...(st.entryBlocks||[]).map(x=>time(x.at)+' bis '+time(x.lastAt)+' · '+x.direction+(x.isin?' · '+x.isin:'')+' · '+x.reason),
      st.entryBlocksTruncated?'Letzte 200 Änderungen der Sperrgründe; Tageszähler vollständig.':'',
      !(st.entryBlocks||[]).length?'Noch keine Sperrgründe seit Aktivierung dieses Protokolls gespeichert. Frühere Gründe werden nicht rückwirkend ergänzt.':''
     ].filter(Boolean).join('\n');blocks.append(blockText);card.append(blocks);
     const events=document.createElement('details');const label=document.createElement('summary');
     label.textContent='Trades und Entscheidungen ('+(acc.cases||[]).length+')';
     events.append(label);
     const host=document.createElement('div');
     for(const trade of (acc.cases||[])){
      const row=document.createElement('p');row.className='small';
      row.textContent=(trade.startedAt?time(trade.startedAt):'')+' · '+
        (trade.plan?.direction||'NEUTRAL')+' · '+(trade.product?.isin||'ohne ISIN')+
        ' · '+(trade.status||'unbekannt')+' · '+(trade.productReturnKnown?
          (Number(trade.productGrossPct)||0).toFixed(2)+' % brutto':'Produktbewertung offen')+
           (Number.isFinite(trade.entrySpreadEur)?' · Spread beim Kauf: '+money.format(trade.entrySpreadEur)+' (im Bruttoergebnis enthalten)':'');
      host.append(row);
     }
     if(!host.childNodes.length){const empty=document.createElement('p');empty.className='small';
      empty.textContent='Noch keine virtuellen Trades; Gründe siehe Status.';host.append(empty);}
     events.append(host);card.append(events);profilesCards.append(card);
    }
    profilesStatus.textContent='Fünf getrennte Konten · Bericht für '+day+
      ' · 1.200 € fiktives Startkapital (4 × 100 €, 1 × 800 €) · keine echten Orders';
   }catch(error){profilesStatus.textContent='Kontostand nicht abrufbar: '+String(error.message||error)+'. Kein Testerfolg bestätigt.';}
   finally{profileBusy=false;}
  }
  document.getElementById('bobProfilesRefresh').addEventListener('click',refreshProfiles);
  refreshProfiles();
  setInterval(()=>{if(document.visibilityState==='visible'&&!window.BobWeekendPause?.())refreshProfiles();},60000);
  const run=document.getElementById('bobAutoDemoRun');
  const scenario=document.getElementById('bobAutoDemoScenario');
  const status=document.getElementById('bobAutoDemoStatus');
  const results=document.getElementById('bobAutoDemoResults');
  const summary=document.getElementById('bobAutoDemoNumbers');
  const events=document.getElementById('bobAutoDemoEvents');
  const eur=new Intl.NumberFormat('de-CH',{style:'currency',currency:'EUR'});
  run.addEventListener('click',async()=>{
   run.disabled=true;status.textContent='Synthetische Trades werden berechnet …';
   results.hidden=true;
   try{
    const response=await fetch('/api/vollautomatisch/demo?scenario='+encodeURIComponent(scenario.value),{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)throw Error('Probelauf konnte nicht geladen werden (HTTP '+response.status+').');
    const data=await response.json();
    if(data.mode!=='PAPER_ONLY'||data.live_order_capable!==false||data.synthetic!==true)throw Error('Unsicherer Simulationsstatus');
    summary.replaceChildren();events.replaceChildren();
    const cells=[
      ['Startkapital',eur.format(data.initial_eur)],
      ['Virtuelles Endkapital',eur.format(data.equity_eur)],
      ['Veränderung',eur.format(data.equity_eur-data.initial_eur)],
      ['Maximaler Rückgang',(data.max_drawdown_fraction*100).toFixed(2)+' %']
    ];
    for(const [label,value] of cells){
     const cell=document.createElement('div');cell.style='padding:10px;border:1px solid #e2e8f0;border-radius:10px;min-width:0';
     const title=document.createElement('small');title.style='display:block;color:#475569';title.textContent=label;
     const body=document.createElement('strong');body.textContent=value;cell.append(title,body);summary.append(cell);
    }
    const descriptions={
      BUY_PAPER:'Virtueller Kauf',SELL_PAPER:'Virtueller Verkauf',
      TRAIL_PAPER:'Stop nachgezogen',BLOCKED:'Einstieg gesperrt',
      STALE_FEED:'Kurs veraltet'
    };
    for(const e of data.events){
     const line=document.createElement('li');
     const name=descriptions[e.event]||'Testereignis';
     const price=typeof e.price_eur==='number'?' · '+eur.format(e.price_eur):'';
     const stop=typeof e.stop_eur==='number'?' · Stop '+eur.format(e.stop_eur):'';
     const amount=typeof e.quantity==='number'?' · '+e.quantity+' Stück':'';
     const gain=typeof e.pnl_eur==='number'?' · Ergebnis '+eur.format(e.pnl_eur):'';
     line.textContent=name+' · '+e.at+amount+price+stop+gain+(e.reason?' · '+e.reason:'');
     events.append(line);
    }
    status.textContent='Funktionstest ('+scenario.options[scenario.selectedIndex].text+') berechnet · '+data.quotes_processed+' künstliche Kursbeobachtungen · keine echte Order';
    results.hidden=false;
   }catch(error){status.textContent='Probelauf nicht verfügbar: '+String(error.message||error);}
   finally{run.disabled=false;}
  });
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
</script>
"""
