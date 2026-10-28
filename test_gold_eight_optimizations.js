/* Eight-point Gold UI: group, concise data, list generation and quote scheduling.
   These checks validate presentation without introducing execution privileges. */
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('degiro_assistant.js','utf8');
const exposed=src.replace('window.BobDegiro={',
 'window.BobDegiro={goldProductGroup,goldProductCompactView,goldProductOverview,goldProductSyncState,goldProductRepairStatus,');
assert.notEqual(exposed,src);
const context={window:{},console,Date,localStorage:{getItem:()=>null,setItem:()=>{}},navigator:{userAgent:'Android'}};
vm.createContext(context);vm.runInContext(exposed,context);
const b=context.window.BobDegiro,isin='DE000FD0S0G4';
const p={isin,index:1,name:'SG Gold Turbo Call',productDirection:'LONG',isinConfirmed:true};
const card=b.compactProductCard(p);
assert(card.includes('data-product-compact-summary'));
assert(card.includes('data-product-technical'));
assert(card.includes('Details · Produktangaben und Aktionen'));
assert(card.includes('data-execution-separate'));
assert(card.includes('data-gold-sync="unconfirmed"'));
assert(card.includes('data-gold-repair'));
assert(card.includes('Geld')&&card.includes('Brief')&&card.includes('Hebel')&&card.includes('KO-Abstand'));
assert(!card.includes('data-selection-approved'));
assert(!/<details data-product-technical[^>]*\sopen(?:[= >])/.test(card));
const factor={isin:'DE000FE4UF01',name:'Gold Faktor 10',productDirection:'LONG'};
const ended={isin:'DE000FC1CHB7',name:'SG Turbo',productDirection:'LONG',
 quote:{isin:'DE000FC1CHB7',productVerified:true,metadata:{status:2}}};
const overview=b.productUploadCards([p,factor,ended],'LONG');
assert(overview.includes('data-gold-summary'));
assert(overview.includes('data-gold-group="review"'));
assert(overview.includes('data-gold-group="factor"'));
assert(overview.includes('data-gold-group="ended"'));
assert(overview.indexOf('data-gold-group="review"')<overview.indexOf('data-gold-group="ended"'));
assert(overview.includes('Faktor Goldprodukt nicht verwendet'));
assert(overview.includes('Produkt beendet'));
assert(!b.evaluateProduct(factor).ok);
const stamp='2026-10-22T06:58:34.572Z',now=Date.parse('2026-10-22T19:40:00Z');
// This pure helper is intentionally tested with an explicit list generation:
 // the full app keeps its mutable listArchive in an isolated closure.
const evidence={Date,window:{},listArchive:{storedAt:stamp}};
vm.runInNewContext(src.slice(src.indexOf('function goldProductSyncState('),
 src.indexOf('function goldProductCompactView(')),evidence);
const row={isin,direction:'LONG',state:'analysis-evidence-complete',missing:[],tradeApproved:false};
evidence.window.BobProductAuditReport={status:'ok',lastCheckedAt:new Date(now-1000).toISOString(),
 listUploadedAt:stamp,items:[row]};
assert.equal(evidence.goldProductSyncState(p,now).state,'matched');
assert(evidence.goldProductRepairStatus(p,now).includes('Keine offenen'));
evidence.window.BobProductAuditReport.listUploadedAt='different-generation';
assert.equal(evidence.goldProductSyncState(p,now).state,'different-list');
evidence.window.BobProductAuditReport.listUploadedAt=stamp;
assert.equal(evidence.goldProductSyncState(p,now+181000).state,'unconfirmed');
evidence.window.BobProductAuditReport.items=[{...row,state:'incomplete',missing:['quote'],
 sourceRecovery:[{state:'waiting',retryAfterSeconds:60}]}];
assert.equal(evidence.goldProductSyncState(p,now).state,'missing');
assert(evidence.goldProductRepairStatus(p,now).includes('60 s'));
assert(!evidence.goldProductRepairStatus(p,now).includes('repariert'));
evidence.window.BobProductAuditReport.items=[{...row,state:'excluded-factor',missing:['factor']}];
assert.equal(evidence.goldProductSyncState(p,now).state,'excluded-factor');
assert(evidence.goldProductRepairStatus(p,now).includes('keine Reparatur'));
(async()=>{
 let clock=0,calls=[],rows=[{id:1,isin,key:'product',suppressed:true},
 {id:2,isin:'DE000FG4JXV7',key:'active'}];
 const scheduler=b.createQuoteRefresh({rows:()=>rows,now:()=>clock,request:async id=>calls.push(id)});
 await scheduler.refresh();assert.deepEqual(calls,[2]);
 await scheduler.refresh(true);assert.deepEqual(calls,[2,2]);
 clock=70000;rows[0]={...rows[0],suppressed:false};
 await scheduler.refresh();assert.deepEqual(calls,[2,2,1,2]);
 console.log('Eight-point Gold UI: grouping, collapsed cards, stale list, source retry, non-executable proof and quote suppression OK');
})().catch(e=>{console.error(e);process.exitCode=1});
// A valid shared issuer observation must survive the compact card's filter.
// Synthetic values: no private product data in regression fixtures.
const sharedAt=new Date(now-1000).toISOString();
const sharedProduct={...p,quote:{isin,productVerified:true,found:false,source:'SG',
 metadata:{status:1},chartEvidence:{pointAt:sharedAt},
 sharedTimeContext:{kind:'issuer-collection',isin,at:sharedAt,fields:['Referenzhebel']},
 issuerLeverageReference:{value:12.345,dated:false,eligible:false,sharedContextAt:sharedAt,source:'SG'}}};
const sharedFields=b.productFieldStates(sharedProduct,now);
assert.equal(sharedFields.leverage.state,'gemeinsamer SG-Zeitbezug · aktuell (nur Analyse)');
function compactLever(product,time){
 const html=b.goldProductCompactView(product,time);
 return {html,value:html.match(/Hebel<\/div><strong>([^<]*)<\/strong>/)?.[1]};
}
const sharedCard=compactLever(sharedProduct,now);
assert.equal(sharedCard.value,'12.345×');
assert(sharedCard.html.includes('data-compact-leverage-source'));
assert(sharedCard.html.includes('nur Analyse'));
assert(sharedCard.html.includes(sharedAt));
assert.equal(b.finalProductStatus(sharedProduct,now).complete,false);
assert.equal(compactLever(sharedProduct,now+300000).value,'—','Expired shared evidence stays unavailable');
assert.equal(compactLever(sharedProduct,now-2000).value,'—','Future time is not current evidence');
const mismatched=JSON.parse(JSON.stringify(sharedProduct));
mismatched.quote.sharedTimeContext.isin='DETEST000001';
assert.equal(compactLever(mismatched,now).value,'—','No cross-product evidence reuse');
const directProduct=JSON.parse(JSON.stringify(sharedProduct));
Object.assign(directProduct.quote,{leverage:8,leverageAt:sharedAt});
assert.equal(compactLever(directProduct,now).value,'8×','Fresh original leverage remains preferred');
console.log('Compact leverage: shared observation visible; stale/future/mismatched evidence rejected; original preferred');

assert(!card.includes('✓ Analyse-Nachweise vorhanden'));
assert(card.includes('data-product-auto-repair'));
assert(card.includes('Geld, Brief, Hebel fehlt'));
(async()=>{
 let calls=[],clock=0;
 const rows=[{id:1,isin,key:'healthy'},
  {id:2,isin,key:'missing',repairNeeded:true},
  {id:3,isin,key:'excluded',repairNeeded:true,suppressed:true}];
 const scheduler=b.createQuoteRefresh({rows:()=>rows,now:()=>clock,limit:1,
  request:async id=>{calls.push(id);if(id===2)throw Error('source unavailable');}});
 await scheduler.refresh();assert.deepEqual(calls,[2,1]);
 await scheduler.refresh();assert.deepEqual(calls,[2,1],'No retry storm after failure');
 clock=60000;await scheduler.refresh();assert.deepEqual(calls,[2,1,2,1]);
 console.log('Automatic repair queue: missing evidence first, bounded retries, excluded rows suppressed');
})().catch(e=>{console.error(e);process.exitCode=1});

// A bid-only source observation is visible but never an eligible pair.
const bidOnlyProduct={...p,quote:{isin,productVerified:true,found:false,eligible:false,
 metadata:{status:1,currency:'EUR'},oneSidedQuote:{isin,bid:7.25,ask:null,
 bidAt:new Date(now-1000).toISOString(),currency:'EUR',missingSide:'ask',
 priceKind:'issuer-bid-only',isExecutableQuote:false,degiroExecutable:false}}};
const onlyCard=b.goldProductCompactView(bidOnlyProduct,now);
assert(onlyCard.includes('7.25 EUR'));
assert(onlyCard.includes('Anbieter stellt keinen Briefkurs'));
assert(onlyCard.includes('Brief, Hebel fehlt'));
assert(!onlyCard.includes('✓ Analyse-Nachweise vorhanden'));
assert.equal(b.finalProductStatus(bidOnlyProduct,now).complete,false);
for(const time of [now+91000,now-2000])
 assert(!b.goldProductCompactView(bidOnlyProduct,time).includes('7.25 EUR'));
for(const change of [{isin:'wrong'},{ask:7.3},{currency:'CHF'},{isExecutableQuote:true}]){
 const bad=JSON.parse(JSON.stringify(bidOnlyProduct));Object.assign(bad.quote.oneSidedQuote,change);
 assert(!b.goldProductCompactView(bad,now).includes('7.25 EUR'));
}
console.log('Bid-only display: original clock, expiry, identity and pair restrictions passed');
