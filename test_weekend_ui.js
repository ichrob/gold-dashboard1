const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const source=scripts.map(x=>x[1]).find(x=>x.includes('window.BobWeekendPause=function'));
assert(source,'Weekend helper must be loaded before pollers');
const sandbox={window:{},Date,Intl,Object,Number};
vm.createContext(sandbox);
const start=source.indexOf('window.BobWeekendPause=function');
const end=source.indexOf('\n};',start);
assert(start>=0&&end>start,'Weekend helper is declared');
vm.runInContext(source.slice(start,end+3),sandbox);
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
assert(html.includes('document.visibilityState==="visible"&&!window.BobWeekendPause?.()')||html.includes('document.visibilityState!=="visible"||window.BobWeekendPause?.()'));
assert(html.includes('MARKT GESCHLOSSEN · SIMULATION PAUSIERT'));
assert(html.includes('restoreWeekendCards'));
assert(html.includes('else loadData();'));

assert(html.includes('const notice=document.getElementById(\'gold-special-session\')'));
console.log('Weekend UI: Friday/Monday and DST behavior; paused market polling and simulation labels OK');

assert(html.includes("fetch('/api/weekend-archive'"));
assert(html.includes('chartHistory=history;'));
assert(html.includes('restoreServerWeekendArchive();'));
console.log('Weekend persistent display-only recovery hooks OK');

assert(html.includes("if(isFuture&&!window.BobWeekendPause?.())loadFutureChart(tf);"));
assert(html.includes("result.cfdHistory?.[tf]"));
assert(html.includes("Keine vollständigen OHLC-Kerzen")||html.includes("keine vollständigen OHLC-Kerzen"));
console.log('Persistent Spot and CFD chart recovery hooks OK');

assert(html.includes("const model=sampledSpot?null:chartFibonacci(v,chartAtr,assessment.available?assessment.dir:null);"));
assert(html.includes("Aufzeichnung vom '+dayExtremes.date"));
assert(html.includes("Fibonacci/Kursziele nicht berechnet"));
assert(html.includes("dayExtremes.historical?' beobachtet':' heute'"));
console.log('Historical chart: sample-only Fibonacci blocked, dates labeled correctly');

// Functional test of the exact display-only projection used by the chart.
const chartScript=scripts.map(x=>x[1]).find(x=>x.includes('function chartDisplayAllowed('));
assert(chartScript,'Main chart script is present');
const viewStart=chartScript.indexOf('function chartDisplayAllowed('),viewEnd=chartScript.indexOf('let chartHitMap=null,chartSelected=null;',viewStart);
assert(viewStart>=0&&viewEnd>viewStart,'Display-only chart projection exists');
const chartSandbox={Date,Intl,Object,Number,Map};
vm.createContext(chartSandbox);
vm.runInContext(chartScript.slice(viewStart,viewEnd),chartSandbox);
const fridayStart=Date.parse('2026-11-12T23:00:00Z'); // Friday 00:00 Zurich
const fridayBars=Array.from({length:274},(_,i)=>({openTime:fridayStart+i*300000,close:4000+i}));
const saturdayFake={openTime:Date.parse('2026-11-14T10:00:00Z'),close:9999};
const syntheticFriday={openTime:fridayStart+274*300000,close:9999,synthetic:true};
const allFriday=[...fridayBars,saturdayFake,syntheticFriday];
const day=chartSandbox.chartVisibleBars(allFriday,'day');
assert.equal(day.length,274,'Whole observed Friday remains available at 5m, not 120 bars');
assert.equal(day[0].openTime,fridayStart);
assert.equal(day.at(-1).close,fridayBars.at(-1).close);
assert.equal(chartSandbox.chartVisibleBars(allFriday,'recent').length,120);
assert.equal(chartSandbox.chartVisibleBars([saturdayFake],'day').length,0);
const sundayReal={openTime:Date.parse('2026-11-15T22:10:00Z'),close:4001};
assert.equal(chartSandbox.chartVisibleBars([...allFriday,sundayReal],'day').length,1,'Original Sunday reopening remains available');
assert(html.includes('id="chartScope"')&&html.includes('Letzter Handelstag'));
assert(html.includes('if(closedMarket&&v.length)'));
assert(html.includes('Schlusskurs: '+"'"+'+priceLabel(Number(chosen.close))'));
console.log('Weekend Friday chart: complete day, user interval scope, no synthetic Saturday, real Sunday OK');
