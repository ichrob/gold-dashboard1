const fs=require('fs'),vm=require('vm'),assert=require('assert');
let closed=0,draws=0,params=[];
const context={window:{},console,setTimeout,clearTimeout,
 createImageBitmap:async()=>({width:710,height:1500,close:()=>closed++}),
 document:{readyState:'loading',addEventListener:()=>{},getElementById:()=>null,createElement:()=>({getContext:()=>({drawImage:()=>draws++}),toBlob:cb=>cb({})})}};
const code=fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={setRecoveryWorker:w=>{ocrWorkerPromise=Promise.resolve(w)},focusedImageIdentityRect,readFocusedImageIdentity,recoverFocusedImageIdentity,');
vm.runInNewContext(code,context);const b=context.window.BobDegiro;
const isin='DE000FG8NHQ3',other='DE000FG34XV8';
const data={words:[{text:'ISIN',bbox:{x0:150,y0:1000,x1:200,y1:1025}},
 {text:'DEOOOFGSNHQ3',bbox:{x0:450,y0:1000,x1:690,y1:1025}}]};
const rect=b.focusedImageIdentityRect(data,710,1500);
assert(rect&&rect.x>200&&rect.x+rect.width<=710);
assert.equal(b.focusedImageIdentityRect({words:[]},710,1500),null);
assert.equal(b.focusedImageIdentityRect({words:[...data.words,data.words[0]]},710,1500),null);
const fixed=b.recoverFocusedImageIdentity('ISIN DEOOOFGSNHQ3',isin);
assert(fixed.corrected);assert(fixed.text.includes(isin));
assert(!b.recoverFocusedImageIdentity('ISIN '+other,isin).corrected);
assert(!b.recoverFocusedImageIdentity('ISIN DEOOOFGSNHQ3\nISIN '+other,isin).corrected);
assert(!b.recoverFocusedImageIdentity('ISIN DE000AAAAAA1',isin).corrected);
assert(!b.recoverFocusedImageIdentity('ISIN DEOOOFGSNHQ3','DE000FGSNHQ3').corrected);
assert(b.recoverFocusedImageIdentity('ISIN unlesbar',isin).text.includes(isin));
(async()=>{
 let reads=[isin,isin];
 const worker={setParameters:async p=>params.push(p),recognize:async()=>({data:{text:reads.shift()}})};
 assert.equal(await b.readFocusedImageIdentity(worker,{},data),isin);
 assert.equal(draws,2);assert.equal(closed,1);
 assert.deepEqual(params.map(p=>p.tessedit_pageseg_mode),['7','6','3']);
 reads=[isin,other];assert.equal(await b.readFocusedImageIdentity(worker,{},data),'');
 reads=['DE000FGSNHQ3',isin];assert.equal(await b.readFocusedImageIdentity(worker,{},data),'');
 const broken={setParameters:worker.setParameters,recognize:async()=>{throw Error('failed')}};
 await assert.rejects(()=>b.readFocusedImageIdentity(broken,{},data));
 assert.equal(closed,4);assert.equal(params.at(-1).tessedit_pageseg_mode,'3');
 let pass=0;
 const primary={...data,text:'ISIN DEOOOFGSNHQ3'};
 const pipeline={setParameters:async()=>{},recognize:async()=>({data:pass++<2?primary:{text:isin}})};
 b.setRecoveryWorker(pipeline);
 const recovered=await b.recognizeOcr({},'',true,isin);
 assert.equal(pass,4);assert(recovered.data.imageRecovery.accepted);
 assert(recovered.data.text.includes(isin));
 console.log('Automatic image identity recovery: bounded crops, consensus, conflicts, cleanup passed');
})().catch(e=>{console.error(e);process.exitCode=1});
