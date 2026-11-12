/* Synthetic touch-screen acceptance for read-only manual DEGIRO quote comparison.
 * No accounts, real orders, external brokerage site, or authorization secrets.
 */
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const origin='https://bob-manual.test';
const scripts=['degiro_android_bridge.js','manual_ranking_order.js'];
const errors=[],outbound=[];
const html='<!doctype html><html lang="de"><head><meta charset="utf-8">'+
 '<meta name="viewport" content="width=device-width, initial-scale=1">'+
 '<style>*{box-sizing:border-box}body{margin:0;padding:10px;font:14px system-ui}'+
 '.card{max-width:100%}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:8px}'+
 'input,select,button{max-width:100%;width:100%;padding:8px;margin:3px 0 6px}'+
 'article{overflow-wrap:anywhere}details{max-width:100%;overflow-wrap:anywhere}'+
 '.small{font-size:12px}button{cursor:pointer}</style></head><body>'+
 '<main id="mobile"><section id="dgTop3Out">Rechnerische Top 3 – nur Vergleich</section></main>'+
 '<script src="/degiro_android_bridge.js"></script>'+
 '<script src="/manual_ranking_order.js"></script></body></html>';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:360,height:780},isMobile:true,deviceScaleFactor:3,hasTouch:true});
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',req=>{if(!req.url().startsWith(origin+'/'))outbound.push(req.url());});
  await page.route('**/*',route=>{
   const u=new URL(route.request().url());
   if(u.origin!==origin)return route.abort();
   if(u.pathname==='/')return route.fulfill({status:200,contentType:'text/html',body:html});
   const file=u.pathname.replace(/^\//,'');
   if(scripts.includes(file))return route.fulfill({status:200,contentType:'application/javascript',body:fs.readFileSync(path.join(__dirname,file),'utf8')});
   return route.fulfill({status:404,contentType:'text/plain',body:'Not found'});
  });
  await page.goto(origin+'/');
  const isin='DE000FG4JXV7';
  // Genuine provider and market functions are separately tested in unit CI;
  // this browser test deliberately stubs *only* the existing read-only UI inputs.
  await page.evaluate(isin=>{
   const at=new Date(Date.now()-10000).toISOString();
   window.__testAt=at;
   window.productMarketPlan=()=>({available:true,direction:'SHORT'});
   window.BobStopAssistant={compareQuoteSources:(_q,match)=>{
    if(match!==isin)throw Error('Wrong ISIN');
    return {quotes:[{isin,currency:'EUR',bid:19.9,ask:20,
       at,askAt:at,source:'Synthetic original issuer',kind:'issuer',origin:'issuer',
       chart:false}]};
   }};
   window.BobDegiro={productRiskPreview:(_p,_m,_now,q)=>({
     available:q?.isin===isin&&q?.ask===20,currency:'EUR',stop:18.5,referenceAt:at
   })};
   window.__candidate={isin,direction:'SHORT',score:82};
   window.__product={isin,productDirection:'SHORT',isinConfirmed:true,
      quote:{isin,currency:'EUR',productVerified:true,metadata:{currency:'EUR',status:1}}};
   window.__flow={approved:true,direction:'SHORT',groups:[{candidates:[window.__candidate]}]};
   window.__bundle={spots:{usd_chf_meta:{rate:0.9,fetchedAt:at},
     usd_eur_meta:{rate:0.9,fetchedAt:at}}};
   window.BobManualTop3.render(window.__flow,[window.__product],window.__bundle);
  },isin);
  const panel=page.locator('#bobManualTop3');
  await panel.waitFor({state:'visible'});
  assert((await panel.innerText()).includes(isin));
  await panel.locator('#bobManualBudget').fill('1000');
  await panel.locator('#bobManualRisk').fill('100');
  await panel.locator('#bobManualFees').fill('8');
  assert((await panel.innerText()).includes('49'),'Preliminary calculation is visible before broker data');
  const draft=['BOB OCR-ENTWURF – NICHT VERIFIZIERT','ISIN: '+isin,
   'Geld (OCR ungeprüft): 20,20','Brief (OCR ungeprüft): 20,30',
   'Handelsplatz (OCR ungeprüft): Societe Generale OTC',
   'Anzeigezeit (OCR ungeprüft): 12/11/2026 14:02'].join('\n');
  await page.evaluate(({draft,isin})=>{
    const saved=window.BobAndroidEvidence.storeObservation(localStorage,draft,[{isin}],Date.now());
    if(saved.state!=='saved')throw Error('Cannot store isolated synthetic OCR draft');
  },{draft,isin});
  await panel.locator('[data-manual-broker-compare] summary').click();
  await panel.locator('[data-manual-screen-import]').click();
  assert.equal(await panel.locator('#bobManualScreenBid').inputValue(),'20.2');
  assert.equal(await panel.locator('#bobManualScreenAsk').inputValue(),'20.3');
  assert.equal(await panel.locator('#bobManualScreenAt').inputValue(),'',
    'OCR transfer time never becomes a source quote timestamp');
  let result=await panel.locator('[data-manual-broker-result]').innerText();
  assert(result.includes('Original-Kurszeit'),'OCR import requires checking source clock');
  const currentAt=await page.evaluate(()=>new Date(Date.now()-10000).toISOString());
  await panel.locator('#bobManualScreenCcy').selectOption('EUR');
  await panel.locator('#bobManualScreenAt').fill(currentAt);
  await panel.locator('#bobManualScreenFunds').fill('900');
  await panel.locator('#bobManualScreenFx').fill('0.9');
  await panel.locator('#bobManualScreenFxAt').fill(currentAt);
  await panel.locator('#bobManualScreenTick').fill('0.01');
  await panel.locator('#bobManualScreenLot').fill('1');
  await panel.locator('#bobManualScreenOrderType').selectOption('LIMIT');
  await panel.locator('#bobManualScreenDuration').selectOption('DAY');
  result=await panel.locator('[data-manual-broker-result]').innerText();
  assert(result.includes('Noch kein gültiger'),'Editing fields must invalidate confirmation');
  await panel.locator('[data-manual-screen-confirm]').click();
  result=await panel.locator('[data-manual-broker-result]').innerText();
  assert(result.includes('20.3000'),'Broker display ask price replaces preliminary 20.0000');
  assert(result.includes('48 ganze Stück'),'Quantity recalculated against updated broker display');
  assert(result.includes('keine automatische Kauf-/Verkaufsorder'),'No order action');
  assert.equal(await panel.locator('button[data-manual-copy]').count()>=1,true,'ISIN copy only');
  await panel.locator('#bobManualScreenAt').fill('2026-11-03T12:00:00Z');
  await panel.locator('[data-manual-screen-confirm]').click();
  result=await panel.locator('[data-manual-broker-result]').innerText();
  assert(result.includes('Noch kein gültiger'),'Expired quote is rejected');
  await panel.locator('#bobManualScreenAt').fill(currentAt);
  await panel.locator('#bobManualScreenAsk').fill('18.00');
  await panel.locator('#bobManualScreenBid').fill('17.99');
  await panel.locator('[data-manual-screen-confirm]').click();
  result=await panel.locator('[data-manual-broker-result]').innerText();
  assert(result.includes('Noch kein gültiger'),'Broker ask beneath model stop is rejected');
  await panel.locator('#bobManualScreenAsk').fill('20.30');
  await panel.locator('#bobManualScreenBid').fill('20.20');
  await panel.locator('[data-manual-screen-confirm]').click();
  assert((await panel.locator('[data-manual-broker-result]').innerText()).includes('48 ganze Stück'));
  for(const width of [320,360,390]){
    await page.setViewportSize({width,height:780});
    const dims=await page.evaluate(()=>({client:document.documentElement.clientWidth,
      scroll:document.documentElement.scrollWidth}));
    assert(dims.scroll<=dims.client+1,'Manual mobile panel overflows at '+width+': '+JSON.stringify(dims));
  }
  await page.screenshot({path:'manual-order-mobile.png',fullPage:true});
  assert.deepEqual(errors,[],'No browser errors');
  assert.deepEqual(outbound,[],'No external brokerage/network calls');
  console.log('Mobile synthetic UI: OCR import, no invented time, broker repricing, quantity, stale/KO rejection, 320–390px, no external requests or orders passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
