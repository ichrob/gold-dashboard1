const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
async function shows(prefs,details){let job,shown=0,handlers={};const sandbox={self:{addEventListener:(k,f)=>handlers[k]=f,registration:{showNotification:async()=>shown++}},caches:{open:async()=>({match:async key=>key.startsWith('/__bob_closed_trade__/')?undefined:({json:async()=>prefs})})},Date,Number,String,Boolean};vm.runInNewContext(fs.readFileSync('sw.js','utf8'),sandbox);handlers.push({data:{json:()=>({data:{kind:'general',riskOnly:true,expiresAt:Date.now()+60000,...details}})},waitUntil:p=>job=p});await job;return shown;}
(async()=>{
 assert.equal(await shows({risk:true,general:true},{}),1);
 assert.equal(await shows({risk:false,general:true},{}),0);
 assert.equal(await shows({risk:true,general:false},{}),0);
 assert.equal(await shows({risk:true,general:true},{expiresAt:1}),0);
 assert.equal(await shows({risk:true,general:true},{expiresAt:null}),0);
 assert.equal(await shows({risk:false,trade:true,activeTrade:true,tradeId:'a'},{riskOnly:false,kind:'trade',tradeId:'a'}),1,'Existing stops independent of risk opt-out');
 console.log('Risk push worker: opt-in, channel, expiry and unaffected existing stop alerts passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
