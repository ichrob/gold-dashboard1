/* Two real browser tabs, synthetic exports and simulated userscript-manager storage.
   Does not claim to test the installed Android add-on or a real broker login. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const engines=require('playwright');
const engine=process.env.BOB_BRIDGE_BROWSER||'chromium';
const BOB='https://bob-private-scanner.onrender.com',BROKER='https://trader.degiro.nl';
const header='Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF';
const csv=header+'\nSynthetic Faktor,<ISIN>,2,0.12,EUR,0.24,0.23'.replace('<ISIN>','US0378331005');
const html='<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:8px}</style><section id="bob-view-products"></section><section id="bob-view-degiro"></section>'+['degiro_portfolio_store.js','degiro_report_import.js','degiro_browser_bridge.js'].map(n=>'<script src="/'+n+'"></script>').join('');
(async()=>{
 const browser=await engines[engine].launch({headless:true,...(engine==='chromium'?{args:['--no-sandbox']}: {})});
 try{
  const ctx=await browser.newContext({viewport:{width:360,height:760},acceptDownloads:true});
  const gm={},requests=[],errors=[];
  await ctx.exposeBinding('gmWrite',async({page},key,value,remove)=>{
   if(remove)delete gm[key];else gm[key]=value;
   await Promise.all(ctx.pages().filter(p=>p!==page).map(p=>p.evaluate(({key,value,remove})=>window.gmRemote(key,value,remove),{key,value,remove}).catch(()=>{})));
  });
  await ctx.exposeBinding('gmRead',()=>gm);
  await ctx.addInitScript(async script=>{
   const values=await window.gmRead(),listeners={};
   window.GM_getValue=(k,d)=>k in values?values[k]:d;
   window.GM_setValue=(k,v)=>{const old=values[k];values[k]=v;for(const fn of listeners[k]||[])fn(k,old,v,false);window.gmWrite(k,v,false);};
   window.GM_deleteValue=k=>{delete values[k];window.gmWrite(k,null,true);};
   window.GM_addValueChangeListener=(k,fn)=>(listeners[k]??=[]).push(fn);
   window.gmRemote=(k,v,remove)=>{const old=values[k];if(remove)delete values[k];else values[k]=v;for(const fn of listeners[k]||[])fn(k,old,v,true);};
   (0,eval)(script);
  },fs.readFileSync('bob_degiro_export.user.js','utf8'));
  await ctx.route('https://**/*',route=>{
   const req=route.request(),u=new URL(req.url());requests.push({origin:u.origin,path:u.pathname,method:req.method()});
   if(u.origin===BOB){if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
    if(['/degiro_portfolio_store.js','/degiro_report_import.js','/degiro_browser_bridge.js'].includes(u.pathname))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(u.pathname.slice(1),'utf8')});}
   if(u.origin===BROKER&&u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><h1>Synthetic broker export</h1><input type="password" value="do-not-transfer"><button id="export">CSV</button>'});
   return route.abort();
  });
  const bob=await ctx.newPage(),broker=await ctx.newPage();
  for(const p of[bob,broker])p.on('pageerror',e=>errors.push(e.message));
  await bob.goto(BOB);await broker.goto(BROKER);
  await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStart').disabled);
  async function exportCSV(text){
   await broker.evaluate(text=>{
    document.getElementById('export').onclick=()=>{
     const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/csv'}));a.download='portfolio.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),3000);
    };
   },text);
   await broker.locator('#export').click();
  }
  // A normal export is untouched without explicit activation in Bob.
  await exportCSV(csv);assert.equal(await bob.locator('.dg-holding').count(),0);
  await bob.locator('#bobBridgeStart').click();
  await broker.waitForFunction(()=>GM_getValue('bob-export-arm-v1',0)>Date.now());
  await exportCSV(csv);
  await bob.waitForSelector('.dg-holding');
  assert.equal(await bob.locator('.dg-holding').count(),1);
  assert.equal(await bob.locator('.dg-export-card').count(),1,'Report panel refreshed');
  assert.match(await bob.locator('#bobBridgeStatus').innerText(),/1 Depotprodukte/);
  assert.match(await bob.locator('.dg-holding').innerText(),/Faktorprodukt/);
  const saved=await bob.evaluate(()=>localStorage.getItem(BobDegiroPortfolio.KEY));
  const snapshot=JSON.parse(saved);assert.equal(snapshot.sourceKind,'browser-export');
  for(const key of['ordersEnabled','brokerVerified','rankingEligible','liveAccountConnected','realtime'])assert.equal(snapshot[key],false);
  assert(!JSON.stringify(gm).includes('do-not-transfer'));assert(!JSON.stringify(gm).includes(csv));
  // Invalid and partial exports must preserve the previous snapshot.
  for(const invalid of[
   'Datum,ISIN,Quantity,Type\n20-10-2026,US0378331005,1,Buy',
   csv+'\nBroken,INVALID,3,0.1,EUR,0.3,0.3',
   csv+'\nDuplicate,US0378331005,3,0.1,EUR,0.3,0.3',
   csv+'\nMissing ISIN,,3,0.1,EUR,0.3,0.3',
   csv+'\nCASH & CASH FUND & F,,,,CHF,INVALID,INVALID',
   csv.replace(',EUR,',',BADCCY,')
  ]){
   await exportCSV(invalid);
   await broker.waitForFunction(()=>!document.querySelector('#bob-export-bridge-note')?.textContent.includes('prüft'));
   await bob.waitForTimeout(80);
   assert.equal(await bob.evaluate(()=>localStorage.getItem(BobDegiroPortfolio.KEY)),saved);
  }
  // Fully validated replacement, not cumulative holdings.
  await exportCSV(csv.replace(',2,0.12,',',5,0.12,'));
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===5);
  assert.equal(await bob.locator('.dg-holding').count(),1);
  for(const width of[320,360,390]){await bob.setViewportSize({width,height:760});assert(await bob.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));}
  // Simulate a pending export while Bob's tab was unloaded. Reload requires
  // explicit opt-in but must not consume or lose the queued snapshot.
  await bob.reload();
  await broker.evaluate(report=>GM_setValue('bob-export-pending-v1',{id:crypto.randomUUID(),createdAt:Date.now(),expiresAt:Date.now()+600000,report}),{kind:'portfolio',records:[{isin:'US0378331005',quantity:6,product:'Synthetic',currency:'USD'}],cashBalances:[],invalidRows:[]});
  await bob.reload();
  await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStart').disabled);
  assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),5);
  await bob.locator('#bobBridgeStart').click();
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===6);
  // Only opted-in, exact window-origin offers can write; stale and invalid offers fail closed.
  const goodReport={kind:'portfolio',records:[{isin:'US0378331005',quantity:99,product:'bad',currency:'USD'}],cashBalances:[],invalidRows:[]};
  for(const [origin,at] of[['https://evil.test',Date.now()],[BOB,Date.now()-700000]]){
   await bob.evaluate(({origin,at,report})=>window.dispatchEvent(new MessageEvent('message',{source:window,origin,data:{type:'BOB_EXPORT_OFFER',id:crypto.randomUUID(),createdAt:at,report}})),{origin,at,report:goodReport});
  }
  assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),6);
  await bob.locator('#bobBridgeStop').click();
  await bob.evaluate(report=>window.postMessage({type:'BOB_EXPORT_OFFER',id:crypto.randomUUID(),createdAt:Date.now(),report},location.origin),goodReport);
  await bob.waitForTimeout(80);assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),6);
  await bob.reload();assert.equal(await bob.locator('.dg-holding').count(),1,'Saved snapshot survives reload');
  await bob.locator('#dgExportClear').click();assert.equal(await bob.locator('.dg-holding').count(),0);
  assert(requests.every(r=>[BOB,BROKER].includes(r.origin)&&r.method==='GET'),'No broker API, orders or third-party traffic');
  assert.deepEqual(errors,[]);
  console.log('Browser bridge: 2 tabs, opt-in, CSV handoff, invalid/partial/duplicate/stale rejection, replacement, persistence, mobile widths, deletion, no credential transfer: passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
