'use strict';
const fs = require('node:fs'), assert = require('node:assert/strict');
const {chromium} = require('playwright');
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.BOB_TEST_CHROMIUM || undefined, args:['--no-sandbox']});
 try {
  const page = await browser.newPage({viewport:{width:360,height:780},serviceWorkers:'block'});
  await page.clock.install();
  const errors=[]; page.on('pageerror', e => errors.push(e.message));
  let count=0, fail=false, fresh=false, needsHelp=false;
  await page.route('**/*', async route => {
   const url=new URL(route.request().url());
   if(url.hostname !== 'bob.test')return route.abort();
   if(url.pathname==='/api/operations-summary') {
    count++; assert.equal(route.request().method(),'GET');
    return route.fulfill({status:fail?503:200,contentType:'application/json',body:JSON.stringify({readOnly:true,realOrders:false,
     observedAt:fresh?new Date(await page.evaluate(()=>Date.now()-1000)).toISOString():'2026-11-05T00:00:00Z',problemIndexFresh:fresh,cases:needsHelp?[{code:'android-reader',state:'needs-user'}]:fresh?[]:[{code:'<img src=x onerror=alert(1)>',state:'testing'}],
     phone:{state:'unknown',appVersion:10500,requested:10,complete:6,partial:2,runAt:1793836800,localOcrImages:2},
     jobs:[{id:'background',state:'observed',lastObservedAt:1793836800},{id:'collection',state:'observed'}],productStatus:{state:'incomplete'},
     storage:{diskUsedBytes:104857600,diskObservedAt:1793836800},testOverview:{items:[{label:'Test',state:'unknown'}]}})});
   }
   const files={'/zentrale/':'zentrale/index.html','/zentrale/app.js':'zentrale/app.js','/zentrale/theme.css':'zentrale/theme.css'};
   const file=files[url.pathname];
   return file ? route.fulfill({contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(file,'utf8')}) : route.fulfill({status:404,body:''});
  });
  await page.goto('https://bob.test/zentrale/#storage');
  assert(await page.locator('#storage').isVisible());
  await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  assert.equal(count,1); assert.match(await page.locator('#disk').innerText(),/100 MiB/);
  for(const section of ['overview','studies','maintenance','settings']) {
   await page.locator('nav a[href="#'+section+'"]').click();
   assert(await page.locator('#'+section).isVisible());
   assert.equal(await page.locator('[data-panel]:visible').count(),1);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile overflow');
  }
  assert.equal(await page.locator('nav a').count(),4);
  assert.equal(count,1,'navigation must reuse the same snapshot');
  assert.match(await page.locator('#phone-progress').textContent(),/6 von 10/);
  assert.match(await page.locator('#phone-state').textContent(),/Unbekannt/);
  assert.match(await page.locator('#help-count').textContent(),/Unbekannt/);
  await page.locator('nav a[href="#maintenance"]').click();
  assert.match(await page.locator('#problem-age').textContent(),/veraltet oder unbekannt/);
  assert.equal(await page.locator('#cases img').count(),0,'server text must not become HTML');
  fail=true; await page.locator('#refresh').click(); await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  assert.match(await page.locator('#status').innerText(),/nicht verifizierbar/);
  assert.equal(await page.locator('#monitor').textContent(),'Nicht aktuell bestätigt');
  assert.equal(await page.locator('#disk').textContent(),'Nicht aktuell bestätigt');
  await page.goto('https://bob.test/zentrale/#unknown'); assert(await page.locator('#overview').isVisible());
  assert.equal(count,2,'a hash-only navigation must not reload diagnostics');
  await page.reload();
  await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  assert.equal(count,3,'each actual page reload performs exactly one read');
  assert.match(await page.locator('#phone-state').textContent(),/Nicht aktuell bestätigt/);
  fail=false;fresh=true;await page.locator('#refresh').click();await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  assert.equal(await page.locator('#health-card').getAttribute('data-state'),'confirmed');
  assert.match(await page.locator('#overall').textContent(),/Keine Störung gemeldet/);
  assert.equal(await page.locator('#overview details[open]').count(),0);
  needsHelp=true;await page.locator('#refresh').click();await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  assert.equal(await page.locator('#health-card').getAttribute('data-state'),'attention');
  assert.match(await page.locator('#overall').textContent(),/Deine Hilfe/);
  for(const width of [360,390,768]){
   await page.setViewportSize({width,height:780});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal scroll');
   const action=await page.locator('#next-link').boundingBox(),nav=await page.locator('nav').boundingBox();
   assert(action.y+action.height<nav.y,'Main action is above navigation');
  }
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'/tmp/zentrale-home.png',fullPage:true});
  await page.locator('#next-link').click();assert(await page.locator('#maintenance').isVisible());
  await page.goto('https://bob.test/zentrale/#storage');
  assert(await page.locator('#storage').isVisible());
  assert.equal(await page.locator('#storage').getAttribute('open'),'','Legacy storage link opens existing details');
  // Visible status refreshes without a tap; hidden pages do not poll.
  const beforeRefresh=count;
  await page.clock.runFor(60001);
  await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  assert.equal(count,beforeRefresh+1);
  await page.evaluate(()=>Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'}));
  await page.clock.runFor(120001);
  assert.equal(count,beforeRefresh+1);
  await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>!document.getElementById('refresh').disabled);
  assert.equal(count,beforeRefresh+2);
  assert.deepEqual(errors,[]);
  console.log('Zentrale: mobile navigation, one shared read, safe text and failed-refresh clearing passed');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
