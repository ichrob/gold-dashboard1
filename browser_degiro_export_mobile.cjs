/* Local DEGIRO CSV import, persistence, and Android layout regression. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const store=require('./degiro_portfolio_store');
function mockIsin(n){
 const base='DETEST'+String(n).padStart(5,'0');
 for(let i=0;i<10;i++)if(store.validIsin(base+i))return base+i;
 throw Error('No valid synthetic ISIN');
}
const ids=Array.from({length:5},(_,i)=>mockIsin(i+1));
const header='Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF';
const cash='CASH & CASH FUND & F, , , ,CHF,503.31,503.31';
const rows=ids.map((isin,i)=>'Test Faktor Produkt '+(i+1)+','+isin+','+(i+1)+',0.12,EUR,0.12,0.11');
const csv=[header,cash,...rows].join('\n');
const origin='https://bob.local.test';
const html='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'+
 '<style>*{box-sizing:border-box}body{margin:0;padding:8px}main{max-width:100%}</style></head><body>'+
 '<main><section id="bob-view-products"></section><section id="bob-view-degiro"></section></main>'+
 '<script src="/degiro_portfolio_store.js"></script><script src="/degiro_report_import.js"></script></body></html>';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:360,height:760},deviceScaleFactor:1});
  const page=await context.newPage(),requests=[];
  await page.route(origin+'/**',route=>{
   const pathname=new URL(route.request().url()).pathname;
   if(pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(pathname==='/degiro_portfolio_store.js'||pathname==='/degiro_report_import.js'){
    return route.fulfill({contentType:'application/javascript',
     body:fs.readFileSync(path.join(__dirname,pathname.slice(1)),'utf8')});
   }
   throw Error('Unexpected local request '+pathname);
  });
  page.on('request',req=>{if(!req.url().startsWith(origin+'/'))requests.push(req.url());});
  await page.goto(origin+'/');
  assert.equal(await page.locator('#dgExportPick').count(),1);
  assert((await page.locator('#dgStoredPortfolioStatus').innerText()).includes('Noch keine'));
  await page.locator('#dgExportFile').setInputFiles({name:'portfolio.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
  await page.waitForFunction(()=>document.querySelector('#dgExportStatus')?.textContent?.includes('dauerhaft in Bob'));
  assert.equal(await page.locator('.dg-export-card').count(),5);
  assert.equal(await page.locator('.dg-holding').count(),5);
  assert.equal(await page.locator('#dgExportResults table').count(),0);
  assert((await page.locator('.dg-export-card').first().innerText()).includes('0.12 EUR'));
  assert((await page.locator('.dg-holding').first().innerText()).includes('Faktorprodukt'));
  assert.equal(await page.locator('#dgExportFile').inputValue(),'');
  assert((await page.locator('#dgStoredPortfolioStatus').innerText()).includes('5 Produkte'));
  for(const width of [320,360,390]){
   await page.setViewportSize({width,height:760});
   const m=await page.evaluate(()=>({
    body:document.documentElement.scrollWidth,viewport:document.documentElement.clientWidth,
    card:document.querySelector('.dg-export-card').getBoundingClientRect().width,
    parent:document.querySelector('#bobDegiroReport').getBoundingClientRect().width
   }));
   assert(m.body<=m.viewport+1,'Horizontal overflow '+width+': '+JSON.stringify(m));
   assert(m.card<=m.parent+1,'Card overflow '+width+': '+JSON.stringify(m));
  }
  await page.reload();
  await page.waitForSelector('.dg-holding');
  assert.equal(await page.locator('.dg-holding').count(),5,'Products persist across browser reload');
  assert.equal(await page.locator('.dg-export-card').count(),5,'More tab restores from local snapshot');
  assert((await page.locator('#dgExportStatus').innerText()).includes('Gespeicherter DEGIRO-Depotstand'));
  const onlyTwo=[header,cash,...rows.slice(0,2)].join('\n');
  await page.locator('#dgExportFile').setInputFiles({name:'new-portfolio.csv',mimeType:'text/csv',buffer:Buffer.from(onlyTwo)});
  await page.waitForFunction(()=>document.querySelectorAll('.dg-holding').length===2);
  assert.equal(await page.locator('.dg-export-card').count(),2,'Replacement without duplicates');
  await page.locator('#dgExportFile').setInputFiles({
    name:'transactions.csv',mimeType:'text/csv',
    buffer:Buffer.from('Datum,ISIN,Quantity,Type\n19-10-2026,'+ids[0]+',1,Buy')
  });
  await page.waitForFunction(()=>document.querySelector('#dgExportStatus')?.textContent?.includes('Transaktionen gelesen'));
  assert.equal(await page.locator('.dg-holding').count(),2,'Transactions cannot erase portfolio');
  await page.locator('#dgExportClear').click();
  assert.equal(await page.locator('.dg-holding').count(),0);
  assert.equal(await page.locator('.dg-export-card').count(),0);
  await page.reload();
  assert.equal(await page.locator('.dg-holding').count(),0,'Deleting snapshot persists');
  assert.deepEqual(requests,[],'No external broker traffic');
  console.log('DEGIRO CSV: 5 products persistent under Bob Products, replacement, mobile and no broker traffic: passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
