const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const queued=[{trade:{tradeId:'closed',active:true,stop:95},event:{kind:'stop'}},
 {trade:{tradeId:'other',active:true,stop:80}}];
let stored=JSON.stringify(queued),closedId;
const c={window:{addEventListener(){},BobTradeSync:{current:()=>({tradeId:'closed',active:true}),close:t=>{closedId=t.tradeId;return true;}}},
 document:{addEventListener(){},getElementById(){return null;}},setInterval(){},
 localStorage:{getItem:()=>stored,setItem:(key,value)=>{stored=value;}}};
vm.runInNewContext(fs.readFileSync('real_trade_journal.js','utf8'),c);
c.window.BobRealTrades.reconcileClosed([{id:'closed',active:false,snapshot:{tradeId:'closed',active:false,stop:100,settlement:{netCHF:7}}}]);
const saved=JSON.parse(stored);
assert.equal(closedId,'closed');assert.equal(saved[0].trade.active,false);
assert.equal(saved[0].trade.settlement.netCHF,7);assert.equal(saved[0].event.staleClientTrade.stop,95);
assert.equal(saved[0].event.kind,'stop');assert.deepEqual(saved[1],queued[1]);
console.log('Closed-trade sync retains queued observations without reopening or touching another trade');
