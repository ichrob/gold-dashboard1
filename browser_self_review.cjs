'use strict';
// Browser-level safety check for Bob's read-only self-review widget.
const assert=require('node:assert/strict');
const cp=require('node:child_process');
const {chromium}=require('playwright');
const panel=cp.execFileSync('python',['-c','from vollautomatisch_panel import PANEL; print(PANEL)'],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const html='<meta name="viewport" content="width=device-width,initial-scale=1">'+
   '<section id="bob-view-future"></section><section id="bob-view-auto"></section>'+
   '<section id="bob-view-simulation"></section>'+panel.replace(/<script>[\s\S]*?<\/script>/g,'');
  await page.setContent(html);
  await page.evaluate(()=>{
    window.fixtureReview={
      mode:'RESEARCH_ONLY',approved:false,orderExecutionEnabled:false,
      affectsLiveSignals:false,learningCycle:{selfReview:{
        mode:'RESEARCH_ONLY',actionable:false,liveRuleChanged:false,
        automaticOrder:false,productNetValidated:false,
        status:'recently-unreliable',sessions:23,trades:34,baselineTrades:32,
        reason:'Mindestens sieben von zehn Fenstern schwächer <script>alert(1)</script>',
        comparedScenarios:{
          standard:{relativeDifferencePct:-2.43},
          stress:{relativeDifferencePct:-4.55}
        },
        recentWindows:{underperformingOrEqualIntervals:7}
      }}
    };
    window.fetch=async()=>({ok:true,json:async()=>window.fixtureReview});
  });
  await page.addScriptTag({content:panel.match(/<script>([\s\S]*?)<\/script>/)[1]});
  const button=page.locator('#bob-self-review-refresh');
  assert(await button.isVisible());
  await button.click();
  const status=page.locator('#bob-self-review-status');
  await page.waitForFunction(()=>document.querySelector('#bob-self-review-status')?.textContent.includes('7/10'));
  let text=await status.innerText();
  assert(text.includes('Warnung: jüngste'));
  assert(text.includes('Standardkosten'));
  assert(text.includes('Höhere Kosten'));
  assert(text.includes('keine automatische Order'));
  assert.equal(await page.locator('#bob-self-review-status script').count(),0);
  assert.equal(await page.evaluate(()=>window.__hacked===true),false);

  await page.evaluate(()=>{window.fixtureReview.approved=true;});
  await button.click();
  await page.waitForFunction(()=>document.querySelector('#bob-self-review-status')?.textContent.includes('nicht verfügbar'));
  text=await status.innerText();
  assert(!text.includes('7/10'));
  assert(text.includes('keine Handelsfreigabe'));
  assert.deepEqual(errors,[]);
  console.log('Bob self review panel: cost scenarios, caution and fail-closed status passed');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
