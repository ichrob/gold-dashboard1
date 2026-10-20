/* Verified DEGIRO broker-source proof is the only admission from issuer research. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const policy=require('./broker_candidate_pools');

function sampleISIN(n){
 const head='DETEST'+String(n).padStart(5,'0');
 for(let i=0;i<10;i++)if(policy.isValidISIN(head+i))return head+i;
 throw Error('Bad synthetic ISIN');
}
const a=sampleISIN(1),b=sampleISIN(2),c=sampleISIN(3);
const at='2026-10-20T06:00:00Z';
const observed='2026-10-20T10:15';
const proof={
 isin:a,broker:'DEGIRO',venue:'Societe Generale OTC',currency:'EUR',
 kind:'owner-reviewed-screenshot',listingConfirmed:true,executionConfirmed:false,
 timezone:'Europe/Zurich',timePrecision:'minute',imageReference:'Screenshot: controlled CI sample',
 listUploadedAt:at,observedMinute:observed,validUntil:'2026-10-20T22:00:00+02:00'
};
const issuerCatalog={
 status:'ok',lastScanAt:'2026-10-20T08:00:00Z',
 candidates:[
  {isin:a,name:'Test Gold KO Alpha',direction:'LONG',issuerVerified:true,issuerStatus:'verified',
   degiroListed:true,eligibleForTop3:true,liveApproved:true},
  {isin:b,name:'Test Gold KO Beta',direction:'SHORT',issuerVerified:true,issuerStatus:'verified'}
 ]
};
let audit={
 status:'ok',listUploadedAt:at,lastCheckedAt:'2026-10-20T08:29:00Z',
 items:[{isin:a,brokerVenueEvidence:proof}]
};
const base='https://bob.local.test';
const html='<!doctype html><html lang="de"><head><meta charset="utf-8">'+
 '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>'+
 '<main><section id="bob-view-products"></section><section id="bob-view-future"></section></main>'+
 '<script src="/degiro_all_products.js"></script>'+
 '<script src="/broker_candidate_pools.js"></script></body></html>';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:360,height:760}});
  const external=[];
  page.on('request',req=>{
   if(!req.url().startsWith(base+'/'))external.push(req.url());
  });
  await page.addInitScript(()=>{
   const Native=Date;
   const frozen=Native.parse('2026-10-20T08:30:00Z');
   class TestDate extends Native{
    constructor(...args){super(...(args.length?args:[frozen]));}
    static now(){return frozen;}
   }
   globalThis.Date=TestDate;
  });
  await page.route(base+'/**',route=>{
   const pathname=new URL(route.request().url()).pathname;
   if(pathname==='/')return route.fulfill({contentType:'text/html',body:html});
   if(pathname==='/api/degiro/candidates')return route.fulfill({
    contentType:'application/json',body:JSON.stringify(issuerCatalog)});
   if(pathname==='/api/degiro/audit')return route.fulfill({
    contentType:'application/json',body:JSON.stringify(audit)});
   if(['/degiro_all_products.js','/broker_candidate_pools.js'].includes(pathname)){
    return route.fulfill({contentType:'application/javascript',
     body:fs.readFileSync(path.join(__dirname,pathname.slice(1)),'utf8')});
   }
   throw Error('Unknown route '+pathname);
  });
  await page.goto(base+'/');
  await page.waitForFunction(()=>document.querySelector('#bobBrokerResearchStatus')?.textContent?.includes('2 Emittentenprodukte'));
  assert.equal(await page.locator('#bobDegiroConfirmedRows article').count(),0,
   'Issuer claim degiroListed:true cannot authorize a DEGIRO listing');
  assert.equal(await page.locator('#bobBrokerResearchRows article').count(),2);
  assert((await page.locator('#bobBrokerResearchRows').innerText()).includes('IBKR: nicht geprüft'));
  assert((await page.locator('#bobBrokerResearchRows').innerText()).includes('IG: nicht geprüft'));
  await page.locator('#bobBrokerResearchInput').fill(c.toLowerCase());
  await page.locator('#bobBrokerResearchForm button[type=submit]').click();
  assert.equal(await page.locator('#bobBrokerResearchRows article').count(),3);
  assert((await page.locator('#bobBrokerResearchRows').innerText()).includes('manuell vorgemerkt'));
  const check=await page.evaluate(()=>([
   localStorage.getItem('bobIssuerResearchCandidatesV1'),
   localStorage.getItem('bobDegiroProductsV2'),
   localStorage.getItem('bob.degiro.csv.depot.v1')
  ]));
  assert(check[0], 'The future broker research queue persists locally');
  assert.equal(check[1],null,'Issuer queue cannot write active screenshot products');
  assert.equal(check[2],null,'Issuer queue cannot write depot holdings');
  await page.evaluate(({isin,at})=>{
   localStorage.setItem('bobDegiroProductsV2',JSON.stringify({
    version:2,listUploadedAt:at,products:[{isin,name:'Test screenshot',direction:'LONG'}]
   }));
  },{isin:a,at});
  await page.locator('#bobBrokerResearchRefresh').click();
  await page.waitForFunction(()=>document.querySelector('#bobDegiroCandidateStatus')?.textContent?.includes('1 Produkt(e)'));
  assert.equal(await page.locator('#bobDegiroConfirmedRows article').count(),1);
  assert((await page.locator('#bobDegiroConfirmedRows').innerText()).includes('kein ausführbarer DEGIRO-Kurs'));
  assert.equal(await page.locator('#bobBrokerResearchRows article').count(),2);
  assert.equal(await page.evaluate(()=>localStorage.getItem('bobDegiroProductsV2')!==null),true);
  audit={...audit,status:'stale'};
  await page.locator('#bobBrokerResearchRefresh').click();
  await page.waitForFunction(()=>document.querySelector('#bobDegiroCandidateStatus')?.textContent?.startsWith('Keine neuen Produkte'));
  assert.equal(await page.locator('#bobDegiroConfirmedRows article').count(),0,
   'A stale report may not retain DEGIRO listing confirmation');
  assert.equal(await page.locator('#bobBrokerResearchRows article').count(),3,
   'Expired proof falls back to broker-neutral research');
  for(const width of [320,360,390]){
   await page.setViewportSize({width,height:760});
   const metrics=await page.evaluate(()=>({
    scroll:document.documentElement.scrollWidth,
    width:document.documentElement.clientWidth,
    card:document.querySelector('#bobIssuerResearchRows article').getBoundingClientRect().width,
    panel:document.querySelector('#bobIssuerResearch').getBoundingClientRect().width
   }));
   assert(metrics.scroll<=metrics.width+1,'Browser horizontal overflow '+width+JSON.stringify(metrics));
   assert(metrics.card<=metrics.panel+1,'Research card overflow '+width);
  }
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#bobBrokerResearchRows article')?.textContent?.includes('Test'));
  assert.equal(await page.locator('#bobBrokerResearchRows article').count(),3,'Research survives restart');
  assert.deepEqual(external,[],'No calls to DEGIRO or third-party brokerage');
  console.log('Broker candidate split UI passed: issuer-only pending, current screenshot proof, stale rollback, future brokers and mobile');
 }finally{
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
