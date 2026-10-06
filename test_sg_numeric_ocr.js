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
 // Actual 1000070760: address hidden while scrolling; Android confuses
 // both the overlong ISIN token and WKN. Resolve from pixels, not the target.
 const noAddress=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_no_address.json','utf8'));
 noAddress[1].text=noAddress[1].text.replace(/DEOOOFG7K283/g,'DEOOOFGT7K283').replace(/FG7K28/g,'FGTK28');
 assert(!b.detailScreenshotData(b.recoverTermRows(noAddress[1],noAddress[3]),'DE000FG7K283').ok);
 inputPasses=noAddress.concat([{text:'DEOOOFG7K283'},{text:'DEOOOFG7K283'}]);index=0;
 const headerless=await b.recognizeOcr({});assert.equal(index,7);
 const parsedHeaderless=b.detailScreenshotData(headerless.data.text,'DE000FG7K283');assert(parsedHeaderless.ok,parsedHeaderless.reason);
 for(const key of ['ko','strike']){assert.equal(parsedHeaderless.terms[key].value,4246.7452);assert.equal(parsedHeaderless.terms[key].dateText,'06.10.2026');}
 assert.equal(parsedHeaderless.terms.ratio.value,.1);
 assert(!b.detailScreenshotData(headerless.data.text,'DE000FG5NMF2').ok);
 assert.equal(b.sgIdentityRect({text:'ISIN WKN',words:noAddress[0].words},709,1536),null);
 assert.equal(b.sgIdentityRect({...noAddress[0],words:noAddress[0].words.concat(noAddress[0].words.find(w=>w.text==='ISIN'))},709,1536),null);
 const latest=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_terms_1216.json','utf8'));
 inputPasses=latest.concat([{text:'4.246,7452 10 502)\n) usp (°'},{text:'4.246,7452\n06.10.2026)\nUSD ('}]);index=0;
 const latestResult=await b.recognizeOcr({});assert.equal(index,7);
 const latestTerms=b.detailScreenshotData(latestResult.data.text,'DE000FG7K283');assert(latestTerms.ok,latestTerms.reason);
 assert.equal(latestTerms.terms.strike.value,4246.7452);assert.equal(latestTerms.terms.strike.dateText,'06.10.2026');
 const description=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_description.json','utf8'));
 inputPasses=description;index=0;
 const proseResult=await b.recognizeOcr({});assert.equal(index,2);
 const prose=b.detailScreenshotData(proseResult.data.text,'DE000FG7K283');assert(prose.ok,prose.reason);
 assert.equal(prose.terms.ratio.value,.1);assert.equal(prose.terms.strike.value,4246.7452);
 assert.equal(prose.terms.ko.value,4246.7452);assert.equal(prose.terms.ko.dateText,null);
 assert.equal(prose.terms.underlying.value,'Gold');assert.equal(prose.bid,null);assert.equal(prose.ask,null);
 assert(!b.detailScreenshotData(proseResult.data.text,'DE000FG5NMF2').ok);
 for(const order of [[latestTerms,prose],[prose,latestTerms]]){
  const merged=order.reduce((prev,x)=>b.mergeScreenshotEvidence(prev,x,'test.jpg'),null);
  assert.equal(merged.terms.ko.dateText,'06.10.2026');assert.equal(merged.terms.strike.dateText,'06.10.2026');
 }
 const conflict=description[0].text+'\nDer Basispreis und die Knock-Out-Barriere des Produkts liegen aktuell bei 4.200,0000 USD.';
 assert(b.parseProductTerms(conflict).error);
 // A crop that disagrees must not validate the selected amount.
 inputPasses=latest.concat([{text:'4.246,7459 USD'},{text:'4.246,7459 USD'}]);index=0;
 await assert.rejects(()=>b.recognizeOcr({}),/Zahlen nicht sicher bestätigt/);
 // Native Tesseract passes from user image 1000070842.jpg: no labelled ISIN/WKN.
 inputPasses=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_partial_0842.json','utf8'));index=0;
 const partialImage=await b.recognizeOcr({});assert.equal(index,5);assert(partialImage.data.numericCrossChecked);
 const productContext={isin:'DE000FG7K283',basis:'opened-product'};
 const partialResult=b.detailScreenshotData(partialImage.data.text,productContext.isin,productContext);
 assert(partialResult.ok,partialResult.reason);
 for(const key of ['ko','strike']){assert.equal(partialResult.terms[key].value,4246.7452);assert.equal(partialResult.terms[key].dateText,'06.10.2026');}
 assert.equal(Number(partialResult.leverage),47.7599);assert.equal(partialResult.sourceTime,'');
 assert(!b.detailScreenshotData(partialImage.data.text+'\nWKN FG5NMF',productContext.isin,productContext).ok);
 const damagedDate=b.parseProductTerms(b.recoverTermRows(inputPasses[0],inputPasses[0]));
 assert.equal(damagedDate.ko.value,4246.7452);assert.equal(damagedDate.ko.dateText,null);assert(damagedDate.ko.ocrCorrection);
 console.log('SG partial original image: spatial values, date, context, absent quote time and foreign WKN verified');
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

// Text extracted by PDF.js from the actual single-product final terms.
{
 const pages=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_pdf.json','utf8'));
 const isin='DE000FG7K283',pdf=b.parseProductPdf(pages,isin,'terms.pdf');
 assert.equal(pdf.terms.underlying.value,'XAU/USD');
 assert.deepEqual(Array.from(pdf.referenceDocument.pages),[23,14,13]);
 assert(!pdf.terms.ko&&!pdf.terms.strike&&!pdf.leverage&&!pdf.sourceTime);
 assert.throws(()=>b.parseProductPdf(pages,'DE000FG5NMF2','wrong.pdf'),/ISIN/);
 assert.throws(()=>b.parseProductPdf(pages.concat(['DE000FG5NMF2']),isin,'multi.pdf'),/ISIN/);
 assert.throws(()=>b.parseProductPdf(pages.map(p=>p.replaceAll('XAU Curncy','unknown')),isin,'ambiguous.pdf'),/nicht eindeutig/);
 const old={isin,bid:8.67,ask:8.68,sourceTime:'06.10.2026 12:04:30',ko:4246.7452,leverage:42.3982,evidence:{KO:{value:4246.7452},Hebel:{value:42.3982}},terms:{ko:{value:4246.7452,dateText:'06.10.2026'}}};
 const merged=b.mergeScreenshotEvidence(old,pdf,pdf.terms.underlying.source);
 assert.equal(merged.bid,8.67);assert.equal(merged.sourceTime,old.sourceTime);assert.equal(merged.terms.ko.dateText,'06.10.2026');assert.equal(merged.leverage,42.3982);
 const again=b.mergeScreenshotEvidence(merged,{isin,terms:{underlying:{value:'Gold'}}},'new-image.jpg');assert.equal(again.terms.underlying.value,'XAU/USD');
 const saved=JSON.stringify({[isin]:pdf});context.localStorage={getItem:k=>k==='bobProductPdfReferencesV1'?saved:null};
 const restored=b.restorePdfReference({isin});assert.equal(restored.snapshot.terms.underlying.value,'XAU/USD');
 assert(!b.restorePdfReference({isin:'DE000FG5NMF2'}).snapshot);
 assert(b.screenshotSummary(merged).includes('Bloomberg XAU Curncy'));
 console.log('PDF identity, reference definitions, persistence and market-data isolation passed');
}
{
 const cases=[['Basiswert ungenau: Gold allein','Endgültige Bedingungen'],['Hebel fehlt','Kennzahlen'],['Geld und Brief fehlen','Kursbereich'],['Basispreis fehlt','Stammdaten'],['KO fehlt','Stammdaten'],['Bezugsverhältnis fehlt','Stammdaten'],['ISIN fehlt','Stammdaten'],['Laufzeit fehlt','Fälligkeit'],['Future-Kontrakt fehlt','Kontraktmonat'],['Währung fehlt','Währung']];
 for(const [reason,where] of cases){assert(b.missingValueLocation(reason).includes(where));const html=b.compactProductCard({isin:'DE000FG7K283',index:0},[reason]);assert(html.includes('Fundort:'));assert(html.includes(where));}
}
