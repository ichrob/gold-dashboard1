const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8'),ctx={};vm.createContext(ctx);
vm.runInContext(html.slice(html.indexOf('function volatilityDisplay('),html.indexOf('function renderAnalysisBlocks(')),ctx);
assert.equal(ctx.volatilityDisplay(0,4000).label,'NIEDRIG');
assert.equal(ctx.volatilityDisplay(10,4000).label,'NIEDRIG');
assert.equal(ctx.volatilityDisplay(20,4000).label,'MITTEL');
assert.equal(ctx.volatilityDisplay(26,4000).label,'HOCH');
for(const v of [null,NaN,-1,Infinity])assert.equal(ctx.volatilityDisplay(v,4000).label,'NICHT VERFÜGBAR');
assert.equal(ctx.analysisBlockDataLabel(false,0,[]),'DATEN FEHLEN');
assert.equal(ctx.analysisBlockDataLabel(false,100,['alt']),'AKTUALITÄT UNBESTÄTIGT');
assert.equal(ctx.analysisBlockDataLabel(false,20,[]),'DATEN UNVOLLSTÄNDIG');
assert.equal(ctx.analysisBlockDataLabel(true,100,[]),'ANMELDUNG FEHLT');
for(const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
console.log('Analysis labels: boundaries, invalid inputs, missing/stale/session states and syntax passed');
// Choosing 100 visible candles must not discard available EMA200 history.
const warm={C:[],lastPrice:0,analyze(){},reportBobDiag(){}};vm.createContext(warm);
vm.runInContext(html.slice(html.indexOf('function hydrateTechnicalFromBundle('),html.indexOf('async function loadData(')),warm);
for(const count of [100,240,500]){
 const rows=Array.from({length:count},(_,i)=>({close:4000+i,isOpen:false}));
 rows.push({close:9999,isOpen:true});
 assert(warm.hydrateTechnicalFromBundle({history:{bars_by_tf:{'5m':rows}}},100));
 assert.equal(warm.C.length,Math.min(count,240));
 assert.equal(warm.C.at(-1).close,4000+count-1);
}
console.log('EMA200 history: 100-candle display retains warm-up; open bars excluded; short history not fabricated');
