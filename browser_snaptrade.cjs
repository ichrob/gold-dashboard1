'use strict';
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
const panel=cp.execFileSync('python',['-c','from snaptrade_panel import PANEL;print(PANEL)'],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BOB_CHROMIUM_PATH?{executablePath:process.env.BOB_CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://bob.test/**',route=>route.fulfill({contentType:'text/html; charset=utf-8',body:'<meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:8px}button{max-width:100%;white-space:normal}</style><section id="bob-view-degiro"></section>'+panel.replace(/<script>[\s\S]*?<\/script>/g,'')}));
  await page.goto('https://bob.test/');
  await page.evaluate(()=>{
   window.state={code:'SETUP_REQUIRED',configured:false,nextCheckSeconds:0};window.calls=[];window.failSave=true;
   window.setInterval=fn=>{window.poll=fn;return 1;};
   window.fetch=async(url,options={})=>{
    calls.push({url,body:options.body});
    if(url.endsWith('/configure')&&failSave)return{ok:false,status:503,json:async()=>({code:'CRYPTO_UNAVAILABLE'})};
    if(url.endsWith('/configure'))state={code:'READY',configured:true,nextCheckSeconds:0};
    if(url.endsWith('/disconnect'))state={code:'SETUP_REQUIRED',configured:false,nextCheckSeconds:0};
    if(url.endsWith('/csv-import')){
     const payload=JSON.parse(options.body),account=state.snapshot.accounts.find(a=>a.accountKey===payload.accountKey);
     for(const position of account.positions){const link=payload.links.find(l=>l.positionKey===position.positionKey);position.isin=link?.isin||null;position.csvEvidence=link?payload.records.find(r=>r.isin===link.isin):null;}
    }
    return{ok:true,json:async()=>state};
   };
  });
  await page.addScriptTag({content:panel.match(/<script>([\s\S]*?)<\/script>/)[1]});
  await page.locator('#snapStatus').filter({hasText:'Noch nicht verbunden.'}).waitFor();
  await page.locator('#snapClient').fill('test-client');await page.locator('#snapKey').fill('test-consumer-key');await page.locator('#snapFree').check();
  await page.locator('#snapSave').click();await page.locator('#snapFormStatus').filter({hasText:'Nicht gespeichert: Verschlüsselung'}).waitFor();
  await page.evaluate(()=>poll());
  assert((await page.locator('#snapFormStatus').innerText()).includes('Nicht gespeichert:'),'Polling must not erase save errors');
  assert(await page.locator('#snapCheck').isDisabled());assert(await page.locator('#snapRemove').isDisabled());
  await page.evaluate(()=>{failSave=false;});
  await page.locator('#snapClient').fill('test-client');await page.locator('#snapKey').fill('test-consumer-key');
  await page.locator('#snapSave').click();await page.locator('#snapStatus').filter({hasText:'Schlüssel gespeichert.'}).waitFor();
  assert((await page.locator('#snapFeedback').innerText()).includes('Eingabefelder wurden geleert'));
  assert(await page.locator('#snapRemove').isEnabled(),'Saved key must be manageable immediately');
  assert(await page.locator('#snapCheck').isEnabled(),'No stale busy state after saving');
  assert.equal(await page.locator('#snapKey').inputValue(),'');assert.equal(await page.locator('#snapClient').inputValue(),'');
  assert(await page.evaluate(()=>calls.some(x=>x.url==='/api/snaptrade/configure'&&JSON.parse(x.body).personalFreeConfirmed===true)));
  assert(await page.evaluate(()=>Object.keys(localStorage).length===0));
  // A provider name is text; receiving a position is not an ISIN or quote proof.
  await page.evaluate(()=>{state={code:'READ_OK',configured:true,nextCheckSeconds:0,fresh:false,snapshot:{accounts:[{positions:[{name:'<img src=x onerror=alert(1)>',units:'2.5'}],cash:[{currency:'CHF',amount:'12.34'}],freshnessMode:'delayed-or-unknown'}]}};});
  await page.locator('#snapCheck').click();await page.getByText('ISIN nicht nachgewiesen',{exact:false}).waitFor();
  assert.equal(await page.locator('#snapHoldings img').count(),0);
  assert((await page.locator('#snapClock').innerText()).includes('nicht als aktuell bestätigt'));
  // Provider prices, missing acquisition values, journal failures and history stay distinct.
  await page.evaluate(()=>{
   const account=state.snapshot.accounts[0];account.accountKey='test-account';account.netValue={amount:'105',currency:'CHF'};
   Object.assign(account.positions[0],{kind:'stock',valuationPrice:'8',costBasis:'10',marketValue:'20',unrealizedPnl:'-5',unrealizedPercent:'-20',currency:'CHF'});
   account.journal={orders:{code:'UNAVAILABLE',checkedAt:null,rows:[]},activities:{code:'READ_OK',checkedAt:'2026-10-20T12:00:00Z',complete:true,rows:[{name:'<img src=x>',date:'2026-10-20',type:'CONTRIBUTION',currency:'CHF',amount:'100',fee:null}]}};
   state.snapshot.historyPersistence='SAVED';state.snapshot.history=[{at:'2026-10-20T12:00:00Z',complete:true,accounts:[{accountKey:account.accountKey,netValue:{amount:'100',currency:'CHF'}}]},{at:'2026-10-21T12:00:00Z',complete:true,accounts:[{accountKey:account.accountKey,netValue:account.netValue}]}];
  });
  await page.evaluate(()=>poll());
  assert((await page.locator('#snapHoldings').innerText()).includes('Offener Gewinn/Verlust: -5 CHF (-20.00 %)'));
  await page.locator('#snapHistorytest-account > summary').click();
  assert.equal(await page.locator('#snapHoldings svg').count(),1);
  assert((await page.locator('#snapHistorytest-account').innerText()).includes('Depotwert ist kein Gewinn'));
  await page.locator('#snapJournaltest-account > summary').click();
  assert((await page.locator('#snapJournaltest-account').innerText()).includes('Abruf nicht verfügbar'));
  await page.evaluate(()=>{
   const item=state.snapshot.accounts[0].journal.activities;
   item.activitySourceTotal=12599;
   item.activityCoverageReason='PAGE_LIMIT';
   item.complete=false;
   item.conflictingActivityIdentifiers=2;
   poll();
  });
  const coverageText=await page.locator('#snapJournaltest-account').innerText();
  assert(coverageText.includes('1 von 12599 gemeldeten Buchungen'));
  assert(coverageText.includes('Teilabruf gespeichert; Fortsetzung im nächsten zulässigen Abgleich'));
  assert(coverageText.includes('2 Gruppen vorsorglich ausgelassen'));
  assert(coverageText.includes('keine vollständige Ergebnisrechnung'));
  await page.evaluate(()=>{
   state.snapshot.accounts[0].journal.tradeCoverage={
     code:'READ_OK', checkedAt:'2026-10-24T10:00:00Z', filter:'BUY,SELL',
     totalMatching:2704, observed:2704, buyCount:1352, sellCount:1352,
     validIsinCount:2704, distinctIsins:16,
     currentHoldingsIsinMatches:10, missingOrInvalidIsinCount:1503,
     holdingBreakdown:[
      {isin:'DE000FG309G0', buys:3, sells:7, firstDay:'2026-10-01',lastDay:'2026-10-24'},
      {isin:'DE000FG14AV8', buys:0, sells:0, firstDay:null,lastDay:null}
     ], holdingBreakdownTruncated:false,
     earliestTradeDay:'2023-01-10',
     latestTradeDay:'2026-10-24', completeFilteredTradeWindow:true,
     accountHistoryComplete:false, fifoEligible:false
   };
   poll();
  });
  await page.locator('#snapFilteredTradestest-account > summary').click();
  const tradesText=await page.locator('#snapFilteredTradestest-account').innerText();
  assert(tradesText.includes('2704 von 2704'));
  assert(tradesText.includes('10 Buchungen'));
  assert(tradesText.includes('Keine Freigabe für FIFO-Gewinne'));
  assert(tradesText.includes('1503 Buchungen'));
  assert(tradesText.includes('DE000FG309G0: 3 Käufe · 7 Verkäufe'));
  assert(tradesText.includes('DE000FG14AV8: 0 Käufe · 0 Verkäufe'));
  assert.equal(await page.locator('#snapFilteredTradestest-account button').count(),2);
  assert.equal(await page.locator('#snapFilteredTradestest-account button').first().getAttribute('aria-label'),'DE000FG309G0 kopieren');
  assert(tradesText.includes('Keine vollständige Kontohistorie')||
         tradesText.includes('keine vollständige Kontohistorie'));
  await page.evaluate(()=>{
   const item=state.snapshot.accounts[0].journal.activities;
   item.code='UNAVAILABLE';item.failureCode='RATE_LIMITED';item.activityPagesReceived=3;
   item.failureAt='2026-10-24T12:00:00Z';poll();
  });
  const throttled=await page.locator('#snapJournaltest-account').innerText();
  assert(throttled.includes('Anbieter-Abrufbegrenzung'));
  assert(throttled.includes('3 Seiten vor dem Fehler gelesen'));
  assert(throttled.includes('nicht als neuer bestätigter Verlauf übernommen'));
  await page.evaluate(()=>{state.snapshot.accounts[0].journal.activities.code='READ_OK';poll();});
  await page.evaluate(()=>{state.snapshot.accounts[0].journal.orders.conflictingOrderIdentifiers=2;poll();});
  assert((await page.locator('#snapJournaltest-account').innerText()).includes('2 Gruppen vorsorglich ausgelassen'));
  assert.equal(await page.locator('#snapHoldings img').count(),0);
  await page.evaluate(()=>{state.snapshot.accounts[0].positions[0].valuationPrice='7.9';poll();});
  assert(await page.locator('#snapHistorytest-account').evaluate(el=>el.open),'Polling must preserve open history');
  // Automatic transaction results and quote observations remain separately labelled.
  await page.evaluate(()=>{
   const a=state.snapshot.accounts[0],p=a.positions[0];
   a.tradeJournal={sourceAt:'2026-10-21T12:00:00Z',sourceAvailable:true,historyComplete:true,
    events:[{name:'<img src=x>',type:'BUY',date:'2026-10-20',quantity:'2',price:'8',currency:'CHF',fee:null}],
    realized:[{name:'Synthetic',date:'2026-10-21',quantity:'1',openQuantityAfter:'1',cost:'8',proceeds:'9',grossPnl:'1',fees:null,netPnl:null,currency:'CHF'}],
    unresolved:[{name:'Synthetic',reason:'Gebühr nicht geliefert.'}],totals:[{currency:'CHF',grossPnl:'1',netPnl:null}],separateCharges:[],cashMovements:[]};
   p.issuerObservation={code:'CURRENT',kind:'issuer-chart',source:'Synthetic issuer chart',currency:'CHF',bid:'9',ask:'10',bidAt:'2026-10-21T12:00:00Z',askAt:'2026-10-21T12:00:00Z',bidFresh:true,askFresh:true,observedAt:'2026-10-21T12:00:01Z'};
   p.observedPositionValue='22.5';p.observedUnrealizedPnl='-2.5';
   a.evidenceQuality={orderRows:2,positiveFills:1,noPositiveFill:1,
    filledQuantityMissing:0,filledQuantityZero:1,filledQuantityInvalid:0,
    missingExecutionTime:1,missingVerifiedIsin:1,missingPrice:0,
    activityTrades:2,activityMissingFees:1};
   a.profitReadiness={accountHistoryComplete:false,unresolvedLots:1};
   a.tradeInsights={ordersAvailable:true,executionsCount:1,readyForHistoricalComparison:0,
    executions:[],feesByCurrency:[],reconciliation:{
     status:'available',candidatePairs:1,ambiguousGroups:2,
     missingEvidence:3,orderFillsWithoutExactActivity:4,
     accountHistoryComplete:false,netProfitVerified:false,
     pairs:[],reportedMatchedFeesByCurrency:[]
    }};
   poll();
  });
  await page.locator('#snapQualitytest-account > summary').click();
  const quality=await page.locator('#snapQualitytest-account').innerText();
  assert(quality.includes('Fehlende Ausführungszeit: 1'));
  assert(quality.includes('Ausführungsmenge ausdrücklich 0: 1'));
  assert(quality.includes('Ausführungsmenge fehlt beim Anbieter: 0'));
  assert(quality.includes('Offene Gebührenangaben bei Kauf/Verkauf: 1'));
  assert(quality.includes('Keine vollständige Gewinn- oder Steuerberechnung'));
  await page.locator('#snapExecutionstest-account > summary').click();
  await page.locator('#snapOrderFillstest-account > summary').click();
  await page.locator('#snapReconciliationtest-account > summary').click();
  const review=await page.locator('#snapReconciliationtest-account').innerText();
  assert(review.includes('Eindeutige Anbieter-Prüfkandidaten: 1'));
  assert(review.includes('Mehrdeutige Gruppen: 2'));
  assert(review.includes('Fehlende Zeit- oder Identitätsnachweise: 3'));
  assert(review.includes('Die vollständige Gewinnrechnung bleibt gesperrt'));
  assert((await page.locator('#snapExecutionstest-account').innerText()).includes('nicht vollständig berechenbar'));
  assert((await page.locator('#snapHoldings').innerText()).includes('Chartbeobachtung, kein ausführbarer Kurs'));
  assert((await page.locator('#snapHoldings').innerText()).includes('22.5 CHF'));
  assert.equal(await page.locator('#snapHoldings img').count(),0);
  // Existing on-device CSV stays local until explicit review and confirmation.
  const fs=require('node:fs');
  await page.addScriptTag({content:fs.readFileSync('degiro_portfolio_store.js','utf8')});
  await page.addScriptTag({content:fs.readFileSync('degiro_report_import.js','utf8')});
  await page.evaluate(()=>{
   const parsed=BobDegiroReport.readReport('Produkt;ISIN;Anzahl;Währung;Kurs;Wert;Einstandskurs\nExample Faktor 3 Lo...;DE000FG309G0;2;CHF;7;14;6\nOther Faktor;DE000FG14AV8;2;CHF;8;16;6');
   BobDegiroPortfolio.save(localStorage,parsed);
   const p=state.snapshot.accounts[0].positions[0];Object.assign(p,{name:'Example Faktor 3 Long R 1',positionKey:'test-position',symbol:'OPAQUE',kind:'other',stableInstrumentId:true,providerIsin:null,isin:null});
   window.csvCallsBefore=calls.filter(x=>x.url.endsWith('/csv-import')).length;
  });
  await page.evaluate(()=>poll());
  await page.locator('#snapCsvLink > summary').click();
  await page.locator('#snapCsvManual').evaluate(el=>{el.parentElement.open=true;});
  await page.locator('#snapCsvManual').click();
  assert.equal(await page.locator('#snapCsvProduct0').inputValue(),'DE000FG309G0','Name match may suggest, never confirm');
  assert.equal(await page.locator('#snapCsvConfirm0').isChecked(),false);
  await page.locator('#snapCsvSave').click();
  assert((await page.locator('#snapCsvFeedback').innerText()).includes('Bestätigungshaken'));
  assert(await page.evaluate(()=>calls.filter(x=>x.url.endsWith('/csv-import')).length===csvCallsBefore));
  await page.locator('#snapCsvConfirm0').check();
  await page.locator('#snapCsvProduct0').selectOption('DE000FG14AV8');
  assert.equal(await page.locator('#snapCsvConfirm0').isChecked(),false,'Changing the selected ISIN revokes confirmation');
  await page.locator('#snapCsvProduct0').selectOption('DE000FG309G0');
  await page.locator('#snapCsvConfirm0').check();await page.locator('#snapCsvSave').click();
  await page.locator('#snapCsvFeedback').filter({hasText:'CSV-Zuordnung gespeichert'}).waitFor();
  const csvPayload=await page.evaluate(()=>JSON.parse(calls.find(x=>x.url.endsWith('/csv-import')).body));
  assert.equal(csvPayload.accountKey,'test-account');assert.equal(csvPayload.records[0].isin,'DE000FG309G0');
  assert.equal(csvPayload.records[0].costBasis,6);assert.equal(csvPayload.links[0].confirmed,true);
  assert(!('consumerKey' in csvPayload));
  assert((await page.locator('#snapCsvFeedback').innerText()).includes('1 von 1'));
  // A checked box with no selected ISIN must not be silently omitted.
  await page.evaluate(()=>{state.snapshot.accounts[0].positions.push({name:'Unmatched test certificate',positionKey:'second-position',symbol:'SECOND',kind:'other',units:'2',currency:'CHF',stableInstrumentId:true,providerIsin:null,isin:null});poll();});
  await page.locator('#snapCsvManual').click();
  assert.equal(await page.locator('#snapCsvProduct1').inputValue(),'');
  await page.locator('#snapCsvConfirm1').check();
  const beforePartial=await page.evaluate(()=>calls.filter(x=>x.url.endsWith('/csv-import')).length);
  await page.locator('#snapCsvSave').click();
  assert((await page.locator('#snapCsvFeedback').innerText()).includes('ISIN-Auswahl oder der Bestätigungshaken'));
  assert.equal(await page.evaluate(()=>calls.filter(x=>x.url.endsWith('/csv-import')).length),beforePartial);
  assert(await page.locator('#snapCsvConfirm1').isChecked(),'Incomplete save preserves entered choices');
  await page.locator('#snapCsvProduct1').selectOption('DE000FG309G0');
  await page.locator('#snapCsvConfirm1').check();await page.locator('#snapCsvSave').click();
  assert((await page.locator('#snapCsvFeedback').innerText()).includes('mehrfach'));
  await page.locator('#snapCsvProduct1').selectOption('DE000FG14AV8');
  await page.locator('#snapCsvSave').click();
  assert((await page.locator('#snapCsvFeedback').innerText()).includes('Bestätigungshaken'));
  await page.locator('#snapCsvConfirm1').check();await page.locator('#snapCsvSave').click();
  await page.locator('#snapCsvFeedback').filter({hasText:'2 von 2'}).waitFor();
  assert((await page.locator('#snapHoldings').innerText()).includes('CSV-Zuordnung: 2 von 2 Positionen verknüpft'));
  await page.evaluate(()=>{
   const previous=window.fetch;
   window.fetch=async(url,options={})=>{
    if(url.endsWith('/csv-auto')){
     calls.push({url,body:options.body});
     state.snapshot.accounts[0].csvAutoReport={matched:0,total:1,unresolved:[{positionKey:'test-position',reason:'Kennung fehlt.'}]};
     return {ok:true,json:async()=>state};
    }
    return previous(url,options);
   };
  });
  await page.locator('#snapCsvPrepare').click();
  await page.locator('#snapCsvFeedback').filter({hasText:'Automatisch zugeordnet: 0 von 1'}).waitFor();
  assert.equal(await page.locator('#snapCsvConfirm0').count(),0,'Automatic workflow requires no per-ISIN checkbox');
  const autoPayload=await page.evaluate(()=>JSON.parse(calls.find(x=>x.url.endsWith('/csv-auto')).body));
  assert.deepEqual(autoPayload.links,[],'Server must establish identity itself');
  assert.equal(autoPayload.records.length,2);
  assert((await page.locator('#snapHoldings').innerText()).includes('Kennung fehlt.'));

  for(const width of [320,390]){
   await page.setViewportSize({width,height:844});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),'Mobile overflow');
  }
  // Only a visible DEGIRO view enables the 10-minute backend read cadence.
  // A hidden page must never wake the provider reader.
  const readCount=await page.evaluate(()=>calls.filter(x=>x.url==='/api/snaptrade/check').length);
  await page.evaluate(()=>{
   window.__realDateNow=Date.now;
   const actual=Date.now;Date.now=()=>actual()+120000;
   document.getElementById('bob-view-degiro').style.display='none';
   poll();
  });
  assert.equal(await page.evaluate(()=>calls.filter(x=>x.url==='/api/snaptrade/check').length),readCount,'Hidden DEGIRO view must not poll SnapTrade');
  await page.evaluate(()=>{document.getElementById('bob-view-degiro').style.display='block';poll();});
  await page.waitForFunction(expected=>calls.filter(x=>x.url==='/api/snaptrade/check').length>expected,readCount);
  const nextCount=await page.evaluate(()=>calls.filter(x=>x.url==='/api/snaptrade/check').length);
  await page.evaluate(()=>{poll();Date.now=window.__realDateNow;});
  assert.equal(await page.evaluate(()=>calls.filter(x=>x.url==='/api/snaptrade/check').length),nextCount,'Visible heartbeat cannot exceed its 60-second gate');
  await page.locator('#snapRemove').click();await page.locator('#snapStatus').filter({hasText:'Noch nicht verbunden.'}).waitFor();
  assert.equal(await page.locator('#snapHoldings').innerText(),'');assert.deepEqual(errors,[]);
  console.log('SnapTrade mobile: setup, secret clearing, no browser persistence, unknown proof, safe rendering and deletion passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
