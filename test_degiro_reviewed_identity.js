const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const c={window:{},navigator:{userAgent:'Android'}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),c);
const api=c.window.BobDegiro,id='DE000PJ9NB98';
const quote='Kursdaten\nGeld € 14,74\nBrief € 14,75\n19/10/2026 13:30\nSymbol | ISIN\nDEOOOPJONB9S\nBörse BNP OTC';
const title='DEOOOPJONB98 · BNP OTC\nBNP GOLD Unlimited Long SL\n4005.9009 STR 4005.9009 R 10 LV\n24.63';
for(const raw of [quote,title]){
 const r=api.detailScreenshotData(raw,id);assert.equal(r.ok,true,JSON.stringify(r));assert.equal(r.isin,id);
 assert.equal(api.detailScreenshotData(raw,'DE000FG14AV8').ok,false);
}
assert.equal(api.detailScreenshotData(quote.replace('BNP OTC','OTHER'),id).ok,false);
assert.equal(api.detailScreenshotData(quote+'\nISIN DE000FG14AV8',id).ok,false);
assert.equal(api.detailScreenshotData(quote.replace('DEOOOPJONB9S','DE000PJ1NB9S'),id).ok,false);
console.log('Reviewed DEGIRO identity aliases accepted; wrong product, missing broker and conflicting ISIN rejected');
