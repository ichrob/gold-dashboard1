'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const source=fs.readFileSync('degiro_android_bridge.js','utf8');
const draft=['BOB APP-LESEENTWURF – NICHT VERIFIZIERT','ISIN: DE000FG77MY4','Quelle: DEGIRO-App',
 'Erfasst: 2026-10-28T06:55:44Z','Währung (Anzeige ungeprüft): EUR','Geld (Anzeige ungeprüft): 11,14',
 'Brief (Anzeige ungeprüft): 11,16','Anzeigezeit (Anzeige ungeprüft): 28/10/2026 07:55',
 'Hinweis (Anzeige ungeprüft): Keine Aussage zur Handelbarkeit','Kein automatischer Handelsnachweis, keine Freigabe, keine Order.'].join('\n');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.route('https://bob.local.test/**',route=>route.fulfill({contentType:'text/html',body:'<section id="bob-view-degiro"></section>'}));
  await page.goto('about:blank');
  await page.goto('https://bob.local.test/#bob-ocr='+encodeURIComponent(draft));
  await page.addScriptTag({content:source});
  assert.equal(await page.evaluate(()=>location.hash),'');
  assert.ok(await page.evaluate(()=>localStorage.getItem('bobAndroidPendingObservationV1')));
  await page.evaluate(()=>{window.BobDegiro={tradeTestProducts:()=>[{isin:'DE000FG77MY4'}]};});
  await page.waitForFunction(()=>localStorage.getItem('bobAndroidProductObservationsV1'));
  assert.match(await page.locator('#bobAndroidEvidence').innerText(),/Automatisch über die ISIN zugeordnet/);
  assert.match(await page.locator('#bobAndroidEvidence').innerText(),/Geld 11,14 · Brief 11,16/);
  await page.reload();
  await page.evaluate(()=>{window.BobDegiro={tradeTestProducts:()=>[{isin:'DE000FG77MY4'}]};});
  await page.addScriptTag({content:source});
  await page.locator('#bobAndroidEvidence summary').click();
  assert.match(await page.locator('#bobAndroidEvidence').innerText(),/Geld 11,14 · Brief 11,16/);
  await page.getByRole('button',{name:'Gespeicherte Lesebeobachtungen löschen',exact:true}).click();
  assert.equal(await page.evaluate(()=>localStorage.length),0);
  // A different browser can have empty UI rows while the existing server list
  // contains the product. Keep the draft over reload and match read-only.
  await page.goto('about:blank');
  await page.goto('https://bob.local.test/#bob-ocr='+encodeURIComponent(draft));
  await page.evaluate(()=>{window.BobDegiro={tradeTestProducts:()=>[]};});
  await page.addScriptTag({content:source});
  assert.ok(await page.evaluate(()=>localStorage.getItem('bobAndroidPendingObservationV1')));
  assert.equal(await page.evaluate(()=>localStorage.getItem('bobAndroidProductObservationsV1')),null);
  await page.reload();
  await page.evaluate(()=>{window.BobDegiro={tradeTestProducts:()=>[],readServerProductList:async()=>({products:[{isin:'DE000FG77MY4'}],listUploadedAt:'2026-10-28T07:09:32Z'})};});
  await page.addScriptTag({content:source});
  await page.waitForFunction(()=>localStorage.getItem('bobAndroidProductObservationsV1'));
  assert.equal(await page.evaluate(()=>localStorage.getItem('bobAndroidPendingObservationV1')),null);
  assert.match(await page.locator('#bobAndroidEvidence').innerText(),/Automatisch über die ISIN zugeordnet/);
  assert.match(await page.locator('#bobAndroidEvidence').innerText(),/Listenstand: 2026-10-28T07:09:32Z/);
  // Clearing the draft during a delayed response must not resurrect it.
  await page.goto('about:blank');
  await page.goto('https://bob.local.test/#bob-ocr='+encodeURIComponent(draft));
  await page.evaluate(()=>{localStorage.clear();window.BobDegiro={tradeTestProducts:()=>[],readServerProductList:()=>new Promise(resolve=>{window.finishList=resolve;})};});
  await page.addScriptTag({content:source});
  await page.getByRole('button',{name:'Eingabe entfernen',exact:true}).click();
  await page.evaluate(()=>window.finishList({products:[{isin:'DE000FG77MY4'}],listUploadedAt:'2026-10-28T07:09:32Z'}));
  assert.equal(await page.evaluate(()=>localStorage.length),0);
  // Exercise the production retry helper in the browser: no second tap.
  await page.goto('about:blank');
  await page.goto('https://bob.local.test/#bob-ocr='+encodeURIComponent(draft));
  await page.evaluate(()=>{
   localStorage.clear();window.BobDegiro={tradeTestProducts:()=>[]};window.listCalls=0;
   window.validIsin=v=>v==='DE000FG77MY4';
   window.fetch=async()=>{
    if(++window.listCalls===1)throw new DOMException('signal timed out','TimeoutError');
    return new Response(JSON.stringify({ok:true,listUploadedAt:new Date(Date.now()-1000).toISOString(),products:[{isin:'DE000FG77MY4'}]}),{status:200});
   };
  });
  const assistant=fs.readFileSync('degiro_assistant.js','utf8');
  const helper=assistant.slice(assistant.indexOf('async function readServerProductList('),assistant.indexOf('async function restoreServerCorrection(){'));
  await page.addScriptTag({content:helper+'\nwindow.BobDegiro.readServerProductList=readServerProductList;'});
  await page.addScriptTag({content:source});
  await page.waitForFunction(()=>document.getElementById('bobAndroidEvidence').innerText.includes('Automatischer Versuch 2 von 3'));
  assert.ok(await page.evaluate(()=>localStorage.getItem('bobAndroidPendingObservationV1')));
  await page.waitForFunction(()=>localStorage.getItem('bobAndroidProductObservationsV1'));
  assert.equal(await page.evaluate(()=>window.listCalls),2);
  assert.equal(await page.evaluate(()=>localStorage.getItem('bobAndroidPendingObservationV1')),null);
  console.log('Android observation handoff: delayed list, exact ISIN, persistence, reload and deletion passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
