'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOB_TEST_CHROMIUM||undefined,args:['--no-sandbox']});
 try{
 for(const mode of ['analysis-failed','all-unavailable','analysis-hung']){
  const page=await browser.newPage({viewport:{width:390,height:844}}),reports=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const at='2026-11-13T17:30:00.000Z';
  await page.clock.install({time:new Date(at)});
  await page.route('**/*',r=>{
   const u=new URL(r.request().url());if(u.hostname!=='bob.test')return r.abort();
   if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('Bob.html','utf8')});
   const f=path.basename(u.pathname);
   if(f.endsWith('.js')&&fs.existsSync(f))return r.fulfill({contentType:'text/javascript',body:fs.readFileSync(f,'utf8')});
   if(u.pathname==='/api/diag'){
    const d=r.request().postDataJSON();if(d.event==='market-ui:observation')reports.push(d.details.code);
    return r.fulfill({status:204});
   }
   if(u.pathname==='/api/live'&&mode==='analysis-hung')return new Promise(()=>{});
   if(u.pathname==='/api/market-cards'&&mode!=='all-unavailable')return r.fulfill({json:{spot:{price:3880.10,at,kind:'spot',symbol:'XAU/USD',source:'fixture'},cfd:{price:3880.15,at,kind:'cfd'}}});
   return r.fulfill({status:503,json:{status:'unavailable'}});
  });
  await page.goto('https://bob.test/',{waitUntil:'domcontentloaded'});
  await page.clock.runFor(12000);
  assert(await page.locator('#gold-spot-price').isVisible());
  const text=await page.locator('#gold-spot-price').textContent();
  assert.equal(text,mode==='all-unavailable'?'—':'3.880,10');
  assert(!(await page.locator('#earlyImpulseStatus').textContent()).includes('wird geladen'));
  assert.equal(await page.locator('#gold-estimate-price').count(),0);
  if(mode==='all-unavailable'){
   assert(reports.includes('data-unavailable'));assert(!reports.includes('ok'));
  }else{
   assert(reports.includes('ok'));
   await page.locator('#gold-spot-price').evaluate(e=>e.textContent='—');
   await page.clock.runFor(11000);
   assert(reports.includes('spot-mismatch'),'DOM failure must reach diagnostics');
   assert.equal(await page.locator('#gold-spot-price').textContent(),'3.880,10','same original restores display');
   assert.equal(reports.at(-1),'ok','recovery separately confirmed');
   assert((await page.locator('#gold-spot-time').textContent()).includes('18:30:00'),'original clock preserved');
   await page.locator('#gold-spot-price').evaluate(e=>e.style.visibility='hidden');
   await page.clock.runFor(11000);assert.equal(reports.at(-1),'spot-hidden');
   await page.locator('#gold-spot-price').evaluate(e=>e.style.visibility='');
   await page.clock.runFor(11000);assert.equal(reports.at(-1),'ok');
   await page.clock.runFor(125000);
   assert.equal(reports.at(-1),'data-unavailable','old original is not a healthy current quote');
  }
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Market UI browser: failed/hung analysis, missing data, visible spot, DOM repair, telemetry and original clock passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
