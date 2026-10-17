const {chromium}=require('playwright');
const fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const page=await browser.newPage();
 await page.setContent('<main></main>');await page.addScriptTag({content:fs.readFileSync('video_evidence.js','utf8')});
 await page.evaluate(()=>BobVideoEvidence.controls(document.querySelector('main'),{videoId:'abcdefghijk',overview:{moments:[{at:1},{at:2}]}},()=>{}));
 await page.locator('summary').click();await page.locator('input[type=file]').setInputFiles('/tmp/bob-video-fixture.webm');await page.locator('input[type=checkbox]').check();
 await page.getByRole('button',{name:'Videobilder auswählen',exact:true}).click();try{await page.getByRole('button',{name:'Diese Bilder in Bob speichern'}).waitFor({state:'visible',timeout:25000});}catch(e){console.log(await page.locator('main').innerText());throw e;}
 const images=await page.locator('figure img').count();assert(images>=1&&images<=5);assert(await page.locator('figure img').first().evaluate(i=>i.naturalWidth>0));
 console.log('Real browser video extraction: '+images+' JPEG stills, review and save visible');
 await page.clock.install();
 await page.evaluate(()=>{
  window.__historyReady=false;
  const item={videoId:'abcdefghijk',url:'https://www.youtube.com/watch?v=abcdefghijk',channelId:'UCsl6Z6p7GOkczo8Cv-GH6Dg',trustedTranscript:true,title:'Fixture',mcoValues:{values:[{metric:'goldPrice',price:4200,unit:'USD',label:'Gold',comparisonContext:{instrument:'XAU/USD',currency:'USD',timeframe:'1m',analysisAt:Date.now()-60000}}]}};
  window.fetch=async url=>({ok:true,json:async()=>url==='/api/gold-research'?{items:[item],fresh:true}:{history:{'1m':window.__historyReady?[{}]:[]}}});
  window.BobMcoHistoricalMetric=(bars,at)=>bars.length?{available:true,value:4202,goldPrice:4202,asOf:at,source:'Test'}:{available:false,reason:'Historie fehlt'};
  document.querySelector('main').replaceChildren();
 });
 await page.addScriptTag({content:fs.readFileSync('mco_comparison.js','utf8')});
 await page.evaluate(()=>BobMcoComparison.mount(document.querySelector('main')));
 await page.getByText(/Vergleiche: 0 abgeschlossen/).waitFor();
 await page.evaluate(()=>{window.__historyReady=true;});
 await page.clock.runFor(31000);
 await page.getByText(/Vergleiche: 1 abgeschlossen/).waitFor();
 console.log('Missing historical comparison automatically resolved after new data');

 const jpeg=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=640;c.height=360;const x=c.getContext('2d');x.fillStyle='#112233';x.fillRect(0,0,640,360);return c.toDataURL('image/jpeg');});
 await page.addScriptTag({content:fs.readFileSync('video_brief.js','utf8')});
 await page.evaluate(dataUrl=>{document.querySelector('main').replaceChildren();BobVideoBrief.render(document.querySelector('main'),{url:'https://www.youtube.com/watch?v=abcdefghijk',overview:{evidence:[{id:'e',at:30,text:'If support holds, the scenario remains possible.'}],sections:[{label:'Bedingung',evidenceIds:['e']}]},enhancements:{frames:[{at:30,dataUrl}],ocr:{images:[{index:0,at:30,lines:[{text:'Gold Futures COMEX'}]}]}}});},jpeg);
 await page.getByRole('button',{name:'Chartbild vergrößern'}).click();
 assert(await page.getByRole('dialog').isVisible());await page.getByRole('button',{name:'2× vergrößern'}).click();
 assert.equal(await page.locator('dialog img').evaluate(i=>i.style.width),'200%');
 await page.getByRole('button',{name:'Schließen',exact:true}).click();assert.equal(await page.locator('dialog').count(),0);
 assert(await page.getByText(/Gold-Future im Bild erkannt/).isVisible());
 assert(await page.getByText('If support holds, the scenario remains possible.').isVisible());
 console.log('Full chart, enlargement, caption explanation and Futures separation passed');
 await browser.close();})();
