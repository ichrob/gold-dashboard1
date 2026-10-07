const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={console,Date,URL,URLSearchParams,Map,Set,Promise,setTimeout,clearTimeout,localStorage:{getItem:()=>null,setItem(){}},document:{readyState:'loading',addEventListener(){},getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[]}};
context.window=context;vm.createContext(context);
const source=fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={termLabelRows,normalizeProductTermLayout,');
vm.runInContext(source,context);const api=context.BobDegiro;
const identity='BNP PARIBAS\nISIN DE000PJ9NCK0\nWKN PJ9NCK\n';
for(const raw of [
 'Knock-Out Schwelle\n(07.10.2026) 3.985,0025 USD\nBasispreis\n(07.10.2026) 3.985,0025 USD',
 'Knock-Out Schwelle\no\n(07.10.2026)\n3.985,0025 USD\nBasispreis\n3.985,0025 USD\n\n(07.10.2026)',
 'Knock-Out\nSchwelle (07.10.2026) 3.985,0025 USD\nBasispreis (07.10.2026) 3.985,0025 USD'
]){
 const terms=api.parseProductTerms(identity+raw+'\nBezugsverhältnis 0,1\nLaufzeit & Open End');
 assert.equal(terms.error,undefined);for(const key of ['ko','strike']){assert.equal(terms[key].value,3985.0025);assert.equal(terms[key].displayDecimals,4);assert.equal(terms[key].dateText,'07.10.2026');}
 assert.equal(terms.ratio.value,0.1);assert.equal(terms.maturity.value,'Open End');
}
const bad=identity+'Knock-Out Schwelle (07.10.2026) 3.985,OO25 USD\nBasispreis (07.10.2026) 3.985,0025 USD\nBezugsverhältnis 0,1\nTyp Unlimited Long\nLaufzeit Open End';
assert.ok(api.parseProductTerms(bad).error);
const partial=api.detailScreenshotData(bad,'DE000PJ9NCK0');
assert.equal(partial.ok,true);assert.equal(partial.terms.ko,undefined);assert.equal(partial.terms.strike.value,3985.0025);assert.equal(partial.terms.ratio.value,0.1);assert.ok(partial.importWarnings.length);
const conflict=api.detailScreenshotData(identity+'Knock-Out Schwelle 3.985,0025 USD\nKnock-Out Schwelle 4.000,00 USD','DE000PJ9NCK0');
assert.equal(conflict.ok,false);
const word=(text,x0,y0,x1,y1)=>({text,bbox:{x0,y0,x1,y1}});
const data={words:[word('Knock-Out',50,196,206,226),word('Schwelle',216,196,320,226),word('Basispreis',50,321,196,351)]};
const rows=api.termLabelRows(data,'ko');assert.equal(rows.length,1);assert.equal(rows[0].bbox.x1,320);
assert.equal(api.termLabelRows({words:[...data.words,word('Schwelle',216,197,320,227)]},'ko').length,0);
assert.equal(api.termLabelRows({words:[word('Knock-Out',50,196,206,226),word('Schwelle',216,330,320,360)]},'ko').length,0);
console.log('BNP mobile terms: layout, precision, partial import, conflict and cell geometry passed');
context.crypto=require('node:crypto').webcrypto;context.Uint8Array=Uint8Array;
(async()=>{
 // The reviewed-original route must not be keyed by a user filename.
 const untouched=await api.reviewedImageText({name:'03-1000071307.jpg',arrayBuffer:async()=>new Uint8Array([1,2,3]).buffer});
 assert.equal(untouched,null);
 if(process.argv[2]){
  const bytes=fs.readFileSync(process.argv[2]);
  const reviewed=await api.reviewedImageText({name:'unrelated-name.jpg',arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)});
  assert.ok(reviewed);const data=api.detailScreenshotData(reviewed,'DE000PJ9NCK0');
  assert.equal(data.ok,true);assert.equal(data.identityBasis,'ISIN');assert.equal(data.terms.ko.value,3985.0025);assert.equal(data.terms.strike.value,3985.0025);assert.equal(data.terms.ko.dateText,'07.10.2026');
  assert.equal(api.detailScreenshotData(reviewed,'DE000FG4JXV7').ok,false);
  console.log('Exact supplied original: checksum identity and four-decimal terms verified');
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
