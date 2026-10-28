const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOB_TEST_CHROMIUM||undefined,args:['--no-sandbox']});
 try{
 const page=await browser.newPage({viewport:{width:360,height:800}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const html=fs.readFileSync('Bob.html','utf8');
 await page.route('**/*',route=>{
  const u=new URL(route.request().url());
  if(u.hostname!=='bob.test')return route.abort();
  if(u.pathname==='/api/risk-paper')return route.fulfill({contentType:'application/json',body:JSON.stringify({checkedAt:Date.now(),accounts:{'0':{delaySeconds:0,cash:2000,equity:2000,realized:0,closed:0,wins:0,incomplete:0,maxDrawdown:0,reason:'Warte auf bestätigtes Risiko-Signal',recent:[]}}})});
  if(u.pathname==='/')return route.fulfill({body:html,contentType:'text/html'});
  const file=require('node:path').basename(u.pathname);
  if(file.endsWith('.js')&&fs.existsSync(file))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(file,'utf8')});
  return route.fulfill({status:503,contentType:'application/json',body:'{"status":"unavailable"}'});
 });
 await page.goto('https://bob.test/');
 await page.locator('#bobNavigation [data-view="risk"]').click();
 await page.locator('#bob-view-risk').waitFor({state:'visible'});
 await page.locator('#bobRiskPaper').getByText('0 s Verzögerung',{exact:true}).waitFor();
 assert((await page.locator('#bobRiskPaper').innerText()).includes('2000.00 €'));
 assert.equal(await page.locator('#bobNavigation button').count(),5);
 assert(await page.locator('#bobRiskContent').innerText().then(x=>x.includes('ABWARTEN')));
 assert(await page.locator('#bob-view-risk').innerText().then(x=>x.includes('Risiko-Push')));
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow on 360px phone');
 await page.locator('#bobNavigation [data-view="trade"]').click();
 assert(await page.locator('#bob-view-risk').isHidden());
 await page.locator('#bobNavigation [data-view="risk"]').click();
 // Stub only the server acknowledgement; this is not a real delivery test.
 await page.evaluate(()=>{
  window.BobPush.set('serverRegistered',true);window.BobPush.set('general',true);
  window.BobRiskPush={set:async enabled=>{
   window.BobPush.set('risk',enabled);
   window.BobRisk.server({riskEnabled:enabled,riskState:{checkedAt:Date.now(),signal:{ready:true}}});return true;
  }};
 });
 await page.locator('#bobRiskPushToggle').click();
 assert.equal(await page.locator('#bobRiskPushToggle').getAttribute('aria-pressed'),'true');
 assert((await page.locator('#bobRiskPushStatus').innerText()).includes('Hintergrundprüfung'));
 await page.locator('#bobRiskPushToggle').click();
 assert.equal(await page.locator('#bobRiskPushToggle').getAttribute('aria-pressed'),'false');
 assert((await page.locator('#bobRiskPushStatus').innerText()).includes('ausgeschaltet'));
 await page.screenshot({path:'risk-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('Browser: five mobile tabs, Risiko visibility, empty-data status, scope disclosure, return navigation and 360px width passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
