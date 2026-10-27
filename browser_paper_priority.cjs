'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),cp=require('node:child_process');
const {chromium}=require('playwright');
const panel=cp.execFileSync('python',['-c','from vollautomatisch_panel import PANEL;print(PANEL)'],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:8px}</style><section id="bob-view-simulation"></section>'+panel.replace(/<script>[\s\S]*?<\/script>/g,''));
  await page.evaluate(()=>{
   window.fixture={mode:'seven-independent-paper-accounts',realOrders:false,accounts:['conservative','balanced','offensive','early100','trend800','early1000oct','normal1000oct'].map(profile=>({profile,sessionMode:'trading',control:{checkedAt:Date.now(),initialCapital:100,equity:100,cash:100},stats:{},cases:[]}))};
   const a=fixture.accounts[1];
   a.stats.lastEntryChecklist={capturedAt:Date.now(),sourceAt:Date.now(),decision:'wait',reason:'Goldkurs fehlt <script>unsafe</script>',checks:[{label:'Goldkurs',state:'fail',required:true},{label:'Trend',state:'unknown',required:false}]};
   a.decisionReview={day:'2026-10-21',entries:3,checkedEntries:1,ruleConsistent:1,requiredViolations:0,entriesWithUnknownChecks:1,legacyEntries:2,waitChecks:8,pricedClosed:0,unpricedClosed:1,modelNetEur:null,note:'Keine rückwirkenden Checklisten'};
   a.stopStudy={total:1,paired:0,open:1,unavailable:0,variants:['Fester Bob-Anfangsstopp','ATR','Struktur'].map(label=>({label,paired:0,modelNetEur:null,stopHits:0})),note:'Vergleich ohne weitere Abbuchung'};
   window.fetch=async()=>({ok:true,json:async()=>fixture});
  });
  await page.addScriptTag({content:panel.match(/<script>([\s\S]*?)<\/script>/)[1]});
  await page.getByText('Einstiegscheckliste · Einstieg oder Abwarten',{exact:true}).first().waitFor();
  assert.equal(await page.locator('#bobProfilesCards > div').count(),7);
  await page.getByRole('heading',{name:'Frühwarnung · 1.000 € · bis Fr 16 Uhr',exact:true}).waitFor();
  await page.getByRole('heading',{name:'Hauptsignal · 1.000 € · bis Fr 16 Uhr',exact:true}).waitFor();
  const account=page.locator('#bobProfilesCards > div').nth(1);
  for(const width of [320,390]){
   await page.setViewportSize({width,height:844});
   for(const title of ['Einstiegscheckliste · Einstieg oder Abwarten','Tagesauswertung · Entscheidungen und Nachweise','Stoppvergleich · fest / ATR / Struktur']){
    const detail=account.locator('details').filter({has:page.locator('summary',{hasText:title})});
    await detail.evaluate(el=>el.open=true);
   }
   const text=await account.innerText();
   assert(text.includes('Abwarten'));assert(text.includes('✗ nicht erfüllt'));assert(text.includes('Trend: offen'));
   assert(text.includes('2 ältere Einstiege'));assert(text.includes('Ergebnis nach eingefrorenen Beispielkosten: offen'));
   assert(text.includes('0 vollständig gepaarte Ergebnisse'));assert(text.includes('nach Beispielkosten offen'));
   assert.equal(await account.locator('script').count(),0);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),'Mobile overflow');
  }
  assert.deepEqual(errors,[]);
  console.log('Paper priorities: mobile checklist, original unknowns, daily review, costs and paired stop study passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
