const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOB_TEST_CHROMIUM||undefined,args:['--no-sandbox']});
 try{
 const page=await browser.newPage({viewport:{width:360,height:800}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const html=fs.readFileSync('Bob.html','utf8');
 await page.route('https://bob.test/**',route=>route.fulfill({body:html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''),contentType:'text/html'}));
 await page.goto('https://bob.test/');
 await page.addScriptTag({path:'risk_workspace.js'});
 const mobile=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).find(x=>x.includes('function initMobile()'));
 await page.evaluate(mobile);
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
