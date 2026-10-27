'use strict';
/* Mobile synthetic regression: no live account, provider or brokerage calls. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const api=require('./bob_unified_workspace.js');
const origin='https://bob-workspace.test';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOB_TEST_CHROMIUM||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:360,height:780}});
  const errors=[],requests=[];
  let explained=false;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.url()!==origin+'/'&&!r.url().endsWith('/favicon.ico'))requests.push(r.url());});
  await page.route(origin+'/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/api/degiro/audit')return route.fulfill({contentType:'application/json',body:JSON.stringify({
    status:'ok',lastCheckedAt:new Date().toISOString(),items:[{isin:'DE000FG14AV8'}],incomplete:1
   })});
   if(path==='/api/operations-summary')return route.fulfill({contentType:'application/json',body:JSON.stringify({
    version:1,actionStatus:'known',actions:[],productStatus:{state:explained?'differences-explained':'conflict',conflicts:[{isin:'DE000FG14AV8',fields:['ko'],resolution:explained?'Datierte Emittentenangabe gewählt':'Originalquelle prüfen'}]},
    cases:[{}],jobs:[{label:'Simulation',state:'unavailable',lastSuccessAt:null,lastObservedAt:null,expectedNextAt:null}],
    historicalPolicy:{note:'Historischer Abschluss ist kein Gewinn.'},comparisonPolicy:{note:'Keine automatische Regeländerung.'}
   })});
   if(path==='/api/problems')return route.fulfill({contentType:'application/json',body:JSON.stringify({
    status:'ok',count:1,problems:[{number:726,code:'product-terms-evidence-missing'}]
   })});
   return route.fulfill({
   contentType:'text/html; charset=utf-8',
   body:'<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:6px}section.card{padding:8px}button{max-width:100%;white-space:normal}</style></head><body>'+
     '<section id="bob-view-overview"><h2>Übersicht</h2></section>'+
     '<section id="bob-view-degiro2"></section>'+
     '<select id="dg2-product"><option value="">Manuell</option><option value="DE000FG14AV8">Goldtest</option></select>'+
     '<div id="quickSignal">ABWARTEN</div><div id="quickReason">noch nicht aktuell</div>'+
     '</body></html>'
  });
  });
  await page.goto(origin+'/');
  await page.evaluate(()=>{
   window.calls={load:0,quotes:0,handOff:0};
   window.BobSession={expired:()=>false};
   window.BobTradeSync={current:()=>({active:false})};
   window.BobDegiro={
    tradeTestProducts:()=>[],
    refreshTradeTestQuotes:async()=>{calls.quotes++}
   };
   window.loadData=async(force)=>{
    if(force!==true)throw Error('Must use standard explicit refresh');
    calls.load++;
    window.liveBundleCache={spots:{spot_price_as_of:new Date().toISOString(),is_genuine_xauusd_spot:true}};
    window.A={ready:true};
    document.getElementById('quickSignal').textContent='LONG';
    document.getElementById('quickReason').textContent='Signal bestätigt';
   };
   document.getElementById('dg2-product').addEventListener('change',()=>{calls.handOff++});
   document.addEventListener('click',e=>{const button=e.target.closest?.('[data-view]');if(button)window.lastView=button.dataset.view;});
  });
  await page.addScriptTag({content:fs.readFileSync('product_evidence_contract.js','utf8')});
  await page.addScriptTag({content:fs.readFileSync('bob_unified_workspace.js','utf8')});
  assert(await page.locator('#bobUnifiedWorkspace').isVisible());
  // Product report should appear immediately without explicit preparation,
  // even when there are no manual DEGIRO rows or archived screenshot rows.
  await page.waitForFunction(()=>document.getElementById('bobUnifiedChecks')
     ?.textContent?.includes('1 identifizierte Produkte'));
  assert.equal(await page.locator('#bobUnifiedProduct option').count(),2);
  await page.locator('#bobGoldProductBanner').filter({hasText:'1 unterschiedliche ISINs'}).waitFor();
  assert((await page.locator('#bobGoldProductBanner').innerText()).includes('Keine Handelsfreigabe'));
  assert(await page.locator('#bobOpenGoldProducts').isVisible());
  await page.locator('#bobGoldProductList summary').click();
  assert(await page.locator('#bobGoldProductRows').isVisible());
  assert((await page.locator('#bobGoldProductRows').innerText()).includes('DE000FG14AV8'));
  assert((await page.locator('#bobGoldProductRows').innerText()).includes('keine Handelsfreigabe'));
  assert.deepEqual(await page.evaluate(()=>window.calls),{load:0,quotes:0,handOff:0},
    'Initial audit is read-only, no market reload/issuer query or handoff');
  await page.evaluate(()=>{
    window.BobDegiro.tradeTestProducts=()=>[{isin:'DE000FG14AV8',name:'Gold LONG',direction:'LONG',
     quote:{isin:'DE000FG14AV8',found:true,productVerified:true,currency:'EUR',
      metadata:{currency:'EUR',direction:'LONG',status:1},bid:10,ask:10.1,
      bidAt:new Date().toISOString(),askAt:new Date().toISOString(),
      source:'Emittent-Beobachtung',leverage:14,leverageAt:new Date().toISOString()}}];
  });
  await page.evaluate(()=>{
    localStorage.setItem('bobDegiroProductsV2',JSON.stringify({
      version:2,listUploadedAt:new Date(Date.now()-90000).toISOString(),
      products:[{isin:'DE000FG14AV8'},{isin:'US0378331005'}]
    }));
  });
  await page.locator('#bobPrepareReadOnly').click();
  await page.locator('#bobPrepareStatus').filter({hasText:'Marktdaten geprüft.'}).waitFor();
  const values=await page.evaluate(()=>window.calls);
  assert.deepEqual(values,{load:1,quotes:1,handOff:0});
  assert((await page.locator('#bobUnifiedUploadedDiff').innerText()).includes('Ausgangsstand'));
  await page.evaluate(()=>{
    localStorage.setItem('bobDegiroProductsV2',JSON.stringify({
      version:2,listUploadedAt:new Date(Date.now()-1000).toISOString(),
      products:[{isin:'US0378331005'}]
    }));
  });
  await page.locator('#bobPrepareReadOnly').click();
  await page.waitForFunction(()=>document.getElementById('bobUnifiedUploadedDiff').textContent.includes('1 in der neuen Liste fehlende ISIN'));
  assert((await page.locator('#bobUnifiedUploadedDiff').innerText()).includes('Kein aktueller DEGIRO-Handelsnachweis'));
  await page.locator('#bobUnifiedCheckOperations').click();
  await page.locator('#bobUnifiedOperations').filter({hasText:'1 Produkt mit fehlenden Nachweisen'}).waitFor();
  assert((await page.locator('#bobUnifiedOperations').innerText()).includes('1 offene öffentliche technische KI-Hilfeanfragen'));
  assert((await page.locator('#bobUnifiedOperations').innerText()).includes('Keine Echtgeldorder'));
  assert((await page.locator('#bobRequiredActions').innerText()).includes('keine bestätigte persönliche Aufgabe'));
  assert((await page.locator('#bobOperationsDetail').textContent()).includes('Quellenentscheidung offen'));
  assert((await page.locator('#bobOperationsDetail').textContent()).includes('Letzter Erfolg: unbekannt'));
  explained=true;
  await page.locator('#bobUnifiedCheckOperations').click();
  await page.waitForFunction(()=>document.getElementById('bobOperationsDetail').textContent.includes('Quellenabweichungen eingeordnet'));
  assert((await page.locator('#bobOperationsDetail').textContent()).includes('Datierte Emittentenangabe gewählt'));
  assert(!(await page.locator('#bobOperationsDetail').textContent()).includes('Quellenentscheidung offen'));
  await page.locator('#bobUnifiedProduct').selectOption('DE000FG14AV8');
  assert((await page.locator('#bobUnifiedProductNote').innerText()).includes('kein bestätigter DEGIRO-Kurs')||
    (await page.locator('#bobUnifiedProductNote').innerText()).includes('Kein bestätigter DEGIRO-Kurs'));
  assert((await page.locator('#bobUnifiedEvidenceRows').textContent()).includes('Geld 10 / Brief 10.1'));
  assert((await page.locator('#bobUnifiedEvidenceRows').textContent()).includes('KO-Originalnachweis fehlt'));
  assert((await page.locator('#bobUnifiedEvidenceRows').textContent()).includes('keine DEGIRO-Orderquotierung'));
  assert((await page.locator('#bobUnifiedEvidenceRows').textContent()).includes('DEGIRO-Handelsplatz'));
  await page.locator('#bobUnifiedProduct').selectOption('');
  assert((await page.locator('#bobUnifiedEvidenceRows').textContent()).includes('Geld/Brief und Originalzeiten fehlen'));
  await page.locator('#bobUnifiedProduct').selectOption('DE000FG14AV8');
  await page.locator('#bobUnifiedToDraft').click();
  assert.equal(await page.locator('#dg2-product').inputValue(),'DE000FG14AV8');
  assert.equal(await page.evaluate(()=>window.lastView),'degiro2');
  assert.equal(await page.evaluate(()=>window.calls.handOff),1);
  // Screenshot regression: no manually visible DEGIRO rows, but the private
  // audit + locally archived screenshot list still contain identities.
  await page.evaluate(()=>{window.BobDegiro.tradeTestProducts=()=>[]});
  await page.locator('#bobPrepareReadOnly').click();
  await page.locator('#bobPrepareStatus').filter({hasText:'Marktdaten geprüft.'}).waitFor();
  assert((await page.locator('#bobUnifiedChecks').innerText()).includes('2 identifizierte Produkte'));
  assert.equal(await page.locator('#bobUnifiedProduct option').count(),3);
  await page.locator('#bobUnifiedProduct').selectOption('DE000FG14AV8');
  assert((await page.locator('#bobUnifiedEvidenceRows').textContent()).includes('Geld/Brief und Originalzeiten fehlen'));
  assert((await page.locator('#bobUnifiedProductNote').innerText()).includes('Bob-Prüfbericht'));
  await page.locator('#bobUnifiedToDraft').click();
  assert.equal(await page.evaluate(()=>window.calls.handOff),1,
    'Audit identity alone must never authorize manual draft transfer');
  assert((await page.locator('#bobUnifiedProductNote').innerText()).includes('nicht bestätigt'));
  const widest=await page.locator('#bobUnifiedWorkspace').evaluate(el=>el.scrollWidth);
  assert(widest<=360,'Workspace must fit 360px mobile viewport; got '+widest);

  const today=api.zurichDay(),backup=api.serializeDraftBackup({
   day:today,currency:'EUR',budget:10000,
   orders:[{isin:'DE000FG14AV8',side:'Kauf',qty:2,price:1100,fees:100,cost:2300,stop:900,target:1400}]
  });
  await page.evaluate(()=>{window.restoreCount=0;window.addEventListener('bob-order-drafts-restored',()=>restoreCount++)});
  await page.locator('#bobRestoreOrdersFile').setInputFiles({
   name:'bob-tagesentwuerfe.json',mimeType:'application/json',buffer:Buffer.from(backup)
  });
  await page.waitForFunction(()=>document.getElementById('bobBackupStatus')?.textContent?.includes('wiederhergestellt'));
  assert.equal(await page.evaluate(()=>restoreCount),1);
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('bob.degiro2.plan.v1')).orders.length),1);
  await page.locator('#bobRestoreOrdersFile').setInputFiles({
   name:'again.json',mimeType:'application/json',buffer:Buffer.from(backup)
  });
  await page.waitForFunction(()=>document.getElementById('bobBackupStatus')?.textContent?.includes('nicht erfolgt'));
  assert.deepEqual(requests.sort(),[origin+'/api/degiro/audit',origin+'/api/problems',origin+'/api/problems',origin+'/api/operations-summary'].sort(),
   'Only the four expected read-only status API requests; no broker/external calls');
  assert.deepEqual(errors,[],'No client-side JavaScript errors');
  console.log('Bob unified mobile: 360px layout, one-click existing fetch, product handoff and safe backup recovery passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
