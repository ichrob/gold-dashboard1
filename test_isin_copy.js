const assert=require('assert'),fs=require('fs'),vm=require('vm');
const source=fs.readFileSync('degiro_assistant.js','utf8');
const isin='DE000FC1CHB7';
const writes=[];
const widgetContext={
 validIsin:value=>/^[A-Z]{2}[A-Z0-9]{10}$/.test(String(value||'')),
 esc:value=>String(value).replace(/&/g,'&amp;').replace(/"/g,'&quot;'),
 navigator:{clipboard:{writeText:async value=>{writes.push(value);}}},
 document:{body:{append:()=>{}},execCommand:()=>true,
  createElement:()=>({style:{},select:()=>{},setSelectionRange:()=>{},remove:()=>{}})}
};
vm.createContext(widgetContext);
vm.runInContext(source.slice(source.indexOf('function renderIsinCopy('),
 source.indexOf('function missingValueLocation(')),widgetContext);

const html=widgetContext.renderIsinCopy(isin);
assert(html.includes('data-copy-product-isin="'+isin+'"'),html);
assert(html.includes('aria-label="ISIN '+isin+' kopieren"'),html);
assert(html.includes('min-height:44px'),html);
assert(html.includes('📋'),html);
assert.equal(widgetContext.renderIsinCopy('BAD'),'');

const app={window:{}};
vm.runInNewContext(source,app);
const card=app.window.BobDegiro.compactProductCard({isin,index:1});
assert(card.includes('<b>'+isin+'</b>'),card.slice(0,1500));
assert(card.includes('data-isin-check="none"'),card.slice(0,1500));
assert(card.includes(html),card.slice(0,1500));
const factor=app.window.BobDegiro.compactProductCard({isin,index:1,name:'FAKTOR Gold'});
assert(factor.includes('data-copy-product-isin="'+isin+'"'),factor.slice(0,1500));

const knockoutContext={
 knockoutStatus:p=>p.knockout,
 esc:widgetContext.esc,renderIsinCopy:widgetContext.renderIsinCopy,
 renderProductDirectionStatus:()=>''
};
vm.createContext(knockoutContext);
vm.runInContext(source.slice(source.indexOf('function knockoutCard('),
 source.indexOf('function evaluateProduct(')),knockoutContext);
const knocked=knockoutContext.knockoutCard({isin,productDirection:'LONG',
 knockout:{source:'Emittent',observedDate:'2026-10-15'}});
assert(knocked.includes('<b>'+isin+'</b>'),knocked);
assert(knocked.includes('data-isin-check="none"'),knocked);
assert(knocked.includes(html),knocked);
assert(knocked.includes('Ausgeknockt'),knocked);
assert(source.includes('data-copy-product-isin="" aria-label="ISIN kopieren"'),
 'The saved product input also needs a one-tap copy icon.');

async function testInteractions(){
 let status={textContent:''};
 const input={value:''};
 const button={dataset:{copyProductIsin:isin},parentNode:{querySelector:selector=>
  selector==='[data-copy-status]'?status:selector==='[data-dg="isin"]'?input:null},
  addEventListener:(event,handler)=>{assert.equal(event,'click');button.click=handler;}};
 const root={querySelectorAll:selector=>selector==='[data-copy-product-isin]'?[button]:[]};
 widgetContext.bindIsinCopy(root);
 await button.click();
 assert.deepEqual(writes,[isin]);
 assert.equal(status.textContent,' ✓ Kopiert');
 // Product row button has no fixed ISIN; it reads the current row input.
 input.value='DE000FG7K3G2';status.textContent='';
 await button.click();
 assert.equal(writes.at(-1),'DE000FG7K3G2');
 widgetContext.navigator.clipboard.writeText=async()=>{throw Error('clipboard blocked');};
 status.textContent='';
 await button.click();
 assert.equal(status.textContent,' ✓ Kopiert','Fallback to legacy copy must work');
 input.value='BAD';status.textContent='';
 const count=writes.length;
 await button.click();
 assert.equal(writes.length,count);
 assert(status.textContent.includes('gültige ISIN'));
}
testInteractions().then(()=>console.log('Gold-Hebelprodukte: ISIN copy icons and click handlers OK'),
 error=>{console.error(error);process.exitCode=1;});
