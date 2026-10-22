'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('Bob.html', 'utf8');
const start = html.indexOf('/* BOB_ISIN_COPY_START');
const end = html.indexOf('</script>', start);
assert(start > 0 && end > start, 'Global copy module must be part of Bob HTML');
let body = html.slice(start, end);
const initializer = "  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});\n  else start();";
assert(body.includes(initializer), 'Expected browser initializer must be present');
body = body.replace(initializer,
 '  globalThis.__bobIsinCopyTest={isCopyableIsin,hasExistingCopy,decorateText};');
const context = {};
vm.runInNewContext(body, context);
const {isCopyableIsin, hasExistingCopy, decorateText} = context.__bobIsinCopyTest;
for(const isin of ['DE000FG14AV8','DE000FG309G0','US0378331005']) {
 assert.equal(isCopyableIsin(isin), true, isin+' should have a copy control');
}
for(const code of ['DE000FG14AV9','DE000FG14AV0','DE0000O00001','abc',
 'DE000FG14AV8 x','secret123456','CH0000000001']) {
 assert.equal(isCopyableIsin(code), false, code+' must not be copied as a verified ISIN');
}
// Existing product cards and rankings already have copy icons.
// A parent <b> with a sibling <span data-copy-product-isin> must not get two.
function fakeElement(own={},children=[]){
 return {getAttribute:k=>own[k]??null,
 querySelectorAll:()=>children,
 nextElementSibling:null,
 closest:()=>null};
}
const existing = fakeElement({'data-copy-product-isin':'DE000FG14AV8'});
const adjacent = fakeElement({},[existing]);
const label = fakeElement();
label.nextElementSibling=adjacent;
assert.equal(hasExistingCopy({parentElement:label},'DE000FG14AV8'),true);
assert.equal(hasExistingCopy({parentElement:label},'DE000FG309G0'),false);
assert.equal(hasExistingCopy({parentElement:fakeElement()},'DE000FG14AV8'),false);
assert.match(html,/data-bob-copy-isin/, 'Copier is an actual button with a click handler');
assert.match(html,/navigator\.clipboard\?\.writeText/, 'Use normal clipboard when permitted');
assert.match(html,/document\.execCommand\('copy'\)/, 'Fallback for Samsung in-app browser');
assert.match(html,/event\.stopPropagation\(\)/, 'Do not toggle collapsed cards on copy');
assert.match(html,/new MutationObserver/, 'Newly updated product/ranking/voice DOM is covered');
assert.match(html,/setAttribute\('aria-label'/,'ISIN copy affordance needs accessible label');
const degiro=fs.readFileSync('degiro_assistant.js','utf8');
assert.match(degiro,/function renderIsinCopy/, 'Existing copy controls retained');
assert.match(degiro,/data-copy-product-isin/, 'Existing product copy controls must still work');
const voice=html.slice(html.indexOf('function leverageComparisonFromCurrentUi'),
html.indexOf('function mountReadOnlyVoiceButton'));
assert.match(voice,/data-risk-isins/, 'Voice answer must retain grounded ISINs');
console.log('ISIN copy: valid check digits, no duplicates with existing controls, dynamic updates and voice ISIN affordances.');
