'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {validIsin,readDraft,takeTransferFragment}=require('./degiro_android_bridge');

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
assert.equal(combined.fields.bid,undefined);
assert.equal(combined.tradeApproved,false);
assert.equal(combined.sourceTime,null);
const grouped=screenshotPair.replace('Bildzeit/Originalquelle',
 'Bildserie (OCR ungeprüft): 2 Bilder, 1 mit gültiger ISIN\\nBildzeit/Originalquelle');
const groupedDraft=readDraft(grouped);
assert.deepEqual(groupedDraft.series,{imageCount:2,anchorCount:1,provisional:true});
assert.equal(groupedDraft.tradeApproved,false);
assert.equal(groupedDraft.sourceTime,null);
assert.throws(()=>readDraft(grouped.replace('2 Bilder, 1','2 Bilder, 3')));
assert.throws(()=>readDraft(grouped.replace('Bildzeit/Originalquelle',
 'Bildserie (OCR ungeprüft): 2 Bilder, 1 mit gültiger ISIN\\nBildzeit/Originalquelle')));
assert.throws(()=>readDraft(screenshotPair+'\nZuletzt (OCR ungeprüft): 9,72'));
const manifest=fs.readFileSync('./android_companion/app/src/main/AndroidManifest.xml','utf8');
const kotlin=fs.readFileSync('./android_companion/app/src/main/java/ch/bob/degirocompanion/MainActivity.kt','utf8');
assert.match(manifest,/android.intent.action.SEND_MULTIPLE/);
assert.match(kotlin,/Intent.ACTION_SEND_MULTIPLE/);
assert.match(kotlin,/SeriesEvidence\.analyze\(texts\)/);
assert.match(kotlin,/uris\.size > 4/);
assert.match(kotlin,/Bilder enthalten keine eindeutig gleiche ISIN/);

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
assert.ok(!/\b(fetch\(|XMLHttpRequest|localStorage\.setItem|api\/degiro\/candidate-proof)\b/.test(script));
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
console.log('Android-OCR-Entwurf: Parser und Sicherheitsgrenzen geprüft.');
