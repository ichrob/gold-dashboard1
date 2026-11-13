const assert=require('node:assert/strict'),{preferences,purchaseCandidates}=require('./degiro_handoff.js');
assert.deepEqual(preferences({budget:'1000',currency:'CHF',fees:'2,50',maxLoss:'10',minRR:'2',isin:'US0378331005',price:'42',qty:'8'}),{budget:'1000',currency:'CHF',fees:'2,50',maxLoss:'10',minRR:'2'});
assert.deepEqual(preferences({budget:'-3',currency:'XXX',fees:'NaN',minRR:'.3'}),{});
const now=Date.parse('2026-11-05T10:00:00Z'),id='DE000FG14AV8',products=[{isin:id,direction:'LONG'}];
const row={key:'execution',type:'BUY',isin:id,currency:'EUR',securityCurrency:'EUR',date:'2026-11-05T09:59:00Z',quantity:5,price:10,amount:-51,fee:1};
const data=()=>({code:'READ_OK',readOnly:true,fresh:true,snapshot:{accounts:[{accountKey:'account',journal:{activities:{code:'READ_OK',complete:true,checkedAt:'2026-11-05T10:00:00Z',rows:[{...row}]}}}]}});
const candidates=(d,known=[])=>purchaseCandidates(d,products,known,now);
assert.equal(candidates(data()).length,1);
assert.equal(candidates(data())[0].entry,10);
assert.equal(candidates(data())[0].settlementTotal,51);
const grossOnly=data();grossOnly.snapshot.accounts[0].journal.activities.rows[0].amount=-50;assert.equal(candidates(grossOnly)[0].settlementTotal,null,'Gross cash is not an all-in settlement');
for(const patch of [{type:'SELL'},{status:'CANCELLED'},{amount:-100},{quantity:0},{date:'2026-11-04T09:59:00Z'},{date:'2026-11-05T10:01:00Z'},{securityKind:'option'},{currency:'USD'},{securityCurrency:'CHF'}]){
 const d=data();Object.assign(d.snapshot.accounts[0].journal.activities.rows[0],patch);assert.equal(candidates(d).length,0,JSON.stringify(patch));
}
for(const patch of [{complete:false},{checkedAt:'2026-11-05T09:54:59Z'},{code:'ERROR'}]){const d=data();Object.assign(d.snapshot.accounts[0].journal.activities,patch);assert.equal(candidates(d).length,0);}
for(const type of ['SELL','BUY','TRANSFER']){const d=data();d.snapshot.accounts[0].journal.activities.rows.push({...row,type,key:'other',date:'2026-11-05T09:59:30Z'});assert.equal(candidates(d).length,0);}
assert.equal(candidates(data(),[{active:true,snapshot:{}}]).length,0);
assert.equal(candidates(data(),[{active:false,snapshot:{product:{isin:id,entry:10,quantity:5}}}]).length,0);
const noHistory=data();noHistory.snapshot.accounts[0].journal={};noHistory.snapshot.accounts[0].positions=[row];assert.equal(candidates(noHistory).length,0,'Holdings cannot manufacture a purchase');
const dateOnly=data();dateOnly.snapshot.accounts[0].journal.activities.rows[0].date='2026-11-05';assert.equal(candidates(dateOnly)[0].at,'','Never invent execution time');
console.log('Trade automation: preferences whitelist, original execution evidence, stale/incomplete history, fills, sales and duplicate guards passed');
