/* One uploaded DEGIRO detail image drives a separate proof, not the trade list. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const policy=require('./broker_candidate_pools');
function isin(i){
 const prefix='DETEST'+String(i).padStart(5,'0');
 for(let check=0;check<10;check++)if(policy.isValidISIN(prefix+check))return prefix+check;
 throw Error('Cannot make synthetic ISIN');
}
const watched=isin(1),candidate=isin(2);
const brokerDate='2026-10-20T08:30:00Z';
let receipt={status:'ok',source:'user-uploaded-degiro-detail-image',
 checkedAt:brokerDate,items:[]};
const serverWrites=[];
const origin='https://bob.local.test';
const html='<!doctype html><html lang="de"><head><meta charset="utf-8">'+
 '<meta name="viewport" content="width=device-width,initial-scale=1">'+
 '<style>*{box-sizing:border-box}body{margin:0;padding:8px}main{max-width:100%}</style>'+
 '</head><body><main><section id="bob-view-products"></section>'+
 '<section id="bob-view-future"></section></main>'+
 '<script src="/degiro_all_products.js"></script>'+
 '<script src="/broker_candidate_pools.js"></script></body></html>';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:360,height:760}});
  const outside=[];
  page.on('request',r=>{if(!r.url().startsWith(origin+'/'))outside.push(r.url());});
  await page.addInitScript(({isin})=>{
   const Native=Date;
   class Frozen extends Native{
    constructor(...args){super(...(args.length?args:[Native.parse('2026-10-20T08:30:00Z')]));}
    static now(){return Native.parse('2026-10-20T08:30:00Z');}
   }
   globalThis.Date=Frozen;
   globalThis.BobDegiro={
    normalizeOcrIsin:token=>({isin:token}),
    recognizeOcr:async()=>({data:{text:
     'Kursdaten\nGeld 5,45 EUR\nBrief 5,47 EUR\n20.10.2026 10:15\n'+
     'Börse Societe Generale OTC\nSymbol | ISIN '+isin
    }}),
    parseDegiroDisplayedQuote:(raw,id,venueOnly)=>{
     if(id!==isin||!raw.includes(isin))return null;
     return {isin:id,source:'DEGIRO-Produktdetail',
       venue:'Societe Generale OTC',currency:'EUR',
       sourceTime:'20.10.2026 10:15',brokerDisplayConfirmed:true,
       isExecutableQuote:false,orderWindowVerified:false,
       orderSubmitted:false,executionGuaranteed:false,
       ...(venueOnly?{}:{bid:5.45,ask:5.47})};
    }
   };
  },{isin:candidate});
  await page.route(origin+'/**',route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;
   if(pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(pathname==='/api/degiro/candidates')return route.fulfill({
    contentType:'application/json',body:JSON.stringify({status:'ok',lastScanAt:brokerDate,
     sourceType:'historic-user-list-plus-issuer-research',candidates:[]})});
   if(pathname==='/api/degiro/audit')return route.fulfill({
    contentType:'application/json',body:JSON.stringify({
     status:'stale',lastCheckedAt:'2026-10-19T20:00:00Z',items:[]
    })});
   if(pathname==='/api/degiro/candidate-proofs'){
    return route.fulfill({contentType:'application/json',body:JSON.stringify(receipt)});
   }
   if(pathname==='/api/degiro/candidate-proof'&&req.method()==='POST'){
    const data=req.postDataJSON();
    serverWrites.push(data);
    const record={
     ...data,origin:'user-uploaded-degiro-detail-image',
     kind:'user-uploaded-detail-ocr',broker:'DEGIRO',
     listingConfirmed:true,brokerDisplayObserved:true,executionConfirmed:false,
     tradeApproved:false,rankingsEligible:false,isExecutableQuote:false,
     observedAt:'2026-10-20T10:15:00+02:00',observedMinute:'2026-10-20T10:15',
     validUntil:'2026-10-20T22:00:00+02:00',
     timezone:'Europe/Zurich',timePrecision:'minute'
    };
    receipt.items=[record];
    return route.fulfill({contentType:'application/json',body:JSON.stringify({
     ok:true,preserved:false,evidence:record,ordersEnabled:false,rankingsEligible:false
    })});
   }
   if(pathname==='/api/degiro/enrich')return route.fulfill({
    contentType:'application/json',body:JSON.stringify({
     isin:candidate,productVerified:true,found:true,
     metadata:{underlyingType:'SPOT',underlying:'XAU/USD',type:'TURBO'}
    })});
   if(['/broker_candidate_pools.js','/degiro_all_products.js'].includes(pathname))
    return route.fulfill({contentType:'application/javascript',
     body:fs.readFileSync(path.join(__dirname,pathname.slice(1)),'utf8')});
   throw Error('Unexpected route '+pathname);
  });
  await page.goto(origin+'/');
  await page.waitForFunction(()=>document.querySelector('#bobBrokerResearchStatus')?.textContent?.includes('0 Emittentenprodukte'));
  await page.evaluate(({isin,at})=>{
   localStorage.setItem('bobDegiroProductsV2',
    JSON.stringify({version:2,listUploadedAt:at,products:[
     {isin,name:'Older gold product',direction:'SHORT'}]}));
  },{isin:watched,at:'2026-10-19T06:29:00Z'});
  assert.equal(await page.locator('#bobDegiroConfirmedRows article').count(),0);
  // The only user action needed: select one DEGIRO product detail screenshot.
  await page.locator('#bobBrokerCandidateFile').setInputFiles({
   name:'degiro-product.png',mimeType:'image/png',buffer:Buffer.alloc(2500,0x40)
  });
  await page.waitForFunction(()=>document.querySelector('#bobBrokerCandidateImageStatus')
   ?.textContent?.includes('Bild erkannt und zeitlich geprüft'));
  assert.equal(serverWrites.length,1);
  const data=serverWrites[0];
  assert.equal(data.isin,candidate);
  assert.equal(data.venue,'Societe Generale OTC');
  assert.equal(data.sourceTime,'20.10.2026 10:15');
  assert.equal(data.orderSubmitted,false);
  assert.equal(data.isExecutableQuote,false);
  assert.equal(data.imageBytes,2500);
  assert(/^[a-f0-9]{64}$/.test(data.imageSha256));
  assert.equal(data.imageMime,'image/png');
  assert(!('file' in data)&&!('blob' in data)&&!('ocrText' in data)&&
   !('imageData' in data)&&!('account' in data),'No screenshot text, image or account data posted');
  assert.equal(await page.locator('#bobDegiroConfirmedRows article').count(),1);
  assert((await page.locator('#bobDegiroConfirmedRows').innerText()).includes(candidate));
  assert((await page.locator('#bobDegiroConfirmedRows').innerText()).includes('kein ausführbarer'));
  assert.equal(await page.locator('#bobBrokerResearchRows article').count(),0);
  const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('bobDegiroProductsV2')));
  assert.deepEqual(state.products.map(x=>x.isin),[watched],
    'Single candidate must not overwrite active DEGIRO screenshot products');
  assert((await page.evaluate(()=>localStorage.getItem('bobIssuerResearchCandidatesV1'))).includes(candidate));
  await page.reload();
  await page.waitForFunction(isin=>document.querySelector('#bobDegiroConfirmedRows article')
   ?.textContent?.includes(isin),candidate);
  assert.equal(await page.locator('#bobDegiroConfirmedRows article').count(),1,
   'The separate proof survives browser refresh via authenticated private server');
  assert.deepEqual(outside,[],'No login, network call to DEGIRO or third-party brokers');
  console.log('DEGIRO one-image Android import: auto OCR, ISIN assignment, private proof, issuer check, persistence, trade list unchanged');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
