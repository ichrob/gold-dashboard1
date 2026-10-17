const {chromium}=require('playwright');
const fs=require('fs'),assert=require('assert');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const page=await browser.newPage();
 await page.setContent('<main></main>');await page.addScriptTag({content:fs.readFileSync('video_evidence.js','utf8')});
 await page.evaluate(()=>BobVideoEvidence.controls(document.querySelector('main'),{videoId:'abcdefghijk',overview:{moments:[{at:1},{at:2}]}},()=>{}));
 await page.locator('summary').click();await page.locator('input[type=file]').setInputFiles('/tmp/bob-video-fixture.webm');await page.locator('input[type=checkbox]').check();
 await page.getByRole('button',{name:'Videobilder auswählen',exact:true}).click();try{await page.getByRole('button',{name:'Diese Bilder in Bob speichern'}).waitFor({state:'visible',timeout:25000});}catch(e){console.log(await page.locator('main').innerText());throw e;}
 const images=await page.locator('figure img').count();assert(images>=2&&images<=5);assert(await page.locator('figure img').first().evaluate(i=>i.naturalWidth>0));
 console.log('Real browser video extraction: '+images+' JPEG stills, review and save visible');await browser.close();})();
