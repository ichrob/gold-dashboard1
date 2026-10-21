'use strict';
const assert=require('node:assert/strict'),cp=require('node:child_process');
const {chromium}=require('playwright');
const panel=cp.execFileSync('python',['-c','from snaptrade_panel import PANEL;print(PANEL)'],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://bob.test/**',route=>route.fulfill({contentType:'text/html',body:'<meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:8px}button{max-width:100%;white-space:normal}</style><section id="bob-view-degiro"></section>'+panel.replace(/<script>[\s\S]*?<\/script>/g,'')}));
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
  for(const width of [320,390]){
   await page.setViewportSize({width,height:844});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),'Mobile overflow');
  }
  await page.locator('#snapRemove').click();await page.locator('#snapStatus').filter({hasText:'Noch nicht verbunden.'}).waitFor();
  assert.equal(await page.locator('#snapHoldings').innerText(),'');assert.deepEqual(errors,[]);
  console.log('SnapTrade mobile: setup, secret clearing, no browser persistence, unknown proof, safe rendering and deletion passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
