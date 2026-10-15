const fs=require('fs'),vm=require('vm'),assert=require('assert');
const panel=fs.readFileSync('degiro_product_audit_panel.py','utf8');
const start=panel.indexOf(' const safe=value=>');
const end=panel.indexOf(' function mobileAuditPayload(){',start);
assert(start>0&&end>start,'Pure mobile handoff formatter exists');
const isolated={};
vm.createContext(isolated);
vm.runInContext(panel.slice(start,end)+';globalThis.build=auditTextForChatGPT;',isolated);
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
assert(stale.includes('Keine einzelnen Produktdaten abrufbar.'));
assert(!stale.includes('Keine offenen Probleme'));
const unavailable=isolated.build({status:'unavailable',items:[]});
assert(unavailable.includes('Prüfstatus: unavailable'));
for(const needle of ['id="bobAuditShareChatGPT"','id="bobAuditCopyChatGPT"',
                     'navigator.share({title:','navigator.clipboard.writeText(value)',
                     "latestReport=null;render({status:'unavailable'","credentials:'same-origin'",
                     "byId('bobAuditShareChatGPT')?.addEventListener('click',shareMobileAudit)"])
 assert(panel.includes(needle),needle);
assert(!panel.includes('window.open('),'Avoid opening an external URL with ISINs in query strings');
console.log('Android private audit handoff: format, no secrets or prices, stale state, share, copy and auth passed');
