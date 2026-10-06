const fs=require('fs'),vm=require('vm'),assert=require('assert');
const fixture=JSON.parse(fs.readFileSync('test_fixtures/sg_mobile_cells.json'));
const context={window:{},document:{readyState:'loading',addEventListener(){},getElementById(){return null},createElement(){let crop=false;return {getContext(){return {drawImage(...args){crop=args.length===9&&args[3]<400}}},toBlob(cb){cb({crop})}}}},createImageBitmap:async()=>({width:709,height:1536,close(){}}),console,setTimeout,clearTimeout};
vm.createContext(context);
vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={setWorker:w=>{ocrWorkerPromise=Promise.resolve(w)},'),context);
const b=context.window.BobDegiro,isin='DE000FG7EPT1',opened={isin,basis:'opened-product'};
(async()=>{
 for(const f of fixture.terms){
  let n=0;
  b.setWorker({setParameters:async()=>{},recognize:async image=>({data:image.crop?{text:f.cropReads[n++%2]}:structuredClone(f)}),terminate:async()=>{}});
  const result=await b.recognizeOcr({});
  assert(!result.data.reviewedOriginal,'must exercise generic OCR, not image hash');
  assert.equal(b.ocrNumericFields(result.data.text).strike,4376.6213);
 }
 const f=fixture.terms[0];let reads=0;
 b.setWorker({setParameters:async()=>{},recognize:async image=>({data:image.crop?{text:++reads%2?'4.376,6213 USD':'4.376,6219 USD'}:structuredClone(f)}),terminate:async()=>{}});
 const disagreement=await b.recognizeOcr({});assert.equal(b.ocrNumericFields(disagreement.data.text).strike,undefined);
 const quote=b.detailScreenshotData(fixture.quote,isin,opened);
 assert(quote.ok,quote.reason);assert.equal(quote.identityBasis,'Produktkontext');
 assert.equal(quote.bid,17.65);assert.equal(quote.ask,17.66);assert.equal(quote.sourceTime,'06.10.2026 21:03:12');
 assert(!b.detailScreenshotData(fixture.quote,isin).ok);
 assert(!b.detailScreenshotData(fixture.quote.replace('FGTEPT','AB1234'),isin,opened).ok);
 assert(!b.detailScreenshotData(fixture.quote+'\nISIN DE000FG7K283',isin,opened).ok);
 console.log('Mobile SG: real OCR and focused original-pixel reads recover strike; contextual 7/T preserves quote/time and rejects foreign identity');
})().catch(e=>{console.error(e);process.exitCode=1});
