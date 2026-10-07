const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,isin='DE000PJ9NCK0';
function batch(date='07.10.2026',clock='17:21:32'){
 return [
 {ok:true,name:'terms.jpg',raw:'BNP PARIBAS\nBasispreis '+date+'\nKnock-Out '+date,data:{isin,terms:{strike:{value:3985.0025,dateText:date}}}},
 {ok:true,name:'quote.jpg',raw:'BNP PARIBAS\nGeld 10,46 Brief 10,47',data:{isin,bid:10.46,ask:10.47,price:'10.47',currency:'EUR',sourceTime:'',times:{}}},
 {ok:true,name:'indication.jpg',raw:'BNP PARIBAS\nIndikation\n'+clock+'\nÄhnliche Produkte',data:{isin,leverage:'35',times:{}}}];
}
let rows=batch(),series=b.linkScreenshotSeries(rows);
assert.equal(series.text,'07.10.2026 17:21:32');assert.equal(series.timeOrigin,'underlying');
assert.equal(rows[1].data.times.quote.at,'2026-10-07T15:21:32.000Z');assert(rows[1].data.times.quote.fromSeries);
assert(rows[2].data.times.leverage.fromSeries);assert.equal(rows[0].data.terms.strike.dateText,'07.10.2026');
let snapshot=b.mergeScreenshotEvidence(null,rows[1].data,'quote.jpg');snapshot=b.mergeScreenshotEvidence(snapshot,rows[2].data,'indication.jpg');
assert(snapshot.evidence.Geld.fromSeries);assert(snapshot.evidence.Brief.fromSeries);assert.equal(snapshot.evidence.Brief.timeOrigin,'underlying');
assert(b.productFieldStates({isin,price:10.47,leverage:35,snapshot},Date.parse(series.at)).ask.fromSeries);
assert(b.screenshotSummary(snapshot).includes('keine gesondert bestätigte Geld-/Briefzeit'));
rows=batch('');series=b.linkScreenshotSeries(rows);assert(series.dateUnknown);assert.equal(series.at,null);assert.equal(series.text,'17:21:32');
snapshot=b.mergeScreenshotEvidence(null,rows[1].data,'quote.jpg');assert.equal(snapshot.evidence.Brief.at,null);assert(!b.evidenceTiming(snapshot.evidence.Brief).fresh);
rows=batch('07.10.2026','17:21');series=b.linkScreenshotSeries(rows);assert.equal(series.text,'07.10.2026 17:21');assert.equal(series.at,null);
rows=batch();rows[1].data.times.quote={present:true,text:'invalid',at:null};b.linkScreenshotSeries(rows);assert.equal(rows[1].data.times.quote.text,'invalid');
rows=batch();rows[2].data.times.leverage={present:true,text:'07.10.2026 17:20:00',at:'2026-10-07T15:20:00Z'};b.linkScreenshotSeries(rows);assert.equal(rows[2].data.times.leverage.at,'2026-10-07T15:20:00Z');
for(const change of [r=>r[2].raw+='\nIndikation 17:25:00',r=>r[0].raw+='\n08.10.2026',r=>r[2].data.isin='DE000FG34XV8',r=>r[2].raw='17:27\nHandelszeiten 08:00:00 - 22:00:00',r=>r[2].raw='Indikation 29:00:00']){rows=batch();change(rows);assert.equal(b.linkScreenshotSeries(rows),null);}
rows=batch();rows[1].data.sourceTime='07.10.2026 17:25:00';rows[1].data.times.quote={present:true,text:rows[1].data.sourceTime,at:'2026-10-07T15:25:00Z'};series=b.linkScreenshotSeries(rows);assert.equal(series.timeOrigin,'product');assert.equal(rows[1].data.sourceTime,'07.10.2026 17:25:00');
console.log('Underlying series timing: automatic inheritance, provenance, own clocks, missing dates and conflicts passed');
