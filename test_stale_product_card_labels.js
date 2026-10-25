'use strict';
// Regression: stale issuer snapshots must never render a fresh green tick.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('degiro_product_audit_panel.py','utf8');
const start=src.indexOf(' function productCardHeadline(');
const end=src.indexOf(' function mount(){',start);
assert(start>0&&end>start,'Pure audit headline classifier exists');
const ctx={};vm.createContext(ctx);
vm.runInContext(src.slice(start,end)+'\nglobalThis.headline=productCardHeadline;',ctx);
const item={isin:'DE000FG34XV8',state:'issuer-evidence-complete',missing:[],tradeApproved:false};
const active=ctx.headline('ok',item);
assert(active.startsWith('✓ '),'Current complete analysis may keep its existing checkmark');
for(const status of ['stale','unavailable','checking-new-list','waiting-for-screenshot','']) {
 const title=ctx.headline(status,item);
 assert(!title.includes('✓'),status+' must NOT show green verified status');
 assert(title.includes('aktuelle Quellenprüfung fehlt'),'Missing freshness must be explicit: '+status);
}
assert(ctx.headline('ok',{...item,state:'incomplete',missing:['leverage-time']}).includes('Fehlende Nachweise: 1'));
for(const status of ['ok','stale','unavailable'])
 assert.equal(ctx.headline(status,{isin:'DE000FG4TJL6',state:'terminated'}),'DE000FG4TJL6 · Produkt beendet');
assert(!ctx.headline('ok',{...item,state:'incomplete',missing:[]}).includes('✓'));
assert(src.includes("const shareHint=byId('bobAuditShareHint')"),'Staleness also shown outside collapsed status details');
assert(src.includes("summary.textContent=productCardHeadline(r.status,item)"));
assert(!src.includes("const healthy=['issuer-evidence-complete'"),'Previous unchecked headline gate removed');
console.log('Product audit: stale/unknown/current, incomplete, and issuer-ended badges preserved without false live proof');
