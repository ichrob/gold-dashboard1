const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOB_TEST_CHROMIUM||undefined,args:['--no-sandbox']});
 try{
  let state={ok:true,revision:0,config:null,result:null,resultFresh:false},writes=0;
  const page=await browser.newPage({viewport:{width:360,height:800}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://bob.test/**',async route=>{
   if(route.request().method()==='POST'){
    const p=route.request().postDataJSON();
    if(p.action==='plan-save'){
     if(p.expectedRevision!==state.revision)return route.fulfill({status:400,json:{error:'Vorgaben wurden anderswo geändert. Neu laden.'}});
     writes++;state={...state,config:p.config,revision:state.revision+1};
    }
    return route.fulfill({json:state});
   }
   return route.fulfill({contentType:'text/html',body:'<meta name="viewport" content="width=device-width"><style>*{box-sizing:border-box}body{margin:8px}input,select{max-width:100%}button{max-width:100%;white-space:normal}</style><input id="trailAtr" value="1.8"><input id="minRR" value="2.5"><div id="dgTop3Out"></div>'});
  });
  async function open(){
   await page.goto('https://bob.test/');
   await page.addScriptTag({content:fs.readFileSync('manual_ranking_order.js','utf8')});
   await page.evaluate(()=>{window.BobProductAuditReport={listUploadedAt:'today'};window.BobManualTop3.render({approved:false},[],{});});
   await page.locator('[data-planning-status]').filter({hasText:/gespeichert/}).waitFor();
  }
  await open();
  assert.equal(await page.locator('#bobManualBudget').inputValue(),'');
  await page.locator('#bobManualBudget').fill('1000');
  await page.locator('#bobManualRisk').fill('100');
  await page.locator('[data-planning-save]').click();
  await page.locator('[data-planning-status]').filter({hasText:'dauerhaft gespeichert'}).waitFor();
  assert.equal(state.config.feesCHF,null);
  assert.equal(state.config.feeProfile,'unknown');
  await open();
  assert.equal(await page.locator('#bobManualFees').inputValue(),'');
  await page.locator('#bobManualFees').fill('0');
  await page.locator('[data-planning-save]').click();
  await page.locator('[data-planning-status]').filter({hasText:'dauerhaft gespeichert'}).waitFor();
  assert.deepEqual(state.config,{budgetCHF:1000,riskCHF:100,feesCHF:0,trailAtr:1.8,minRR:2.5,feeProfile:'unknown',fxMode:'unknown'});
  await open();
  assert.equal(await page.locator('#bobManualBudget').inputValue(),'1000');
  assert.equal(await page.locator('#bobManualFees').inputValue(),'0');
  state={...state,revision:state.revision+1,config:{...state.config,budgetCHF:900}};
  await page.locator('#bobManualBudget').fill('800');
  await page.locator('[data-planning-save]').click();
  await page.locator('[data-planning-status]').filter({hasText:'anderswo geändert'}).waitFor();
  assert.equal(writes,2);assert.equal(state.config.budgetCHF,900);
  assert.equal(await page.locator('#bobManualBudget').inputValue(),'800');
  await page.locator('[data-planning-load]').click();
  await page.waitForFunction(()=>document.querySelector('#bobManualBudget').value==='900');
  state.resultFresh=true;state.result={listUploadedAt:'today',available:0,conditionalAvailable:1,calculatedAt:Date.now(),items:[{
   isin:'DE000FG14AV8',available:false,modelStop:17.4,modelTarget:23.7,reasons:['Tarifeinstellung fehlt'],automaticScenarios:[{
    assumptions:['Schweizer Standardtarif angenommen','CHF-Konto mit AutoFX angenommen'],
    feeAssessment:{available:true,feesCHF:1.5},available:true,quantity:4,totalCHF:81.5,lossCHF:13.5,
    currency:'CHF',stop:17.4,riskUsagePct:45,
    entryWarning:'Kein Einstieg: Hindernis vor ausreichendem Chance-Risiko-Verhältnis. Nur Vergleichsrechnung.'}]}]};
  await page.locator('[data-planning-load]').click();
  await page.locator('[data-server-handset-plans]').filter({hasText:'Bedingte Rechnung'}).waitFor();
  assert.match(await page.locator('[data-server-handset-plans]').innerText(),/keine bestätigte Kontoeinstellung/);
  const planText=await page.locator('[data-server-handset-plans]').innerText();
  assert.match(planText,/Kein Einstieg/);
  assert.match(planText,/4 Stück/);
  assert.match(planText,/81\.50 CHF inkl\. Gebühren/);
  assert.match(planText,/Modellstopp 17\.4000 CHF/);
  assert.match(planText,/Modellziel 23\.7000 CHF/);
  assert.match(planText,/Modellrisiko 13\.50 CHF \(45\.0 % des Risikobudgets\)/);
  assert.match(planText,/keine bestätigte Kontoeinstellung/);
  assert.equal(await page.locator('[data-server-handset-plans] button').count(),0);
  assert.equal(await page.locator('#bobFeeProfile').inputValue(),'unknown');
  assert.equal(writes,2);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log('360px handset planning: explicit zero fees, save/reload, concurrent edit rejection, no silent writes, no overflow passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
