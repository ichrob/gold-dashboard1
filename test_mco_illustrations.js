const assert=require('node:assert/strict');
const {illustrationPlan:plan}=require('./video_brief');
const item={transcriptAnalyzed:true,trustedTranscript:true};
const section=(text,source=text)=>({text,evidence:[{at:42,text:source}]});
assert.equal(plan(item,section('Gold bleibt seitwärts.','Gold is trading sideways in a range.')).kind,'range');
assert.equal(plan(item,section('Gold könnte aufwärts steigen.','Gold could move higher.')).direction,'up');
assert.equal(plan(item,section('Gold könnte abwärts fallen.','Gold could move lower.')).direction,'down');
assert.equal(plan(item,section('Ein Ausbruch nach oben wäre möglich, wenn der Widerstand fällt.','If gold can break above resistance, a breakout is possible.')).kind,'breakout');
assert.equal(plan(item,section('Ausbruch nach unten möglich.','A breakout could break below support.')).direction,'down');
assert.equal(plan(item,section('Ein Rücksetzer ist möglich.','A pullback is possible.')).kind,'pullback');
assert.equal(plan(item,section('Gold könnte steigen oder fallen.','The upside and downside are both possible.')).kind,'scenarios');
for(const text of ['Gold will not move higher.','There is no breakout above resistance.','Gold wird nicht steigen.']){
 const p=plan(item,section(text));assert.equal(p.kind,'statement',text);assert.equal(p.direction,null);
}
assert.equal(plan(item,section('Gold steigt.','Gold will not move higher.')).direction,null,'Summary alone cannot invent a direction');
assert.equal(plan(item,section('Wirtschaftliche Einordnung ohne Richtung.')).kind,'statement');
assert.equal(plan({...item,trustedTranscript:false},section('Gold is bullish.')),null);
assert.equal(plan({...item,transcriptAnalyzed:false},section('Gold is bullish.')),null);
assert.equal(plan(item,{text:'Gold steigt.',evidence:[]}),null);
assert.equal(plan(item,{text:'Gold steigt.',evidence:[{at:-1,text:'Gold could move higher.'}]}),null);
assert.equal(plan(item,{text:'Gold steigt.',evidence:[{at:Infinity,text:'Gold could move higher.'}]}),null);
const p=plan(item,section('Unterstützung und Widerstand sind entscheidend.','For XAU/USD, support at 4200 USD and resistance at 4250 USD matter.'));
assert.equal(p.kind,'levels');assert.equal(p.instrument,'Gold Spot / XAU/USD');
assert.deepEqual(p.levels.map(x=>[x.label,x.amount,x.at]),[['Unterstützung','4200 USD',42],['Widerstand','4250 USD',42]]);
assert.equal(plan(item,section('Support 4200 with RSI 70.')).levels.length,0,'No invented unit for unlabelled numbers');
assert.equal(plan(item,section('GDX support at 40 USD; XAU/USD support at 4200 USD.')).levels.length,0,'Never merge instruments onto one price diagram');
assert.equal(plan(item,section('If support holds, gold could move higher.')).conditional,true);
assert(!JSON.stringify(p).includes('marketAt'),'Video position is not a market time');
console.log('MCO illustration plans: sourced concepts, negation, instruments, exact labelled amounts and no fabricated clocks passed');

assert.equal(plan(item,section('Support is not at 4200 USD.')).levels.length,0,'Negated levels cannot become positive labels');
