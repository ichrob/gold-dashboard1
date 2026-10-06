const fs=require('fs'),vm=require('vm'),assert=require('assert'),{webcrypto}=require('crypto');
// Async IndexedDB contract double: requests queue within one transaction, result resolves on commit.
function memoryDb(){const rows=new Map();let fail=false;return {rows,setFail:v=>fail=v,open(){const request={};setTimeout(()=>{if(fail){request.error=Error('quota');request.onerror();return;}request.result={close(){},transaction(){const tx={};let pending=0;const run=fn=>{pending++;const r={};setTimeout(()=>{r.result=fn();r.onsuccess?.();if(!--pending)setTimeout(()=>{if(!pending)tx.oncomplete?.()},0)},0);return r};tx.objectStore=()=>({getAll:()=>run(()=>[...rows.values()]),get:id=>run(()=>rows.get(id)),put:r=>run(()=>rows.set(r.id,r)),delete:id=>run(()=>rows.delete(id))});return tx}};request.onsuccess()},0);return request}};}
const db=memoryDb(),c={window:{},indexedDB:db,crypto:webcrypto,File,Blob,console,setTimeout,clearTimeout,document:{readyState:'loading',addEventListener(){},getElementById(){return null}}};
vm.createContext(c);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),c);const b=c.window.BobDegiro;
(async()=>{
 const isin='DE000FG7EPT1',context={isin,basis:'opened-product'},file=new File(['original bytes'],'terms.jpg',{type:'image/jpeg'});
 const record=await b.saveProductOriginal(file,isin,context,'batch-one');
 let all=await b.loadProductOriginals();assert.equal(all.length,1);assert.equal(await all[0].blob.text(),'original bytes');assert.equal(all[0].context.isin,isin);assert.equal(all[0].version,null);
 await b.markOriginalProcessed(record,{ok:true});all=await b.loadProductOriginals();assert(all[0].version);assert.equal(all[0].lastResult,'zugeordnet');
 await b.saveProductOriginal(file,isin,context,'batch-one');assert.equal((await b.loadProductOriginals()).length,1);
 await b.saveProductOriginal(file,'DE000FG7K283',null,'batch-two');await b.deleteProductOriginals(isin);all=await b.loadProductOriginals();assert.equal(all.length,1);assert.equal(all[0].isin,'DE000FG7K283');
 db.setFail(true);await assert.rejects(()=>b.loadProductOriginals(),/quota/);db.setFail(false);
 const now=Date.now();assert.equal(b.originalRetention([{savedAt:now-8*86400000,size:1}],now).length,0);
 const kept=b.originalRetention([{savedAt:now-1,size:70*1024*1024},{savedAt:now,size:60*1024*1024}],now);assert.equal(kept.length,1);assert.equal(kept[0].savedAt,now);
 const data={isin,terms:{strike:{value:4000},ratio:{value:.1}},ko:4000,leverage:20,bid:10,ask:11,price:11,times:{quote:{present:true}},combinedDraft:{fields:{bid:10,ask:11,quoteAt:'old'},hasQuote:true}};
 b.removeUnconfirmedFields(data,['strike','bid']);assert(!data.terms.strike);assert.equal(data.terms.ratio.value,.1);assert.equal(data.leverage,20);assert.equal(data.ask,null);assert.equal(data.bid,null);assert(!data.combinedDraft.hasQuote);
 const summary=b.screenshotBatchSummary([{ok:true,name:'a.jpg',reason:'zugeordnet',data},{ok:false,name:'b.jpg',reason:'andere ISIN'}]);assert(summary.includes('Werte teilweise'));assert(summary.includes('1 von 2 Dateien zugeordnet'));assert(!summary.includes('2 Bild(ern) übernommen'));
 const shot=(time,lev='')=>({ok:true,name:time||'leverage',raw:'',data:{isin,sourceTime:time,leverage:lev,times:{},bid:null,ask:null}});
 const series=[shot('06.10.2026 21:03:09'),shot('06.10.2026 21:03:12'),shot('',20)];const linked=b.linkScreenshotSeries(series);assert(linked);assert.equal(series[1].data.sourceTime,'06.10.2026 21:03:12');assert.equal(series[2].data.times.leverage.text,'06.10.2026 21:03:09');assert(series[2].data.times.leverage.fromSeries);
 assert.equal(b.linkScreenshotSeries([shot('06.10.2026 21:03:09'),shot('06.10.2026 21:05:00'),shot('',20)]),null);
 const newer={isin,identityBasis:'ISIN',ko:4376,terms:{strike:{value:4376,dateText:'06.10.2026'},ko:{value:4376,dateText:'06.10.2026'}}};
 const old={isin,identityBasis:'ISIN',ko:4300,terms:{strike:{value:4300,dateText:'05.10.2026'},ko:{value:4300,dateText:'05.10.2026'}}};
 const stored=b.mergeScreenshotEvidence(null,newer,'new');const merged=b.mergeScreenshotEvidence(stored,old,'old');assert.equal(merged.terms.strike.value,4376);assert.equal(merged.ko,4376);
 const words=[{text:'Hebel',bbox:{x0:30,x1:100,y0:100,y1:120}},{text:'20,9696',bbox:{x0:500,x1:600,y0:100,y1:120}}];assert(b.scalarCellRect({words},'leverage'));assert.equal(b.scalarCellRect({words:words.concat(words[1])},'leverage'),null);
 const replayCalls=[],field={value:isin,dataset:{i:'1'}},status={textContent:''},input={};
 const replayContext={...c,window:{},replayRead:async(i,file,ctx)=>{replayCalls.push({i,name:file.name,text:await file.text(),ctx});return {ok:true,reason:'zugeordnet'};},document:{readyState:'loading',hidden:false,addEventListener(){},querySelectorAll(){return [field]},querySelector(selector){return selector.includes('data-dg')?field:status},getElementById(id){return id==='dgDetailShot1'?input:status}}};
 let replaySource=fs.readFileSync('degiro_assistant.js','utf8').replace('function rankUI(){','function unusedRankUI(){').replace('async function readScreenshot(i,file,productContext=null){','async function unusedReadScreenshot(i,file,productContext=null){').replace('window.BobDegiro={','function rankUI(){} async function readScreenshot(i,file,ctx){return replayRead(i,file,ctx)} window.BobDegiro={');
 vm.createContext(replayContext);vm.runInContext(replaySource,replayContext);const replay=replayContext.window.BobDegiro;
 const first=await replay.saveProductOriginal(file,isin,context,'replay-group');await replay.markOriginalProcessed(first,{ok:true});
 await replay.saveProductOriginal(new File(['second original'],'quote.jpg'),isin,context,'replay-group');
 await replay.reprocessOriginals(true);assert.equal(replayCalls.length,2,'replay whole batch even after an interrupted upgrade');assert.equal(replayCalls[0].ctx.isin,isin);assert(replayCalls.some(x=>x.text==='second original'));
 await replay.reprocessOriginals(true);assert.equal(replayCalls.length,2,'current version must not replay on every reload');
 console.log('Resilient imports: original bytes, identity/batch isolation, retention/quota errors, field isolation, series clocks and old evidence protection passed');
})().catch(e=>{console.error(e);process.exitCode=1});
