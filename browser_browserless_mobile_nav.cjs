'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');

// Recreate the actual server-side append without a Bob login, provider token,
// external websites, or the Browserless API. The renderer remains the real
// Bob.html mobile shell with its fixed bottom navigation.
const panel=execFileSync('python',['-c','from browserless_public_research import PANEL; print(PANEL)'],{encoding:'utf8'});
const html=fs.readFileSync('Bob.html','utf8').replace('</body>',panel+'</body>');

(async()=>{
 const browser=await chromium.launch({headless:true,
  executablePath:process.env.BOB_TEST_CHROMIUM||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:360,height:780}});
  await page.route('**/*',r=>{
   const u=new URL(r.request().url());
   if(u.hostname!=='bob.test')return r.abort();
   if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:html});
   const file=u.pathname.substring(1);
   if(/^[a-zA-Z0-9_.-]+\.js$/.test(file) && fs.existsSync(file))
    return r.fulfill({contentType:'application/javascript',body:fs.readFileSync(file,'utf8')});
   return r.fulfill({status:503,contentType:'application/json',body:'{"state":"disabled"}'});
  });
  await page.goto('https://bob.test/');
  await page.waitForFunction(()=>document.body.classList.contains('bob-mobile'));
  await page.locator('#bobNavigation').waitFor();
  const panelLocator=page.locator('#bobBrowserlessPublic');
  const clearance=page.locator('#bobBrowserlessMobileClearance');
  assert.equal(await clearance.count(),1,'Clearance exists exactly once after Browserless panel');
  for(const size of [{width:360,height:640},{width:360,height:780},{width:390,height:780}]){
   await page.setViewportSize(size);
   await panelLocator.evaluate(el=>el.open=false);
   await page.evaluate(()=>scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'}));
   const folded=await page.evaluate(()=>{
    const summary=document.querySelector('#bobBrowserlessPublic > summary').getBoundingClientRect();
    const nav=document.querySelector('#bobNavigation').getBoundingClientRect();
    const space=document.querySelector('#bobBrowserlessMobileClearance').getBoundingClientRect();
    return {summaryBottom:summary.bottom,navTop:nav.top,spaceHeight:space.height,
      horizontalOverflow:document.documentElement.scrollWidth>innerWidth};
   });
   assert(!folded.horizontalOverflow,'No horizontal scroll at '+size.width+' px');
   assert(folded.spaceHeight>=125,'Mobile bottom clearance remains effective');
   assert(folded.summaryBottom<=folded.navTop-4,
    'Collapsed Browserless summary must not sit behind fixed Bob nav at '+size.width+' px');
   await panelLocator.evaluate(el=>el.open=true);
   await page.evaluate(()=>scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'}));
   const expanded=await page.evaluate(()=>{
    const button=document.getElementById('bobBlRun').getBoundingClientRect();
    const nav=document.querySelector('#bobNavigation').getBoundingClientRect();
    return {buttonBottom:button.bottom,navTop:nav.top};
   });
   assert(expanded.buttonBottom<=expanded.navTop-4,
    'Expanded Browserless button must be above nav at '+size.width+' px');
  }
  // No network request is issued by merely expanding or scrolling the panel.
  assert.equal(await page.locator('#bobBrowserlessPublic').count(),1);
  console.log('Browserless mobile fixed-nav clearance OK');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
