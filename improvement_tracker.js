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
  const quality=el('section');quality.className='card';quality.dataset.quality='';quality.style.overflowWrap='anywhere';root.append(quality);renderQuality();
  for(let i=0;i<4;i++){
   const card=el('section');card.className='card';card.dataset.goal=i;const h=el('h3',titles[i]),label=el('p','Noch keine bestätigten Daten');label.dataset.percent='';
   const bar=el('progress');bar.max=100;bar.style.cssText='width:100%;height:22px;accent-color:#2563eb';bar.setAttribute('aria-label',titles[i]);bar.hidden=true;
   const summary=el('p');summary.dataset.summary='';const detail=el('details');detail.append(el('summary','Details · Ziel und Berechnung'),el('p',methods[i]));
   const verdict=el('p');verdict.dataset.verdict='';detail.append(summary);card.append(h,label,bar,verdict,detail);root.append(card);
  }
  const result=el('details');result.className='card';result.append(el('summary','Details · Was hat sich verbessert?'));
  const values=el('div');values.dataset.results='';result.append(values);root.append(result);
  for(const [key,title] of [['confidence','Wie belastbar ist das Ergebnis?'],['regimes','Ergebnisse nach Marktphase'],['history','Änderungen und Prüfentscheidungen']]){const d=el('details');d.className='card';d.append(el('summary',title));const body=el('div');body.dataset[key]='';d.append(body);root.append(d);}
  parent.append(root);load();
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
 async function load(){
  if(!root||busy)return;busy=true;const status=root.querySelector('[data-status]');
  try{
   const response=await fetch('/api/improvement/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
   if(!response.ok)throw Error('HTTP '+response.status);const r=await response.json();
   if(!r.ok||!Array.isArray(r.progress)||r.progress.length!==4||r.progress.some(x=>!Number.isFinite(x)||x<0||x>100))throw Error('Unvollständiger Bericht');
   last=r;renderQuality(r.dataQuality);status.textContent=(r.started?'Erfassung freigeschaltet. ':'Start ist für morgen vorbereitet. ')+ 'Berichtsstand: '+new Date(r.generatedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' Schweizer Zeit.';
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
   for(const phase of q.regimes)regimes.append(el('p',phase.label+': '+phase.cases+' Fälle / '+phase.days+' Tage · '+phase.result+' · mittlerer Unterschied '+number(phase.difference,4)+' Prozentpunkte nach angenommenen Standardkosten.'));
   const history=root.querySelector('[data-history]');history.replaceChildren();history.append(el('p','Geprüfte Variante: '+r.protocol.candidate+'. Die aktive Regel wird durch diesen Bereich nicht verändert. Prüfstände werden im Hintergrund gespeichert; neueste zuerst (bis zu 50).'));
   if(!r.history?.length)history.append(el('p','Prüfkonzept eingerichtet. Noch keine abgeschlossene Hintergrundbewertung.'));
   for(const item of r.history||[])history.append(el('p',new Date(item.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' · '+item.baseline+' → '+item.candidate+' · '+item.cases+' Prüffälle / '+item.days+' Tage · '+item.label+' · Entscheidung: '+item.decision+'. Tatsächliche Regeländerung: nein.'));
   window.BobTrainingHelp?.observe('improve',true);
  }catch(e){renderQuality();window.BobTrainingHelp?.observe('improve',false,load);root.querySelector('[data-headline]').textContent='Aktueller Stand nicht bestätigt';root.querySelector('[data-next]').textContent='Bob versucht den Abruf automatisch erneut.';status.textContent='Aktueller Stand nicht abrufbar. '+(last?'Angezeigte Zahlen stammen vom letzten erfolgreichen Abruf.':'Fortschritt unbekannt; keine erfundenen Prozentwerte.');}
  finally{busy=false;}
 }
 window.BobImprovement={mount,load,renderQuality};
 document.addEventListener('click',e=>{if(e.target.closest?.('[data-view="improve"]'))load();});
 setInterval(()=>{if(root&&!root.closest('[hidden]')&&!document.hidden)load();},30000);
})();
