'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {validIsin,readDraft,displayedPairStatus,takeTransferFragment}=require('./degiro_android_bridge');

const HEADER='BOB OCR-ENTWURF – NICHT VERIFIZIERT';
const safe=(extra='')=>[
 HEADER,
 'ISIN: DE000FG14AV8',
 'Geld (OCR ungeprüft): 13,22',
 'Brief (OCR ungeprüft): 13,35',
 'Hebel (OCR ungeprüft): 32,10',
 'KO-Schwelle (OCR ungeprüft): 4560,00',
 'Handelsplatz (OCR ungeprüft): Swiss DOT',
 extra,
 'Bildzeit/Originalquelle wurden nicht verifiziert. Kein automatischer Handelsnachweis, keine Freigabe, keine Order.'
].filter(Boolean).join('\n');

assert.equal(validIsin('DE000FG14AV8'),true);
assert.equal(validIsin('DE000FG14AV9'),false);
assert.equal(validIsin('DE000FG14AV8<script>'),false);
const parsed=readDraft(safe());
assert.deepEqual(parsed,{
 isin:'DE000FG14AV8',fields:{bid:'13,22',ask:'13,35',leverage:'32,10',ko:'4560,00',venue:'Swiss DOT'},
 verified:false,tradeApproved:false,sourceTime:null
});
assert.equal(readDraft([HEADER,'ISIN: DE000FG14AV8','Kein automatischer Handelsnachweis'].join('\n')).fields.bid,undefined);
const screenshotPair = [
 HEADER,
 'ISIN: DE000PJ9NB98',
 'Handelsplatz (OCR ungeprüft): BNP OTC',
 'Zuletzt (OCR ungeprüft): 11,31',
 'Bildzeit/Originalquelle wurden nicht verifiziert. Kein automatischer Handelsnachweis, keine Freigabe, keine Order.'
].join('\n');
const combined=readDraft(screenshotPair);
assert.equal(combined.isin,'DE000PJ9NB98');
assert.equal(combined.fields.venue,'BNP OTC');
assert.equal(combined.fields.last,'11,31');
const dated=readDraft(screenshotPair.replace(
 'Zuletzt (OCR ungeprüft): 11,31',
 'Zuletzt (OCR ungeprüft): 11,31\nAnzeigezeit (OCR ungeprüft): 22/10/2026 10:35'
));
assert.equal(dated.fields.displayedTime,'22/10/2026 10:35');
assert.equal(dated.sourceTime,null);
assert.equal(dated.tradeApproved,false);
assert.throws(()=>readDraft(screenshotPair.replace(
 'Zuletzt (OCR ungeprüft): 11,31',
 'Zuletzt (OCR ungeprüft): 11,31\nAnzeigezeit (OCR ungeprüft): 99-99-2099 now'
)));
assert.equal(combined.fields.bid,undefined);
assert.equal(combined.tradeApproved,false);
assert.equal(combined.sourceTime,null);
const grouped=screenshotPair.replace('Bildzeit/Originalquelle',
 'Bildserie (OCR ungeprüft): 2 Bilder, 1 mit gültiger ISIN\nBildzeit/Originalquelle');
const groupedDraft=readDraft(grouped);
assert.deepEqual(groupedDraft.series,{imageCount:2,anchorCount:1,provisional:true});
assert.equal(groupedDraft.tradeApproved,false);
assert.equal(groupedDraft.sourceTime,null);
assert.throws(()=>readDraft(grouped.replace('2 Bilder, 1','2 Bilder, 3')));
assert.throws(()=>readDraft(grouped.replace('Bildzeit/Originalquelle',
 'Bildserie (OCR ungeprüft): 2 Bilder, 1 mit gültiger ISIN\nBildzeit/Originalquelle')));
assert.throws(()=>readDraft(screenshotPair+'\nZuletzt (OCR ungeprüft): 9,72'));
const manifest=fs.readFileSync('./android_companion/app/src/main/AndroidManifest.xml','utf8');
const kotlin=fs.readFileSync('./android_companion/app/src/main/java/ch/bob/degirocompanion/MainActivity.kt','utf8');
assert.match(manifest,/android.intent.action.SEND_MULTIPLE/);
assert.match(kotlin,/Intent.ACTION_SEND_MULTIPLE/);
assert.match(kotlin,/SeriesEvidence\.analyze\(texts\)/);
assert.match(kotlin,/QuoteLayout\.extract\(coordinates\)/);
assert.match(kotlin,/uris\.size > 4/);
assert.match(kotlin,/Bildserie hat keine eindeutige gemeinsame ISIN/);

for(const input of [
 safe().replace('DE000FG14AV8','DE000FG14AV9'),
 safe().replace('DE000FG14AV8','DE000FG14AV8, DE000FG7Q3A9'),
 safe('ISIN: DE000FG14AV8'),
 safe('Geld (OCR ungeprüft): 14,00'),
 safe('Zeit (OCR ungeprüft): jetzt'),
 safe('TradeApproved (OCR ungeprüft): ja'),
 safe().replace('Swiss DOT','<script>alert(1)</script>'),
 safe().replace('13,22','1e99'),
 safe().replace('13,22','-13,22'),
 safe().replace(HEADER,'BOB ECHTHANDEL BESTÄTIGT'),
 'x'.repeat(8001)
]){
 assert.throws(()=>readDraft(input),undefined,'Reject unsafe or ambiguous draft');
}
const server=fs.readFileSync('./server.py','utf8');
assert.match(server,/DEGIRO_ANDROID_BRIDGE_JS/);
assert.match(server,/\/degiro_android_bridge\.js/);
const script=fs.readFileSync('./degiro_android_bridge.js','utf8');
assert.ok(!/\b(fetch\(|XMLHttpRequest|api\/degiro\/candidate-proof)\b/.test(script));
assert.ok(!/tradeApproved\s*:\s*true/.test(script));
// Android → Bob navigation: only a local URL fragment, never a server-side write.
function testTransfer(value){
 const state={hash:'#bob-ocr='+encodeURIComponent(value),pathname:'/',search:''};
 const calls=[];
 const history={replaceState(_state,_title,url){calls.push(url);state.hash='';}};
 return {draft:takeTransferFragment(state,history),history:calls,remaining:state.hash};
}
const transferred=testTransfer(safe());
assert.equal(transferred.draft,safe());
assert.deepEqual(transferred.history,['/']);
assert.equal(transferred.remaining,'');
assert.equal(takeTransferFragment({hash:'#degiro',pathname:'/',search:''},{replaceState(){throw Error('must not navigate')}}),null);
for(const invalid of [safe().replace('DE000FG14AV8','DE000FG14AV9'), 'not an OCR draft']){
 assert.throws(()=>testTransfer(invalid),'Invalid transfer rejected');
}
const alreadyEncoded={hash:'#bob-ocr=%E0%A4%A',pathname:'/',search:''};
const invalidHistory={replaceState(_state,_title,url){alreadyEncoded.hash='';}};
assert.throws(()=>takeTransferFragment(alreadyEncoded,invalidHistory));
assert.equal(alreadyEncoded.hash,''); // Clear before decoding even on error.
// User-shared bid/ask is a local comparison, not a binding DEGIRO order or fill.
const pair=displayedPairStatus(parsed);
assert.equal(pair.state,'screen-observation');
assert.equal(pair.bid,13.22);assert.equal(pair.ask,13.35);
assert.equal(pair.broker,'DEGIRO');
assert.equal(pair.sourceTime,null);
assert.equal(pair.originalQuoteTimeVerified,false);
assert.equal(pair.executable,false);
assert.equal(pair.canTrade,false);
assert.equal(pair.permissions,'comparison-only');
assert.equal(displayedPairStatus(dated).state,'incomplete');
assert.equal(displayedPairStatus(readDraft(safe().replace('13,35','13,20'))).state,'conflict');
assert.equal(displayedPairStatus(readDraft(safe().replace('13,22','1.322,00'))).state,'incomplete');
assert.throws(()=>displayedPairStatus({...parsed,tradeApproved:true}));
assert.throws(()=>displayedPairStatus({...parsed,sourceTime:'2026-10-24T09:00:00+02:00'}));
assert(script.includes('data-degiro-screen-quote'));
console.log('Android-OCR-Entwurf: Parser und Sicherheitsgrenzen geprüft.');

// Explicit app-screen provenance stays distinct from OCR and broker execution.
{
 const appDraft='BOB APP-LESEENTWURF – NICHT VERIFIZIERT\nISIN: DE000FD0S0G4\nQuelle: DEGIRO-App\nErfasst: 2026-10-27T14:00:00Z\nWährung (Anzeige ungeprüft): CHF\nGeld (Anzeige ungeprüft): 10,20\nBrief (Anzeige ungeprüft): 10,30\nHinweis (Anzeige ungeprüft): Keine Aussage zur Handelbarkeit\nKein automatischer Handelsnachweis, keine Freigabe, keine Order.';
 const bridge=require('./degiro_android_bridge.js');
 const observed=bridge.readDraft(appDraft);
 assert.equal(observed.sourceKind,'app-screen');
 assert.equal(observed.currency,'CHF');
 assert.equal(observed.sourceTime,null);
 assert.equal(observed.tradeApproved,false);
 assert.equal(observed.verified,false);
 for(const bad of [appDraft+'\nKontostand: 1000',appDraft.replace('Quelle: DEGIRO-App','Quelle: other'),appDraft+'\nErfasst: 2026-10-27T14:00:00Z',appDraft.replace('Keine Aussage zur Handelbarkeit','Handel garantiert')])assert.throws(()=>bridge.readDraft(bad));
 console.log('App screen draft: provenance retained, no quote time or trade permission inferred');
}

// Compact title values survive the handoff as observations, never inferred ratios.
const titleFields=readDraft(safe('Basispreis (OCR ungeprüft): 4181,33\nBv (OCR ungeprüft): 10'));
assert.equal(titleFields.fields.basisPrice,'4181,33');
assert.equal(titleFields.fields.displayedBv,'10');
assert.equal(titleFields.fields.ratio,undefined);
assert.equal(titleFields.sourceTime,null);
assert.equal(titleFields.tradeApproved,false);
assert.throws(()=>readDraft(safe('Bv (OCR ungeprüft): 10\nBv (OCR ungeprüft): 100')));

const memory=new Map(),storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v)};
const bridge=require('./degiro_android_bridge');
assert.equal(bridge.storeObservation(storage,safe(),[]).state,'unmatched');
assert.equal(memory.size,0);
const products=[{isin:'DE000FG14AV8'}];
assert.equal(bridge.storeObservation(storage,safe(),products,1000).state,'saved');
assert.equal(bridge.savedObservations(storage)[0].draft.isin,products[0].isin);
assert.equal(bridge.savedObservations(storage)[0].draft.tradeApproved,false);
assert.equal(bridge.savedObservations(storage)[0].draft.sourceTime,null);
bridge.storeObservation(storage,safe(),products,2000);
assert.equal(bridge.savedObservations(storage).length,1);
assert.equal(bridge.storeObservation(storage,safe(),[...products,...products]).state,'unmatched');
assert.throws(()=>bridge.storeObservation({getItem:()=>null,setItem:()=>{throw Error('full');}},safe(),products));

// The fallback reads only dated, checksum-valid existing server identities.
(async()=>{
 const vm=require('node:vm'),source=fs.readFileSync('degiro_assistant.js','utf8');
 const body=source.slice(source.indexOf('async function readServerProductList('),source.indexOf('async function restoreServerCorrection(){'));
 const invoke=async(data)=>{
  const context={Date,Error,AbortSignal,validIsin,fetch:async(url,options)=>{
   assert.equal(url,'/api/degiro/list-correction');
   assert.deepEqual(JSON.parse(options.body),{action:'read'});
   return {ok:true,json:async()=>data};
  }};
  vm.createContext(context);vm.runInContext(body,context);
  return context.readServerProductList();
 };
 const base={ok:true,listUploadedAt:new Date(Date.now()-1000).toISOString(),products:[{isin:'DE000FG77MY4'}]};
 assert.equal((await invoke(base)).products[0].isin,'DE000FG77MY4');
 await assert.rejects(()=>invoke({...base,products:[...base.products,...base.products]}));
 await assert.rejects(()=>invoke({...base,products:[{isin:'DE000FG77MY5'}]}));
 await assert.rejects(()=>invoke({...base,listUploadedAt:new Date(Date.now()+60000).toISOString()}));
 const scenarios=async(failures,options={})=>{
  let calls=0;const delays=[],timeouts=[];
  const context={Date,Error,validIsin,AbortSignal:{timeout:ms=>{timeouts.push(ms);return undefined;}},
   setTimeout:(fn,ms)=>{delays.push(ms);fn();},fetch:async()=>{
    const failure=failures[calls++];
    if(failure instanceof Error)throw failure;
    if(typeof failure==='number')return {ok:false,status:failure};
    return {ok:true,json:async()=>base};
   }};
  vm.createContext(context);vm.runInContext(body,context);
  let result,error;try{result=await context.readServerProductList(options);}catch(e){error=e;}
  return {calls,delays,timeouts,result,error};
 };
 const timeout=Object.assign(new Error('signal timed out'),{name:'TimeoutError'});
 const recovered=await scenarios([timeout,503,null]);
 assert.equal(recovered.calls,3);assert.ok(recovered.result);assert.deepEqual(recovered.delays,[1500,4000]);
 assert.deepEqual(recovered.timeouts,[15000,15000,15000]);
 const exhausted=await scenarios([timeout,timeout,timeout]);
 assert.equal(exhausted.calls,3);assert.match(exhausted.error.message,/drei Versuchen/);
 assert.equal((await scenarios([401])).calls,1);
 assert.equal((await scenarios([403])).calls,1);
 let active=true;
 const cancelled=await scenarios([timeout,null],{isCurrent:()=>active,onRetry:()=>{active=false;}});
 assert.equal(cancelled.calls,1);assert.equal(cancelled.result,undefined);
 console.log('Android automatic retry: timeout recovery, finite budget, auth rejection and cancellation passed');
 console.log('Android server-list fallback: read-only dated identities, duplicates and invalid ISIN rejected');
})().catch(e=>{console.error(e);process.exitCode=1;});
