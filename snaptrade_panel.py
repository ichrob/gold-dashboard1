"""Personal setup in the existing DEGIRO tab; no broker credentials collected."""
PANEL = r'''
<section id="bobSnapTrade" class="card" style="padding:16px;overflow-wrap:anywhere">
<h3>DEGIRO über SnapTrade Personal</h3>
<p><button id="snapCatalogProbe" type="button" disabled>DEGIRO-Produktverzeichnis einmalig prüfen</button></p>
<p id="snapCatalogProbeStatus" class="small" role="status">Produktverzeichnis noch nicht geprüft. Dies ist kein Nachweis aller handelbaren Gold-Knock-outs.</p>
<p id="snapAccountSymbolStatus" class="small" role="status">Kontobezogene Symbolsuche: noch nicht geprüft.</p>
<p>Kostenloser Personal-Zugang für dein eigenes Depot. Bob liest Bestände und Bargeld bei aktiver Bob-Ansicht frühestens alle zehn Minuten. Im Hintergrund gilt ein sparsamer Sechs-Stunden-Takt. Eindeutig zugeordnete Produktkurse prüft Bob zusätzlich etwa alle 30 Sekunden über seine bestehenden Emittentenquellen; dies sind keine DEGIRO-Ausführungskurse.</p>
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
<p class="small">Der Schlüssel wird verschlüsselt auf Bobs bestehendem Server gespeichert. Er wird nicht im Browser gespeichert oder zurück angezeigt. Keine Zahlungskarte und keinen kostenpflichtigen Tarif einrichten. Das Löschen unten entfernt den Schlüssel sowie den gespeicherten Depotverlauf und das Journal aus Bob; die Verbindung bei SnapTrade verwaltest du dort.</p>
</details>
<p class="small">Optional: <a href="https://docs.snaptrade.com/docs/mcp-server" target="_blank" rel="noopener noreferrer">SnapTrade mit ChatGPT verbinden</a>. Separate schreibgeschützte Verbindung, die du selbst autorisieren musst.</p>
<p id="snapFeedback" role="status" aria-live="polite"></p>
<p><button id="snapCheck" type="button" disabled>Verbindung prüfen</button> <button id="snapRemove" type="button" disabled>Schlüssel aus Bob löschen</button></p>
<p id="snapClock" class="small"></p>
<details id="snapCsvLink"><summary>Portfolio-CSV mit diesem Depot verknüpfen</summary>
<p>Die CSV bleibt zunächst auf diesem Gerät. Mit dem automatischen Abgleich werden die CSV-Felder verschlüsselt auf Bobs Server gespeichert. Bob prüft die Kennungen selbst. Für den kostenlosen FIGI-Abgleich werden nur ISIN und Währung an OpenFIGI gesendet, keine Depotwerte oder Zugangsdaten. Der Exportstand bleibt historisch; Importzeit ist keine Kurszeit. Die Zuordnung schaltet keine Produkte zum Handel frei.</p>
<button id="snapCsvPrepare" type="button">CSV automatisch prüfen und zuordnen</button>
<details><summary>Nur bei Bedarf selbst zuordnen</summary><button id="snapCsvManual" type="button">Manuelle Zuordnung öffnen</button></details>
<div id="snapCsvReview"></div><p id="snapCsvFeedback" role="status" aria-live="polite"></p>
</details><div id="snapHoldings"></div>
<p class="small">Die Daten zeigen nur den vom Anbieter gelieferten Depotstand. Bewertungskurse können verzögert sein; die Bestandsabrufzeit ist keine Originalkurszeit. Produktfreigabe, Hebel- und KO-Nachweise werden weiterhin separat geprüft. Das Journal bleibt getrennt von Top 3 und aktiven Trades. Keine Orders. CSV-Import und bisherige Produktquellen bleiben verfügbar.</p>
</section>
<script>
(function(){
function mount(){
 const panel=document.getElementById('bobSnapTrade'),target=document.getElementById('bob-view-degiro');if(!panel||!target)return;
 target.prepend(panel);
 const status=document.getElementById('snapStatus'),clock=document.getElementById('snapClock'),list=document.getElementById('snapHoldings');
 const client=document.getElementById('snapClient'),key=document.getElementById('snapKey'),free=document.getElementById('snapFree');
 const save=document.getElementById('snapSave'),check=document.getElementById('snapCheck'),remove=document.getElementById('snapRemove');
 const catalogButton=document.getElementById('snapCatalogProbe'),catalogStatus=document.getElementById('snapCatalogProbeStatus');
 let busy=false,lastData=null,lastHoldings=null,csvReviewData=null,lastVisibleReadRequestAt=Date.now();
 function feedback(message){const inline=document.getElementById('snapFormStatus'),outside=document.getElementById('snapFeedback');inline.textContent=message;outside.textContent=message;(document.getElementById('snapSetup').open?inline:outside).scrollIntoView({block:'nearest'});}
 function controls(){check.disabled=busy||!lastData?.configured||lastData.nextCheckSeconds>0;remove.disabled=busy||!lastData?.configured;catalogButton.disabled=busy||!lastData?.configured;}
 const messages={INVALID_CSV_LINK:'CSV-Zuordnung nicht gespeichert: Depot, Währung, stabile Anbieterkennung und Bestätigungen prüfen.',CSV_CONNECTION_REQUIRED:'Für die CSV-Zuordnung zuerst einen erfolgreichen Depotabruf abwarten.',CSV_RETRY_REQUIRED:'Depotabruf läuft oder wurde erneuert. CSV-Vergleich erneut öffnen.',HISTORY_STORE_UNAVAILABLE:'Verschlüsselte CSV-Speicherung nicht bestätigt.',SETUP_REQUIRED:'Noch nicht verbunden. Einmalige Einrichtung oben durchführen.',READY:'Schlüssel gespeichert. Lesetest wird gestartet.',CHECKING:'Depot-Lesetest läuft …',READ_OK:'✓ Depotdaten empfangen. Goldprodukt-Abdeckung noch nicht bestätigt.',CONNECT_DEGIRO:'Personal-Zugang erreichbar. DEGIRO im SnapTrade-Dashboard verbinden.',READ_CONNECTION_REQUIRED:'DEGIRO-Verbindung bei SnapTrade muss auf Lesen stehen.',AUTH_REQUIRED:'Anmeldung nicht bestätigt oder Verbindung abgelaufen. Im SnapTrade-Dashboard prüfen.',ACCESS_DENIED:'Anbieter verweigert den Zugriff. Personal-Zugang und Berechtigungen prüfen.',PLAN_REQUIRED:'Anbieter verlangt einen anderen Tarif. Kein kostenpflichtiger Abruf wird ausgelöst.',RATE_LIMITED:'Anbieter begrenzt die Abrufe. Nächster Versuch frühestens nach zehn Minuten.',PROVIDER_UNAVAILABLE:'Anbieter momentan nicht erreichbar. Letzter Stand ist nicht als aktuell bestätigt.',INVALID_RESPONSE:'Datenformat nicht vollständig erkannt. Kein vollständiger Abgleich bestätigt.',STORE_UNAVAILABLE:'Geschützter Schlüsselspeicher momentan nicht erreichbar.',SETTINGS_UNREADABLE:'Gespeicherter Schlüssel kann nicht gelesen werden. Personal-Schlüssel erneut speichern.',NO_ACCOUNTS:'Noch kein lesbares DEGIRO-Depot gefunden.',TOO_MANY_ACCOUNTS:'Mehr als drei DEGIRO-Depots/Verbindungen. Abgleich zur Prüfung angehalten.'};
 function stamp(value){const d=new Date(value);return value&&Number.isFinite(d.getTime())?d.toLocaleString('de-CH'):'nicht geliefert';}
 function render(data){
  lastData=data;
  status.textContent=messages[data.code]||'Verbindung nicht bestätigt.';
  controls();
  const probe=data.catalogProbe||{},pcode=probe.code||'NOT_TESTED';
  if(pcode==='CATALOG_EMPTY')catalogStatus.textContent='Prüfung '+stamp(probe.checkedAt)+': SnapTrade liefert für DEGIRO ein leeres Instrumentenverzeichnis. Automatische Goldproduktliste damit nicht bestätigt.';
  else if(pcode==='CATALOG_RETURNED')catalogStatus.textContent='Prüfung '+stamp(probe.checkedAt)+': '+probe.instrumentCount+' Broker-Instrumente gemeldet; '+(probe.historicalMatches?.length||0)+' von '+(probe.historicalWatchCount||0)+' historisch bekannten ISINs gefunden. Keine vollständige Gold-Knock-out-Liste oder Handelsfreigabe.';
  else if(pcode==='NOT_TESTED')catalogStatus.textContent='DEGIRO-Produktverzeichnis über SnapTrade noch nicht geprüft. Einmaliger Lesetest ohne Orders.';
  else catalogStatus.textContent='Produktverzeichnis-Abfrage '+stamp(probe.checkedAt)+': '+pcode+'. Kein vollständiger Katalognachweis.';
  const symbol=data.accountSymbolProbe||{},scode=symbol.code||'NOT_TESTED';
  const accountSymbolStatus=document.getElementById('snapAccountSymbolStatus');
  if(scode==='EXACT_SYMBOL_CANDIDATE')accountSymbolStatus.textContent='SnapTrade-Kontosuche '+stamp(symbol.checkedAt)+': '+symbol.exactSymbolCandidates+' exakter Symbol-Suchkandidat. KEINE bestätigte DEGIRO-Handelbarkeit oder ausführbare Quote.';
  else if(scode==='SEARCH_EMPTY'||scode==='NO_EXACT_SYMBOL')accountSymbolStatus.textContent='SnapTrade-Kontosuche '+stamp(symbol.checkedAt)+': Kein exakter ISIN-Suchtreffer in der begrenzten Probe. Dies beweist NICHT, dass das Produkt bei DEGIRO nicht handelbar ist.';
  else if(scode==='NOT_TESTED')accountSymbolStatus.textContent='Kontobezogene Symbolsuche: noch nicht geprüft; bei erfolgreichem Depotlesestand einmalig im Hintergrund.';
  else accountSymbolStatus.textContent='Kontobezogene Symbolsuche '+stamp(symbol.checkedAt)+': '+scode+'. Kein Produkt- oder Handelsnachweis.';
  document.getElementById('snapSetup').open=!data.configured;
  clock.textContent=(data.checkedAt?'Letzte Prüfung: '+stamp(data.checkedAt)+'. ':'')+(data.configured?'Nächster möglicher Abruf in '+data.nextCheckSeconds+' Sekunden. ':'')+(data.snapshot?(data.fresh?'Quellenstand innerhalb des Depotintervalls.':'Quellenstand nicht als aktuell bestätigt. '):'');
  const flags=[...new Set(data.connectionWatch?.codes||[])];
  if(flags.length)clock.textContent+=' Quellenstatus: '+flags.join(', ')+'.';
  const fingerprint=JSON.stringify([data.snapshot,data.fresh]);
  if(fingerprint===lastHoldings)return;lastHoldings=fingerprint;
  const opened=new Set(Array.from(list.querySelectorAll('details[open]')).map(e=>e.id));
  list.replaceChildren();
  function line(parent,label,value){const p=document.createElement('p');p.textContent=label+value;parent.append(p);return p;}
  function amount(value,currency){return value===null||value===undefined?'nicht geliefert':Number(value).toLocaleString('de-CH',{maximumFractionDigits:4})+' '+(currency||'');}
  function details(parent,id,title){const d=document.createElement('details'),s=document.createElement('summary');d.id=id;d.open=opened.has(id);s.textContent=title;d.append(s);parent.append(d);return d;}
  function qualityPanel(parent,account){
   const q=account.evidenceQuality||{},p=account.profitReadiness||{};
   const d=details(parent,'snapQuality'+account.accountKey,'Trade-Prüfung · offene Nachweise');
   line(d,'Orderzeilen / positive Ausführungsangaben: ',(q.orderRows??'–')+' / '+(q.positiveFills??'–'));
   line(d,'Ohne positive Ausführung: ',String(q.noPositiveFill??'–'));
   if(q.filledQuantityMissing!==undefined)line(d,'Ausführungsmenge fehlt beim Anbieter: ',String(q.filledQuantityMissing));
   if(q.filledQuantityZero!==undefined)line(d,'Ausführungsmenge ausdrücklich 0: ',String(q.filledQuantityZero));
   if(q.filledQuantityInvalid!==undefined)line(d,'Ungültige oder negative Menge: ',String(q.filledQuantityInvalid));
   line(d,'','Eine fehlende Menge ist kein Nachweis für eine nicht ausgeführte Order. Eine Nullmeldung ist ebenfalls kein vollständiger Nachweis der gesamten Handelshistorie.');
   line(d,'Fehlende Ausführungszeit: ',String(q.missingExecutionTime??'–'));
   line(d,'Fehlende bestätigte ISIN: ',String(q.missingVerifiedIsin??'–'));
   line(d,'Offene Gebührenangaben bei Kauf/Verkauf: ',String(q.activityMissingFees??'–'));
   line(d,'Historische Transaktionen vollständig: ',p.accountHistoryComplete?'Ja':'Nein');
   line(d,'Offene Ergebnisprüfungen: ',String(p.unresolvedLots??'–'));
   line(d,'','Keine vollständige Gewinn- oder Steuerberechnung, kein automatischer Handel.');
  }
  function history(parent,account){
   const d=details(parent,'snapHistory'+account.accountKey,'Depotverlauf · gespeicherte Abrufe');
   line(d,'','Depotwert ist kein Gewinn: Einzahlungen, Auszahlungen und Überträge verändern ihn ebenfalls. Keine Renditeberechnung.');
   const points=(data.snapshot?.history||[]).filter(p=>p.complete).map(p=>({at:p.at,value:p.accounts.find(a=>a.accountKey===account.accountKey)?.netValue}));
   const currencies=[...new Set(points.map(p=>p.value?.currency).filter(Boolean))];
   for(const currency of currencies){
    const series=points.filter(p=>p.value?.currency===currency&&p.value.amount!==null&&Number.isFinite(Number(p.value.amount)));
    if(series.length<2)continue;
    const values=series.map(p=>Number(p.value.amount)),lo=Math.min(...values),hi=Math.max(...values),first=Date.parse(series[0].at),last=Date.parse(series.at(-1).at);
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 300 110');svg.setAttribute('role','img');svg.setAttribute('aria-label','Depotwertverlauf in '+currency);svg.style.width='100%';svg.style.maxWidth='600px';
    const path=document.createElementNS(svg.namespaceURI,'polyline');path.setAttribute('fill','none');path.setAttribute('stroke','#2368a5');path.setAttribute('stroke-width','2');path.setAttribute('points',series.map((p,i)=>(10+280*(Date.parse(p.at)-first)/(last-first||1))+','+(95-80*(values[i]-lo)/(hi-lo||1))).join(' '));svg.append(path);d.append(svg);
    line(d,currency+': ',amount(series[0].value.amount,currency)+' → '+amount(series.at(-1).value.amount,currency));
    line(d,'Zeitraum: ',stamp(series[0].at)+' – '+stamp(series.at(-1).at));
   }
   if(points.length<2)line(d,'','Der Verlauf beginnt mit den nächsten erfolgreichen Abrufen.');
   line(d,'Speicherung: ',data.snapshot.historyPersistence==='SAVED'?'verschlüsselt gespeichert':'nicht bestätigt; Verlauf möglicherweise nur vorübergehend verfügbar');
  }
  function journal(parent,account){
   const d=details(parent,'snapJournal'+account.accountKey,'Handelsjournal · Orders und Transaktionen');
   line(d,'','Orders: jüngstes Anbieterfenster. Transaktionen: täglicher Abruf, üblicherweise einen Tag verzögert. Keine automatische Trade-Freigabe.');
   const failures={AUTH_REQUIRED:'Anbieter-Anmeldung nicht bestätigt',ACCESS_DENIED:'Anbieter verweigert den Journalzugriff',RATE_LIMITED:'Anbieter-Abrufbegrenzung',PLAN_REQUIRED:'Journal im bestehenden Tarif nicht verfügbar',PROVIDER_UNAVAILABLE:'Anbieter momentan nicht erreichbar',RESPONSE_TOO_LARGE:'Anbieterantwort überschreitet das Größenlimit',INVALID_RESPONSE:'Anbieterantwort nicht vollständig verarbeitet'};
   for(const [category,title] of [['orders','Orders'],['activities','Transaktionen']]){
    const value=account.journal?.[category];
    line(d,title+': ',!value?'noch nicht gelesen':(value.code==='READ_OK'?'gelesen':'Abruf nicht verfügbar; vorheriger Stand')+' · letzter erfolgreicher Abruf '+stamp(value.checkedAt));
    if(!value)continue;
    if(value.code!=='READ_OK'&&value.failureCode)line(d,'Letzter fehlgeschlagener Abruf: ',stamp(value.failureAt)+' · '+(failures[value.failureCode]||'Grund nicht bestätigt'));
    if(category==='orders'&&value.conflictingOrderIdentifiers>0)line(d,'Widersprüchliche Order-Kennungen: ',value.conflictingOrderIdentifiers+' Gruppen vorsorglich ausgelassen; keine bestätigten Ausführungen daraus.');
    if(category==='activities'){
     if(value.code!=='READ_OK'&&Number.isInteger(value.activityPagesReceived)&&value.activityPagesReceived>0)line(d,'Gedrosselter Verlauf: ',value.activityPagesReceived+' Seiten vor dem Fehler gelesen, nicht als neuer bestätigter Verlauf übernommen. Nächste Prüfung im regulären Tagesintervall.');
     if(value.code==='READ_OK'&&Number.isInteger(value.activitySourceTotal))line(d,'Historische Abdeckung: ',(value.rows?.length||0)+' von '+value.activitySourceTotal+' gemeldeten Buchungen in diesem sicheren Abruffenster.');
     const limits={SIZE_LIMIT:'Sicheres Speicherlimit erreicht',PAGE_LIMIT:'Teilabruf gespeichert; Fortsetzung im nächsten zulässigen Abgleich',IDENTITY_COUNT_MISMATCH:'Anzahl eindeutiger Originaleinträge weicht vom Anbieter ab',SHORT_PAGE:'Anbieter liefert weniger Einträge als seine Gesamtzahl ausweist'};
     if(value.activityCoverageReason)line(d,'Abrufbegrenzung: ',limits[value.activityCoverageReason]||'nicht bestätigt');
     if(value.conflictingActivityIdentifiers>0)line(d,'Widersprüchliche Transaktionskennungen: ',value.conflictingActivityIdentifiers+' Gruppen vorsorglich ausgelassen.');
     if(!value.complete)line(d,'','Historie unvollständig; keine vollständige Ergebnisrechnung.');
    }
    if(!value.rows?.length)line(d,'','Keine Einträge geliefert.');
    for(const row of (value.rows||[]).slice(0,100)){
     const card=document.createElement('div');card.style.cssText='border-top:1px solid #ddd;padding:8px 0';
     line(card,'',(row.type||'Vorgang')+' · '+(row.name||row.symbol||'ohne Produktzuordnung')+' · '+(row.date||'Datum nicht geliefert'));
     if(category==='orders')line(card,'Anbieterstatus: ',(row.status||'unbekannt')+' · ausgeführte Menge '+(row.quantity??'nicht geliefert'));
     else line(card,'Menge: ',row.quantity??'nicht geliefert');
     line(card,'Ausführungskurs: ',amount(row.price,row.currency));
     if(category==='activities'){line(card,'Geldbewegung: ',amount(row.amount,row.currency));line(card,'Gebühr: ',amount(row.fee,row.currency));}
     if(row.stop!==null&&row.stop!==undefined)line(card,'Gemeldeter Order-Stopp: ',amount(row.stop,row.currency)+' · gilt nur für diese Order und ihren Anbieterstatus');
     d.append(card);
    }
    if(value.rows?.length>100)line(d,'','Anzeige auf die ersten 100 gelieferten Einträge begrenzt.');
   }
   const filtered=account.journal?.tradeCoverage;
   if(filtered){
    const view=details(d,'snapFilteredTrades'+account.accountKey,'Historische Käufe und Verkäufe · Anbieterfilter');
    line(view,'','Gesonderter, höchstens wöchentlicher BUY/SELL-Leseabruf. Keine vollständige Kontohistorie; Überträge, Gebühren, Steuern und sonstige Änderungen fehlen in diesem Filter.');
    if(filtered.code==='READ_OK'){
     line(view,'Gelesene Handelsbuchungen: ',filtered.observed+' von '+filtered.totalMatching+' gemeldeten Käufen/Verkäufen.');
     line(view,'Davon Käufe / Verkäufe: ',filtered.buyCount+' / '+filtered.sellCount);
     line(view,'Belastbare ISIN: ',filtered.validIsinCount+' Buchungen · '+filtered.distinctIsins+' verschiedene ISINs');
     line(view,'Mit den aktuell nachgewiesenen Depot-ISINs übereinstimmend: ',filtered.currentHoldingsIsinMatches+' Buchungen (keine bestätigte Positions- oder Gewinnzuordnung).');
     const unknownIsin=Number.isInteger(filtered.missingOrInvalidIsinCount)?filtered.missingOrInvalidIsinCount:
      Number.isInteger(filtered.observed)&&Number.isInteger(filtered.validIsinCount)&&filtered.observed>=filtered.validIsinCount?filtered.observed-filtered.validIsinCount:null;
     if(unknownIsin!==null)line(view,'Ohne gültigen ISIN-Nachweis: ',unknownIsin+' Buchungen. Keine automatische Namenszuordnung.');
     if(!Array.isArray(filtered.holdingBreakdown))line(view,'ISIN-Einzelübersicht: ','Bei der nächsten regulären wöchentlichen Anbieterprüfung verfügbar. Bisheriger Gesamtstand bleibt erhalten.');
     for(const item of (filtered.holdingBreakdown||[]).slice(0,25)){
      const isin=String(item.isin||'');
      if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))continue;
      const row=line(view,isin+': ',(item.buys||0)+' Käufe · '+(item.sells||0)+' Verkäufe · Buchungstage '+(item.firstDay||'nicht belegt')+' bis '+(item.lastDay||'nicht belegt'));
      const copy=document.createElement('button');copy.type='button';copy.textContent='ISIN kopieren';copy.setAttribute('aria-label',isin+' kopieren');
      copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(isin);copy.textContent='Kopiert';}catch(_){copy.textContent='Kopieren nicht verfügbar';}});
      row.append(document.createTextNode(' '),copy);
     }
     if(filtered.holdingBreakdownTruncated)line(view,'','Die Einzelübersicht ist auf 25 geprüfte ISINs begrenzt. Die Gesamtsumme umfasst alle geprüften aktuellen ISINs.');
     line(view,'','Nur historische Anbieterbuchungen mit derselben ISIN; die genaue Zuordnung zu einer heutigen Position und deren Gewinn bleibt unbestätigt.');
     line(view,'Historischer Zeitraum (Anbieter-Tagesdaten): ',(filtered.earliestTradeDay||'nicht bestätigt')+' bis '+(filtered.latestTradeDay||'nicht bestätigt'));
     line(view,'Filter vollständig: ',filtered.completeFilteredTradeWindow?'Ja, nur für BUY/SELL':'Nein, Filter nur teilweise gelesen');
    }else{
     line(view,'Filterstatus: ','Abruf derzeit nicht bestätigt; zuletzt geprüfter Stand bleibt erhalten.');
    }
    line(view,'Letzter erfolgreicher Filterabruf: ',stamp(filtered.checkedAt));
    line(view,'','Keine Freigabe für FIFO-Gewinne, Handelsaufträge oder Strategielernen.');
   }
  }
  function tradeJournal(parent,account){
   const report=account.tradeJournal;if(!report)return;
   const d=details(parent,'snapExecutions'+account.accountKey,'Automatisch dokumentierte Trades');
   line(d,'Transaktionsquelle: ',stamp(report.sourceAt)+' · '+(report.sourceAvailable?'gelesen':'Abruf nicht verfügbar; letzter gespeicherter Stand'));
   line(d,'','Tägliche Anbieterhistorie, üblicherweise einen Tag verzögert. FIFO ist eine Rechenmethode, kein Steuerbericht. Bestandsänderungen allein erzeugen keine Trades.');
   line(d,'','Dokumentierte Käufe/Verkäufe: '+report.events.length+' · berechnete Verkäufe/Teilverkäufe: '+report.realized.length+' · offene Rechenprüfungen: '+report.unresolved.length);
   if(!report.historyComplete)line(d,'','Historie unvollständig; Ergebnisrechnung bleibt offen.');
   for(const total of report.totals){line(d,'FIFO-Ergebnis der berechenbaren Verkäufe: ',amount(total.grossPnl,total.currency)+' vor Gebühren');line(d,'Nach zugeordneten Gebühren: ',total.netPnl===null?'nicht vollständig berechenbar':amount(total.netPnl,total.currency)+' · vor separaten Gebühren und Steuern');}
   for(const row of report.realized.slice(0,100)){
    const card=document.createElement('section');card.style.cssText='border-top:1px solid #ddd;padding:8px 0';
    line(card,'',row.name+' · Verkauf '+row.quantity+' · '+row.date+' · danach noch '+row.openQuantityAfter+' Stück aus dokumentierten Käufen');
    line(card,'FIFO-Einstand: ',amount(row.cost,row.currency));line(card,'Verkaufserlös vor Gebühren: ',amount(row.proceeds,row.currency));
    const pnl=line(card,'Ergebnis vor Gebühren: ',amount(row.grossPnl,row.currency));pnl.style.fontWeight='700';pnl.style.color=Number(row.grossPnl)<0?'#b42318':'#217a3d';
    line(card,'Zugeordnete Gebühren: ',amount(row.fees,row.currency));line(card,'Nach zugeordneten Gebühren: ',amount(row.netPnl,row.currency));d.append(card);
   }
   const executions=details(d,'snapExecutionRows'+account.accountKey,'Käufe und Verkäufe · Originalbuchungen');
   for(const row of report.events.slice(0,100)){line(executions,'',row.type+' · '+row.name+' · '+row.date+' · Menge '+(row.quantity??'nicht geliefert')+' · Kurs '+amount(row.price,row.currency)+' · Gebühr '+amount(row.fee,row.currency));}
   const issues=details(d,'snapExecutionIssues'+account.accountKey,'Offene Rechenprüfungen');
   for(const row of report.unresolved)line(issues,row.name+': ',row.reason);
   line(d,'Separate Gebühren/Steuern: ',report.separateCharges.length+' Buchungen; nicht automatisch zusätzlich zu Transaktionsgebühren abgezogen.');
   for(const row of report.separateCharges.slice(0,50))line(d,'',row.type+' · '+row.date+' · '+amount(row.amount,row.currency));
   line(d,'Ein-/Auszahlungen: ',report.cashMovements.length+' Buchungen; kein Tradinggewinn.');
   line(d,'','Diese Dokumentation ändert keine aktiven Trades, Simulationen, Strategieregeln oder Handelsfreigaben.');
  }
  function tradeInsights(parent,account){
   const view=account.tradeInsights;
   const d=details(parent,'snapOrderFills'+account.accountKey,'Erkannte Ausführungen · Prüfliste für Bob');
   line(d,'','Nur gemeldete ausgeführte Stückzahlen zählen. Keine automatische Übernahme in Mein Trade, keine echte Order und keine automatische Lernregeländerung.');
   if(!view){line(d,'','Noch keine Auswertung vorhanden.');return;}
   const audit=view.reconciliation;
   if(audit){
    const d2=details(d,'snapReconciliation'+account.accountKey,'Ausführungen und Buchungen abgleichen');
    line(d2,'Eindeutige Anbieter-Prüfkandidaten: ',String(audit.candidatePairs||0));
    line(d2,'Mehrdeutige Gruppen: ',String(audit.ambiguousGroups||0));
    line(d2,'Fehlende Zeit- oder Identitätsnachweise: ',String(audit.missingEvidence||0));
    line(d2,'Ohne passenden Transaktionseintrag: ',String(audit.orderFillsWithoutExactActivity||0));
    line(d2,'','Diese Treffer sind keine unabhängigen Börsenbestätigungen. Die vollständige Gewinnrechnung bleibt gesperrt.');
   }
   line(d,'Orders: ',view.ordersAvailable?'Abruf erfolgreich · '+stamp(view.ordersCheckedAt):'Anbieter-Abruf nicht bestätigt oder vorübergehend nicht verfügbar');
   line(d,'Erkannte Ausführungen: ',String(view.executionsCount));
   line(d,'Für einen späteren historischen Signalvergleich ausreichend zugeordnet: ',String(view.readyForHistoricalComparison));
   for(const item of (view.executions||[]).slice(0,40)){
    const card=document.createElement('div');card.style.cssText='border-top:1px solid #ddd;padding:8px 0';
    line(card,'',(item.name||item.symbol||'Unbekanntes Instrument')+' · '+(item.side||'Aktion unbekannt')+' · '+item.filledQuantity+' Stück');
    line(card,'ISIN: ',item.isin||'Nicht eindeutig nachgewiesen');
    line(card,'Ausgeführt laut Orders: ',stamp(item.executedAt)+' · '+amount(item.executionPrice,item.currency));
    line(card,'Anbieterstatus: ',item.providerStatus||'nicht geliefert');
    line(card,'Auswertung: ',item.reviewReady?'Identität, Zeitpunkt und Kurs vorhanden; Abgleich mit damaligem Bob-Signal noch nicht abgeschlossen.':'Originalzeit, Kurs oder belastbare ISIN-Zuordnung fehlen.');
    d.append(card);
   }
   if(view.executionsCount>40)line(d,'','Nur die ersten 40 Ausführungen angezeigt.');
   const fees=details(d,'snapFees'+account.accountKey,'Gebühren aus gemeldeten Kontotransaktionen');
   line(fees,'','Unveränderte Anbieter-Vorzeichen; keine automatische Zuordnung zu Käufen/Verkäufen. Keine Net-P/L-Aussage.');
   line(fees,'Transaktionsstand: ',stamp(view.activitiesCheckedAt)+' · '+(view.activitiesComplete?'vollständig im abgefragten Fenster':'unvollständig oder nicht bestätigt'));
   for(const v of view.feesByCurrency||[])line(fees,v.currency+': ',v.reportedFeeSum+' ('+v.entries+' Datensätze)');
   if(!view.feesByCurrency?.length)line(fees,'','Keine belastbaren Gebühreneinträge verfügbar.');
  }
  for(const [i,account] of (data.snapshot?.accounts||[]).entries()){
   const box=document.createElement('section'),title=document.createElement('h4'),meta=document.createElement('p');
   title.textContent='DEGIRO-Depot '+(i+1)+' · '+account.positions.length+' gelieferte Positionen';box.append(title);
   line(box,'CSV-Zuordnung: ',account.positions.filter(p=>p.csvEvidence).length+' von '+account.positions.length+' Positionen verknüpft');
   meta.textContent='Bestandsquelle: '+stamp(account.positionsSourceAt)+' · Bargeldquelle: '+stamp(account.cashSourceAt)+' · '+(account.freshnessMode==='realtime'?'Anbieter meldet aktuellen Abruf':'verzögert oder unbekannt');box.append(meta);
   line(box,'Gesamter Depotwert: ',amount(account.netValue?.amount,account.netValue?.currency));
   for(const cash of account.cash){const p=document.createElement('p');p.textContent='Bargeld: '+(cash.amount??'unbekannt')+' '+cash.currency;box.append(p);}
   for(const item of account.positions){
    const card=document.createElement('section');card.style.cssText='border-top:1px solid #ddd;padding:8px 0';
    line(card,'',(item.name||item.symbol||'Unbenannte Position')+' · Menge '+(item.units??'unbekannt')+' · '+(item.isin?(item.isinSource==='user-confirmed'?'ISIN aus bestätigter CSV-Zuordnung: ':['figi-verified','provider-wkn'].includes(item.isinSource)?'ISIN automatisch zugeordnet: ':'ISIN: ')+item.isin:'ISIN nicht nachgewiesen'));
    line(card,'Bewertungskurs vom Anbieter: ',amount(item.valuationPrice,item.currency));
    line(card,'Einstand je Stück: ',amount(item.costBasis,item.currency));
    line(card,item.valuationBasis==='csv-calculated-unit-quotation'?'Positionswert · CSV-Rechenwert: ':'Positionswert: ',amount(item.marketValue,item.currency));
    const pnl=line(card,item.valuationBasis==='csv-calculated-unit-quotation'?'Gewinn/Verlust · CSV-Rechenwert: ':'Offener Gewinn/Verlust: ',item.unrealizedPnl===null||item.unrealizedPnl===undefined?'nicht berechenbar':amount(item.unrealizedPnl,item.currency)+(item.unrealizedPercent!==null?' ('+Number(item.unrealizedPercent).toFixed(2)+' %)':'')+' · vor separaten Gebühren');
    pnl.style.fontWeight='700';if(item.unrealizedPnl!==null&&item.unrealizedPnl!==undefined)pnl.style.color=Number(item.unrealizedPnl)<0?'#b42318':'#217a3d';
    if(item.valuationNote)line(card,'',item.valuationNote);
    if(item.csvEvidence){const c=item.csvEvidence;line(card,'CSV-Exportwert: ',amount(c.value,c.currency)+' · damalige Menge '+c.quantity+' · damaliger Kurs '+amount(c.price,c.currency));line(card,'CSV eingelesen: ',stamp(c.importedAt)+' · Export-/Kurszeit nicht bestätigt');if(c.costBasis!==null&&c.costBasis!==undefined)line(card,'Historischer CSV-Einstand: ',amount(c.costBasis,c.currency));}
    if(item.csvLinkConflict)line(card,'','CSV-Zuordnung widerspricht den Anbieterdaten und wird nicht verwendet.');
    if(item.cashEquivalent)line(card,'','Bereits im Bargeld enthalten; nicht doppelt zum Depotwert addieren.');
    const quote=item.issuerQuote;
    if(quote){line(card,'Produktquelle Geld/Brief: ',amount(quote.bid,quote.currency)+' / '+amount(quote.ask,quote.currency));line(card,'Originalzeiten: ',stamp(quote.bidAt)+' / '+stamp(quote.askAt)+' · '+quote.source);}
    else if(!item.issuerObservation)line(card,'Produktkursüberwachung: ',item.isin?'Noch kein passender aktueller Originalkurs bestätigt.':'Eindeutige ISIN fehlt.');
    const observation=item.issuerObservation;
    if(observation){
     const states={CURRENT:'aktuelles Kurspaar beobachtet',ONE_SIDED:'nur eine Kursseite aktuell',STALE_OR_UNDATED:'keine aktuellen datierten Kurse',ENDED:'Emittent meldet Produktende',SOURCE_UNAVAILABLE:'Quelle momentan nicht lesbar',UNSUPPORTED:'noch kein passender Depot-Kursleser'};
     line(card,'30-Sekunden-Depotbeobachtung: ',states[observation.code]||'noch nicht bestätigt');
     if(observation.source)line(card,'Quelle: ',observation.source+(observation.kind==='issuer-chart'?' · Chartbeobachtung, kein ausführbarer Kurs':' · kein DEGIRO-Ausführungskurs'));
     if(observation.bid!==null&&observation.bid!==undefined)line(card,'Beobachtet Geld: ',amount(observation.bid,observation.currency)+' · '+stamp(observation.bidAt)+(observation.bidFresh?'':' · nicht aktuell bestätigt'));
     if(observation.ask!==null&&observation.ask!==undefined)line(card,'Beobachtet Brief: ',amount(observation.ask,observation.currency)+' · '+stamp(observation.askAt)+(observation.askFresh?'':' · nicht aktuell bestätigt'));
     line(card,'Zuletzt geprüft: ',stamp(observation.observedAt));
     if(item.observedPositionValue!==null&&item.observedPositionValue!==undefined){line(card,'Wert aus beobachtetem Geldkurs · berechnet: ',amount(item.observedPositionValue,item.currency)+' · Menge aus letztem Depotabruf');line(card,'Gewinn/Verlust dazu · berechnet: ',amount(item.observedUnrealizedPnl,item.currency)+' · vor separaten Gebühren');}
    }
    box.append(card);
   }
   if(account.csvAutoReport){const report=account.csvAutoReport;line(box,'Automatischer CSV-Abgleich: ',report.matched+' von '+report.total+' Positionen zugeordnet');for(const item of report.unresolved||[]){const p=account.positions.find(p=>p.positionKey===item.positionKey);line(box,(p?.name||'Position')+': ',item.reason);}}
   if(account.csvImportedAt){const unlink=document.createElement('button');unlink.type='button';unlink.textContent='CSV-Zuordnung für dieses Depot entfernen';unlink.addEventListener('click',async()=>{if(busy)return;busy=true;unlink.disabled=true;controls();try{await call('csv-clear',{accountKey:account.accountKey});csvMessage('CSV-Zuordnung auf dem Server gelöscht. Die lokale CSV bleibt erhalten.');}catch(error){csvMessage(error.message);}finally{busy=false;unlink.disabled=false;controls();}});box.append(unlink);}
   history(box,account);journal(box,account);tradeJournal(box,account);tradeInsights(box,account);qualityPanel(box,account);
   list.append(box);
  }
  const changes=data.snapshot?.changes||[];if(changes.length){const d=details(list,'snapChanges','Beobachtete Bestandsänderungen');line(d,'','Eine Mengenänderung allein belegt keinen Kauf oder Verkauf.');for(const c of changes.slice(-20).reverse())line(d,'',stamp(c.at)+' · '+c.name+' · '+(c.before??'nicht vorhanden')+' → '+(c.after??'nicht vorhanden'));}
  for(const note of data.snapshot?.limitations||[]){const p=document.createElement('p');p.textContent=note;list.append(p);}
 }
 function csvMessage(message){document.getElementById('snapCsvFeedback').textContent=message;}
 function csvManualPrepare(){
  const review=document.getElementById('snapCsvReview');review.replaceChildren();csvReviewData=null;
  let csv;try{csv=window.BobDegiroPortfolio?.load(window.localStorage);}catch(_){}
  if(!csv){csvMessage('Keine Portfolio-CSV auf diesem Gerät gefunden. Unter DEGIRO zuerst den Portfolioexport einlesen.');return;}
  const accounts=lastData?.snapshot?.accounts||[];
  if(lastData?.code!=='READ_OK'||!accounts.length){csvMessage('Zuerst einen erfolgreichen SnapTrade-Depotabruf abwarten.');return;}
  if(csv.records.length>1000){csvMessage('Für die Verknüpfung sind höchstens 1.000 CSV-Positionen zulässig. Die lokale CSV bleibt erhalten.');return;}
  const accountSelect=document.createElement('select');accountSelect.id='snapCsvAccount';accountSelect.style.maxWidth='100%';
  for(const [i,a]of accounts.entries()){const option=document.createElement('option');option.value=a.accountKey;option.textContent='DEGIRO-Depot '+(i+1);accountSelect.append(option);}
  const label=document.createElement('label');label.textContent='CSV gehört zu: ';label.append(accountSelect);review.append(label);
  const rows=document.createElement('div');review.append(rows);
  const saveCsv=document.createElement('button');saveCsv.type='button';saveCsv.id='snapCsvSave';saveCsv.textContent='Zuordnung speichern';review.append(saveCsv);
  function build(){
   rows.replaceChildren();const account=accounts.find(a=>a.accountKey===accountSelect.value),choices=[];
   for(const [i,position]of account.positions.entries()){
    const block=document.createElement('section');block.style.cssText='border-top:1px solid #ddd;padding:10px 0;overflow-wrap:anywhere';
    const title=document.createElement('p');title.textContent='SnapTrade: '+(position.name||position.symbol)+' · '+position.units+' Stück · '+position.currency;block.append(title);
    const exact=position.isin?csv.records.filter(r=>r.isin===position.isin&&r.currency===position.currency):[];
    const select=document.createElement('select');select.id='snapCsvProduct'+i;select.style.cssText='max-width:100%;width:100%';select.setAttribute('aria-label','CSV-Produkt für '+(position.name||position.symbol));
    const empty=document.createElement('option');empty.value='';empty.textContent='Nicht zuordnen';select.append(empty);
    for(const record of csv.records.filter(r=>r.currency===position.currency&&(!position.providerIsin||position.providerIsin===r.isin))){const option=document.createElement('option');option.value=record.isin;option.textContent=record.isin+' · '+record.name+' · CSV-Menge '+record.quantity;select.append(option);}
    block.append(select);
    const confirmation=document.createElement('input');confirmation.type='checkbox';confirmation.id='snapCsvConfirm'+i;
    const confirmLabel=document.createElement('label');confirmLabel.append(confirmation,document.createTextNode(' Ich bestätige: Diese CSV-ISIN gehört zu dieser SnapTrade-Position.'));block.append(confirmLabel);
    if(exact.length===1){select.value=exact[0].isin;confirmation.checked=true;confirmLabel.hidden=true;}
    else{
     const normalize=v=>(v||'').normalize('NFKC').toLowerCase().replace(/\s+/g,' ').trim();
     const name=normalize(position.name);
     const hints=csv.records.filter(r=>{
      if(r.currency!==position.currency)return false;
      const candidate=normalize(r.name),prefix=candidate.replace(/(?:\.{3}|…)$/,'').trim();
      return candidate===name||(prefix.length>=18&&prefix!==candidate&&name.startsWith(prefix));
     });
     if(hints.length===1){select.value=hints[0].isin;const hint=document.createElement('p');hint.textContent='Vorschlag anhand der Bezeichnung. ISIN und Produkt prüfen und mit dem Haken bestätigen.';block.append(hint);}
    }
    select.addEventListener('change',()=>{const same=exact.length===1&&select.value===exact[0].isin;confirmation.checked=same;confirmLabel.hidden=same;});
    if(!position.providerIsin&&!position.stableInstrumentId){select.disabled=true;confirmation.disabled=true;const p=document.createElement('p');p.textContent='Stabile Anbieterkennung fehlt; dauerhafte Zuordnung nicht möglich.';block.append(p);}
    choices.push({position,select,confirmation});rows.append(block);
   }
   csvReviewData={csv,account,choices};
  }
  accountSelect.addEventListener('change',build);build();
  const clearCsv=document.createElement('button');clearCsv.type='button';clearCsv.id='snapCsvUnlink';clearCsv.textContent='CSV-Zuordnung für dieses Depot entfernen';review.append(clearCsv);
  clearCsv.addEventListener('click',async()=>{if(busy)return;busy=true;clearCsv.disabled=true;controls();try{await call('csv-clear',{accountKey:accountSelect.value});csvMessage('CSV-Zuordnung auf dem Server gelöscht. Die lokale CSV bleibt erhalten.');review.replaceChildren();csvReviewData=null;}catch(error){csvMessage(error.message);}finally{busy=false;clearCsv.disabled=false;controls();}});
  csvMessage('Bitte Depot und Produktpaare prüfen. Namen oder gleiche Mengen allein erzeugen keine automatische Zuordnung.');
  saveCsv.addEventListener('click',async()=>{
   if(busy||!csvReviewData)return;
   const {csv,account,choices}=csvReviewData;
   const incomplete=choices.filter(c=>!c.select.disabled&&((c.confirmation.checked&&!c.select.value)||(c.select.value&&!c.confirmation.checked)));
   if(incomplete.length){csvMessage('Noch nicht gespeichert: Bei '+incomplete.length+' Position(en) fehlt die ISIN-Auswahl oder der Bestätigungshaken. Bitte die markierte Auswahl vervollständigen.');const c=incomplete[0];(c.select.value?c.confirmation:c.select).focus();return;}
   const links=choices.filter(c=>c.select.value&&c.confirmation.checked&&!c.select.disabled).map(c=>({positionKey:c.position.positionKey,isin:c.select.value,confirmed:true}));
   if(!links.length){csvMessage('Mindestens eine eindeutige Zuordnung auswählen und bestätigen.');return;}
   if(new Set(links.map(l=>l.isin)).size!==links.length){csvMessage('Noch nicht gespeichert: Eine ISIN wurde mehrfach ausgewählt. Jede Depotposition benötigt ihr eigenes passendes Produkt.');return;}
   const parse=window.BobDegiroReport?.parseNumber;
   if(!parse){csvMessage('CSV-Zahlenleser nicht geladen. Bob neu öffnen.');return;}
   const num=v=>v===null||v===undefined||String(v).trim()===''?null:parse(v);
   const used=new Set(links.map(l=>l.isin));
   const records=csv.records.filter(r=>used.has(r.isin)).map(r=>({isin:r.isin,name:r.name,quantity:String(r.quantity),currency:r.currency,price:num(r.price),value:num(r.value),costBasis:num(r.costBasis)}));
   const payload={accountKey:account.accountKey,importedAt:csv.importedAt,records,links};
   busy=true;saveCsv.disabled=true;controls();csvMessage('Bestätigte Zuordnung wird verschlüsselt gespeichert …');
   try{
    const data=await call('csv-import',payload),stored=data.snapshot?.accounts.find(a=>a.accountKey===account.accountKey);
    const verified=links.every(l=>stored?.positions.some(p=>p.positionKey===l.positionKey&&p.isin===l.isin&&p.csvEvidence?.isin===l.isin));
    if(!verified){csvMessage('Speicherantwort erhalten, aber die gewählten Zuordnungen sind noch nicht vollständig bestätigt. Auswahl bleibt zur Prüfung geöffnet.');return;}
    const count=stored.positions.filter(p=>p.csvEvidence).length;
    csvMessage('✓ CSV-Zuordnung gespeichert: '+count+' von '+stored.positions.length+' Positionen verknüpft. Exportwerte bleiben historisch. Passende Produktkurse werden separat geprüft.');review.replaceChildren();csvReviewData=null;
   }
   catch(error){csvMessage(error.message);}finally{busy=false;saveCsv.disabled=false;controls();}
  });
 }
 async function csvAuto(){
  if(busy)return;
  let csv;try{csv=window.BobDegiroPortfolio?.load(window.localStorage);}catch(_){}
  if(!csv){csvMessage('Keine Portfolio-CSV auf diesem Gerät gefunden. Zuerst den Portfolioexport einlesen.');return;}
  const accounts=lastData?.snapshot?.accounts||[];
  if(lastData?.code!=='READ_OK'||!accounts.length){csvMessage('Erfolgreichen Depotabruf abwarten.');return;}
  const review=document.getElementById('snapCsvReview');review.replaceChildren();csvReviewData=null;
  if(accounts.length===1){await runCsvAuto(csv,accounts[0].accountKey);return;}
  const label=document.createElement('label');label.textContent='Welches Depot gehört zu dieser CSV? ';
  const select=document.createElement('select');select.id='snapCsvAutoAccount';select.style.maxWidth='100%';
  const empty=document.createElement('option');empty.value='';empty.textContent='Depot auswählen';select.append(empty);
  for(const [i,a]of accounts.entries()){const o=document.createElement('option');o.value=a.accountKey;o.textContent='DEGIRO-Depot '+(i+1);select.append(o);}
  label.append(select);review.append(label);
  const go=document.createElement('button');go.type='button';go.textContent='Dieses Depot automatisch abgleichen';go.addEventListener('click',()=>{if(select.value)runCsvAuto(csv,select.value);});review.append(go);
 }
 async function runCsvAuto(csv,accountKey){
  if(busy)return;
  const parse=window.BobDegiroReport?.parseNumber;
  if(!parse||csv.records.length>1000){csvMessage('CSV-Zahlenleser nicht verfügbar oder mehr als 1.000 Positionen.');return;}
  const num=v=>v===null||v===undefined||String(v).trim()===''?null:parse(v);
  const records=csv.records.map(r=>({isin:r.isin,name:r.name,quantity:String(r.quantity),currency:r.currency,price:num(r.price),value:num(r.value),costBasis:num(r.costBasis)}));
  const button=document.getElementById('snapCsvPrepare');busy=true;button.disabled=true;controls();csvMessage('Bob prüft die Wertpapierkennungen und speichert eindeutige Zuordnungen …');
  try{
   const data=await call('csv-auto',{accountKey,importedAt:csv.importedAt,records,links:[]});
   const report=data.snapshot?.accounts.find(a=>a.accountKey===accountKey)?.csvAutoReport;
   if(report)csvMessage('Automatisch zugeordnet: '+report.matched+' von '+report.total+'. '+(report.matched===report.total?'Keine ISIN-Einzelbestätigung nötig.':'Offene Positionen werden mit Begründung angezeigt und bei weiteren Depotabrufen erneut geprüft.'));
   else csvMessage('Automatischer Prüfstatus nicht bestätigt.');
   document.getElementById('snapCsvReview').replaceChildren();
  }catch(error){csvMessage(error.message);}finally{busy=false;button.disabled=false;controls();}
 }
 document.getElementById('snapCsvPrepare').addEventListener('click',csvAuto);
 document.getElementById('snapCsvManual').addEventListener('click',csvManualPrepare);
 async function call(action,payload){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),action==='csv-auto'?45000:20000);
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
 catalogButton.addEventListener('click',async()=>{
  if(busy)return;busy=true;controls();catalogStatus.textContent='Einmalige SnapTrade-Verzeichnisabfrage wird geprüft …';
  try{await call('catalog-probe',{});}
  catch(error){catalogStatus.textContent='Verzeichnisabfrage nicht bestätigt: '+error.message;}
  finally{busy=false;controls();}
 });
 document.getElementById('snapForm').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!free.checked)return;busy=true;save.disabled=true;controls();feedback('Schlüssel werden verschlüsselt gespeichert …');
  const payload={clientId:client.value.trim(),consumerKey:key.value.trim(),personalFreeConfirmed:true};client.value='';key.value='';
  try{const data=await call('configure',payload);feedback(data.configured?'✓ Schlüssel gespeichert. Die Eingabefelder wurden geleert. '+(messages[data.code]||'Lesetest wird gestartet.'):'Speichern nicht bestätigt.');}catch(error){feedback(error.message);status.textContent=error.message;}finally{payload.clientId='';payload.consumerKey='';busy=false;save.disabled=false;controls();}
 });
 for(const [button,action] of [[check,'check'],[remove,'disconnect']])button.addEventListener('click',async()=>{if(busy)return;if(action==='check')lastVisibleReadRequestAt=Date.now();busy=true;controls();try{const data=await call(action);feedback(messages[data.code]||'Status aktualisiert.');}catch(error){feedback(error.message);}finally{busy=false;controls();await refresh();}});
 // When the user actually views DEGIRO, keep the existing 10-minute reader
 // interactive. Never trigger this from a hidden page or another Bob view.
 // This POST only wakes the already rate-limited GET-only server worker.
 async function visibleReadHeartbeat(){
  if(busy||document.hidden||!lastData?.configured||!panel.getClientRects().length||window.getComputedStyle(panel).visibility==='hidden')return;
  const now=Date.now();if(now-lastVisibleReadRequestAt<60000)return;
  lastVisibleReadRequestAt=now;busy=true;controls();
  try{await call('check');}catch(_){/* The regular status check reports failures without secrets. */}
  finally{busy=false;controls();}
 }
 refresh();setInterval(()=>{if(!document.hidden){refresh();void visibleReadHeartbeat();}},10000);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
</script>
'''
