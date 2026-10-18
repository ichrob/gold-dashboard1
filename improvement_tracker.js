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
  const intro=el('section');intro.className='card';intro.append(el('h3','Besser werden · Ziele und Nachweise'),el('p','Start: Montag, 19. Oktober 2026. Automatische Markterfassung ab 08:00 Schweizer Zeit, auch bei geschlossener App. Die Leisten zeigen erreichte Nachweisziele, keine Gewinnwahrscheinlichkeit.'));
  const status=el('p','Stand wird geladen …');status.dataset.status='';status.setAttribute('role','status');intro.append(status);
  const refresh=el('button','Stand aktualisieren');refresh.type='button';refresh.onclick=load;
  const download=el('button','Nachweise als Datei speichern');download.type='button';download.onclick=()=>{if(!last)return;const blob=new Blob([JSON.stringify(last,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='Bob-Besser-werden-'+new Date(last.generatedAt).toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  intro.append(refresh,download);root.append(intro);
  for(let i=0;i<4;i++){
   const card=el('section');card.className='card';card.dataset.goal=i;const h=el('h3',titles[i]),label=el('p','Noch keine bestätigten Daten');label.dataset.percent='';
   const bar=el('progress');bar.max=100;bar.style.cssText='width:100%;height:22px;accent-color:#2563eb';bar.setAttribute('aria-label',titles[i]);bar.hidden=true;
   const summary=el('p');summary.dataset.summary='';const detail=el('details');detail.append(el('summary','Details · Ziel und Berechnung'),el('p',methods[i]));
   card.append(h,label,bar,summary,detail);root.append(card);
  }
  const result=el('section');result.className='card';result.append(el('h3','Gemessene Ergebnisse'));
  const values=el('div');values.dataset.results='';result.append(values);root.append(result);parent.append(root);load();
 }
 async function load(){
  if(!root||busy)return;busy=true;const status=root.querySelector('[data-status]');
  try{
   const response=await fetch('/api/improvement/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
   if(!response.ok)throw Error('HTTP '+response.status);const r=await response.json();
   if(!r.ok||!Array.isArray(r.progress)||r.progress.length!==4||r.progress.some(x=>!Number.isFinite(x)||x<0||x>100))throw Error('Unvollständiger Bericht');
   last=r;status.textContent=(r.started?'Erfassung freigeschaltet. ':'Start ist für morgen vorbereitet. ')+ 'Berichtsstand: '+new Date(r.generatedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' Schweizer Zeit.';
   if(r.started)status.textContent+=' Letzte gespeicherte Beobachtung: '+(r.reliability.lastAt?new Date(r.reliability.lastAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch keine – außerhalb der Erfassungszeit normal.');
   const a=r.reliability,b=r.real,c=r.comparison;
   const summaries=[
    a.days+'/20 Handelstage · Datenabdeckung '+number(a.coveragePct)+' % / Ziel 95 % · '+a.missingSlots+' fehlende Zeitfenster.',
    b.count+'/20 vollständige Abschlüsse · '+b.days+'/10 Tage · '+b.missing+' Abrechnungen/Zeitzuordnungen offen.',
    'Entwicklung: '+c.development.count+'/60 Fälle an '+c.development.days+'/10 Tagen. Spätere Prüfung: '+c.validation.count+'/100 Fälle an '+c.validation.days+'/20 Tagen. '+c.excludedOtherVersions+' Fälle anderer Regelstände getrennt.',
    b.pairedCount+'/20 zeitlich zugeordnete Nettovergleiche an '+b.pairedDays+'/10 späteren Tagen. '+r.adoption.status+'.'
   ];
   for(let i=0;i<4;i++){const card=root.querySelector('[data-goal="'+i+'"]');card.querySelector('[data-percent]').textContent=r.progress[i]+' % des Nachweisziels erreicht';card.querySelector('progress').value=r.progress[i];card.querySelector('progress').hidden=false;card.querySelector('[data-summary]').textContent=summaries[i];}
   const values=root.querySelector('[data-results]');values.replaceChildren();
   const lines=[
    'Echte abgeschlossene Trades: Netto '+number(b.netCHF)+' CHF; größter Rückgang der abgeschlossenen Ergebnissumme '+number(b.drawdownCHF)+' CHF.',
    'Spätere Signalprüfung: '+number(c.validation.falseSignalPct)+' % ohne positive Bewegung nach 60 Minuten (hier als Fehlprognose definiert).',
    'Durch den Testfilter ausgelassen: '+c.validation.avoidedLosses+' negative und '+c.validation.missedGains+' positive Ergebnisse nach angenommenen Standardkosten.',
    'Erfassung der Prüfzeitfenster: '+number(c.coveragePct)+' %. Vollständige Folgeergebnisse: '+number(c.outcomeCoveragePct)+' %.',
    'Zugeordnete echte Trades: tatsächlich '+number(b.pairedBaselineCHF)+' CHF; rechnerisch mit Auslassen durch Testfilter '+number(b.pairedCandidateCHF)+' CHF. Kein Nachweis für ungehandelte Chancen.'
   ];
   for(const s of c.validation.scenarios)lines.push('Spotvergleich bei '+s.costPct+' % angenommenen Kosten: bisherige Regel '+number(s.baselineMean)+' %, Testregel '+number(s.candidateMean)+' %, Unterschied '+number(s.difference)+' Prozentpunkte je Fall. Keine DEGIRO-Produktrendite.');
   lines.push(r.adoption.note);for(const line of lines)values.append(el('p',line));
  }catch(e){status.textContent='Aktueller Stand nicht abrufbar. '+(last?'Angezeigte Zahlen stammen vom letzten erfolgreichen Abruf.':'Fortschritt unbekannt; keine erfundenen Prozentwerte.');}
  finally{busy=false;}
 }
 window.BobImprovement={mount,load};
 document.addEventListener('click',e=>{if(e.target.closest?.('[data-view="improve"]'))load();});
 setInterval(()=>{if(root&&!root.closest('[hidden]')&&!document.hidden)load();},30000);
})();
