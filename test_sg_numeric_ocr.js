const fs=require('fs'),vm=require('vm'),assert=require('assert');
// Actual Tesseract.js 5.1.1 passes of the user's 1000070723.jpg.
const passes=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_ocr.json','utf8'));
let index=0,inputPasses=passes;
const worker={setParameters:async()=>{},recognize:async()=>({data:structuredClone(inputPasses[index++])})};
const context={window:{},document:{getElementById:()=>null,readyState:'loading',addEventListener:()=>{}},console,setTimeout,clearTimeout};
vm.createContext(context);
let code=fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={recognizeOcr,setTestWorker:w=>{ocrWorkerPromise=Promise.resolve(w)},');
vm.runInContext(code,context);const b=context.window.BobDegiro;b.setTestWorker(worker);
(async()=>{
 const result=await b.recognizeOcr({});assert(result.data.numericCrossChecked);assert.equal(index,5);
 const parsed=b.detailScreenshotData(result.data.text,'DE000FG7K283');assert(parsed.ok,parsed.reason);
 assert.equal(parsed.direction,'SHORT');assert.equal(parsed.terms.ratio.value,.1);
 for(const key of ['ko','strike']){assert.equal(parsed.terms[key].value,4246.7452);assert.equal(parsed.terms[key].dateText,'06.10.2026');}
 assert.equal(parsed.bid,null);assert.equal(parsed.ask,null);
 assert(!b.detailScreenshotData(result.data.text,'DE000FG5NMF2').ok);
 const text='Basispreis 4.246,7452 USD\nKnock-Out-Barriere 4.246,7452 USD\nBezugsverhältnis 10:1';
 assert.equal(b.unconfirmedOcrFields(text,[text]).length,3);
 const partial='Basispreis unreadable\nKnock-Out-Barriere 4.246,7452 USD\nBezugsverhältnis 10:1';
 assert.deepEqual(Array.from(b.unconfirmedOcrFields(text,[partial,partial])),['strike']);
 const bad=text.replaceAll('4.246,7452','4.246,7459');
 assert(b.unconfirmedOcrFields(text,[text,text,bad,bad]).includes('ko'));
 // Android-reported variant: overlong ISIN token and T/7 WKN confusion.
 const variant=structuredClone(passes);
 variant[1].text=variant[1].text.replace(/DEOOOFG7K283/g,'DEOOOFGT7K283').replace(/FG7K28/g,'FGTK28');
 assert(!b.detailScreenshotData(b.recoverTermRows(variant[1],variant[3]),'DE000FG7K283').ok);
 inputPasses=variant.concat([{text:'DEOOOFG7K283\n'},{text:'DEOOOFG7K283\n'}]);index=0;
 context.createImageBitmap=async()=>({width:709,height:1536,close(){}});
 context.document.createElement=()=>({getContext:()=>({drawImage(){}}),toBlob:cb=>cb({})});
 const fixed=await b.recognizeOcr({});assert.equal(index,7);
 assert(b.detailScreenshotData(fixed.data.text,'DE000FG7K283').ok);
 assert(!b.detailScreenshotData(fixed.data.text,'DE000FG5NMF2').ok);
 assert.deepEqual(JSON.parse(JSON.stringify(b.sgIdentityRect(passes[0],709,1536))),{x:118,y:281,width:591,height:57});
 assert.equal(b.sgIdentityRect({text:'other issuer',words:passes[0].words},709,1536),null);
 for(const values of [['DEOOOFG7K283','DE000FG5NMF2'],['DEOOOFGTK283','DEOOOFGTK283']]){
  let n=0;const probe={setParameters:async()=>{},recognize:async()=>({data:{text:values[n++]}})};
  assert.equal(await b.readSgIdentity(probe,{},passes[0]),'');
 }
 console.log('Actual SG image passes: independent numeric agreement, dates, identity and disagreement gates passed');
})().catch(e=>{console.error(e);process.exitCode=1});

// Actual 12:04 terms image followed by a same-value undated quote header.
{
 const reads=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_terms_1204.json','utf8'));
 const isin='DE000FG7K283',now=Date.parse('2026-10-06T10:06:00Z');
 const terms=b.detailScreenshotData(b.recoverTermRows(reads[1],reads[3]),isin);assert(terms.ok);
 const quote=b.detailScreenshotData('ISIN '+isin+'\nSHORT\nEUR\nGeld 8,64\nBrief 8,65\nHebel 45\nKO 4246,7452\nKurszeit: 06.10.2026 12:04:30',isin);assert(quote.ok);
 const make=items=>items.reduce((prev,[data,name])=>b.mergeScreenshotEvidence(prev,data,name),null);
 for(const items of [[[terms,'terms.jpg'],[quote,'quote.jpg']],[[quote,'quote.jpg'],[terms,'terms.jpg']]]){
  const snapshot=make(items),p={isin,isinConfirmed:true,productDirection:'SHORT',price:8.65,leverage:45,ko:4246.7452,snapshot};
  const result=b.finalProductStatus(p,now);
  assert(!result.complete);assert.deepEqual(Array.from(result.reasons),['Basiswert ungenau: Gold allein bestätigt keinen Spot-Basiswert']);
  assert(!b.compactProductCard(p,result.reasons).includes('Geld, Brief und Quellenzeit'));
  assert(b.compactProductCard(p,result.reasons).includes('Basiswert „Gold“ erkannt'));
  assert(b.productTermsStatus(p,now+86400000).reasons.some(r=>/Knock-out/.test(r)));
  const changed=make([[terms,'terms.jpg'],[{...quote,ko:'4247'},'changed.jpg']]);
  assert(b.productTermsStatus({...p,ko:4247,snapshot:changed},now).reasons.some(r=>/Knock-out/.test(r)));
  for(const change of [{conflict:true},{revoked:true},{dateText:'05.10.2026'}]){
   const bad={...snapshot,evidence:{...snapshot.evidence,KO:{...snapshot.evidence.KO,...change}}};
   assert(b.productTermsStatus({...p,snapshot:bad},now).reasons.some(r=>/Knock-out/.test(r)));
  }
 }
 const snapshot=make([[terms,'terms.jpg'],[quote,'quote.jpg']]);
 assert.equal(snapshot.evidence.KO.source,'quote.jpg');assert.equal(snapshot.evidence.KO.at,null);assert(!snapshot.evidence.KO.dateText);
 assert.equal(snapshot.terms.ko.source,'terms.jpg');assert.equal(snapshot.terms.ko.dateText,'06.10.2026');
 console.log('Dated KO evidence survives undated repeats in either image order; expiry and conflicts still block');
}
