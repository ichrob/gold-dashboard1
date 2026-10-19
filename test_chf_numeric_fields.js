const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobDegiro;
for(const text of ['Geld CHF 12,34\nBrief CHF 12,35','Geld CHF12,34 Brief CHF12,35','Geld\nCHF 12,34\nBrief\nCHF 12,35']){
 assert.equal(b.ocrNumericFields(text).bid,12.34,text);
 assert.equal(b.ocrNumericFields(text).ask,12.35,text);
 assert.equal(b.unconfirmedOcrFields(text,[text,text]).length,0);
}
assert.equal(b.ocrNumericFields('Geld Vol. 25K\nBrief Vol. 25K').bid,undefined);
assert.equal(b.ocrNumericFields('Geld CHF 12,O4').bid,undefined);
assert(b.unconfirmedOcrFields('Geld CHF 12,34',['Geld CHF 12,34','Geld CHF 12,84']).includes('bid'));
const words=[{text:'Geld',bbox:{x0:10,x1:50,y0:100,y1:120}},{text:'CHF12,34',bbox:{x0:100,x1:190,y0:100,y1:120}},{text:'Brief',bbox:{x0:210,x1:250,y0:100,y1:120}},{text:'CHF12,35',bbox:{x0:300,x1:390,y0:100,y1:120}}];
assert(b.scalarCellRect({words},'bid').x<100);
assert(b.scalarCellRect({words},'ask').x>250);
console.log('CHF prefixed and two-column amounts, volume exclusion and disagreeing reads checked');
const broker='DEGIRO\nKursdaten\nZuletzt CHF 12,34 19/10/2026 16:10\nGeld CHF 12,34 Brief CHF 12,35\nGeld Vol. 25K Brief Vol. 25K\nSymbol | ISIN\nDE000FG8NHQ3\nBörse Societe Generale OTC';
const imported=b.detailScreenshotData(broker,'DE000FG8NHQ3');
assert(imported.ok,imported.reason);assert.equal(imported.bid,12.34);assert.equal(imported.ask,12.35);assert.equal(imported.currency,'CHF');
assert.equal(b.unconfirmedOcrFields(broker,[broker,broker]).length,0);
