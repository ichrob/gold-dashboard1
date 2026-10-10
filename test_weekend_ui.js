const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const source=scripts.map(x=>x[1]).find(x=>x.includes('window.BobWeekendPause=function'));
assert(source,'Weekend helper must be loaded before pollers');
const sandbox={window:{},Date,Intl,Object,Number};
vm.createContext(sandbox);vm.runInContext(source,sandbox);
function epoch(iso){return Date.parse(iso)}
const closed=sandbox.window.BobWeekendPause;
assert.equal(closed(epoch('2026-10-09T20:59:00Z')),false);
assert.equal(closed(epoch('2026-10-09T21:00:00Z')),true);
assert.equal(closed(epoch('2026-10-10T04:00:00Z')),true);
assert.equal(closed(epoch('2026-10-11T21:59:00Z')),true);
assert.equal(closed(epoch('2026-10-11T22:00:00Z')),false);
assert.equal(closed(epoch('2026-10-23T21:00:00Z')),true);
assert.equal(closed(epoch('2026-10-25T22:59:00Z')),true);
assert.equal(closed(epoch('2026-10-25T23:00:00Z')),false);
// Pollers stay disabled on weekend; explicit manual user actions remain available.
assert(html.includes('document.visibilityState==="visible"&&!window.BobWeekendPause()'));
assert(html.includes('MARKT GESCHLOSSEN · SIMULATION PAUSIERT'));
assert(html.includes('const notice=document.getElementById(\'gold-special-session\')'));
console.log('Weekend UI: Friday/Monday and DST behavior; paused market polling and simulation labels OK');
