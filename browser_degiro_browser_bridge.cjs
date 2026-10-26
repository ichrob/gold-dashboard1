/* Two real browser tabs, synthetic exports and simulated userscript-manager storage.
   Does not claim to test the installed Android add-on or a real broker login. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const engines=require('playwright'),path=require('node:path');
const fixtureSource=name=>fs.readFileSync(path.join(process.env.BOB_BRIDGE_TEST_SOURCE||__dirname,name),'utf8');
const engine=process.env.BOB_BRIDGE_BROWSER||'chromium';
const BOB='https://bob-private-scanner.onrender.com',BROKER='https://trader.degiro.nl';
const header='Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF';
const csv=header+'\nSynthetic Faktor,<ISIN>,2,0.12,EUR,0.24,0.23'.replace('<ISIN>','US0378331005');
const html='<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:8px}</style><section id="bob-view-products"></section><section id="bob-view-degiro"></section>'+['degiro_portfolio_store.js','degiro_report_import.js','degiro_browser_bridge.js'].map(n=>'<script src="/'+n+'"></script>').join('');
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
   window.unsafeWindow=window;
   window.GM_getValue=(k,d)=>k in values?values[k]:d;
   window.gmStatusWrites=0;
   window.exportResults=[];window.addEventListener("message",e=>{if(e.source===window&&e.data?.type==="BOB_EXPORT_RESULT")window.exportResults.push(e.data);});
   window.GM_setValue=(k,v)=>{if(k==='bob-export-status-v1')window.gmStatusWrites++;const old=values[k];values[k]=v;for(const fn of listeners[k]||[])fn(k,old,v,false);window.gmWrite(k,v,false);};
   window.GM_deleteValue=k=>{delete values[k];window.gmWrite(k,null,true);};
   window.GM_addValueChangeListener=(k,fn)=>(listeners[k]??=[]).push(fn);
   window.gmRemote=(k,v,remove)=>{const old=values[k];if(remove)delete values[k];else values[k]=v;for(const fn of listeners[k]||[])fn(k,old,v,true);};
   // Real managers can provide a window wrapper distinct from event.source.
   const wrapped={postMessage:window.postMessage.bind(window),addEventListener:window.addEventListener.bind(window)};
   new Function('window','unsafeWindow',script)(wrapped,window);
  },fixtureSource('bob_degiro_export.user.js'));
  await ctx.route('https://**/*',route=>{
   const req=route.request(),u=new URL(req.url());requests.push({origin:u.origin,path:u.pathname,method:req.method()});
   if(u.origin===BOB){if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
    if(['/degiro_portfolio_store.js','/degiro_report_import.js','/degiro_browser_bridge.js'].includes(u.pathname))return route.fulfill({contentType:'application/javascript; charset=utf-8',body:fixtureSource(u.pathname.slice(1))});}
   if(u.origin===BROKER&&u.pathname==='/reporting/secure/v3/positionReport/csv')return route.fulfill({contentType:'text/csv',headers:{'Content-Disposition':'attachment; filename=portfolio.csv'},body:u.searchParams.has('invalid')?'not a CSV':csv.replace(',2,0.12,',','+(u.searchParams.get('qty')||7)+',0.12,')});
   if(u.origin===BROKER&&u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><h1>Synthetic broker export</h1><input type="password" value="do-not-transfer"><button id="export">CSV</button>'});
   return route.abort();
  });
  const bob=await ctx.newPage(),broker=await ctx.newPage();
  for(const p of[bob,broker])p.on('pageerror',e=>errors.push(e.message));
  await bob.goto(BOB);await broker.goto(BROKER);
  await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStart').disabled);
  async function exportCSV(text,method='click'){
   const resultsBefore=await bob.evaluate(()=>window.exportResults.length);
   const before=await broker.evaluate(()=>({armed:GM_getValue('bob-export-arm-v1',0)>Date.now(),writes:window.gmStatusWrites}));
   await broker.evaluate(({text,method})=>{
    document.getElementById('export').onclick=()=>{
     const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/csv'}));a.download='portfolio.csv';if(method==='dispatch')a.dispatchEvent(new MouseEvent('click'));else a.click();setTimeout(()=>URL.revokeObjectURL(a.href),3000);
    };
   },{text,method});
   await broker.locator('#export').click();
   if(before.armed){
    // Await this export's own terminal status, not an old note or a fixed sleep.
    await broker.waitForFunction(writes=>window.gmStatusWrites>writes&&
     ['staged','error'].includes(GM_getValue('bob-export-status-v1',null)?.state),before.writes,{timeout:12000});
    const state=await broker.evaluate(()=>GM_getValue('bob-export-status-v1',null)?.state);
    if(state==='error')return false;
    // Follow the UI instruction to return to Bob after choosing the export.
    await bob.bringToFront();
    // Bob was in the background while the broker button was clicked. Poll by
    // timer: requestAnimationFrame may be suspended for a background tab.
    await bob.waitForFunction(n=>window.exportResults.length>n,resultsBefore,{timeout:12000,polling:100}).catch(async error=>{
     const state=await bob.evaluate(()=>({results:window.exportResults.length,
      armed:GM_getValue('bob-export-arm-v1',0)>Date.now(),
      pending:!!GM_getValue('bob-export-pending-v1',null),
      active:!document.querySelector('#bobBridgeStop').disabled,
      holdings:document.querySelectorAll('.dg-holding').length}));
     error.message+='; synthetic bridge state '+JSON.stringify(state);throw error;
    });
    return bob.evaluate(()=>window.exportResults.at(-1).ok);
   }
  }
  // A normal export is untouched without explicit activation in Bob.
  await exportCSV(csv);assert.equal(await bob.locator('.dg-holding').count(),0);
  await bob.locator('#bobBridgeStart').click();
  await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStop').disabled);
  await broker.waitForFunction(()=>GM_getValue('bob-export-arm-v1',0)>Date.now());
  await bob.waitForFunction(()=>document.querySelector('#bobBridgeBrokerStatus').textContent.includes('erreichbar'));
  await exportCSV(csv);
  await bob.waitForSelector('.dg-holding');
  assert.equal(await bob.locator('.dg-holding').count(),1);
  assert.equal(await bob.locator('.dg-export-card').count(),1,'Report panel refreshed');
  assert.match(await bob.locator('#bobBridgeStatus').innerText(),/1 Depotprodukte/);
  assert.match(await bob.locator('.dg-holding').innerText(),/Faktorprodukt/);
  let saved=await bob.evaluate(()=>localStorage.getItem(BobDegiroPortfolio.KEY));
  const snapshot=JSON.parse(saved);assert.equal(snapshot.sourceKind,'browser-export');
  for(const key of['ordersEnabled','brokerVerified','rankingEligible','liveAccountConnected','realtime'])assert.equal(snapshot[key],false);
  assert(!JSON.stringify(gm).includes('do-not-transfer'));assert(!JSON.stringify(gm).includes(csv));
  // Regression: detached dispatchEvent bypasses both document and .click hooks.
  await exportCSV(csv.replace(',2,0.12,',',8,0.12,'),'dispatch');
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===8,{},{timeout:8000});
  // Real download behavior is preserved, including direct /csv reporting URLs.
  const directDownload=broker.waitForEvent('download');
  await broker.evaluate(()=>{
   const a=document.createElement('a');a.href='/reporting/secure/v3/positionReport/csv?qty=7';a.click();
  });
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===7,{},{timeout:8000});
  assert.equal((await directDownload).suggestedFilename(),'portfolio.csv','Original same-tab download still occurs');
  // Native user clicks are forwarded once after the copy, not double-dispatched.
  await broker.evaluate(()=>{
   window.__handlerCalls=0;const a=document.createElement('a');a.id='http-export';a.textContent='Download';a.href='/reporting/secure/v3/positionReport/csv?qty=10';a.onclick=()=>window.__handlerCalls++;document.body.append(a);
  });
  await broker.locator('#http-export').click();
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===10,{},{timeout:8000});
  assert.equal(await broker.evaluate(()=>window.__handlerCalls),1);
  // An invalid read must still forward the normal download and preserve holdings.
  const failedDownload=broker.waitForEvent('download');
  await broker.evaluate(()=>{const a=document.createElement('a');a.href='/reporting/secure/v3/positionReport/csv?invalid=1';a.click();});
  await failedDownload;
  await bob.waitForFunction(()=>document.querySelector('#bobBridgeBrokerStatus').textContent.includes('nicht vollständig gelesen'));
  assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),10);
  // window.open is forwarded while a read-only copy reaches Bob.
  await broker.evaluate(()=>{document.getElementById('export').onclick=()=>{window.__popup=window.open('/reporting/secure/v3/positionReport/csv?qty=9','_blank');};});
  await broker.locator('#export').click();
  assert(await broker.evaluate(()=>Boolean(window.__popup)),'Original window.open return value preserved');
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===9,{},{timeout:8000});
  // A blank popup followed by a generated CSV has no URL at window.open.
  // The selected CSV blob must be captured before the downloader revokes it.
  await broker.evaluate(()=>{document.getElementById('export').onclick=()=>{
   window.__blank=window.open('about:blank','_blank');
   setTimeout(()=>{
    const url=URL.createObjectURL(new Blob([window.__blankCSV],{type:window.__blankMime}));
    window.__blank.location.href=url;URL.revokeObjectURL(url);
   },50);
  };},{});
  await broker.evaluate(text=>window.__blankCSV=text,csv.replace(',2,0.12,',',11,0.12,'));
  let blankQuantity=10;
  for(const mime of ['text/csv;charset=utf-8','application/octet-stream','']){
   blankQuantity++;await broker.evaluate(text=>window.__blankCSV=text,csv.replace(',2,0.12,',','+blankQuantity+',0.12,'));
   await broker.evaluate(mime=>{window.__blankMime=mime;GM_setValue('bob-export-status-v1',{state:'ready',at:Date.now(),version:'1.2.0'});},mime);
   await broker.locator('#export').click();
   // Headless browser startup can be delayed under the full Python+JS CI load.
   // Keep the exact quantity and issuer-source assertions; only allow the
   // cross-tab event to settle before declaring a failure.
   await bob.waitForFunction(qty=>BobDegiroPortfolio.load(localStorage).records[0].quantity===qty,blankQuantity,{timeout:8000});
   await broker.waitForFunction(()=>GM_getValue('bob-export-status-v1',null)?.state==='staged');
  }
  // CSV blobs outside a trusted CSV choice, or with receipt stopped, are not read.
  await bob.locator('#bobBridgeStop').click();
  const blobRequests=requests.length;
  await broker.evaluate(text=>URL.createObjectURL(new Blob([text],{type:'text/csv'})),csv);
  await bob.waitForTimeout(80);assert.equal(requests.length,blobRequests);
  assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),13);
  await bob.locator('#bobBridgeStart').click();
  await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStop').disabled);
  // Synchronize the new allowlisted read-only arm across tabs before making
  // assertions about created blobs and the next *explicit* CSV export.
  await broker.waitForFunction(()=>GM_getValue('bob-export-arm-v1',0)>Date.now());
  await bob.waitForFunction(()=>document.querySelector('#bobBridgeBrokerStatus').textContent.includes('erreichbar'));
  await broker.evaluate(text=>URL.createObjectURL(new Blob([text],{type:'text/csv'})),csv);
  await bob.waitForTimeout(80);assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),13,'Armed receipt alone does not capture generated blobs without a new CSV choice');
  // Do not follow arbitrary URLs, non-reporting APIs, credentials in URLs or PDF exports.
  const before=requests.length;
  await broker.evaluate(()=>{
   for(const url of['https://evil.test/reporting/file.csv','https://name:secret@trader.degiro.nl/reporting/file.csv','/trading/order.csv','/reporting/report.pdf']){
    const a=document.createElement('a');a.href=url;a.addEventListener('click',e=>e.preventDefault());a.dispatchEvent(new MouseEvent('click',{cancelable:true}));
   }
  });
  await bob.waitForTimeout(100);assert.equal(requests.length,before,'Rejected anchors do not trigger bridge requests');
  await exportCSV(csv);
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===2, null,{timeout:12000});
  saved=await bob.evaluate(()=>localStorage.getItem(BobDegiroPortfolio.KEY));
  // Invalid and partial exports must preserve the previous snapshot.
  for(const invalid of[
   'Datum,ISIN,Quantity,Type\n20-10-2026,US0378331005,1,Buy',
   csv+'\nBroken,INVALID,3,0.1,EUR,0.3,0.3',
   csv+'\nDuplicate,US0378331005,3,0.1,EUR,0.3,0.3',
   csv+'\nMissing ISIN,,3,0.1,EUR,0.3,0.3',
   csv+'\nCASH & CASH FUND & F,,,,CHF,INVALID,INVALID',
   csv.replace(',EUR,',',BADCCY,')
  ]){
   assert.equal(await exportCSV(invalid),false,'Each invalid export reaches its own rejection before checking preservation');
   assert.equal(await bob.evaluate(()=>localStorage.getItem(BobDegiroPortfolio.KEY)),saved);
  }
  // Fully validated replacement, not cumulative holdings.
  await exportCSV(csv.replace(',2,0.12,',',5,0.12,'));
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===5);
  assert.equal(await bob.locator('.dg-holding').count(),1);
  for(const width of[320,360,390]){await bob.setViewportSize({width,height:760});assert(await bob.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1));}
  // Android can unload Bob while the broker tab is in front. Restore only
  // this tab's existing consent, without extending its original deadline.
  const consentDeadline=await bob.evaluate(()=>Number(sessionStorage.getItem('bob-export-tab-consent-v1')));
  await bob.reload();
  await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStop').disabled);
  assert.equal(await bob.evaluate(()=>Number(sessionStorage.getItem('bob-export-tab-consent-v1'))),consentDeadline);
  await broker.evaluate(report=>GM_setValue('bob-export-pending-v1',{id:crypto.randomUUID(),createdAt:Date.now(),expiresAt:Date.now()+600000,report}),{kind:'portfolio',records:[{isin:'US0378331005',quantity:6,product:'Synthetic',currency:'USD'}],cashBalances:[],invalidRows:[]});
  await bob.reload();
  await bob.waitForFunction(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity===6);
  assert.equal(await bob.evaluate(()=>Number(sessionStorage.getItem('bob-export-tab-consent-v1'))),consentDeadline);
  const freshBob=await ctx.newPage();await freshBob.goto(BOB);
  await freshBob.waitForFunction(()=>!document.querySelector('#bobBridgeStart').disabled);
  assert(await freshBob.locator('#bobBridgeStop').isDisabled(),'New tab has no automatic consent');
  await freshBob.close();
  // Only opted-in, exact window-origin offers can write; stale and invalid offers fail closed.
  const goodReport={kind:'portfolio',records:[{isin:'US0378331005',quantity:99,product:'bad',currency:'USD'}],cashBalances:[],invalidRows:[]};
  for(const [origin,at] of[['https://evil.test',Date.now()],[BOB,Date.now()-700000]]){
   await bob.evaluate(({origin,at,report})=>window.dispatchEvent(new MessageEvent('message',{source:window,origin,data:{type:'BOB_EXPORT_OFFER',id:crypto.randomUUID(),createdAt:at,report}})),{origin,at,report:goodReport});
  }
  assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),6);
  await bob.locator('#bobBridgeStop').click();
  await bob.evaluate(report=>window.postMessage({type:'BOB_EXPORT_OFFER',id:crypto.randomUUID(),createdAt:Date.now(),report},location.origin),goodReport);
  await bob.waitForTimeout(80);assert.equal(await bob.evaluate(()=>BobDegiroPortfolio.load(localStorage).records[0].quantity),6);
  await bob.reload();await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStart').disabled);assert(await bob.locator('#bobBridgeStop').isDisabled(),'Stop persists after reload');assert.equal(await bob.locator('.dg-holding').count(),1,'Saved snapshot survives reload');
  await bob.evaluate(()=>sessionStorage.setItem('bob-export-tab-consent-v1',String(Date.now()-1)));
  await bob.reload();await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStart').disabled);assert(await bob.locator('#bobBridgeStop').isDisabled(),'Expired consent cannot resume');
  await bob.locator('#dgExportClear').click();assert.equal(await bob.locator('.dg-holding').count(),0);
  assert(requests.every(r=>[BOB,BROKER].includes(r.origin)&&r.method==='GET'),'No broker API, orders or third-party traffic');
  // Seeing a helper is not an activation acknowledgment. Drop ARM messages to
  // reproduce a broken script message listener and ensure Bob never claims active.
  await bob.evaluate(()=>{window.__realPost=window.postMessage;window.postMessage=function(d,...args){if(d?.type!=='BOB_EXPORT_ARM')return window.__realPost.call(this,d,...args);};});
  await bob.locator('#bobBridgeStart').click();
  assert.match(await bob.locator('#bobBridgeStatus').innerText(),/wird aktiviert/);
  await bob.waitForFunction(()=>document.querySelector('#bobBridgeStatus').textContent.includes('nicht bestätigt'));
  assert(await bob.locator('#bobBridgeStop').isDisabled());
  await bob.evaluate(()=>window.postMessage=window.__realPost);
  // A stale helper cannot silently keep the activation UI available.
  await bob.evaluate(()=>postMessage({type:'BOB_EXPORT_HELPER_READY',version:'1.0.0'},location.origin));
  await bob.waitForFunction(()=>document.querySelector('#bobBridgeStart').disabled);
  assert.match(await bob.locator('#bobBridgeStatus').innerText(),/veraltet/);
  assert(await bob.locator('#bobBridgeUpdate').isVisible());
  await bob.evaluate(()=>postMessage({type:'BOB_EXPORT_HELPER_READY',version:'1.2.0'},location.origin));
  await bob.waitForFunction(()=>!document.querySelector('#bobBridgeStart').disabled);
  assert.deepEqual(errors,[]);
  console.log('Browser bridge: 2 tabs, detached dispatch, /csv URLs, window.open, version/heartbeat diagnostics, opt-in, rejection, persistence, mobile widths, deletion, no credential transfer: passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
