'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {validIsin,readDraft}=require('./degiro_android_bridge');

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
console.log('Android-OCR-Entwurf: Parser und Sicherheitsgrenzen geprüft.');
