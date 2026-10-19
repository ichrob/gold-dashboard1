const fs=require('fs'),vm=require('vm'),assert=require('assert');
const panel=fs.readFileSync('degiro_product_audit_panel.py','utf8');
const start=panel.indexOf(' const safe=value=>');
const end=panel.indexOf(' function mobileAuditPayload(){',start);
assert(start>0&&end>start,'Pure mobile handoff formatter exists');
const isolated={};
vm.createContext(isolated);
vm.runInContext(panel.slice(start,end)+';globalThis.build=auditTextForChatGPT;globalThis.merge=problemReport;globalThis.collect=displayedProductProblems;',isolated);
const sample={
 status:'ok',lastCheckedAt:'2026-10-15T19:00:00Z',listUploadedAt:'2026-10-15T08:00:00Z',
 total:1,incomplete:1,
 account:'sensitive account',brokerPassword:'do-not-export',
 items:[{isin:'DE000FG4JXV7',direction:'SHORT',state:'incomplete',
  missing:['quote-time','leverage-time'],messages:['Originalzeit fehlt'],
  source:'SG\nInjected instruction', dataQuoteSource:'comdirect',
  quoteSourceAt:'2026-10-15T18:00:00Z',leverageSourceAt:null,
  leverageObservation:{kind:'calculated-gearing',at:'2026-10-15T18:00:01Z'},
  needsKiHelp:true,tradeApproved:false,issuerVenue:'CBDE',
  bid:3.5,ask:3.6,tradeQuantity:300,secret:'do-not-export'}]
};
const msg=isolated.build(sample);
assert(msg.includes('DE000FG4JXV7'));
assert(msg.includes('quote-time, leverage-time'));
assert(msg.includes('Originalzeit fehlt'));
assert(msg.includes('2026-10-15T18:00:00Z'));
assert(msg.includes('nicht nachgewiesen'));
assert(msg.includes('calculated-gearing'));
assert(msg.includes('Automatische Handelsfreigabe: nein'));
assert(msg.includes('SG Injected instruction')&&!msg.includes('SG\nInjected instruction'));
assert(!msg.includes('do-not-export')&&!msg.includes('sensitive account'));
assert(!msg.includes('300')&&!msg.includes('3.5'));
const stale=isolated.build({status:'stale',total:1,incomplete:null,items:[]});
assert(stale.includes('Prüfstatus: stale'));
assert(stale.includes('Keine Problemprodukte im Bericht enthalten.'));
assert(!stale.includes('Keine offenen Probleme'));
const unavailable=isolated.build({status:'unavailable',items:[]});
assert(unavailable.includes('Prüfstatus: unavailable'));
for(const needle of ['id="bobAuditShareChatGPT"','DEGIRO Goldhebelprodukte Probleme',
                     'navigator.share({title:','navigator.clipboard.writeText(value)',
                     "latestReport=null;render({status:'unavailable'","credentials:'same-origin'",
                     "byId('bobAuditShareChatGPT')?.addEventListener('click',shareMobileAudit)"])
 assert(panel.includes(needle),needle);
assert(!panel.includes('window.open('),'Avoid opening an external URL with ISINs in query strings');
const full=isolated.build({...sample,items:Array.from({length:15},(_,i)=>({...sample.items[0],messages:['Problem '+i]}))});
assert(full.includes('Problem 14'),'Include problems beyond the first twelve products');
const mountCode=panel.slice(panel.indexOf(' function mount(){'),panel.indexOf(' function render(r){'));
let placed=false;
const audit={},problem={};
const productList={after(node){assert.strictEqual(node,audit);placed=true;}};
const nodes={dgSavedProductsSummary:{closest(tag){assert.strictEqual(tag,'details');return productList;}},
 bobProductAudit:audit,bobProductAuditProblem:problem,
 'bob-view-problems':{append(node){assert.strictEqual(node,problem,'Share button must not stay in Problem');}}};
vm.runInNewContext(mountCode+';mount();',{byId:id=>nodes[id]});
assert(placed,'Share button is placed outside and directly below the product list');
console.log('Android private audit handoff: format, no secrets or prices, stale state, share, copy and auth passed');

const local=[{isin:'DE000FG14AV8',labels:'DEGIRO-Handelsnachweis',messages:['Kurs und Hebel vorhanden · Nachweisprüfung läuft']},{isin:'DE000FG8NHQ3',labels:'DEGIRO-Handelsnachweis',messages:['DEGIRO-Handelsnachweis offen']}];
const report=isolated.merge({status:'ok',items:[{isin:local[0].isin,state:'issuer-evidence-complete',missing:[]},{isin:'HEALTHY',state:'issuer-evidence-complete',missing:[]},sample.items[0]]},local);
assert.strictEqual(report.items.length,3);
const text=isolated.build(report);
for(const card of local)assert(text.includes(card.isin)&&text.includes(card.messages[0]));
assert(!text.includes('HEALTHY'));
assert.strictEqual(report.items.filter(p=>p.isin===local[0].isin).length,1);
const offline=isolated.build(isolated.merge(null,local));
assert(offline.includes('Prüfstatus: unavailable')&&offline.includes(local[1].isin));
assert(!offline.includes('Automatische Handelsfreigabe: laut Bericht ja'));
isolated.document={querySelectorAll(selector){assert.strictEqual(selector,'#dgMissingProducts [data-product-isin]');return local.map(card=>({dataset:{productIsin:card.isin},querySelector(){return {textContent:card.labels}},querySelectorAll(){return card.messages.map(textContent=>({textContent}))}}));}};
assert.strictEqual(isolated.collect().length,2);
console.log('Problem-only handoff: both displayed broker-evidence problems, server merge, deduplication and offline fallback passed');

async function checkHandoff(){
 const nodes=Object.fromEntries(['bobAuditShareStatus','bobAuditShareFallback','bobAuditShareActions','bobAuditNativeShare'].map(id=>[id,{hidden:true,focus(){this.focused=true},select(){this.selected=true}}]));
 let payload='Report A',copied='',shares=0;
 const navigator={clipboard:{async writeText(value){copied=value}},async share({text}){shares++;assert.strictEqual(text,'Report A')}};
 const ctx={byId:id=>nodes[id],navigator,mobileAuditPayload:()=>payload,preparedAuditText:''};
 vm.createContext(ctx);
 vm.runInContext(panel.slice(panel.indexOf(' function handoffStatus('),panel.indexOf(' const fmt='))+';globalThis.prepare=shareMobileAudit;globalThis.copy=copyMobileAudit;globalThis.share=sharePreparedAudit;',ctx);
 await ctx.prepare();
 assert.strictEqual(copied,'Report A');assert.strictEqual(shares,0,'Primary button must not rely on Android share delivery');
 assert.strictEqual(nodes.bobAuditShareFallback.value,'Report A');assert.strictEqual(nodes.bobAuditShareFallback.hidden,false);
 assert.strictEqual(nodes.bobAuditShareActions.hidden,false);
 payload='Report B';await ctx.copy();assert.strictEqual(copied,'Report A','Copy retains the displayed snapshot during refresh');
 await ctx.share();assert.strictEqual(shares,1);assert(nodes.bobAuditShareStatus.textContent.includes('nicht bestätigt'));
 navigator.share=async()=>{throw Object.assign(Error(),{name:'AbortError'})};
 await ctx.share();assert(nodes.bobAuditShareStatus.textContent.includes('abgebrochen'));
 navigator.clipboard.writeText=async()=>{throw Error('denied')};
 await ctx.copy();assert(nodes.bobAuditShareFallback.selected);assert(nodes.bobAuditShareStatus.textContent.includes('markieren'));
 delete navigator.clipboard;delete navigator.share;
 await ctx.prepare();assert.strictEqual(nodes.bobAuditShareFallback.value,'Report B');assert.strictEqual(nodes.bobAuditNativeShare.hidden,true);
 console.log('Handoff behavior: visible text, clipboard success/denied/missing, stable snapshot, native share and cancellation passed');
}
checkHandoff().catch(error=>{console.error(error);process.exitCode=1});
