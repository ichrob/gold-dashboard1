/* Bob Zukunft: read-only research/test cockpit. No broker, trade or secret endpoint. */
(function(root){
'use strict';
const FIELDS=[
 {id:'data',name:'Datenqualität und Zeitstempel',phase:'Grundlage',state:'teilweise vorhanden',
  trial:'Gold-Spot, Gold-Future und Produktquote getrennt prüfen; 5m/15m/30m/1h, Kerzenschluss, Zeitstempel und Lücken archivieren.',
  gate:'Keine rückwirkend erfundenen Kurse; Eingang, Analyse und Beobachtung referenzieren dieselbe belegte Datenzeit.'},
 {id:'regime',name:'Marktphasen und Trendfolge',phase:'Strategie',state:'geplant',
  trial:'Aufwärts-, Abwärts-, Seitwärts- und Hochvolatilitätsphasen klassifizieren; EMA, DMI/ADX, ATR und Struktur als Kombination gegen aktuelle Bob-Regeln testen.',
  gate:'Auf unabhängigen Perioden nach Kosten besser als Basismodell und keine unvertretbar höhere Verlustserie.'},
 {id:'entryexit',name:'Einstieg, Halten, Ausstieg und Wiedereinstieg',phase:'Strategie',state:'teilweise vorhanden',
  trial:'Signalwechsel-Hysterese, bestätigte Trendwende, Breakout/Pullback, Trailing-Stop und verlängerte Ziele gegeneinander testen; bestehende Trendfolge 800 € als Kontrollmodell verwenden.',
  gate:'Alle simulierten Entscheidungen und Stops nachvollziehbar; Gewinne/Verluste nach Produktkurs statt allein nach Goldpreis.'},
 {id:'cost',name:'Hebel, KO und Nettokosten',phase:'Strategie',state:'unvollständig',
  trial:'Brief beim Einstieg, Geld beim Ausstieg, Spread, Gebühren, Finanzierung, Slippage, Währung und KO-/Gap-Risiko je simuliertem Trade prüfen.',
  gate:'Vollständige belegte Netto-Ergebnisse; kein Hebelvorteil ohne Verlust- und KO-Prüfung. Spread bleibt ausserhalb der Produkterangliste.'},
 {id:'learning',name:'Experimentelle ML-Filter und externe Analysen',phase:'Strategie',state:'Forschung',
  trial:'Nur als optionales Shadow-Modell untersuchen, ob ML oder belegte MCO-Kontexte schlechte Signale aussortieren; keine Kurse oder Fibonacci-Level erfinden.',
  gate:'Unabhängiger Nettovorteil gegenüber Bobs festen Regeln, vollständige Belege, keine direkten MCO-Auslösungssignale.'},
 {id:'backtest',name:'Walk-forward und unbekannte Testdaten',phase:'Beweise',state:'geplant',
  trial:'Zeitlich getrennte Train-/Validierungs-/Testfenster, rollierende Walk-forward-Auswertung, verschiedene Volatilitätsregime und Konfidenzintervalle einsetzen.',
  gate:'Kein zufälliges Durchmischen der Zeitreihe; Version vor unabhängigen Tests festschreiben und Ergebnisse archivieren.'},
 {id:'paper',name:'Vier langfristige Paper-Konten',phase:'Beweise',state:'laufende Grundlage',
  trial:'100 € konservativ, ausgewogen und offensiv sowie 800 € Trendfolge getrennt über Handelstage beobachten; alle offenen/nicht bewertbaren Fälle zählen.',
  gate:'30 Handelstage und 100 auswertbare abgeschlossene Trades sind nur erste Prüfschwellen. Mehrere Marktphasen und unabhängige Nettotests bleiben nötig.'},
 {id:'robustness',name:'Extremsituationen und Not-Aus',phase:'Sicherheit',state:'Testprotokoll vorhanden',
  trial:'Veraltete/missing Quotes, Doppelorders, Kurslücken, KO-Ereignisse, Tageslimit, Instanzwechsel, Broker-Ausfall und unbekannte Orderbestätigung injizieren.',
  gate:'Jeder kritische Fehler blockiert neue Orders; echte Notabschaltung unabhängig von Anzeige und Strategie testen.'},
 {id:'broker',name:'Broker und offizielle Schnittstellen',phase:'Anbindung',state:'offen',
  trial:'Broker-API-Dokumentation, Verfügbarkeit für Schweizer Kunden, Goldprodukt, Paper-Konto, Echtzeitrechte, Kosten, Authentifizierung und Orderstatus vergleichen.',
  gate:'Nur erlaubte offizielle API und Demo-/Paper-Modus; keine DEGIRO-Umgehung und keine zusätzlichen bezahlten Verträge.'},
 {id:'execution',name:'Broker-Paper-Ausführung und Positionsabgleich',phase:'Anbindung',state:'nicht verbunden',
  trial:'In einer späteren offiziellen Demo-API Idempotenz, Order-ID, Teilausführung, Storno, Gebühren und Wiederanlauf nach Serverabbruch testen.',
  gate:'Broker-Rückmeldung ist massgeblich; lokale Empfehlung nie als tatsächliche Ausführung deklarieren.'},
 {id:'live',name:'Echtgeld-Freigabe',phase:'Freigabe',state:'gesperrt',
  trial:'Erst nach Strategie-, Daten-, Kosten-, Sicherheits- und API-Prüfung gesonderte menschliche Entscheidung und harte Handelslimits definieren.',
  gate:'Keine automatische Freigabe aus der Zukunft-Sparte; ausdrückliche Zustimmung für spätere echte Orders.'}
];
const CORE_SOURCES=[
 ['Trendfolge · Moskowitz, Ooi & Pedersen','https://doi.org/10.1016/j.jfineco.2011.11.003'],
 ['Volatilitätssteuerung · Moreira & Muir','https://doi.org/10.1111/jofi.12513'],
 ['Handelskosten · Almgren & Chriss','https://doi.org/10.3905/jpm.2001.319783'],
 ['Backtest-Überanpassung · Bailey u. a.','https://escholarship.org/uc/item/4w1110bb']
];
function preflight(t){
 const reasons=[];
 if(t.marketOpen!==true)reasons.push('Marktstatus nicht freigegeben');
 if(t.sourceConfirmed!==true)reasons.push('Datenquelle nicht bestätigt');
 if(!Number.isFinite(t.quoteAgeSeconds)||t.quoteAgeSeconds<0||t.quoteAgeSeconds>90)reasons.push('Produktkurs fehlt oder ist älter als 90 Sekunden');
 if(!Number.isFinite(t.stopDistance)||t.stopDistance<=0)reasons.push('Stop-Abstand fehlt');
 if(!Number.isFinite(t.koDistance)||t.koDistance<=0||t.koDistance<=t.stopDistance)reasons.push('KO-Schwelle vor/auf dem Stop');
 if(!Number.isFinite(t.expectedNetR)||t.expectedNetR<=0)reasons.push('Erwarteter Nettovorteil nicht positiv');
 if(!Number.isFinite(t.remainingDailyLoss)||t.remainingDailyLoss<=0)reasons.push('Tagesverlustgrenze erreicht');
 if(t.duplicateOrder===true)reasons.push('Doppelorder erkannt');
 if(t.brokerAckKnown!==true)reasons.push('Brokerstatus nicht bestätigt');
 if(t.emergencyStop===true)reasons.push('Not-Aus aktiv');
 return {allowed:reasons.length===0,reasons};
}
function stressCases(){
 const safe={marketOpen:true,sourceConfirmed:true,quoteAgeSeconds:12,stopDistance:20,koDistance:100,
   expectedNetR:1.2,remainingDailyLoss:1,duplicateOrder:false,brokerAckKnown:true,emergencyStop:false};
 const cases=[
  ['Kontrollfall',{},true],
  ['Veralteter Produktkurs',{quoteAgeSeconds:180},false],
  ['Kurslücke / KO zu nah',{koDistance:8},false],
  ['Doppelorder',{duplicateOrder:true},false],
  ['Tagesverlustgrenze',{remainingDailyLoss:0},false],
  ['Server-Neustart: Brokerstatus unklar',{brokerAckKnown:false},false],
  ['Not-Aus',{emergencyStop:true},false],
  ['Kein bestätigter Marktpreis',{sourceConfirmed:false},false],
  ['Kein Nettovorteil',{expectedNetR:-.3},false]
 ];
 return cases.map(([name,overrides,expected])=>{
  const result=preflight(Object.assign({},safe,overrides));
  return {name,passed:result.allowed===expected,allowed:result.allowed,reason:result.reasons.join('; ')||'Keine Sperre (nur theoretischer Test)'};
 });
}
function snapshot(raw){
 if(!raw||!['four-independent-paper-accounts','five-independent-paper-accounts','seven-independent-paper-accounts'].includes(raw.mode)||raw.realOrders!==false||
    !Array.isArray(raw.accounts)||raw.accounts.length!==(raw.mode==='seven-independent-paper-accounts'?7:raw.mode==='five-independent-paper-accounts'?5:4))throw Error('Papierkonto-Daten nicht bestätigt');
 const names=new Set(),items=[];
 for(const a of raw.accounts){
  if(!(raw.mode==='seven-independent-paper-accounts'?['conservative','balanced','offensive','trend800','early100','early1000oct','normal1000oct']:raw.mode==='five-independent-paper-accounts'?['conservative','balanced','offensive','trend800','early100']:['conservative','balanced','offensive','trend800']).includes(a.profile)||names.has(a.profile))
   throw Error('Doppelte oder unbekannte Kontenkennung');names.add(a.profile);
  const ctl=a.control||{},p=a.performance||{},day=a.stats||{};
  const daily=Array.isArray(a.daily)?a.daily:[];
  const observedDays=new Set(daily.filter(x=>x&&/^\d{4}-\d{2}-\d{2}$/.test(x.day)&&Number.isFinite(Number(x.lastCheckedAt))&&Number(x.lastCheckedAt)>0).map(x=>x.day)).size;
  const safe=n=>typeof n==='number'&&Number.isFinite(n)?n:null;
  items.push({
   id:a.profile, initial:safe(ctl.initialCapital),equity:safe(ctl.equity),
   priced:safe(p.pricedTrades),positive:safe(p.positivePricedTrades),
   closedTotal:safe(p.closedTrades),observationDays:observedDays,
   drawdown:safe(p.observedMaxDrawdownPct),missing:safe(p.quoteMissingChecks),
   closedToday:safe(day.closed),openUnits:safe(ctl.openUnits),
   checkedAt:(typeof ctl.checkedAt==='string'||safe(ctl.checkedAt)!==null)?ctl.checkedAt:null,
   quoteStatus:typeof p.quoteStatus==='string'?p.quoteStatus:'unbekannt',
   state:typeof ctl.status==='string'?ctl.status:'nicht bestätigt'
  });
 }
 return items;
}
function mount(parent){
 if(typeof document==='undefined'||!parent||parent.querySelector('#bobFutureLab'))return null;
 const el=(tag,txt)=>{const e=document.createElement(tag);if(txt!=null)e.textContent=txt;return e;};
 const shell=el('section');shell.id='bobFutureLab';shell.className='card';shell.style.cssText='margin-top:12px;padding:14px;border:1px solid #b6c5d5';
 const head=el('h3','Zukunft · Entwicklungs- und Testzentrale');
 const preface=el('p','Entwicklungsfahrplan mit Prüfkriterien. Die vorhandenen fünf Paper-Konten können hier ausgelesen werden. Alle Sicherheits-Probeläufe verwenden ausdrücklich erfundene Beispiele; es gibt hier keine Broker- oder Echtgeldfunktion.');
 preface.className='small';
 const banner=el('p','Modus: Planung und Paper-Test. Echtgeld gesperrt; keine neue Broker-Anbindung.');
 banner.style.cssText='padding:10px;border-radius:10px;background:#eef4ff;color:#194476;font-weight:700';
 shell.append(head,preface,banner);
 const paper=el('section');paper.style.cssText='border-top:1px solid #dbe3ee;margin-top:14px;padding-top:12px';
 const paperTitle=el('h4','Langzeittest: vorhandene fünf Paper-Konten');
 const paperText=el('p','Die Zahlen stammen ausschliesslich aus Bobs bestehendem Paper-Test, nicht aus einem neuen Strategie-Backtest. Ergebnisse sind bisher brutto; vollständige Gebühren, Finanzierung und Slippage sind nicht belegt.');
 paperText.className='small';
 const paperBtn=el('button','Aktuelle Paper-Konten prüfen');paperBtn.type='button';paperBtn.className='bob-primary';
 const paperStatus=el('p','Noch nicht in dieser Ansicht abgerufen. Start/Stand und Handelstage nicht abschliessend überprüft.');
 paperStatus.className='small';paperStatus.setAttribute('role','status');
 const paperCards=el('div');paperCards.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px';
 const paperSummary=el('p','Eine erste Prüfschwelle von 30 Handelstagen und 100 auswertbaren abgeschlossenen Trades ersetzt keine unabhängigen Tests. Protokollierte Tage sind nicht automatisch bestätigte Handelstage; nur bepreiste abgeschlossene Trades gelten als auswertbar. Solche Langzeitnachweise werden hier nicht automatisch als bestanden ausgegeben.');
 paperSummary.className='small';
 paper.append(paperTitle,paperText,paperBtn,paperStatus,paperCards,paperSummary);shell.append(paper);
 // Observed-only strategy laboratory. No order action and no client-invented prices.
 const obsPanel=el('section');obsPanel.style.cssText='border-top:1px solid #dbe3ee;margin-top:14px;padding-top:12px';
 obsPanel.append(el('h4','Schritt 2 und 3 · Beobachtete Strategien und Walk-forward'));
 const obsHelp=el('p','Ab Montag sammeln wir je bestätigtem Gold-Spot-Produkt maximal eine belegte Momentaufnahme pro fünf Minuten. Erst wenn einheitliche ISIN, Euro-Geld-/Briefkurse, Quellenzeiten, bestätigte KO-Distanz und ausreichend Daten vorhanden sind, vergleichen wir die Strategien auf zeitlich späteren Testperioden. Kosten sind Modellannahmen, keine belegten Brokerabrechnungen.');
 obsHelp.className='small';obsPanel.append(obsHelp);
 const obsButton=el('button','Forschungsdaten und Walk-forward prüfen');obsButton.type='button';obsButton.className='bob-primary';
 const obsStatus=el('p','Forschungsstand noch nicht abgerufen. Keine automatische Strategiefreigabe.');
 obsStatus.className='small';obsStatus.setAttribute('role','status');
 const obsResults=el('div');obsPanel.append(obsButton,obsStatus,obsResults);shell.append(obsPanel);
 let obsBusy=false;
 obsButton.addEventListener('click',async()=>{
  if(obsBusy)return;obsBusy=true;obsButton.disabled=true;obsStatus.textContent='Beobachtete Daten werden geprüft …';
  try {
   const control=typeof AbortController==='function'?new AbortController():null;
   const timer=setTimeout(()=>control?.abort(),15000);
   let response;
   try {response=await fetch('/api/audit/read',{method:'POST',credentials:'same-origin',
     headers:{'Content-Type':'application/json'},cache:'no-store',
     body:JSON.stringify({mode:'zukunft-research'}),...(control?{signal:control.signal}:{})});}
   finally {clearTimeout(timer);}
   if(!response.ok)throw Error('HTTP '+response.status);
   const x=await response.json();
   if(x.mode!=='zukunft-observed-research'||x.realOrders!==false||x.brokerConnected!==false)
     throw Error('Sicherer Forschungsstatus konnte nicht bestätigt werden');
   obsResults.replaceChildren();
   const details=[
    'Datenstatus: '+String(x.status||'unbekannt'),
    'Aktuelle ISIN: '+String(x.chosenIsin||'keine'),
    'Beobachtete 5-Minuten-Quellen: '+String(x.samples??0),
    'Davon mit bestätigter KO-Basis: '+String(x.verifiedSamples??0),
    'Unvollständige Nachweise: '+String(x.incompleteSamples??0),
    'Unabhängige Testperioden: '+String(x.totalFolds??0),
    'Begründung: '+String(x.reason||'Weiterhin Daten sammeln')
   ];
   for(const v of details){const p=el('p',v);p.className='small';obsResults.append(p);}
   if(Array.isArray(x.instruments)){
    const d=el('details');const heading=el('summary','Beobachtete Produkte ('+x.instruments.length+')');d.append(heading);
    for(const i of x.instruments){const p=el('p',String(i.isin)+' · '+String(i.observations)+' Messpunkte · '+String(i.verifiedKoSamples)+' gültige KO-Referenzen');p.className='small';d.append(p);}
    obsResults.append(d);
   }
   if(x.status==='research_only'&&x.strategies&&typeof x.strategies==='object'){
    const names={baseline:'Bob-Basis',strict_trend:'Bestätigter Trend',breakout:'Ausbruch',pullback:'Rücksetzer',ml_shadow:'ML-Schattenmodell'};
    for(const [key,value] of Object.entries(x.strategies)){
     if(!Object.prototype.hasOwnProperty.call(names,key))continue;
     const p=el('p',names[key]+': '+String(value.folds??0)+' auswertbare Perioden · '+String(value.trades??0)+' abgeschlossene Replays · '+String(value.net_eur??0)+' € modelliertes Ergebnis'+(value.qualifying?' · Forschungsschwelle erreicht':' · keine ausreichende Evidenz'));
     p.className='small';obsResults.append(p);
    }
   }
   obsStatus.textContent='Nur Forschungsdaten · keine echten Orders und keine automatische Regelübernahme.';
  }catch(e){obsStatus.textContent='Forschungsdaten nicht verfügbar: '+String(e.message||e)+'. Keine Ergebnisse erfunden.';}
  finally{obsBusy=false;obsButton.disabled=false;}
 });
 const displayName={conservative:'Konservativ · 100 €',balanced:'Ausgewogen · 100 €',offensive:'Offensiv · 100 €',trend800:'Bob-Stopp & Wiedereinstieg · 800 €',early100:'Frühimpuls · 100 €'};
 let busy=false;
 paperBtn.addEventListener('click',async()=>{
  if(busy)return;busy=true;paperBtn.disabled=true;paperStatus.textContent='Vorhandene Paper-Daten werden gelesen …';
  try{
   const day=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich'}).format(new Date());
   const controller=typeof AbortController==='function'?new AbortController():null;
   const timer=setTimeout(()=>controller?.abort(),15000);
   let response;try{response=await fetch('/api/audit/read',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/json'},cache:'no-store',
      body:JSON.stringify({mode:'simulation-profiles',day}),...(controller?{signal:controller.signal}:{})});}
   finally{clearTimeout(timer);}
   if(!response.ok)throw Error('Abruf HTTP '+response.status);
   const rows=snapshot(await response.json());
   paperCards.replaceChildren();
   const format=n=>Number.isFinite(n)?new Intl.NumberFormat('de-CH',{maximumFractionDigits:2}).format(n):'nicht bestätigt';
   for(const a of rows){
    const box=el('div');box.style.cssText='background:#f5f7fa;border:1px solid #d5dfe9;padding:10px;border-radius:10px;min-width:0';
    const h=el('strong',displayName[a.id]);box.append(h);
    const metrics=[
     'Kapital brutto: '+(a.equity===null?'offen':format(a.equity)+' €'),
     'Abgeschlossene Fälle seit Start: '+format(a.closedTotal),
     'Davon bepreiste Trades: '+format(a.priced),
     'Tage mit protokollierter Prüfung: '+format(a.observationDays),
     'Davon positiv: '+format(a.positive),
     'Grösster beobachteter Rückgang: '+(a.drawdown===null?'offen':format(a.drawdown)+' %'),
     'Kursprüfungen ohne gültige Quote: '+format(a.missing),
     'Abgeschlossene Fälle heute: '+format(a.closedToday),
     'Kursstatus: '+a.quoteStatus,
     'Letzte Prüfung: '+(a.checkedAt?new Date(a.checkedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'nicht protokolliert')
    ];
    for(const str of metrics){const p=el('p',str);p.style.cssText='font-size:12px;margin:6px 0;color:#344155;overflow-wrap:anywhere';box.append(p);}
    paperCards.append(box);
   }
   paperStatus.textContent='Vorhandene Paper-Konten abgerufen · Stand: '+new Date().toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' · nur beobachtete Ergebnisse; kein Nettogewinn-Nachweis.';
  }catch(e){paperStatus.textContent='Paper-Daten konnten nicht bestätigt werden ('+String(e.message||'unbekannt')+'). Keine geschätzten Resultate angezeigt.';}
  finally{busy=false;paperBtn.disabled=false;}
 });
 const research=el('section');research.style.cssText='border-top:1px solid #dbe3ee;margin-top:14px;padding-top:12px';
 research.append(el('h4','Automatischer Strategievergleich · Walk-forward'));
 const expl=el('p','Bob vergleicht Basismodell, verschiedene Trendfolge- und Ausbruchparameter, Gegenbewegung und ein trainiertes lineares Lernmodell. Jede Runde trennt Training, Auswahl und spätere Testdaten. Die Kurse sind Referenz-Kerzen und keine ausführbaren DEGIRO-Geld-/Briefkurse.');
 expl.className='small';research.append(expl);
 const runBtn=el('button','Gespeicherten Vergleich neu anzeigen');runBtn.type='button';runBtn.className='bob-primary';
 const rStatus=el('p','Bob prüft morgens und ab 20:00 Uhr an Handelstagen (Zürich) und kontrolliert am Wochenende das Forschungsarchiv. Kein Knopfdruck notwendig.');
 rStatus.className='small';rStatus.setAttribute('role','status');
 const reportBox=el('div');research.append(runBtn,rStatus,reportBox);shell.append(research);
 let researchBusy=false,researchLoaded=false;
 async function loadResearch(){
  if(researchBusy)return;
  researchBusy=true;runBtn.disabled=true;rStatus.textContent='Gespeicherte automatische Auswertung wird gelesen …';
  try{
   const controller=typeof AbortController==='function'?new AbortController():null;
   const timeout=setTimeout(()=>controller?.abort(),20000);
   let res;try{res=await fetch('/api/zukunft/research',{credentials:'same-origin',cache:'no-store',...(controller?{signal:controller.signal}:{})});}
   finally{clearTimeout(timeout);}
   if(!res.ok)throw Error('Abruf HTTP '+res.status);
   const info=await res.json();
   reportBox.replaceChildren();
   if(info.mode!=='RESEARCH_ONLY'||info.orderExecutionEnabled!==false||info.approved!==false)
    throw Error('Sperrstatus der Studie nicht bestätigt');

   const brokers=info.brokerReadiness||{};
   const auto=info.automation||{};
   const fmt=t=>t?new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch keine';
   const runtime=info.runtime||{};
   const running=runtime.enabled===true&&runtime.running===true;
   const state=running?(runtime.phase==='retry'?'Fehler · erneuter Versuch geplant':runtime.phase==='market-closed'?'ausserhalb des Prüfzeitfensters pausiert':'läuft'):'nicht bestätigt';
   const latest=el('p','Hintergrundbetrieb: '+state+' · werktags 08–21 Uhr und Wochenend-Archivprüfung 11–17 Uhr (Zürich). Letzte gespeicherte Prüfung: '+fmt(auto.lastRunAt)+'. Browser muss nicht geöffnet bleiben.');
   latest.className='small';reportBox.append(latest);
   if(Array.isArray(auto.history)&&auto.history.length){
    const log=el('details');log.className='bob-disclosure';
    log.append(el('summary','Archivierte Tagesprüfungen ('+auto.history.length+')'));
    const ul=el('ul');
    for(const h of auto.history)ul.append(el('li',h.day+' · '+(h.status==='evaluated'?'ausgewertet':h.status==='maintenance'?'Wochenendprüfung ohne neue Kurse':h.status==='insufficient'?'noch nicht ausreichend':'offen')+' · '+(h.closedBars||0)+' geschlossene 1h-Kerzen'));
    log.append(ul);reportBox.append(log);
   }

   const cycle=info.learningCycle;
   if(cycle&&['bob-rolling-shadow-v1','bob-rolling-shadow-v2'].includes(cycle.version)){
    const area=el('section');area.className='bob-disclosure';
    area.style.cssText='padding:10px;border:1px solid #d7e0ea;border-radius:10px;margin:12px 0';
    area.append(el('h4','Bob · tägliche Weiterentwicklung'));
    const descriptions={
     shadow:'Kandidat eingefroren · prospektiver Referenztest läuft',
     collecting:'Noch kein belastbarer neuer Kandidat',
     'paper-required':'Historischer Vorteil und spätere Referenztests · echter EUR-Produkt-/Paper-Nachweis fehlt',
     rejected:'Kandidat im unabhängigen Test verworfen',
     blocked:'Daten-/Instrumentkonflikt · keine Lernfreigabe',
     'weekend-maintenance':'Wochenendprüfung · keine neue unabhängige Evidenz',
     'archive-missing':'Wochenendprüfung: belegbares Forschungsarchiv fehlt'
    };
    const label=descriptions[cycle.status]||'Wissenschaftliche Forschung, nicht Live-Handel';
    area.append(el('p','Status: '+label));
    const proposal=cycle.proposal||{};
    area.append(el('p','Aktueller Forschungsversuch: '+(proposal.strategy||'kein Kandidat')+
      ' · erstmals vorgeschlagen: '+(proposal.proposedOn||'noch nicht')+
      ' · Zustand: '+(proposal.state||'offen')));
    const progress=cycle.prospective||{};
    const scalar=x=>typeof x==='number'&&Number.isFinite(x)?String(x):'0';
    area.append(el('p','Nachfolgende Prüfsitzungen: '+scalar(progress.sessions)+
      ' / '+String(20)+' · hypothetische Referenzabschlüsse: '+scalar(progress.trades)+
      ' / '+String(30)+' · letzter unabhängiger Kurs: '+fmt(progress.lastEvaluatedBarAt)));
    for(const [name,g] of Object.entries(progress.costScenarios||{})){
     const a=g.candidate||{},b=g.baseline||{};
     area.append(el('p',(name==='stress'?'Stresskosten':'Standardkosten')+' · '+g.costBpsPerSide+' Basispunkte je Seite (Annahme): Kandidat '+((a.index-1)*100).toFixed(2)+' % / Referenz '+((b.index-1)*100).toFixed(2)+' % · größter Rückgang '+Number(a.maxDrawdownPct).toFixed(2)+' % / '+Number(b.maxDrawdownPct).toFixed(2)+' %. Kein Produkt-Nettoergebnis.'));
    }
    if(proposal.protocol)area.append(el('p','Vorab fixiert: gleiche spätere Kursfenster, gleiche Kosten je Seite, mindestens 20 Sitzungen und jeweils 30 Abschlüsse. Vorteil muss auch unter dreifachen Kosten und beim Drawdown bestehen.'));
    if(progress.lastObservation&&cycle.newIndependentEvidence===true)
     area.append(el('p','Letzte neue Evidenz: '+progress.lastObservation.day+
         ' · '+scalar(progress.lastObservation.newBars)+' neu beobachtete 1h-Kerzen'));
    area.append(el('p',String(cycle.reason||'Weitere unabhängige Ergebnisse erforderlich.')));
    if(Array.isArray(cycle.completed)&&cycle.completed.length){
     const history=el('details');history.append(el('summary','Abgeschlossene unabhängige Kandidatenprüfungen ('+cycle.completed.length+')'));
     for(const item of cycle.completed){const p=el('p',(item.strategy||'unbekannt')+' · '+(item.result||'offen')+' · '+(item.finishedOn||'ohne Zeitnachweis'));p.className='small';history.append(p);}
     area.append(history);
    }
    const note=el('p','Forschungsmodelle und hypothetische Spotkosten: keine vollständige Bob-v7-Strategie, keine echten DEGIRO-EUR-Nettogewinne und keine automatische Live-Regeländerung.');
    note.className='small';area.append(note);
    reportBox.append(area);
   }
   if(info.status==='evaluated'&&Array.isArray(info.folds)){
    const ev=info.evidence||{},agg=info.validationSelected||{},base=info.samePeriodBaseline||{};
    const n=v=>typeof v==='number'&&Number.isFinite(v)?new Intl.NumberFormat('de-CH',{maximumFractionDigits:2}).format(v):'offen';
    rStatus.textContent='Automatisch gespeichert · '+info.folds.length+' unabhängige Testfenster berechnet; '+n(info.closedBars)+' geschlossene 1h-Kerzen · '+info.historicalInstrument+'. Keine automatische Regelübernahme.';
    const detail=el('p','Auf Validierung gewählte Varianten, spätere Tests: '+n(agg.trades)+' abgeschlossene hypothetische Positionen; mittlere Testrendite je Fenster '+n(agg.meanFoldNetPct)+' %, grösster Fenster-Rückgang '+n(agg.maxFoldDrawdownPct)+' %. Gleiche Zeiträume mit Basismodell: '+n(base.meanFoldNetPct)+' %. Angenommene Kosten: '+n(info.costBpsPerSide)+' Basispunkte je Seite. Kein Produktnettogewinn.');
    detail.className='small';reportBox.append(detail);
    const table=el('table'),head=el('tr');
    for(const h of ['Regelvariante','Testtrades','Ø Fenster (%)','Max. Rückgang (%)'])head.append(el('th',h));
    table.append(head);
    for(const [id,label] of [['baseline','Bob-Forschungsbasis'],['trend-strict','Strenge Trendfolge'],['trend-tight','Engere Trendbestätigung'],['breakout','Ausbruch'],['breakout-confirmed','Bestätigter Ausbruch'],['mean-revert','Gegenbewegung'],['learned-linear','Gelerntes Modell']]){
     const m=info.outOfSampleByStrategy?.[id];if(!m)continue;
     const row=el('tr');for(const v of [label,n(m.trades),n(m.meanFoldNetPct),n(m.maxFoldDrawdownPct)])row.append(el('td',v));
     table.append(row);
    }
    reportBox.append(table);
    const warning=el('p',ev.sufficientForResearch?'Historische Forschungsmenge erreicht, aber weiterhin KEINE Regel- oder Brokerfreigabe.':'Forschungsmenge unzureichend: weitere unabhängige Historie erforderlich.');
    warning.className='small';reportBox.append(warning);
   }else{
    rStatus.textContent='Automatisches Strategielabor: '+(info.status==='maintenance'?'Wochenend-Archivprüfung gespeichert; ohne neue Kurse oder neue Freigaben':info.status==='pending'?'erste Berechnung steht aus':info.status==='insufficient'?'zu wenige verwendbare historische 1h-Kerzen':'gespeicherter Stand vorübergehend nicht verfügbar')+'. Es werden keine Vergleichsergebnisse erfunden.';
    reportBox.append(el('p',info.note||info.reason||'Datenquelle prüfen.'));
   }
   const brokerHead=el('h4','Broker-Anbindung · technische Vorbereitung');reportBox.append(brokerHead);
   for(const b of brokers.brokers||[]){
    const p=el('p',b.name+': '+(b.connection==='not-connected'?'nicht verbunden':'Verbindung unbekannt')+' · Schweizer Handelserlaubnis und DEGIRO-ISIN nicht verifiziert. API-Vertragsschlüssel: '+b.identifier+'. Keine Paper- oder Echtgeldorder.');
    p.className='small';reportBox.append(p);
   }
   researchLoaded=true;
  }catch(error){rStatus.textContent='Strategielabor konnte nicht zuverlässig gelesen werden ('+String(error.message||'Fehler')+'). Keine Resultate übernommen.';}
  finally{researchBusy=false;runBtn.disabled=false;}
 }
 runBtn.addEventListener('click',loadResearch);
 // Open Zukunft screens refresh the archived status, never execute new research.
 setInterval(()=>{
  const view=document.getElementById('bob-view-future');
  if(view&&!view.hidden&&!researchBusy)loadResearch();
 },10*60*1000);
 document.addEventListener('click',event=>{
  if(!researchLoaded&&event.target?.closest?.('[data-view="future"]'))loadResearch();
 });
 const tests=el('section');tests.style.cssText='border-top:1px solid #dbe3ee;margin-top:14px;padding-top:12px';
 const testsHeading=el('h4','Sicherheitstest mit Beispieldaten');
 const testsP=el('p','Diese neun lokalen Tests prüfen nur den vorgeschlagenen Sperrmechanismus gegen Fehlersituationen. Sie testen keine echte Broker-API, kein Produkt, keine Order und nicht die bisherigen Marktregeln.');
 testsP.className='small';
 const testBtn=el('button','Sperrlogik mit Beispieldaten testen');testBtn.type='button';testBtn.className='bob-primary';
 const testResult=el('div');testResult.setAttribute('aria-live','polite');
 testBtn.addEventListener('click',()=>{
  const rows=stressCases(),passed=rows.filter(x=>x.passed).length;
  testResult.replaceChildren(el('p','Synthetische Prüffälle: '+passed+' von '+rows.length+' korrekt verarbeitet. Kein Echtgeld- oder Live-Order-Test.'));
  const ul=el('ul');ul.style.cssText='font-size:13px;padding-left:20px';
  for(const r of rows){const li=el('li',(r.passed?'✓ ':'✗ ')+r.name+': '+r.reason);ul.append(li);}
  testResult.append(ul);
 });tests.append(testsHeading,testsP,testBtn,testResult);shell.append(tests);
 const roadmap=el('section');roadmap.style.cssText='border-top:1px solid #dbe3ee;margin-top:14px;padding-top:12px';
 roadmap.append(el('h4','Entwicklungsplan und Freigabekriterien'));
 const overview=el('p','Die folgenden Statusangaben bezeichnen den Entwicklungsstand, nicht bestandene Praxistests. Eine erfolgreiche Strategie darf erst nach unabhängiger Prüfung übernommen werden.');
 overview.className='small';roadmap.append(overview);
 for(const f of FIELDS){
  const det=el('details');det.className='bob-disclosure';
  const title=el('summary',f.name+' · '+f.state);
  const p=el('p','Test: '+f.trial),gate=el('p','Für eine spätere Freigabe erforderlich: '+f.gate);
  gate.className='small';det.append(title,p,gate);roadmap.append(det);
 }shell.append(roadmap);
 const broker=el('section');broker.style.cssText='border-top:1px solid #dbe3ee;margin-top:14px;padding-top:12px';
 broker.append(el('h4','Spätere Anbindungen: Voraussetzungen'));
 const criteria=['Offizielle API-Dokumentation und ausdrückliche Erlaubnis zur Automatisierung',
 'Zulassung und Konto für Schweizer Wohnsitz',
 'Handelbare Goldinstrumente, eindeutige Kontrakte/ISIN, Long/Short, KO-Risiken',
 'Kosten einschliesslich Finanzierung, Geld/Brief, Börsendaten und API-Gebühren',
 'Kostenlose Demo-/Paper-Umgebung vor jeglichem Echtgeldbetrieb',
 'Order-ID, Teilausführung, Storno, tatsächlicher Kontostand und Positionsabgleich',
 'Sichere Authentifizierung, minimale Berechtigungen, niemals Broker-Schlüssel im Browser',
 'Unabhängiger Not-Aus und kein automatischer Wechsel zu Echtgeld'];
 const ul=el('ul');for(const s of criteria)ul.append(el('li',s));broker.append(ul);
 const note=el('p','Kein Broker verbunden. Keine Kostenpflicht oder Registrierung ausgelöst. Eine API kann nur nach gesonderter Prüfung und Zustimmung angeschlossen werden.');
 note.className='small';broker.append(note);shell.append(broker);
 const bib=el('details');bib.className='bob-disclosure';
 bib.append(el('summary','Wissenschaftliche Grundlagen'));
 const list=el('ul');for(const [name,href]of CORE_SOURCES){
  const li=el('li'),a=el('a',name);a.href=href;a.target='_blank';a.rel='noopener noreferrer';li.append(a);list.append(li);
 }bib.append(list);shell.append(bib);
 parent.prepend(shell);
 return shell;
}
root.BobFutureLab={mount,preflight,stressCases,snapshot,stages:FIELDS.map(x=>x.id)};
if(typeof module!=='undefined'&&module.exports)module.exports={preflight,stressCases,snapshot,stages:FIELDS.map(x=>x.id)};
})(typeof window!=='undefined'?window:globalThis);
