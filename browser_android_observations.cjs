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
  await page.goto('https://bob.local.test/#bob-ocr='+encodeURIComponent(draft));
  await page.addScriptTag({content:source});
  assert.equal(await page.evaluate(()=>location.hash),'');
  assert.equal(await page.evaluate(()=>localStorage.length),0);
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
  console.log('Android observation handoff: delayed list, exact ISIN, persistence, reload and deletion passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
