const {chromium}=require('playwright');
const fs=require('fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
 const page=await browser.newPage({viewport:{width:390,height:844}});
 await page.setContent('<main><section id="group"><h3>Trainieren und auswerten</h3>'+['simulation','learning','diagrams','improve'].map(k=>'<button data-view="'+k+'">'+k+'</button><section id="bob-view-'+k+'"><h2>'+k+'</h2></section>').join('')+'</section></main>');
 await page.clock.install();
 await page.evaluate(()=>{
  window.testReport={available:true,workerCheckedAt:Date.now(),items:[{id:'signal:test:60',type:'Signalprüfung',status:'trying',attempts:1,reason:'Originalkurs fehlt',history:[{at:Date.now(),action:'Archiv prüfen',result:'Originalkurs fehlt'}]}]};
  window.fetch=async url=>({ok:true,json:async()=>url==='/api/assistance'?{ok:true,status:'queued'}:window.testReport});
  Object.defineProperty(navigator,'share',{configurable:true,value:async data=>{window.shared=data;}});
 });
 await page.addScriptTag({content:fs.readFileSync('training_help.js','utf8')});
 await page.evaluate(()=>BobTrainingHelp.mount(document.querySelector('#group')));
 const button=page.getByRole('button',{name:'An ChatGPT senden',exact:true});
 await page.getByText('(X) Bob versucht die Behebung und prüft erneut.',{exact:true}).waitFor();
 assert(await button.isDisabled());assert.equal(await button.evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(21, 101, 192)');
 assert.equal((await page.locator('[data-view=learning] [data-training-mark]').innerText()).trim(),'(X)');
 await page.evaluate(()=>{testReport.items[0].status='escalated';testReport.items[0].attempts=3;});
 await page.clock.runFor(30001);
 assert.equal((await page.locator('[data-view=learning] [data-training-mark]').innerText()).trim(),'X');
 assert(!(await button.isDisabled()));await button.click();
 assert.equal(await page.evaluate(()=>window.shared),undefined);
 await page.getByText(/Gespeicherte Testfälle werden automatisch/).waitFor();
 await page.locator('summary').click();
 await page.getByRole('button',{name:'Bericht zusätzlich manuell teilen'}).click();
 assert.match(await page.evaluate(()=>window.shared.text),/Archiv prüfen/);
 assert.match(await page.evaluate(()=>window.shared.text),/Originalkurs fehlt/);
 // Sharing is not recovery. Only the authoritative successful check removes X.
 assert.equal((await page.locator('[data-view=learning] [data-training-mark]').innerText()).trim(),'X');
 await page.evaluate(()=>{testReport.items[0].status='recovered';});await page.clock.runFor(30001);
 assert(await page.locator('[data-view=learning] [data-training-mark]').isHidden());assert(await button.isDisabled());
 await page.evaluate(()=>{window.retries=0;const retry=()=>{window.retries++;BobTrainingHelp.observe('improve',false,retry);};BobTrainingHelp.observe('improve',false,retry);});
 assert.equal((await page.locator('[data-view=improve] [data-training-mark]').innerText()).trim(),'(X)');
 await page.clock.runFor(60001);assert.equal(await page.evaluate(()=>window.retries),2);
 assert.equal((await page.locator('[data-view=improve] [data-training-mark]').innerText()).trim(),'X');
 await page.evaluate(()=>BobTrainingHelp.observe('improve',true));assert(await page.locator('[data-view=improve] [data-training-mark]').isHidden());
 await page.evaluate(()=>{testReport.problemGroups=[{id:'test:signal:missingFollowup',kind:'signal',status:'escalated',cases:15,escalated:15,maxAttempts:3,type:'Original-Folgekurs fehlt',reason:'missingFollowup'}];testReport.affectedCases=15;});
 await page.clock.runFor(30001);
 await page.getByText(/1 offene Fehlerarten · 15 betroffene Testfälle/).waitFor();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=390));
 console.log('Mobile training help: blue button, automatic retries, escalation, explicit share and verified recovery OK');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
