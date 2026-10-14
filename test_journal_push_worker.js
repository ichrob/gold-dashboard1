const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
async function shows(prefs,details){let job,shown=0,handlers={};const sandbox={self:{addEventListener:(k,f)=>handlers[k]=f,registration:{showNotification:async()=>shown++}},caches:{open:async()=>({match:async key=>key.startsWith('/__bob_closed_trade__/')?((prefs.closedTradeIds||[]).includes(decodeURIComponent(key.split('/').at(-1)))?{}:undefined):({json:async()=>prefs})})},Date,Number,String,Boolean};vm.runInNewContext(fs.readFileSync('sw.js','utf8'),sandbox);handlers.push({data:{json:()=>({data:{kind:'trade',tradeId:'real-1',...details}})},waitUntil:p=>job=p});await job;return shown;}
(async()=>{
assert.equal(await shows({trade:true,activeTrade:false},{journalManaged:true}),1);
assert.equal(await shows({trade:false,activeTrade:false},{journalManaged:true}),0);
assert.equal(await shows({trade:true,activeTrade:true,tradeId:'other'},{journalManaged:true}),0);
assert.equal(await shows({trade:true,activeTrade:true,tradeId:'real-1'},{journalManaged:true}),1);
assert.equal(await shows({trade:true,activeTrade:false},{}),0);
assert.equal(await shows({trade:true,activeTrade:false},{journalManaged:true,expiresAt:1}),0);
assert.equal(await shows({trade:true,activeTrade:false,closedTradeIds:['real-1']},{journalManaged:true}),0);
console.log('6 service-worker delivery cases passed');
})().catch(e=>{console.error(e);process.exitCode=1});
