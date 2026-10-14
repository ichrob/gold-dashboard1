const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync('Bob.html','utf8');
const block=html.slice(html.indexOf('window.BobTradeSync={'),html.indexOf('async function setTradeEntry()'));
function env(current={}){const c={window:{},tradeMgmt:current,localStorage:{setItem(){}},renderActiveTradePlan(){},renderPositionStatus(){},restoreTradeMgmt(){}};vm.runInNewContext(block,c);return c;}
const remote={active:true,tradeId:'one',dir:'SHORT',stop:110,product:{isin:'test'}};
let c=env();assert.equal(c.window.BobTradeSync.restore(remote),true);assert.equal(c.tradeMgmt.tradeId,'one');
c=env({...remote,stop:105});c.window.BobTradeSync.restore(remote);assert.equal(c.tradeMgmt.stop,105);
c=env({...remote,dir:'LONG',stop:115});c.window.BobTradeSync.restore({...remote,dir:'LONG'});assert.equal(c.tradeMgmt.stop,115);
c=env({...remote,tradeId:'other'});assert.equal(c.window.BobTradeSync.restore(remote),false);assert.equal(c.tradeMgmt.tradeId,'other');
c=env();assert.equal(c.window.BobTradeSync.restore({...remote,active:false}),false);
console.log('Automatic restore: fresh device, tighter short/long stop, other position, closed trade passed');
