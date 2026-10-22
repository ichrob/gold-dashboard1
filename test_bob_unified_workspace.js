const assert=require('node:assert/strict');
const fs=require('node:fs');
const a=require('./bob_unified_workspace.js');
const date=new Date('2026-10-22T04:20:00Z');
const now=date.getTime();
assert.equal(a.zurichDay(date),'2026-10-22');
assert.equal(a.originalAge('2026-10-22T06:19:50+02:00',now),10000);
assert.equal(a.originalAge('2026-10-22T04:19:00Z',now),60000);
assert.equal(a.originalAge('2026-10-22T04:18:59Z',now),61000);
assert.equal(a.originalAge('22.10.2026 06:19',now),null);
assert.equal(a.originalAge('2026-10-22T04:20:01Z',now),null);
const base={expired:false,signal:'LONG',reason:'Signal bestätigt',
 spotAt:'2026-10-22T04:19:40Z',spotGenuine:true,spotError:null,
 analysisReady:true,productCount:3,tradeActive:false};
const ok=a.analyzeInputs(base,now);
assert.equal(ok.signal,'LONG');assert.equal(ok.spot.ok,true);assert.equal(ok.analysis.ok,true);
assert.equal(ok.products.ok,true);assert.equal(ok.trade.ok,false);assert.equal(ok.tradeable,false);
assert.equal(ok.canTradeAutomatically,false);
assert.equal(a.analyzeInputs({...base,signal:'ABWARTEN'},now).signal,'ABWARTEN');
assert.equal(a.analyzeInputs({...base,signal:'SHORT'},now).signal,'SHORT');
assert.equal(a.analyzeInputs({...base,expired:true},now).analysis.ok,false);
assert.equal(a.analyzeInputs({...base,spotAt:'2026-10-22T04:18:40Z'},now).spot.ok,false);
assert.equal(a.analyzeInputs({...base,spotGenuine:false},now).analysis.ok,false);
assert.equal(a.analyzeInputs({...base,analysisReady:false},now).analysis.ok,false);
assert.equal(a.analyzeInputs({...base,spotError:'provider-outage'},now).spot.ok,false);
assert.equal(a.analyzeInputs({...base,reason:'Zeitstempel fehlt'},now).analysis.ok,false);
assert.equal(a.analyzeInputs({...base,productCount:null},now).products.ok,false);
const initial=a.visibleChange(null,['DE000FG14AV8','DE000FG14AV8']);
assert.equal(initial.known,false);assert.equal(initial.current.length,1);
const changed=a.visibleChange(['DE000FG14AV8','US0378331005'],['DE000FG309G0','US0378331005']);
assert.deepEqual(changed.added,['DE000FG309G0']);
assert.deepEqual(changed.removed,['DE000FG14AV8']);
assert.deepEqual(changed.unchanged,['US0378331005']);
assert.equal(a.visibleChange([],['DE000FG14AV9']).current.length,0);
const draft={day:'2026-10-22',currency:'EUR',budget:10000,orders:[
 {isin:'DE000FG14AV8',side:'Kauf',qty:5,price:1200,fees:100,cost:6100,stop:900,target:1800},
 {isin:'DE000FG14AV8',side:'Verkauf',qty:2,price:1100,fees:100,cost:2300,stop:null,target:null}
]};
const json=a.serializeDraftBackup({...draft,accessToken:'secret'},date);
assert(!json.includes('accessToken')&&!json.includes('secret'));
const result=a.validateDraftBackup(json,'2026-10-22');
assert.deepEqual(result,draft);
for(const change of [
 data=>{data.drafts.orders[0].cost=6101;},
 data=>{data.drafts.orders[0].isin='DE000FG14AV9';},
 data=>{data.drafts.orders[0].qty=2.5;},
 data=>{data.drafts.orders[0].stop=1400;},
 data=>{data.drafts.orders[0].target=1000;},
 data=>{data.drafts.day='2026-10-21';},
 data=>{data.drafts.currency='USD';},
 data=>{data.drafts.budget=100;},
 data=>{data.drafts.orders=Array(51).fill(data.drafts.orders[0]);},
 data=>{data.format='legacy';}
]){
 const data=JSON.parse(json);change(data);
 assert.throws(()=>a.validateDraftBackup(JSON.stringify(data),'2026-10-22'));
}
assert.throws(()=>a.validateDraftBackup('x'.repeat(100001),'2026-10-22'));
assert.throws(()=>a.serializeDraftBackup({...draft,day:'2026-10-21'},date));
const js=fs.readFileSync('bob_unified_workspace.js','utf8');
const server=fs.readFileSync('server.py','utf8');
assert.match(js,/Bob, bereite alles vor/);
assert.match(js,/root\.loadData\(true\)/);
assert.match(js,/Produkt für Orderentwurf übernehmen/);
assert.match(js,/target\.dispatchEvent\(new Event\('change'/);
assert.match(js,/data-view="degiro2"/);
assert.match(js,/Originalkurs älter als 90 Sekunden/);
assert.match(js,/refreshTradeTestQuotes/);
assert.match(server,/BOB_UNIFIED_WORKSPACE_JS/);
assert.match(server,/\/bob_unified_workspace\.js/);
assert.ok(!/\/api\/(?:trade\/execute|degiro\/order|snaptrade\/orders)/.test(js));
console.log('Unified workspace: same-source preflight gates, safe mobile navigation, explicit backup, strict restoration and no broker orders passed');
