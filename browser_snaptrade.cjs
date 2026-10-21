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
  assert.equal(await page.locator('#snapHoldings img').count(),0);
  await page.evaluate(()=>{state.snapshot.accounts[0].positions[0].valuationPrice='7.9';poll();});
  assert(await page.locator('#snapHistorytest-account').evaluate(el=>el.open),'Polling must preserve open history');
  // Existing on-device CSV stays local until explicit review and confirmation.
  const fs=require('node:fs');
  await page.addScriptTag({content:fs.readFileSync('degiro_portfolio_store.js','utf8')});
  await page.addScriptTag({content:fs.readFileSync('degiro_report_import.js','utf8')});
  await page.evaluate(()=>{
   const parsed=BobDegiroReport.readReport('Produkt;ISIN;Anzahl;Währung;Kurs;Wert;Einstandskurs\nExample Faktor 3;DE000FG309G0;2;CHF;7;14;6');
   BobDegiroPortfolio.save(localStorage,parsed);
   const p=state.snapshot.accounts[0].positions[0];Object.assign(p,{name:'Example Faktor 3',positionKey:'test-position',symbol:'OPAQUE',kind:'other',stableInstrumentId:true,providerIsin:null,isin:null});
   window.csvCallsBefore=calls.filter(x=>x.url.endsWith('/csv-import')).length;
  });
  await page.evaluate(()=>poll());
  await page.locator('#snapCsvLink > summary').click();
  await page.locator('#snapCsvPrepare').click();
  assert.equal(await page.locator('#snapCsvProduct0').inputValue(),'DE000FG309G0','Name match may suggest, never confirm');
  assert.equal(await page.locator('#snapCsvConfirm0').isChecked(),false);
  await page.locator('#snapCsvSave').click();
  assert((await page.locator('#snapCsvFeedback').innerText()).includes('bestätigen'));
  assert(await page.evaluate(()=>calls.filter(x=>x.url.endsWith('/csv-import')).length===csvCallsBefore));
  await page.locator('#snapCsvConfirm0').check();await page.locator('#snapCsvSave').click();
  await page.locator('#snapCsvFeedback').filter({hasText:'CSV-Zuordnung gespeichert'}).waitFor();
  const csvPayload=await page.evaluate(()=>JSON.parse(calls.find(x=>x.url.endsWith('/csv-import')).body));
  assert.equal(csvPayload.accountKey,'test-account');assert.equal(csvPayload.records[0].isin,'DE000FG309G0');
  assert.equal(csvPayload.records[0].costBasis,6);assert.equal(csvPayload.links[0].confirmed,true);
  assert(!('consumerKey' in csvPayload));
  for(const width of [320,390]){
   await page.setViewportSize({width,height:844});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),'Mobile overflow');
  }
  await page.locator('#snapRemove').click();await page.locator('#snapStatus').filter({hasText:'Noch nicht verbunden.'}).waitFor();
  assert.equal(await page.locator('#snapHoldings').innerText(),'');assert.deepEqual(errors,[]);
  console.log('SnapTrade mobile: setup, secret clearing, no browser persistence, unknown proof, safe rendering and deletion passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
