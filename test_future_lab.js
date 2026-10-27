const assert=require('node:assert/strict'),fs=require('node:fs');
const {preflight,stressCases,snapshot,stages}=require('./future_lab.js');
const data={
 mode:'four-independent-paper-accounts',realOrders:false,accounts:[
  {profile:'conservative',control:{initialCapital:100,equity:99.5,checkedAt:'2026-10-12T09:00:00Z',status:'active'},stats:{closed:1},
   performance:{pricedTrades:2,positivePricedTrades:1,observedMaxDrawdownPct:2.5,quoteMissingChecks:1,quoteStatus:'confirmed'}},
  {profile:'balanced',control:{initialCapital:100,equity:102},stats:{closed:0},performance:{pricedTrades:0}},
  {profile:'offensive',control:{initialCapital:100,equity:93},stats:{closed:1},performance:{pricedTrades:1,positivePricedTrades:0}},
  {profile:'trend800',control:{initialCapital:800,equity:801},stats:{closed:0},performance:{pricedTrades:0}}
 ]};
const rows=snapshot(data);
const five={...data,mode:'five-independent-paper-accounts',accounts:[...data.accounts,
 {profile:'early100',control:{initialCapital:100,checkedAt:1792100000000},performance:{}}]};
assert.equal(snapshot(five).length,5,'Current server response has five accounts');
assert.equal(snapshot(five)[4].checkedAt,1792100000000,'Numeric server clocks must remain visible');
assert.throws(()=>snapshot({...five,accounts:data.accounts}),/Papierkonto/);
assert.throws(()=>snapshot({...data,accounts:five.accounts}),/Papierkonto/);
assert.equal(rows.length,4);
assert.equal(rows[0].priced,2);
assert.equal(rows[0].drawdown,2.5);
assert.equal(rows[0].closedToday,1);
assert.equal(rows[0].closedTotal,null,'Unavailable cumulative trade evidence must not be guessed');
assert.equal(rows[0].observationDays,0,'No daily records means no proven observation days');
assert.equal(rows[3].initial,800);
assert.throws(()=>snapshot({...data,realOrders:true}),/Papierkonto/);
assert.throws(()=>snapshot({...data,accounts:data.accounts.slice(0,3)}),/Papierkonto/);
assert.throws(()=>snapshot({...data,accounts:[data.accounts[0],data.accounts[0],...data.accounts.slice(2)]}),/Doppelte/);
const checks=stressCases();
assert.equal(checks.length,9);
assert(checks.every(x=>x.passed), 'Every synthetic safety test must pass.');
assert.equal(checks.filter(x=>x.allowed).length,1,'Only synthetic control case may pass.');
const example={marketOpen:true,sourceConfirmed:true,quoteAgeSeconds:10,stopDistance:20,koDistance:40,expectedNetR:1,
 remainingDailyLoss:1,duplicateOrder:false,brokerAckKnown:true,emergencyStop:false};
assert.equal(preflight(example).allowed,true);
for(const bad of [{quoteAgeSeconds:500},{koDistance:12},{duplicateOrder:true},{brokerAckKnown:false},
 {emergencyStop:true},{sourceConfirmed:false},{expectedNetR:-1},{remainingDailyLoss:0},{marketOpen:false}]){
 assert.equal(preflight({...example,...bad}).allowed,false,JSON.stringify(bad));
}
for(const x of [null,undefined,NaN,Infinity,-1])assert.equal(preflight({...example,quoteAgeSeconds:x}).allowed,false);
assert.equal(stages.length,11);
for(const key of ['paper','backtest','broker','execution','robustness','cost','live','learning'])assert(stages.includes(key));
const js=fs.readFileSync('future_lab.js','utf8'),html=fs.readFileSync('Bob.html','utf8'),py=fs.readFileSync('server.py','utf8');
assert(html.includes('src="/future_lab.js?v=20261011-v1"'));
assert(html.includes('window.BobFutureLab?.mount(futurePanel)'));
assert(html.includes("['future','◇','Zukunft','Pläne und Broker']"));
assert(py.includes('if path == "/future_lab.js"'));
assert(js.includes("body:JSON.stringify({mode:'simulation-profiles',day})"),'Must reuse existing paper mode.');
assert(js.includes('Tage mit protokollierter Prüfung'),'Show longitudinal evidence carefully');
assert(js.includes("if(!response.ok)throw Error"),'Source failure must be surfaced.');
assert(js.includes("raw.realOrders!==false"),'Future panel cannot rely on real order activity.');
assert(js.includes("Kein Broker verbunden"),'No broker connection may be implied.');
assert(!/\/api\/(order|broker\/execute|trade\/open)/.test(js),'No new execution endpoints');
assert(!js.includes('localStorage.'),'Do not silently invent persistent project completion.');
console.log('Zukunft lab: 4 paper accounts, 9 synthetic safety cases, 11 readiness stages and NO trading actions OK');

const seven={...five,mode:"seven-independent-paper-accounts",accounts:[...five.accounts,{profile:"early1000oct",control:{initialCapital:1000}},{profile:"normal1000oct",control:{initialCapital:1000}}]};
assert.equal(snapshot(seven).length,7);
