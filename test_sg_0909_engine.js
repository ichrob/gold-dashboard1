const fs=require('fs'),vm=require('vm'),assert=require('assert');
const passes=JSON.parse(fs.readFileSync('test_fixtures/sg_0909_engine.json'));
let i=0;const crops=[];
const c={window:{},console,setTimeout,clearTimeout,createImageBitmap:async()=>({width:709,height:1536,close(){}}),document:{readyState:'loading',getElementById(){return null},addEventListener(){},createElement(){return {getContext(){return {drawImage(...a){if(a.length===9)crops.push(a.slice(1,5))}}},toBlob(cb){cb({})}}}}};
vm.createContext(c);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={setWorker:w=>ocrWorkerPromise=Promise.resolve(w),'),c);
const b=c.window.BobDegiro;
(async()=>{
 b.setWorker({setParameters:async()=>{},recognize:async()=>({data:structuredClone(passes[i++])})});
 const result=await b.recognizeOcr({});assert.equal(i,passes.length);assert(!result.data.reviewedOriginal);
 const parsed=b.detailScreenshotData(result.data.text,'DE000FG7EPT1');assert(parsed.ok,parsed.reason);
 assert.equal(parsed.identityBasis,'WKN');assert.equal(parsed.importWarnings.length,0);
 for(const key of ['strike','ko']){assert.equal(parsed.terms[key].value,4376.6213);assert.equal(parsed.terms[key].dateText,'06.10.2026');}
 assert(crops.some(([x,y,w])=>y===751&&x>290&&x+w<505),'amount crop excludes label icon and date');
 assert(!b.detailScreenshotData(result.data.text,'DE000FG7K283').ok);
 assert(!b.detailScreenshotData(result.data.text+'\nISIN DE000FG7K283','DE000FG7EPT1').ok);
 assert(!b.detailScreenshotData(result.data.text.replace('X FGTEPT','X AB1234'),'DE000FG7EPT1').ok);
 console.log('0909: actual Tesseract.js pipeline imports dated strike/KO, excludes icon, resolves same-image WKN and rejects foreign identifiers');
})().catch(e=>{console.error(e);process.exitCode=1});
