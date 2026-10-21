"""Personal setup in the existing DEGIRO tab; no broker credentials collected."""
PANEL = r'''
<section id="bobSnapTrade" class="card" style="padding:16px;overflow-wrap:anywhere">
<h3>DEGIRO über SnapTrade Personal</h3>
<p>Kostenloser Personal-Zugang für dein eigenes Depot. Bob liest Bestände und Bargeld höchstens alle zehn Minuten, auch wenn diese Ansicht geschlossen ist. Depotwerte alle zehn Minuten. Eindeutig zugeordnete Produktkurse prüft Bob zusätzlich etwa alle 30 Sekunden über seine bestehenden Emittentenquellen; dies sind keine DEGIRO-Ausführungskurse.</p>
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
 let busy=false,lastData=null,lastHoldings=null,csvReviewData=null;
 function feedback(message){const inline=document.getElementById('snapFormStatus'),outside=document.getElementById('snapFeedback');inline.textContent=message;outside.textContent=message;(document.getElementById('snapSetup').open?inline:outside).scrollIntoView({block:'nearest'});}
 function controls(){check.disabled=busy||!lastData?.configured||lastData.nextCheckSeconds>0;remove.disabled=busy||!lastData?.configured;}
 const messages={INVALID_CSV_LINK:'CSV-Zuordnung nicht gespeichert: Depot, Währung, stabile Anbieterkennung und Bestätigungen prüfen.',CSV_CONNECTION_REQUIRED:'Für die CSV-Zuordnung zuerst einen erfolgreichen Depotabruf abwarten.',CSV_RETRY_REQUIRED:'Depotabruf läuft oder wurde erneuert. CSV-Vergleich erneut öffnen.',HISTORY_STORE_UNAVAILABLE:'Verschlüsselte CSV-Speicherung nicht bestätigt.',SETUP_REQUIRED:'Noch nicht verbunden. Einmalige Einrichtung oben durchführen.',READY:'Schlüssel gespeichert. Lesetest wird gestartet.',CHECKING:'Depot-Lesetest läuft …',READ_OK:'✓ Depotdaten empfangen. Goldprodukt-Abdeckung noch nicht bestätigt.',CONNECT_DEGIRO:'Personal-Zugang erreichbar. DEGIRO im SnapTrade-Dashboard verbinden.',READ_CONNECTION_REQUIRED:'DEGIRO-Verbindung bei SnapTrade muss auf Lesen stehen.',AUTH_REQUIRED:'Anmeldung nicht bestätigt oder Verbindung abgelaufen. Im SnapTrade-Dashboard prüfen.',ACCESS_DENIED:'Anbieter verweigert den Zugriff. Personal-Zugang und Berechtigungen prüfen.',PLAN_REQUIRED:'Anbieter verlangt einen anderen Tarif. Kein kostenpflichtiger Abruf wird ausgelöst.',RATE_LIMITED:'Anbieter begrenzt die Abrufe. Nächster Versuch frühestens nach zehn Minuten.',PROVIDER_UNAVAILABLE:'Anbieter momentan nicht erreichbar. Letzter Stand ist nicht als aktuell bestätigt.',INVALID_RESPONSE:'Datenformat nicht vollständig erkannt. Kein vollständiger Abgleich bestätigt.',STORE_UNAVAILABLE:'Geschützter Schlüsselspeicher momentan nicht erreichbar.',SETTINGS_UNREADABLE:'Gespeicherter Schlüssel kann nicht gelesen werden. Personal-Schlüssel erneut speichern.',NO_ACCOUNTS:'Noch kein lesbares DEGIRO-Depot gefunden.',TOO_MANY_ACCOUNTS:'Mehr als drei DEGIRO-Depots/Verbindungen. Abgleich zur Prüfung angehalten.'};
 function stamp(value){const d=new Date(value);return value&&Number.isFinite(d.getTime())?d.toLocaleString('de-CH'):'nicht geliefert';}
 function render(data){
  lastData=data;
  status.textContent=messages[data.code]||'Verbindung nicht bestätigt.';
  controls();
  document.getElementById('snapSetup').open=!data.configured;
  clock.textContent=(data.checkedAt?'Letzte Prüfung: '+stamp(data.checkedAt)+'. ':'')+(data.configured?'Nächster möglicher Abruf in '+data.nextCheckSeconds+' Sekunden. ':'')+(data.snapshot?(data.fresh?'Quellenstand innerhalb des Depotintervalls.':'Quellenstand nicht als aktuell bestätigt. '):'');
  const fingerprint=JSON.stringify([data.snapshot,data.fresh]);
  if(fingerprint===lastHoldings)return;lastHoldings=fingerprint;
  const opened=new Set(Array.from(list.querySelectorAll('details[open]')).map(e=>e.id));
  list.replaceChildren();
  function line(parent,label,value){const p=document.createElement('p');p.textContent=label+value;parent.append(p);return p;}
  function amount(value,currency){return value===null||value===undefined?'nicht geliefert':Number(value).toLocaleString('de-CH',{maximumFractionDigits:4})+' '+(currency||'');}
  function details(parent,id,title){const d=document.createElement('details'),s=document.createElement('summary');d.id=id;d.open=opened.has(id);s.textContent=title;d.append(s);parent.append(d);return d;}
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
   for(const [category,title] of [['orders','Orders'],['activities','Transaktionen']]){
    const value=account.journal?.[category];
    line(d,title+': ',!value?'noch nicht gelesen':(value.code==='READ_OK'?'gelesen':'Abruf nicht verfügbar; vorheriger Stand')+' · letzter erfolgreicher Abruf '+stamp(value.checkedAt));
    if(!value)continue;
    if(category==='activities'&&!value.complete)line(d,'','Historie unvollständig; keine vollständige Ergebnisrechnung.');
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
  }
  for(const [i,account] of (data.snapshot?.accounts||[]).entries()){
   const box=document.createElement('section'),title=document.createElement('h4'),meta=document.createElement('p');
   title.textContent='DEGIRO-Depot '+(i+1)+' · '+account.positions.length+' gelieferte Positionen';box.append(title);
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
    else line(card,'Produktkursüberwachung: ',item.isin?'Noch kein passender aktueller Originalkurs bestätigt.':'Eindeutige ISIN fehlt.');
    box.append(card);
   }
   if(account.csvAutoReport){const report=account.csvAutoReport;line(box,'Automatischer CSV-Abgleich: ',report.matched+' von '+report.total+' Positionen zugeordnet');for(const item of report.unresolved||[]){const p=account.positions.find(p=>p.positionKey===item.positionKey);line(box,(p?.name||'Position')+': ',item.reason);}}
   if(account.csvImportedAt){const unlink=document.createElement('button');unlink.type='button';unlink.textContent='CSV-Zuordnung für dieses Depot entfernen';unlink.addEventListener('click',async()=>{if(busy)return;busy=true;unlink.disabled=true;controls();try{await call('csv-clear',{accountKey:account.accountKey});csvMessage('CSV-Zuordnung auf dem Server gelöscht. Die lokale CSV bleibt erhalten.');}catch(error){csvMessage(error.message);}finally{busy=false;unlink.disabled=false;controls();}});box.append(unlink);}
   history(box,account);journal(box,account);
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
    else{const hints=csv.records.filter(r=>r.currency===position.currency&&r.name.trim().toLowerCase()===(position.name||'').trim().toLowerCase());if(hints.length===1)select.value=hints[0].isin;}
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
   const links=choices.filter(c=>c.select.value&&c.confirmation.checked&&!c.select.disabled).map(c=>({positionKey:c.position.positionKey,isin:c.select.value,confirmed:true}));
   if(!links.length){csvMessage('Mindestens eine eindeutige Zuordnung auswählen und bestätigen.');return;}
   const parse=window.BobDegiroReport?.parseNumber;
   if(!parse){csvMessage('CSV-Zahlenleser nicht geladen. Bob neu öffnen.');return;}
   const num=v=>v===null||v===undefined||String(v).trim()===''?null:parse(v);
   const used=new Set(links.map(l=>l.isin));
   const records=csv.records.filter(r=>used.has(r.isin)).map(r=>({isin:r.isin,name:r.name,quantity:String(r.quantity),currency:r.currency,price:num(r.price),value:num(r.value),costBasis:num(r.costBasis)}));
   const payload={accountKey:account.accountKey,importedAt:csv.importedAt,records,links};
   busy=true;saveCsv.disabled=true;controls();csvMessage('Bestätigte Zuordnung wird verschlüsselt gespeichert …');
   try{await call('csv-import',payload);csvMessage('✓ CSV-Zuordnung gespeichert. Exportwerte bleiben historisch. Passende Produktkurse werden separat geprüft.');review.replaceChildren();csvReviewData=null;}
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
