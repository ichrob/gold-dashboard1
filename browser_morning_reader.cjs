'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const evidence=fs.readFileSync('degiro_android_bridge.js','utf8'),source=fs.readFileSync('degiro_morning_reader.js','utf8');
const at=new Date().toISOString(),isin='DE000FD0S0G4';
const draft=['BOB APP-LESEENTWURF – NICHT VERIFIZIERT','ISIN: '+isin,'Quelle: DEGIRO-App','Erfasst: '+at,'Währung (Anzeige ungeprüft): EUR','Geld (Anzeige ungeprüft): 13,06','Brief (Anzeige ungeprüft): 13,07','Hinweis (Anzeige ungeprüft): Keine Aussage zur Handelbarkeit','Kein automatischer Handelsnachweis, keine Freigabe, keine Order.'].join('\n');
const run={batchId:'a'.repeat(32),revision:4,listUploadedAt:at,isins:[isin],results:[{isin,attempts:2,draft,code:'PARTIAL',missingFields:['Hebel']}],events:[]};
const encode=require('./degiro_morning_reader.js').encode;
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:390,height:844}});let calls=0,accept=false;
 await page.route('https://bob.local.test/**',async route=>{
  if(route.request().url().includes('/api/degiro/android-observations')){
   calls++;const body=route.request().postDataJSON();assert.equal(body.run.batchId,run.batchId);
   return route.fulfill({status:accept?200:401,contentType:'application/json',body:JSON.stringify({ok:accept,saved:accept,batchId:run.batchId,revision:4})});
  }
  return route.fulfill({contentType:'text/html',body:'<section id="bob-view-degiro"></section>'});
 });
 async function scripts(){await page.evaluate(()=>{window.BobDegiro={tradeTestProducts:()=>[]};});await page.addScriptTag({content:evidence});await page.addScriptTag({content:source});}
 await page.goto('https://bob.local.test/#bob-read-results='+encode(run));await scripts();
 await page.waitForFunction(()=>document.querySelector('#bobMorningReader').textContent.includes('Bitte in Bob anmelden'));
 assert.equal(calls,1);assert.equal(await page.evaluate(()=>location.hash),'');
 assert.ok(await page.evaluate(()=>localStorage.getItem('bobMorningReadPendingV1')));
 await page.reload();accept=true;await scripts();
 await page.waitForFunction(()=>!localStorage.getItem('bobMorningReadPendingV1'));
 assert.equal(calls,2);
 assert.match(await page.locator('#bobMorningReader').innerText(),/in Bob gespeichert/);
 assert.match(await page.locator('#bobMorningReader a').getAttribute('href'),/revision=4/);
 assert.ok(await page.evaluate(()=>localStorage.getItem('bobAndroidProductObservationsV1')));
 await page.goto('about:blank');
 await page.goto('https://bob.local.test/#bob-read-list='+'b'.repeat(32));
 await page.evaluate(at=>{window.BobDegiro={tradeTestProducts:()=>[],readServerProductList:async()=>({listUploadedAt:at,products:[{isin:'DE000FD0S0G4'}]})};},at);
 await page.addScriptTag({content:evidence});await page.addScriptTag({content:source});
 await page.waitForFunction(()=>document.querySelector('#bobMorningReader a').href.includes('/list?nonce='));
 const href=await page.locator('#bobMorningReader a').getAttribute('href');
 assert.ok(href.includes('nonce='+'b'.repeat(32)));
 assert.deepEqual(require('./degiro_morning_reader.js').decode(href.split('#')[1]).isins,[isin]);
 console.log('Browser morning reader: authenticated list handoff, failed upload retained, reload retry, exact revision ACK passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
