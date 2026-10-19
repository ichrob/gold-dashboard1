/* Browser layout regression with synthetic DEGIRO data. Uses the CI Playwright browser. */
'use strict';
const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:360,height:760},deviceScaleFactor:1});
  const brokerRequests=[];
  page.on('request',req=>{if(/^https?:/.test(req.url()))brokerRequests.push(req.url());});
  await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="bob-view-degiro"></main></body></html>');
  await page.addScriptTag({path:path.join(__dirname,'degiro_report_import.js')});
  assert.equal(await page.locator('#dgExportPick').count(),1);
  const sample=[
   'Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF',
   'CASH & CASH FUND & F, , , ,CHF,503.31,503.31',
   'SG GOLD FUTURE FAKTOR LONG HB 15,DE000FE4UF84,1,0.12,EUR,0.12,0.11'
  ].join('\n');
  await page.locator('#dgExportFile').setInputFiles({name:'portfolio.csv',mimeType:'text/csv',buffer:Buffer.from(sample)});
  await page.waitForFunction(()=>document.querySelector('#dgExportStatus')?.textContent?.includes('Datei eingelesen'));
  assert.equal(await page.locator('.dg-export-card').count(),1);
  assert.equal(await page.locator('#dgExportResults table').count(),0);
  assert((await page.locator('.dg-export-card').innerText()).includes('0.12 EUR'));
  assert((await page.locator('.dg-export-card').innerText()).includes('Faktorprodukt'));
  assert.equal(await page.locator('#dgExportFile').inputValue(),'');
  for(const width of [320,360,390]){
   await page.setViewportSize({width,height:760});
   const measured=await page.evaluate(()=>({
    body:document.documentElement.scrollWidth,
    viewport:document.documentElement.clientWidth,
    card:document.querySelector('.dg-export-card').getBoundingClientRect().width,
    view:document.querySelector('#bobDegiroReport').getBoundingClientRect().width
   }));
   assert(measured.body<=measured.viewport+1,'Horizontal overflow at '+width+'px: '+JSON.stringify(measured));
   assert(measured.card<=measured.view+1,'Card overflows its container at '+width+'px');
  }
  assert.deepEqual(brokerRequests,[],'Local CSV parsing must not call DEGIRO or any external site');
  await page.locator('#dgExportClear').click();
  assert.equal(await page.locator('.dg-export-card').count(),0,'Clearing removes portfolio from DOM');
  assert((await page.locator('#dgExportStatus').innerText()).includes('Keine Daten eingelesen'));
  console.log('DEGIRO mobile Playwright layouts passed (320, 360, 390px)');
 }finally{
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
