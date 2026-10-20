/* Synthetic browser regression: all distinct DEGIRO holdings and watched products. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const {validIsin}=require('./degiro_all_products');
function testIsin(n){
 const base='DETEST'+String(n).padStart(5,'0');
 for(let k=0;k<10;k++)if(validIsin(base+k))return base+k;
 throw Error('No synthetic ISIN generated');
}
const ids=Array.from({length:12},(_,i)=>testIsin(i+1));
const csv=[
 'Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF',
 'CASH & CASH FUND & F, , , ,CHF,503.31,503.31',
 ...ids.slice(0,5).map((isin,i)=>'Test Faktor '+(i+1)+','+isin+',1,0.12,EUR,0.12,0.11')
].join('\n');
const audit={
 status:'stale',lastCheckedAt:'2026-10-19T19:34:00Z',
 items:ids.slice(4,12).map(isin=>({isin,direction:'SHORT',
  state:'analysis-evidence-complete',quoteSourceAt:'2026-10-19T19:33:00Z',
  tradeApproved:false,degiroVerified:false}))
};
const origin='https://bob.local.test';
const html='<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+
 '<style>*{box-sizing:border-box}body{margin:0;padding:8px}main{max-width:100%}</style></head><body><main>'+
 '<section id="bob-view-products"></section><section id="bob-view-degiro"></section></main>'+
 '<script src="/degiro_portfolio_store.js"></script>'+
 '<script src="/degiro_report_import.js"></script>'+
 '<script src="/degiro_all_products.js"></script></body></html>';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:360,height:760}});
  const external=[];
  page.on('request',r=>{if(!r.url().startsWith(origin+'/'))external.push(r.url());});
  await page.route(origin+'/**',route=>{
   const pathname=new URL(route.request().url()).pathname;
   if(pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(pathname==='/api/degiro/audit')
    return route.fulfill({contentType:'application/json',body:JSON.stringify(audit)});
   if(['/degiro_portfolio_store.js','/degiro_report_import.js','/degiro_all_products.js'].includes(pathname)){
    return route.fulfill({contentType:'application/javascript',
     body:fs.readFileSync(path.join(__dirname,pathname.slice(1)),'utf8')});
   }
   throw Error('Unexpected route '+pathname);
  });
  await page.goto(origin+'/');
  assert(await page.locator('#dgUnifiedDepotMissing').isVisible(),'No local depot must show import guidance');
  assert(await page.locator('#dgStoredCsvImport').isVisible(),'Separate depot section has CSV import button');
  assert.equal(await page.locator('#dgUnifiedImportCsv').getAttribute('data-view'),'degiro',
    'Guidance button navigates using Bob mobile navigation');
  await page.locator('#dgExportFile').setInputFiles({
   name:'portfolio.csv',mimeType:'text/csv',buffer:Buffer.from(csv)
  });
  await page.waitForFunction(()=>document.querySelector('#dgExportStatus')?.textContent?.includes('dauerhaft in Bob'));
  await page.evaluate(items=>localStorage.setItem('bobDegiroProductsV2',
   JSON.stringify({version:2,products:items.map(isin=>({
    isin,name:'Screenshot Watched '+isin,direction:'SHORT'})),
    listUploadedAt:'2026-10-19T06:29:00Z'})),ids.slice(4,12));
  await page.locator('#dgUnifiedRefresh').click();
  await page.waitForFunction(()=>document.querySelector('#dgUnifiedSummary')?.textContent?.includes('12 verschiedene Produkte'));
  assert.equal(await page.locator('#dgUnifiedCards .dg-unified-card').count(),12);
  assert((await page.locator('#dgUnifiedSummary').innerText()).includes('5 im Depot-CSV'));
  assert.equal(await page.locator('#dgUnifiedDepotMissing').isVisible(),false,
    'Import guidance hides when CSV is stored');
  assert.equal(await page.locator('#dgStoredCsvImport').isVisible(),false,
    'Stored CSV hides reimport reminder');
  const observedSummary=await page.locator('#dgUnifiedSummary').innerText();
  console.log('Unified browser counts:',JSON.stringify(observedSummary));
  assert(observedSummary.includes('8 in Beobachtung/Prüfbericht'),'Unexpected observation count: '+observedSummary);
  assert((await page.locator('#dgUnifiedSync').innerText()).includes('Keine DEGIRO-Konto-API'));
  assert((await page.locator('#dgUnifiedSync').innerText()).includes('Letzte tatsächliche serverseitige Produktprüfung'));
  assert((await page.locator('#dgUnifiedSync').innerText()).includes('Bob-Bericht im Browser abgerufen'));
  assert((await page.locator('#dgUnifiedSync').innerText()).includes('19.10.2026'));

  assert((await page.locator('#dgUnifiedCards').innerText()).includes('Handelsfreigabe über DEGIRO: nicht bestätigt'));
  assert((await page.locator('#dgUnifiedCards').innerText()).includes('Faktorprodukt'));
  await page.locator('#dgUnifiedFilter').selectOption('depot');
  assert.equal(await page.locator('#dgUnifiedCards .dg-unified-card').count(),5);
  await page.locator('#dgUnifiedFilter').selectOption('watch');
  assert.equal(await page.locator('#dgUnifiedCards .dg-unified-card').count(),8);
  await page.locator('#dgUnifiedFilter').selectOption('all');
  await page.locator('#dgUnifiedSearch').fill(ids[11]);
  assert.equal(await page.locator('#dgUnifiedCards .dg-unified-card').count(),1);
  await page.locator('#dgUnifiedSearch').fill('');
  for(const width of [320,360,390]){
   await page.setViewportSize({width,height:760});
   const values=await page.evaluate(()=>({
    width:document.documentElement.clientWidth,
    scroll:document.documentElement.scrollWidth,
    panel:document.querySelector('#dgCombinedProducts').getBoundingClientRect().width,
    card:document.querySelector('.dg-unified-card').getBoundingClientRect().width
   }));
   assert(values.scroll<=values.width+1,'Whole view overflows at '+width+': '+JSON.stringify(values));
   assert(values.card<=values.panel+1,'Card overflows at '+width);
  }
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#dgUnifiedSummary')?.textContent?.includes('12 verschiedene Produkte'));
  assert.equal(await page.locator('#dgUnifiedCards .dg-unified-card').count(),12);
  await page.locator('#dgExportClear').click();
  await page.waitForFunction(()=>document.querySelector('#dgUnifiedSummary')?.textContent?.includes('8 verschiedene Produkte'));
  assert.equal(await page.locator('#dgUnifiedCards .dg-unified-card').count(),8,'Clear only depot, not watched list');
  assert(await page.locator('#dgUnifiedDepotMissing').isVisible(),
    'Import guidance returns when user removes saved depot');
  assert(await page.locator('#dgStoredCsvImport').isVisible(),'Removed CSV reopens import prompt');
  assert.deepEqual(external,[],'No external DEGIRO account access or 3rd-party network');
  console.log('DEGIRO combined products UI passed: 12 unique, 5 depot, 8 watched, refresh, mobile and privacy');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
