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
  if(u.pathname==='/')return route.fulfill({body:html,contentType:'text/html'});
  const file=require('node:path').basename(u.pathname);
  if(file.endsWith('.js')&&fs.existsSync(file))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(file,'utf8')});
  return route.fulfill({status:503,contentType:'application/json',body:'{"status":"unavailable"}'});
 });
 await page.goto('https://bob.test/');
 await page.locator('#bobNavigation [data-view="risk"]').click();
 await page.locator('#bob-view-risk').waitFor({state:'visible'});
 assert.equal(await page.locator('#bobNavigation button').count(),5);
 assert(await page.locator('#bobRiskContent').innerText().then(x=>x.includes('ABWARTEN')));
 assert(await page.locator('#bob-view-risk').innerText().then(x=>x.includes('kein eigener Hintergrund-Push')));
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow on 360px phone');
 await page.locator('#bobNavigation [data-view="trade"]').click();
 assert(await page.locator('#bob-view-risk').isHidden());
 await page.locator('#bobNavigation [data-view="risk"]').click();
 await page.screenshot({path:'risk-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('Browser: five mobile tabs, Risiko visibility, empty-data status, scope disclosure, return navigation and 360px width passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
