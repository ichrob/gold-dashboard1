'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOB_TEST_CHROMIUM||undefined,args:['--no-sandbox']});
 try{
 const page=await browser.newPage({viewport:{width:360,height:780}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{
  const u=new URL(r.request().url());
  if(u.hostname!=='bob.test')return r.abort();
  if(u.pathname==='/'||u.pathname==='/zentrale/workspace')return r.fulfill({contentType:'text/html',body:fs.readFileSync('Bob.html','utf8').replace('</body>','<script src="/degiro_handoff.js"></script><script src="/bob_unified_workspace.js"></script></body>')});
  if(u.pathname==='/zentrale/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('zentrale/index.html','utf8')});
  if(u.pathname==='/zentrale/theme.css')return r.fulfill({contentType:'text/css',body:fs.readFileSync('zentrale/theme.css','utf8')});
  if(u.pathname==='/zentrale/app.js')return r.fulfill({contentType:'text/javascript',body:fs.readFileSync('zentrale/app.js','utf8')});
  const file=path.basename(u.pathname);
  if(file.endsWith('.js')&&fs.existsSync(file))return r.fulfill({contentType:'text/javascript',body:fs.readFileSync(file,'utf8')});
  return r.fulfill({status:503,contentType:'application/json',body:'{"status":"unavailable"}'});
 });
 await page.goto('https://bob.test/');
 await page.locator('#bobSimpleHome').waitFor();
 assert(await page.locator('#chart').isVisible(),'Chart visible with analysis collapsed');
 assert.equal(await page.locator('#chart').evaluate(el=>el.closest('details')),null,'Chart is never inside a disclosure');
 assert.equal(await page.locator('#earlyImpulseStatus').count(),1,'Keep a single live warning');
 assert(await page.locator('#bobEarlyCompact').isVisible(),'Compact warning always visible');
 assert(!(await page.locator('#earlyImpulseStatus').isVisible()),'Full explanation initially folded');
 assert.equal(await page.locator('#bobNavigation button').count(),3);
 assert.deepEqual(await page.locator('#bobNavigation button').allTextContents(),['◫Markt','▤Produkte','◎Mein Trade']);
 for(const width of [360,390,768]){
  await page.setViewportSize({width,height:780});
  assert(await page.locator('#bobHomePrimary').isVisible());
  const b=await page.locator('#bobHomePrimary').boundingBox();assert(b.y+b.height<680,'Primary action above navigation');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow');
 }
 await page.setViewportSize({width:360,height:780});
 await page.locator('#bobHomePrimary').click();
 assert(await page.locator('#bob-view-products').isVisible());
 assert(!(await page.locator('#bobUnifiedWorkspace').isVisible()));
 await page.locator('#bobProductPreparation > summary').click();
 assert(await page.locator('#bobUnifiedWorkspace').isVisible());
 await page.locator('#bobProductTools').evaluate(el=>el.open=true);
 await page.locator('#bobProductTools [data-view="more"]').click();
 assert.equal(await page.locator('#bob-view-more [data-view="problems"]').count(),0);
 assert.equal(await page.locator('#bob-view-more [data-view="simulation"]').count(),0);
 assert.equal(await page.locator('#bob-view-more a[href="/zentrale/"]').count(),1);
 assert.equal(await page.locator('#bobNavigation [data-view="products"]').getAttribute('aria-current'),'page');
 await page.locator('#bobNavigation [data-view="overview"]').click();
 await page.evaluate(()=>{
  window.BobTradeSync={current:()=>({active:true,test:false,product:{isin:'TEST'}}),overview:()=>({pnl:'+12 CHF',stop:'≈ 2 CHF',target:'≈ 4 CHF',note:'Berechneter Produktkurs',action:'Bestehenden Stop nicht lockern.'})};
 });
 await page.waitForFunction(()=>!document.getElementById('bobHomeTrade').hidden);
 assert.equal(await page.locator('#bobHomeStop').textContent(),'≈ 2 CHF');
 assert.equal(await page.locator('#bobHomePrimary').getAttribute('data-view'),'trade');
 const b=await page.locator('#bobHomePrimary').boundingBox();assert(b.y+b.height<680,'Active trade primary action visible');
 await page.screenshot({path:'/tmp/bob-simple-home-active.png',fullPage:true});
 await page.evaluate(()=>window.BobTradeSync.current=()=>({active:true,test:true}));
 await page.waitForFunction(()=>document.getElementById('bobHomeTrade').hidden);
 await page.locator('#bobHomeDetails > summary').click();
 assert(await page.locator('#quickSignal').isVisible());
 await page.locator('#bobHomeDetails > summary').click();
 assert(await page.locator('#chart').isVisible(),'Chart remains visible after collapsing analysis again');
 assert(await page.locator('#bobEarlyCompact').isVisible(),'Compact early warning stays visible after collapsing analysis');
 for(const label of ['FRÜH LONG · VORWARNUNG','FRÜH SHORT · VORWARNUNG','VORWARNUNG ABGELAUFEN','DATEN FEHLEN']){
  await page.locator('#earlyImpulseStatus').evaluate((el,text)=>{el.textContent=text;},label);
  await page.waitForFunction(text=>document.getElementById('bobEarlyCompact').textContent.includes(text),label);
 }
 // A notification opened in an existing window must escape collapsed analysis.
 const facts={eventKind:'early-warning',direction:'SHORT',generatedAt:Date.now()-600000,expiresAt:Date.now()-1};
 await page.evaluate(data=>{location.hash='push='+encodeURIComponent(JSON.stringify(data));},facts);
 await page.locator('#pushOpened').waitFor({state:'visible'});
 assert.equal(await page.locator('#pushOpened').evaluate(el=>el.closest('details')),null);
 const context=await page.locator('#pushOpenedText').innerText();
 assert(context.includes('FRÜHWARNUNG · SHORT')&&context.includes('abgelaufen'));
 assert(context.includes('Einstieg: ABWARTEN'),'Unavailable fixture never invents an entry');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.locator('#pushOpenedDismiss').click();
 assert(!(await page.locator('#pushOpened').isVisible()));
 // Cold-open metadata survives startup and the simplified home rearrangement.
 await page.goto('https://bob.test/#push='+encodeURIComponent(JSON.stringify(facts)));
 await page.locator('#bobSimpleHome').waitFor();
 assert(await page.locator('#pushOpened').isVisible());
 assert.equal(await page.locator('#pushOpened').evaluate(el=>el.closest('details')),null);
 await page.screenshot({path:'/tmp/bob-simple-home.png',fullPage:true});
 // Old links enter the new workspace; management uses the existing live controls.
 await page.goto('https://bob.test/?view=simulation#simulation');
 await page.waitForURL('**/zentrale/workspace?view=simulation#simulation');
 await page.locator('#bob-view-simulation').waitFor();
 assert.equal(await page.locator('h1').textContent(),'Bob Zentrale');
 assert.equal(await page.locator('#bobNavigation [aria-current="page"]').count(),1);
 assert.equal(await page.locator('#bobNavigation a').count(),4);
 assert(!(await page.locator('body').innerText()).includes('BOB_ISIN_COPY_END'),'No code marker in visible UI');
 await page.waitForFunction(()=>getComputedStyle(document.body).backgroundColor==='rgb(12, 19, 33)');
 assert.equal(await page.locator('#bobNavigation [aria-current="page"]').getAttribute('data-central-section'),'studies');
 await page.screenshot({path:'/tmp/zentrale-workspace.png',fullPage:true});
 for(const key of ['simulation','learning','diagrams','improve','research','future','problems','settings']){
  await page.goto('https://bob.test/zentrale/workspace?view='+key+'#'+key);
  await page.locator('#bob-view-'+key).waitFor();
  assert(await page.locator('#bob-view-'+key).isVisible(),key+' stays usable');
  assert.equal(new URL(page.url()).pathname,'/zentrale/workspace');
  assert.equal(await page.locator('#bobNavigation a').count(),4);
  const section=key==='settings'?'settings':key==='problems'?'maintenance':'studies';
  assert.equal(await page.locator('#bobNavigation [aria-current="page"]').getAttribute('data-central-section'),section);
 }
 await page.goto('https://bob.test/zentrale/workspace?view=problems#problems');
 await page.locator('#bobMobileHelpShare').click();
 assert(await page.locator('#bob-view-problems').isVisible(),'Repair control remains in Zentrale');
 await page.goto('https://bob.test/zentrale/workspace?view=simulation#simulation');
 await page.locator('#bob-view-simulation [data-view="auto"]').click();
 assert(await page.locator('#bob-view-auto').isVisible());
 await page.locator('#bob-view-auto .bob-back').click();
 assert(await page.locator('#bob-view-simulation').isVisible());
 for(const width of [360,390,768]){
  await page.setViewportSize({width,height:780});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Workspace overflow');
 }
 await page.goto('https://bob.test/zentrale/workspace?view=more');
 await page.waitForURL('**/zentrale/#studies');
 await page.locator('.toolbar a[href="/"]').click();
 await page.locator('#bobSimpleHome').waitFor();
 assert(await page.locator('#bobEarlyCompact').isVisible());
 await page.locator('#bobNavigation [data-view="products"]').click();
 await page.evaluate(()=>{
  window.BobDegiro.tradeTestProducts=()=>[{isin:'DE000FG14AV8',name:'Test product',direction:'LONG'}];
  const button=document.createElement('button');button.dataset.simplePrepare='DE000FG14AV8';button.id='test-prepare';button.textContent='Trade vorbereiten';document.getElementById('bob-view-products').prepend(button);
 });
 await page.locator('#test-prepare').click();
 assert(await page.locator('#bob-view-trade').isVisible());
 assert(await page.locator('#dg2-form').isVisible());
 assert.equal(await page.locator('#dg2-form [name="isin"]').inputValue(),'DE000FG14AV8');
 await page.locator('#dg2-form [name="budget"]').fill('1000');
 await page.locator('#dg2-propose').click();
 assert.match(await page.locator('#dg2-proposal').textContent(),/unvollständig|nicht verfügbar/);
 assert.equal(await page.locator('.bob-simple-copy button:not([disabled])').count(),1,'Only identity can be copied without valid calculation');
 assert.equal(await page.locator('#dg2-orders textarea').count(),0,'A preview never stores an order');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal(await page.locator('#bobTradeModeTitle').textContent(),'Deinen nächsten Trade vorbereiten');
 assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('bob.trade.preferences.v1')).budget),'1000');
 await page.reload();await page.locator('#bobSimpleHome').waitFor({state:'attached'});
 await page.locator('#bobNavigation [data-view="trade"]').click();
 assert.equal(await page.locator('#dg2-form [name="budget"]').inputValue(),'1000','Budget survives reload');
 for(const name of ['isin','qty','price','stop','target'])assert.equal(await page.locator('#dg2-form [name="'+name+'"]').inputValue(),'','Market and position values are never restored');
 const executionAt=await page.evaluate(()=>new Date(Date.now()-30000).toISOString());
 await page.route('**/api/snaptrade/status',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({code:'READ_OK',readOnly:true,fresh:true,snapshot:{accounts:[{accountKey:'fixture',journal:{activities:{code:'READ_OK',complete:true,checkedAt:executionAt,rows:[{key:'fixture-fill',type:'BUY',isin:'DE000FG14AV8',currency:'EUR',securityCurrency:'EUR',date:executionAt,quantity:5,price:10,amount:-51,fee:1}]}}}]}})}));
 await page.evaluate(()=>{window.BobDegiro.tradeTestProducts=()=>[{isin:'DE000FG14AV8',direction:'LONG',name:'Fixture'}];});
 await page.locator('#bobPurchaseMatch details').evaluate(el=>el.open=true);
 await page.locator('#bobPurchaseMatchRefresh').click();
 await page.getByRole('button',{name:'Kaufdaten prüfen',exact:true}).click();
 assert.equal(await page.locator('[data-exit="entry"]').inputValue(),'10');
 assert.equal(await page.locator('[data-exit="quantity"]').inputValue(),'5');
 assert.equal(await page.locator('#purchaseAt').inputValue(),executionAt);
 assert.equal(await page.locator('#purchaseFees').inputValue(),'','EUR fees are not invented CHF settlement');
 assert.equal(await page.locator('#purchaseTotal').inputValue(),'');
 assert.match(await page.locator('#purchaseStatus').textContent(),/vorbefüllt/);
 await page.evaluate(()=>{window.BobTradeSync={current:()=>({active:true,product:{isin:'DE000FG14AV8'}}),overview:()=>({})};});
 await page.waitForFunction(()=>document.querySelector('#bobTradeModeTitle').textContent==='Dein aktiver Trade');
 assert.equal(await page.locator('#bobTradePreparation').evaluate(el=>el.open),false);
 assert(!(await page.locator('#bobPurchaseMatch').isVisible()));
 await page.screenshot({path:'/tmp/bob-simple-trade.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('Simple home: three tabs, all destinations, 360/390/768 widths, active/absent/test trades, currency and original analysis passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
