/* Real mobile rendering of automatic, source-bound schematic MCO explanations. */
const {chromium}=require('playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:360,height:800}});
  await page.setContent('<meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:12px;font:16px sans-serif}main{width:100%;max-width:750px;margin:auto}button,input{max-width:100%}</style><main></main>');
  await page.evaluate(()=>{window.fetch=async()=>({ok:false});});
  await page.addScriptTag({content:fs.readFileSync('video_brief.js','utf8')});
  await page.evaluate(()=>{
   const sections=[
    {label:'Seitwärts',text:'Gold bewegt sich seitwärts zwischen Unterstützung und Widerstand.',evidence:[{at:42,text:'XAU/USD is sideways in a range, with support at 4200 USD and resistance at 4250 USD.'}]},
    {label:'Möglicher Ausbruch',text:'Ein Ausbruch nach oben wäre möglich, wenn der Widerstand überwunden wird.',evidence:[{at:85,text:'If gold can break above resistance, a breakout to the upside is possible.'}]},
    {label:'Korrektur',text:'Ein Rücksetzer ist möglich.',evidence:[{at:100,text:'A pullback is possible.'}]}
   ];
   window.sample={url:'https://www.youtube.com/watch?v=abcdefghijk',transcriptAnalyzed:true,trustedTranscript:true,enhancements:{summary:{kind:'ai',sections}}};
   BobVideoBrief.render(document.querySelector('main'),window.sample);
  });
  assert.equal(await page.locator('[data-mco-illustration]').count(),3);
  assert.equal(await page.locator('[data-mco-illustration="range"] svg[role="img"]').count(),1);
  assert.equal(await page.locator('[data-mco-illustration="breakout"]').count(),1);
  assert.equal(await page.locator('[data-mco-illustration="pullback"]').count(),1);
  assert((await page.locator('[data-mco-illustration="range"]').innerText()).includes('Unterstützung laut Transkript: 4200 USD'));
  assert((await page.locator('[data-mco-illustration="range"] a').first().getAttribute('href')).includes('t=42'));
  assert.equal(await page.locator('[data-mco-illustration] img').count(),0,'Generated pictures cannot masquerade as original video frames');
  assert((await page.locator('[data-mco-illustration="breakout"]').innerText()).includes('Wenn-dann-Szenario'));
  for(const width of [320,360,768]){
   await page.setViewportSize({width,height:900});
   assert(await page.locator('main').evaluate(n=>n.scrollWidth<=window.innerWidth),'No horizontal overflow at '+width);
   const content=await page.locator('[data-mco-illustration]').allTextContents();
   assert(content.every(t=>t.includes('kein Originalbild aus dem Video')));
  }
  if(process.env.BOB_MCO_SCREENSHOT){await page.setViewportSize({width:390,height:950});await page.screenshot({path:process.env.BOB_MCO_SCREENSHOT,fullPage:true});}
  await page.evaluate(()=>{document.querySelector('main').replaceChildren();BobVideoBrief.render(document.querySelector('main'),{...window.sample,trustedTranscript:false});});
  assert.equal(await page.locator('[data-mco-illustration]').count(),0,'Untrusted source cannot generate scenario illustrations');
  console.log('Mobile MCO illustrations: sourced scenarios and levels, original links, clear labels, responsive SVG and untrusted-source exclusion passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
