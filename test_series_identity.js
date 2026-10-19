const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const source=fs.readFileSync('degiro_assistant.js','utf8');
const c={window:{},navigator:{userAgent:'Android'}};vm.runInNewContext(source,c);
const api=c.window.BobDegiro,isin='DE000FG14AV8';
const raw='DEGIRO\nISIN '+isin+'\nGeld 12,34 EUR\nBrief 12,35 EUR';
const anchor=api.detailScreenshotData(raw,isin);
assert.equal(anchor.ok,true);
const missing='DEGIRO\nGeld 12,34 EUR\nBrief 12,35 EUR';
assert.equal(api.detailScreenshotData(missing,isin).ok,false);
const outcomes=[{name:'detail.jpg',ok:false,ocr:{data:{text:missing}}},{name:'identity.jpg',ok:true,data:anchor}];
const series=api.screenshotSeriesContext(outcomes,isin);
assert.equal(series.anchor,'identity.jpg');
const linked=api.detailScreenshotData(missing,isin,series);
assert.equal(linked.ok,true);assert.equal(linked.identityBasis,'Bilderserie');
assert.equal(linked.isin,isin);assert.equal(linked.identityContext.anchor,'identity.jpg');
assert.equal(api.screenshotSeriesContext(outcomes.slice(0,1),isin),null);
for(const wrong of ['ISIN DE000PJ9NB98','WKN PJ9NB9']){
 assert.equal(api.detailScreenshotData(missing+'\n'+wrong,isin,series).ok,false);
 assert.equal(api.screenshotSeriesContext([{...outcomes[0],ocr:{data:{text:missing+'\n'+wrong}}},outcomes[1]],isin),null);
}
assert.equal(api.screenshotSeriesContext([{name:'a',ok:true,data:linked},outcomes[0]],isin),null);
const uncertain=api.detailScreenshotData(missing,isin,series,['bid']);
api.removeUnconfirmedFields(uncertain,['bid']);
assert(!uncertain.bid); // Identity inheritance does not validate disputed prices.
assert.equal(linked.times?.quote?.present||false,false); // No manufactured clock.
console.log('Series identity: order independent anchor, missing ID recovery, conflicts blocked, clocks/prices preserved');
