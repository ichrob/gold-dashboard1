const fs=require('fs'),vm=require('vm'),assert=require('assert');
// Actual Tesseract.js 5.1.1 passes of the user's 1000070723.jpg.
const passes=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_ocr.json','utf8'));
let index=0;
const worker={setParameters:async()=>{},recognize:async()=>({data:structuredClone(passes[index++])})};
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
 console.log('Actual SG image passes: independent numeric agreement, dates, identity and disagreement gates passed');
})().catch(e=>{console.error(e);process.exitCode=1});
