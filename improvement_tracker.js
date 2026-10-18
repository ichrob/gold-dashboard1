/* MBO goals: server evidence only. No simulated progress, policy changes or notifications. */
(function(){
 let root,busy=false,last=null;
 const titles=['1 · Zuverlässige Entscheidungsdaten','2 · Echte Ergebnisse vollständig auswerten','3 · Bisherige und neue Regel vergleichen','4 · Verbesserungen unabhängig bewerten'];
 const methods=[
  'Ziel: mindestens 20 erfasste Handelstage und 95 % gültige Datenabdeckung. Grundlage sind geplante 30-Sekunden-Zeitfenster, Mo–Fr 08:00–22:00 Schweizer Zeit. Ausfälle zählen als Lücken; Feiertage sind im festen Wochenplan enthalten. Kein Nachweis für den Empfang jeder Push-Nachricht.',
  'Ziel: 20 abgeschlossene Trades an mindestens 10 Tagen mit nachvollziehbaren Kauf-/Verkaufszeiten und vollständiger CHF-Abrechnung. Keine zusätzlichen Trades nur zum Füllen der Leiste eröffnen. Fehlende Kosten bleiben offen.',
  'Festgelegter Test: aktuelle freigegebene Signale gegen dieselben Signale mit zusätzlichem ADX-Filter (mindestens 25). Ein Fall alle zwei Stunden; Ergebnis nach 60 Minuten. Die erste Hälfte der Leiste: 60 auswertbare Fälle an 10 Tagen. Die zweite Hälfte: danach getrennt 100 Fälle an 20 neuen Tagen. Mindestens 95 % Erfassungs- und Ergebnisabdeckung. Filter und Ziele bleiben während des Tests unverändert. Spotkosten von 0,04/0,12 % sind Annahmen.',
  '50 % stammen aus dem abgeschlossenen unabhängigen Signalvergleich. Weitere 50 % benötigen 20 Nettoabrechnungen an 10 späteren Tagen mit vor dem Kauf gespeichertem Signal. Gegenvergleich: tatsächlich gehandelter Trade oder durch den Filter ausgelassener Trade. Das prüft nur die von dir gehandelten Fälle, nicht alle Marktchancen. 100 % bedeutet Prüfziel erreicht; eine Übernahme benötigt weiterhin eine gesonderte Bewertung. Keine automatische Änderung an Orders, Stopps, KO- oder Risikoregeln.'
 ];
 const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const number=(x,d=2)=>Number.isFinite(x)?x.toLocaleString('de-CH',{maximumFractionDigits:d}):'noch offen';
 function mount(parent){
  if(!parent||document.getElementById('bobImprovementGoals'))return;
  root=el('section');root.id='bobImprovementGoals';
  const intro=el('section');intro.className='card';intro.append(el('h3','Besser werden · Ziele und Nachweise'));const explanation=el('p','Start: Montag, 19. Oktober 2026. Automatische Markterfassung ab 08:00 Schweizer Zeit, auch bei geschlossener App. Die Leisten zeigen erreichte Nachweisziele, keine Gewinnwahrscheinlichkeit.');
  const headline=el('p','Aktueller Stand wird geprüft …');headline.dataset.headline='';const next=el('p');next.dataset.next='';intro.append(headline,next);
  const status=el('p','Stand wird geladen …');status.dataset.status='';status.setAttribute('role','status');intro.append(status);
  const refresh=el('button','Stand aktualisieren');refresh.type='button';refresh.onclick=load;
  const download=el('button','Nachweise als Datei speichern');download.type='button';download.onclick=()=>{if(!last)return;const blob=new Blob([JSON.stringify(last,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='Bob-Besser-werden-'+new Date(last.generatedAt).toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  const tools=el('details');tools.append(el('summary','Details · Erfassung und Bericht'),explanation,status,refresh,download);intro.append(tools);root.append(intro);
  const operating=el('section');operating.className='card';operating.dataset.operating='';root.append(operating);renderOperating();
  const quality=el('section');quality.className='card';quality.dataset.quality='';quality.style.overflowWrap='anywhere';root.append(quality);renderQuality();
  for(let i=0;i<4;i++){
   const card=el('section');card.className='card';card.dataset.goal=i;const h=el('h3',titles[i]),label=el('p','Noch keine bestätigten Daten');label.dataset.percent='';
   const bar=el('progress');bar.max=100;bar.style.cssText='width:100%;height:22px;accent-color:#2563eb';bar.setAttribute('aria-label',titles[i]);bar.hidden=true;
   const summary=el('p');summary.dataset.summary='';const detail=el('details');detail.append(el('summary','Details · Ziel und Berechnung'),el('p',methods[i]));
   const verdict=el('p');verdict.dataset.verdict='';detail.append(summary);card.append(h,label,bar,verdict,detail);root.append(card);
  }
  const result=el('details');result.className='card';result.append(el('summary','Details · Was hat sich verbessert?'));
  const values=el('div');values.dataset.results='';result.append(values);root.append(result);
  const journal=el('section');journal.className='card';journal.dataset.journal='';journal.style.overflowWrap='anywhere';root.append(journal);renderJournal();
  const path=el('section');path.className='card';path.dataset.entryPath='';path.style.overflowWrap='anywhere';root.append(path);renderEntryPath();
  const exits=el('section');exits.className='card';exits.dataset.exitQuality='';exits.style.overflowWrap='anywhere';root.append(exits);renderExitQuality();
  const operations=el('section');operations.className='card';operations.dataset.operations='';operations.style.overflowWrap='anywhere';root.append(operations);renderOperations();
  for(const [key,title] of [['confidence','Wie belastbar ist das Ergebnis?'],['regimes','Ergebnisse nach Marktphase'],['history','Änderungen und Prüfentscheidungen']]){const d=el('details');d.className='card';d.append(el('summary',title));const body=el('div');body.dataset[key]='';d.append(body);root.append(d);}
  parent.append(root);load();
 }
 function renderOperating(data={}){
  const box=root?.querySelector('[data-operating]');if(!box)return;
  box.replaceChildren(el('h3','Bob · Kurzstatus'));box.style.overflowWrap='anywhere';
  if(data.available!==true||!Array.isArray(data.cards)){box.append(el('p','Aktueller Stand nicht bestätigt.'));return;}
  const labels={ok:'✓ Bestätigt',paused:'Ⅱ Pause',waiting:'○ Noch offen',open:'! Nachweise fehlen',candidate:'○ Vergleichsvorteil',warming:'○ Start läuft',degraded:'! Prüfung nötig',unavailable:'? Nicht bestätigt'};
  for(const card of data.cards){const line=el('p');line.append(el('strong',card.label+': '+(labels[card.state]||labels.unavailable)),el('br'),document.createTextNode(card.detail));box.append(line);}
  box.append(el('p',Number.isFinite(data.openErrorTypes)?data.openErrorTypes+' offene Fehlerarten · '+data.affectedCases+' betroffene Testfälle':'Zahl offener Fehlerarten nicht bestätigt.'));
  box.append(el('small','Stand: '+new Date(data.checkedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' · '+data.note));
 }
 function renderQuality(data={}){
  const box=root?.querySelector('[data-quality]');if(!box)return;box.replaceChildren(el('h3','Produktdaten · Qualität'));
  const current=data.status==='ok';
  const metric=(label,value)=>box.append(el('p',label+': '+(current&&Number.isFinite(value)?number(value,1)+' %':'nicht bestätigt')));
  metric('Daten aktuell',data.freshPct);metric('Angaben vollständig',data.completePct);
  box.append(el('p','Kursabweichung: '+(data.comparisons?.length?data.comparisons.length+' Produkte mit Vergleichsdaten':'noch keine belastbaren Vergleichsdaten')));
  const details=el('details');details.append(el('summary','Details · Quellen, Lücken und Kursabweichung'));
  details.append(el('p','Prüfstand: '+(data.checkedAt?new Date(data.checkedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'unbekannt')+(current?' · '+data.total+' aktive Produkte':' · derzeit nicht als aktuell bestätigt')));
  for(const row of data.comparisons||[])details.append(el('p',row.isin+': mittlere absolute Modellabweichung '+number(row.meanAbsoluteError,4)+' '+(row.currency||'Währung unbekannt')+' · '+row.validationCount+' spätere Prüffälle · letzter Vergleich '+(row.lastAt?new Date(row.lastAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'unbekannt')));
  for(const isin of data.conflicts||[])details.append(el('p',isin+': auffällige Abweichung zwischen Kursquellen.'));
  for(const gap of data.gaps||[])details.append(el('p',gap.isin+' · '+(gap.label||gap.field)+': seit '+gap.minutes+' Minuten offen.'));
  for(const row of data.snapshots||[])details.append(el('p',row.isin+' · '+(row.currency||'Währung offen')+' · '+(row.source||'Quelle offen')+' · Originalzeit '+(row.sourceAt?new Date(row.sourceAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'offen')+' · Datenstand '+(row.id||'noch nicht erfasst')));
  details.append(el('p',data.note||'Aktueller Qualitätsnachweis noch nicht verfügbar.'));box.append(details);
 }
 function renderJournal(data={}){
  const box=root?.querySelector('[data-journal]');if(!box)return;
  box.replaceChildren(el('h3','Entscheidung · Ergebnis · Lernpunkt'));
  const rows=data.items||[];
  box.append(el('p',rows.length?rows.length+' gespeicherte Prüffälle · neueste zuerst':'Noch keine Prüffälle vorhanden. Die geplante Erfassung beginnt am 19. Oktober 2026 um 08:00 Schweizer Zeit.'));
  box.append(el('p',data.note||'Ergebnisse werden erst mit gültigen späteren Kursnachweisen bewertet.'));
  const details=el('details');details.append(el('summary','Details · Entscheidungsjournal'));
  for(const row of rows){
   const item=el('article');item.append(el('h4',new Date(row.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' · '+row.decision));
   item.append(el('p','Damals: '+row.reason),el('p','Ergebnis: '+row.result));
   if(Number.isFinite(row.netSpotPct))item.append(el('p','Richtungsbezogen nach angenommenen Standardkosten: '+number(row.netSpotPct,3)+' % (Spot).'));
   if(Number.isFinite(row.marketMovePct))item.append(el('p','Spotbewegung: '+number(row.marketMovePct,3)+' %.'));
   item.append(el('p','Lernpunkt: '+row.lesson));
   const proof=el('details');proof.append(el('summary','Damals gespeicherte Daten'),el('p',(row.phase==='validation'?'Unabhängige Prüfung':'Entwicklung')+' · Regelstand '+row.cohort+' · ADX '+number(row.adx)));
   proof.append(el('p','Originalkurszeit: '+(row.sourceAt?new Date(row.sourceAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'fehlt')));
   const pre=el('pre',JSON.stringify(row.evidence,null,2));pre.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';proof.append(pre);item.append(proof);details.append(item);
  }
  box.append(details);
 }
 function renderEntryPath(data={}){
  const box=root?.querySelector('[data-entry-path]');if(!box)return;
  box.replaceChildren(el('h3','Einstiegszeitpunkt · Verlaufstest'));
  const rows=data.items||[];box.append(el('p',rows.length?rows.length+' geplante Prüffälle · 5 / 15 / 30 / 60 Minuten':'Noch keine Prüffälle. Start der Erfassung: 19. Oktober 2026, 08:00 Schweizer Zeit.'));
  const details=el('details');details.append(el('summary','Details · Verlauf und Testvergleich'),el('p',data.note||'Die Variante wird nur im Hintergrund ausgewertet.'));
  for(const g of data.groups||[]){
   details.append(el('h4',(g.phase==='validation'?'Spätere unabhängige Prüfung':'Entwicklung')+' · '+g.cohort));
   details.append(el('p',g.paired+' auswertbare Filtervergleiche: '+g.avoidedLosses+' negative Verläufe vermieden, '+g.missedGains+' positive Verläufe ausgelassen. Frühvergleich: '+g.earlyPairs+' Fälle, davon '+g.earlierLosses+' frühere Signale nach Standardkosten negativ.'));
   for(const s of g.scenarios)details.append(el('p','Bei '+s.costPct+' % angenommenen Kosten: Filterunterschied '+number(s.difference,3)+' Prozentpunkte/Fall; Frühvergleich '+number(s.earlierDifference,3)+' Prozentpunkte/Fall.'));
  }
  for(const row of rows){
   const item=el('details');item.append(el('summary',new Date(row.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' · '+row.direction+' · '+row.label));
   item.append(el('p','Vorherige 15-Minuten-Bewegung in Signalrichtung: '+number(row.priorMovePct,3)+' %. Testfilter: '+(row.candidateKeep===true?'behalten':row.candidateKeep===false?'auslassen':'Nachweis offen')+'.'));
   for(const h of row.horizons||[])item.append(el('p',h.minutes+' Minuten: '+(h.status==='observed'?number(h.directionalPct??h.movePct,3)+' % '+(h.directionalPct===null?'Spotbewegung':'in Signalrichtung'):h.status==='missing'?'Originalnachweis fehlt':'Ergebnis noch offen')));
   item.append(el('p','Beobachteter Rücklauf: '+number(row.observedAdversePct,3)+' %. Beobachteter günstiger Verlauf: '+number(row.observedFavorablePct,3)+' %. Datenabdeckung: '+number(row.coveragePct,1)+' %.'));
   item.append(el('p','Fünf Minuten früher freigegebenes Signal: '+(row.earlierDirection||'kein belegtes Signal')+'.'));details.append(item);
  }
  box.append(details);
 }
 function renderExitQuality(data={}){
  const box=root?.querySelector('[data-exit-quality]');if(!box)return;
  box.replaceChildren(el('h3','Ausstiegsqualität · Stopp und Ziel'));
  const rows=data.items||[];
  box.append(el('p',rows.length?rows.filter(r=>r.status==='complete').length+' von '+rows.length+' Fällen mit ausreichenden Kursnachweisen':'Noch kein passender Produktfall. Bob benötigt einen aktiven Trade, gültigen Stopp-/Zielplan und Originalkurse. Erfassung ab 19. Oktober, 08:00 Schweizer Zeit.'));
  const details=el('details');details.append(el('summary','Details · Ausstiegsvergleich'),el('p',data.note||'Die Untersuchung verändert keine aktiven Stopps oder Orders.'));
  const reasons={stop:'Stopp berührt',target:'Ziel berührt',horizon:'60-Minuten-Endpunkt'};
  for(const r of rows){
   const item=el('details');item.append(el('summary',r.isin+' · '+r.currency+' · '+(r.status==='complete'?'Vergleich auswertbar':r.status==='missing'?'Nachweise unvollständig':'Beobachtung läuft')));
   item.append(el('p','Start: '+new Date(r.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' · Quelle '+r.source));
   item.append(el('p','Briefkurs am Teststart: '+number(r.entry,4)+' '+r.currency+' · berechneter Stopp '+number(r.stop,4)+' · berechnetes Ziel '+number(r.target,4)));
   item.append(el('p','Originalkurse: '+r.observations+' · Abdeckung '+number(r.coveragePct,1)+' % · größte Lücke '+number(r.maxGapSeconds,1)+' Sekunden.'));
   for(const [name,x] of Object.entries(r.referenceExits||{}))item.append(el('p',(name==='fixed'?'Fester Stopp':'Nachziehvariante')+': '+(reasons[x.reason]||x.reason)+' · beobachteter Geldkurs '+number(x.bid,4)+' '+r.currency+'. Keine bestätigte Ausführung.'));
   item.append(el('p','Erholung nach beobachteter Stoppberührung: '+number(r.stopReboundPct,3)+' %. Rücklauf nach Zielberührung: '+number(r.targetPullbackPct,3)+' %. Rückgabe vom beobachteten Hoch bis zum Endpunkt: '+number(r.peakGivebackPct,3)+' %.'));
   if(!r.scenarios?.length)item.append(el('p','Kostenvergleich noch offen: keine Bewertung aus unvollständigen Nachweisen.'));
   for(const x of r.scenarios||[])item.append(el('p','Zusatzkostenannahme '+x.costPct+' %: fester Stopp '+number(x.baselinePct,3)+' %, Nachziehen '+number(x.candidatePct,3)+' %, Unterschied '+number(x.differencePct,3)+' Prozentpunkte.'));
   details.append(item);
  }
  box.append(details);
 }
 function renderOperations(report={}){
  const box=root?.querySelector('[data-operations]');if(!box)return;
  box.replaceChildren(el('h3','Tagesbericht · Nachweise und nächste Schritte'));
  const days=report.dailyReview||[],today=days.at(-1),costs=report.costEvidence,repairs=report.repairQuality,gate=report.releaseDossier;
  if(today){
   box.append(el('p',today.day+' · '+(today.closed?'Tagesstand abgeschlossen':'Zwischenstand')+' · gültige Daten '+number(today.coveragePct,1)+' %'));
   box.append(el('p','Ausgewertete Signaltests: '+today.completed+' · positiv '+today.positive+' · negativ '+today.negative+'. Keine echten Trade-Ergebnisse.'));
   box.append(el('p','Offen: '+today.missingSlots+' fehlende und '+today.invalidSlots+' ungültige Messfenster · '+today.missingOutcomes+' fehlende Folgeergebnisse.'));
  }else box.append(el('p','Noch kein Tagesbericht aus der geplanten Erfassung verfügbar.'));
  if(report.assessment)box.append(el('p','Nächster Schritt: '+report.assessment.nextStep));
  const resilience=report.resilience;
  const extra=el('details');extra.append(el('summary','Details · Ausfallproben, Lernprioritäten und Hinweise'));
  if(!resilience||resilience.unavailable)extra.append(el('p','Zusätzliche Nachweise derzeit nicht bestätigt.'));
  else{
   extra.append(el('h4','Ausfallproben'));
   for(const row of resilience.drills.items)extra.append(el('p',row.label+': '+({passed:'bestanden',failed:'fehlgeschlagen',timeout:'Zeitgrenze erreicht'}[row.status]||'offen')));
   if(resilience.drills.at)extra.append(el('p','Letzte Probe: '+new Date(resilience.drills.at).toLocaleString('de-CH')+' · Build '+resilience.drills.build));
   if(resilience.drills.items.length&&(!resilience.drills.currentBuild||!resilience.drills.recent))extra.append(el('p','Aktueller Build/Tagesstand noch nicht durch diese Proben bestätigt.'));
   extra.append(el('p',resilience.drills.scope));
   extra.append(el('h4','Nächste Lernversuche'));
   if(!resilience.priorities.items.length)extra.append(el('p','Noch keine belegte Aufgabe abgeleitet; weitere Daten sammeln.'));
   for(const row of resilience.priorities.items){const d=el('details');d.append(el('summary',row.label+' · '+row.cases+' Fälle'));d.append(el('p',row.experiment));d.append(el('p','Prüfziel: '+row.measure));d.append(el('p',row.status));extra.append(d);}
   extra.append(el('p',resilience.priorities.note));
   const h=resilience.hints;extra.append(el('h4','Hinweise auswerten'));
   extra.append(el('p',h.attempts+' Versandversuche · '+h.failed+' fehlgeschlagen · '+h.prompt+' technisch rechtzeitig · '+h.delayed+' verzögert · '+h.unknown+' ohne Zeitnachweis · '+h.repeats+' mögliche Wiederholungen.'));
   extra.append(el('p',h.note));if(h.truncated)extra.append(el('p','Die Auswertung ist wegen der Ereignisgrenze unvollständig.'));
  }box.append(extra);
  const history=el('details');history.append(el('summary','Details · Tagesstände'));
  for(const day of [...days].reverse())history.append(el('p',day.day+': '+day.valid+'/'+day.expected+' gültige geplante Messfenster · '+day.completed+' ausgewertete Signaltests · '+day.missingOutcomes+' Folgenachweise offen. '+day.note));
  box.append(history);
  const repairsBox=el('details');repairsBox.append(el('summary','Details · Wie gut behebt Bob Fehler?'));
  if(repairs?.status==='ok'){
   repairsBox.append(el('p',repairs.episodes+' Betriebsfehler-Episoden in '+repairs.types+' Arten · '+repairs.verified+' mit Reparaturnachweis · '+repairs.open+' noch offen.'));
   repairsBox.append(el('p',repairs.repeatedDetections+' Wiederholungsmeldungen zusammengefasst · '+repairs.recurrences+' erneute Episoden nach zwischenzeitlicher Erholung. Bestätigte Reparaturquote: '+number(repairs.verifiedPct,1)+' %.'));
   repairsBox.append(el('p','Mittlere belegte Reparaturdauer: '+number(repairs.meanRepairSeconds,1)+' Sekunden. '+repairs.recoveredWithoutVerifiedRepair+' Erholungen ohne belegte Reparatur.'));
   repairsBox.append(el('p','Testprobleme: '+repairs.testProblemTypes+' offene Arten, '+repairs.testCases+' betroffene Fälle; '+repairs.recoveredTestCases+' wiederhergestellte Fälle im vorhandenen Archiv. '+repairs.recurringTestTypes+' wiederkehrende Fehlerarten.'));
   if(repairs.truncated)repairsBox.append(el('p','Ereignisgrenze erreicht; die Bilanz ist nur ein Ausschnitt.'));
  }else repairsBox.append(el('p','Reparaturbilanz derzeit nicht bestätigt.'));
  if(repairs?.note)repairsBox.append(el('p',repairs.note));box.append(repairsBox);
  const costBox=el('details');costBox.append(el('summary','Details · Echte Kosten und Ausführungen'));
  if(costs){
   costBox.append(el('p',costs.complete+'/'+costs.total+' Abschlüsse mit vollständigen Kosten-/Zeit-/Ausführungsnachweisen. '+costs.missing+' unvollständig.'));
   for(const row of costs.items){const d=el('details');d.append(el('summary',row.tradeId+' · '+row.currency+' · '+(row.complete?'Belege vollständig':'Belege offen')));
    d.append(el('p','Kauf '+number(row.entry,4)+' · Verkauf '+number(row.exit,4)+' '+row.currency+' · Gebühren '+number(row.feesCHF,2)+' CHF / '+number(row.feesNative,2)+' '+row.currency+' · Netto '+number(row.netCHF,2)+' CHF.'));
    d.append(el('p',row.missing.length?'Fehlt: '+row.missing.join('; '):'Erforderliche Belegfelder vorhanden.'));d.append(el('p',row.source));costBox.append(d);
   }
   costBox.append(el('p',costs.note));if(costs.truncated)costBox.append(el('p','Die Detailansicht zeigt die letzten 30 Abschlüsse.'));
  }else costBox.append(el('p','Kostenbelege noch nicht ausgewertet.'));box.append(costBox);
  const release=el('details');release.append(el('summary','Details · Freigabe und Rückkehr zur bisherigen Regel'));
  if(gate){release.append(el('p',gate.status));for(const c of gate.checks)release.append(el('p',(c.met?'✓ ':'○ ')+c.label));
   release.append(el('p','Persönliche Freigabe: ausstehend. Aktive Regeländerung: keine. '+gate.rollbackStatus));
   for(const step of gate.rollbackSteps)release.append(el('p',step));release.append(el('p',gate.note));
  }else release.append(el('p','Freigabedossier noch nicht verfügbar.'));box.append(release);
 }
 async function load(){
  if(!root||busy)return;busy=true;const status=root.querySelector('[data-status]');
  try{
   const response=await fetch('/api/improvement/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
   if(!response.ok)throw Error('HTTP '+response.status);const r=await response.json();
   if(!r.ok||!Array.isArray(r.progress)||r.progress.length!==4||r.progress.some(x=>!Number.isFinite(x)||x<0||x>100))throw Error('Unvollständiger Bericht');
   last=r;renderOperating(r.operatingStatus);renderQuality(r.dataQuality);renderJournal(r.decisionJournal);renderEntryPath(r.entryPath);renderExitQuality(r.exitQuality);renderOperations(r);status.textContent=(r.started?'Erfassung freigeschaltet. ':'Start ist für morgen vorbereitet. ')+ 'Berichtsstand: '+new Date(r.generatedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' Schweizer Zeit.';
   if(r.started)status.textContent+=' Letzte gespeicherte Beobachtung: '+(r.reliability.lastAt?new Date(r.reliability.lastAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch keine – außerhalb der Erfassungszeit normal.');
   const a=r.reliability,b=r.real,c=r.comparison,q=r.assessment;
   root.querySelector('[data-headline]').textContent='Aktueller Stand · Signalprüfung: '+q.label;root.querySelector('[data-next]').textContent='Nächster Prüfschritt: '+q.nextStep;
   const summaries=[
    a.days+'/20 Handelstage · Datenabdeckung '+number(a.coveragePct)+' % / Ziel 95 % · '+a.missingSlots+' fehlende Zeitfenster.',
    b.count+'/20 vollständige Abschlüsse · '+b.days+'/10 Tage · '+b.missing+' Abrechnungen/Zeitzuordnungen offen.',
    'Entwicklung: '+c.development.count+'/60 Fälle an '+c.development.days+'/10 Tagen. Spätere Prüfung: '+c.validation.count+'/100 Fälle an '+c.validation.days+'/20 Tagen. '+c.excludedOtherVersions+' Fälle anderer Regelstände getrennt.',
    b.pairedCount+'/20 zeitlich zugeordnete Nettovergleiche an '+b.pairedDays+'/10 späteren Tagen. '+r.adoption.status+'.'
   ];
   for(let i=0;i<4;i++){const card=root.querySelector('[data-goal="'+i+'"]');card.querySelector('[data-percent]').textContent=r.progress[i]+' % des Nachweisziels erreicht';card.querySelector('progress').value=r.progress[i];card.querySelector('progress').hidden=false;card.querySelector('[data-summary]').textContent=summaries[i];card.querySelector('[data-verdict]').textContent=i<2?(r.progress[i]===100?'Nachweisziel erreicht':'Daten werden gesammelt'):i===3?q.realLabel:q.label;}
   const values=root.querySelector('[data-results]');values.replaceChildren();
   const lines=[
    'Echte abgeschlossene Trades: Netto '+number(b.netCHF)+' CHF; größter Rückgang der abgeschlossenen Ergebnissumme '+number(b.drawdownCHF)+' CHF.',
    'Spätere Signalprüfung: '+number(c.validation.falseSignalPct)+' % ohne positive Bewegung nach 60 Minuten (hier als Fehlprognose definiert).',
    'Durch den Testfilter ausgelassen: '+c.validation.avoidedLosses+' negative und '+c.validation.missedGains+' positive Ergebnisse nach angenommenen Standardkosten.',
    'Erfassung der Prüfzeitfenster: '+number(c.coveragePct)+' %. Vollständige Folgeergebnisse: '+number(c.outcomeCoveragePct)+' %.',
    'Zugeordnete echte Trades: tatsächlich '+number(b.pairedBaselineCHF)+' CHF; rechnerisch mit Auslassen durch Testfilter '+number(b.pairedCandidateCHF)+' CHF. Kein Nachweis für ungehandelte Chancen.'
   ];
   for(const s of c.validation.scenarios)lines.push('Spotvergleich bei '+s.costPct+' % angenommenen Kosten: bisherige Regel '+number(s.baselineMean)+' %, Testregel '+number(s.candidateMean)+' %, Unterschied '+number(s.difference)+' Prozentpunkte je Fall. Keine DEGIRO-Produktrendite.');
   lines.push('Fehlprognosen: bisher '+q.falseSignals.baseline+' in '+q.independentCases+' Fällen; Testregel '+q.falseSignals.candidate+' in '+c.validation.retained+' beibehaltenen Fällen. Quoten: '+number(q.falseSignals.baselinePct)+' % / '+number(q.falseSignals.candidatePct)+' %. Unterschiedliche Nenner beachten.');lines.push('Rechnerischer Netto-Unterschied bei zugeordneten echten Trades: '+number(q.netDifferenceCHF)+' CHF.');lines.push(q.priceAccuracy);
   lines.push(r.adoption.note);for(const line of lines)values.append(el('p',line));
   const confidence=root.querySelector('[data-confidence]');confidence.replaceChildren();
   for(const text of [q.independentCases+' zeitlich getrennte Prüffälle an '+q.days+' Tagen.',q.independenceNote,'Datenabdeckung: '+number(a.coveragePct)+' %. '+a.missingSlots+' fehlende und '+(a.observed-a.valid)+' ungültige Zeitfenster.'])confidence.append(el('p',text));
   q.intervals.forEach((band,i)=>confidence.append(el('p',band?'Orientierender 95%-Bereich des Vorteils bei '+r.protocol.costPct[i]+' % Kosten: '+number(band.low,4)+' bis '+number(band.high,4)+' Prozentpunkte. '+band.blocks+' Zweitagesblöcke.':'Unsicherheitsbereich bei '+r.protocol.costPct[i]+' % Kosten: noch nicht genügend Prüftage.')));
   confidence.append(el('p','Ein beobachteter Vorteil gilt nur für diesen Test. Viele getestete Ideen und ähnliche Markttage können das Ergebnis verzerren.'));
   const regimes=root.querySelector('[data-regimes]');regimes.replaceChildren();regimes.append(el('p','Zuordnung anhand der vor dem Ergebnis gespeicherten 5m-Daten: ADX unter 20 = seitwärts; sonst EMA-Trend steigend/fallend. Unbekannte Phasen bleiben separat. Mindestens 30 Fälle und 5 Tage je Phase für eine beschreibende Bewertung.'));
   for(const phase of q.regimes)regimes.append(el('p',phase.label+': '+phase.cases+' Fälle / '+phase.days+' Tage · '+phase.result+' · mittlerer Unterschied '+number(phase.difference,4)+' Prozentpunkte nach Standardkosten; bei höheren Kosten '+number(phase.stressDifference,4)+' Prozentpunkte. Vermiedene negative Fälle '+phase.avoidedLosses+', ausgelassene positive Fälle '+phase.missedGains+'.'));
   const history=root.querySelector('[data-history]');history.replaceChildren();history.append(el('p','Geprüfte Variante: '+r.protocol.candidate+'. Die aktive Regel wird durch diesen Bereich nicht verändert. Prüfstände werden im Hintergrund gespeichert; neueste zuerst (bis zu 50).'));
   if(!r.history?.length)history.append(el('p','Prüfkonzept eingerichtet. Noch keine abgeschlossene Hintergrundbewertung.'));
   for(const item of r.history||[])history.append(el('p',new Date(item.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' · '+item.baseline+' → '+item.candidate+' · '+item.cases+' Prüffälle / '+item.days+' Tage · '+item.label+' · Entscheidung: '+item.decision+'. Tatsächliche Regeländerung: nein.'));
   window.BobTrainingHelp?.observe('improve',true);
  }catch(e){renderOperating();renderQuality();const ops=root.querySelector('[data-operations]');if(ops)ops.replaceChildren(el('h3','Tagesbericht'),el('p','Aktueller Bericht nicht abrufbar; kein aktueller Stand bestätigt.'));const exits=root.querySelector('[data-exit-quality]');if(exits)exits.replaceChildren(el('h3','Ausstiegsqualität'),el('p','Aktueller Bericht nicht abrufbar.'));const path=root.querySelector('[data-entry-path]');if(path)path.replaceChildren(el('h3','Einstiegszeitpunkt · Verlaufstest'),el('p','Aktueller Bericht nicht abrufbar.'));const journal=root.querySelector('[data-journal]');if(journal)journal.replaceChildren(el('h3','Entscheidungsjournal'),el('p','Aktueller Bericht nicht abrufbar. Bob versucht es erneut.'));window.BobTrainingHelp?.observe('improve',false,load);root.querySelector('[data-headline]').textContent='Aktueller Stand nicht bestätigt';root.querySelector('[data-next]').textContent='Bob versucht den Abruf automatisch erneut.';status.textContent='Aktueller Stand nicht abrufbar. '+(last?'Angezeigte Zahlen stammen vom letzten erfolgreichen Abruf.':'Fortschritt unbekannt; keine erfundenen Prozentwerte.');}
  finally{busy=false;}
 }
 window.BobImprovement={mount,load,renderOperating,renderQuality,renderJournal,renderEntryPath,renderExitQuality,renderOperations};
 document.addEventListener('click',e=>{if(e.target.closest?.('[data-view="improve"]'))load();});
 setInterval(()=>{if(root&&!root.closest('[hidden]')&&!document.hidden)load();},30000);
})();
