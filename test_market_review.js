const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('// Read-only source and conversion health');
const end=html.indexOf('function renderAnalysisBlocks()',start);
assert(start>=0&&end>start);
const el={textContent:''};
const env={liveBundleCache:null,$:id=>id==='marketInputQuality'?el:null,Date,Number};
vm.createContext(env);vm.runInContext(html.slice(start,end),env);
assert(html.includes('id="marketInputQuality"'));
env.renderMarketInputQuality();
assert(el.textContent.includes('DATENPRÜFUNG NICHT VERFÜGBAR'));
const at=new Date(Date.UTC(2026,9,15,11,0)).toISOString();
env.renderMarketInputQuality({marketReview:{
 version:'market-input-review-v1',warnings:['1h: EMA200-Kontext fehlt'],
 spot:{state:'ok',at},
 frames:{'5m':{state:'ok',closed:220,ema200:'available',lastClosedAt:Date.parse(at)},
         '15m':{state:'ok',closed:220,ema200:'available',lastClosedAt:Date.parse(at)},
         '1h':{state:'insufficient',closed:100,ema200:'context-unavailable',lastClosedAt:Date.parse(at)}},
 spotComparison:{status:'deviation',clockGapSeconds:20},
 fx:{state:'source-time-unknown',eurPerChf:1.15}
}});
for(const term of ['Datenqualität','5m','15m','1h','EMA200','ACHTUNG','Abrufzeit','1 CHF ≈ 1.150000 EUR']){
 assert(el.textContent.toLowerCase().includes(term.toLowerCase()),term+': '+el.textContent);
}
assert(!el.textContent.includes('HANDEL FREIGEGEBEN'));
console.log('Market input diagnostics render accurately without claiming trade clearance');
