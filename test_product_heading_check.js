const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('degiro_assistant.js','utf8');
const c={Date,sharedVenueStatus:p=>p.venueStatus||null,expectedQuotePause:p=>p.paused,currentSgChfAnalysisProof:p=>p.analysis,productDirectionDataState:p=>p.state,knockoutStatus:p=>p.ko,compactProductExclusion:p=>p.excluded};
vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function productDirectionCheck('),source.indexOf('function renderProductDirectionStatus(')),c);
const good={state:{blocked:false,stale:false}},qualified={state:{blocked:false,stale:true}},missing={state:{blocked:true,stale:false}},analysis={analysis:{analysisOnly:true}},paused={paused:true};
const heading=items=>c.renderGoldProductsHeading(items);
assert(heading([good,good]).includes('data-products-check="confirmed"'));
for(const p of [qualified,analysis]){
 assert.equal(c.productDirectionCheck(p).kind,'qualified');
 assert(heading([good,p]).includes('>(✓)</strong>'));
 assert(!heading([good,p,missing]).includes('data-products-check'));
}
for(const products of [[],[missing],[good,missing],[analysis,paused],[{ko:true}],[{excluded:true}]])assert.equal(heading(products),'Gold-Hebelprodukte');
assert(heading([good,{ko:true},{excluded:true}]).includes('data-products-check="confirmed"'));
assert.equal(heading([good,qualified,missing]),'Gold-Hebelprodukte');
assert(heading([good,qualified,good]).includes('qualified'));
assert(heading([good,good,good]).includes('confirmed'));
assert(source.includes('updateProductHtml(savedSummary,renderGoldProductsHeading(savedProducts))'));
assert(source.includes('const check=productDirectionCheck(p,now);'),'Card and heading must share their check state');
console.log('Product heading follows all visible checks, qualified checks, missing checks and pauses');
Object.assign(c,{esc:s=>String(s).replaceAll('<','&lt;'),renderIsinCopy:()=>'<button>Kopieren</button>',productFieldStates:p=>p.fields||{},productDataStatus:p=>({reasons:p.reasons||[]})});
for(const [p,symbol] of [[good,'✓'],[qualified,'(✓)'],[missing,'✗'],[analysis,'(✓)'],[paused,'✗'],[{ko:true},'✗']]){
 const html=c.renderProductIdentity({...p,isin:'TEST'});
 assert(html.includes('<b>TEST</b> <strong data-isin-check='));
 assert(html.includes('>'+symbol+'</strong>'));
 assert(html.includes('data-isin-check-reason'));
}
assert(c.renderProductIdentity(analysis).includes('kein bestätigter DEGIRO-Ausführungskurs'));
assert(c.renderProductIdentity({...qualified,fields:{ko:{key:'KO',state:'veraltet'}}}).includes('KO: veraltet'));
assert(c.renderProductIdentity({...missing,reasons:['Basispreis fehlt']}).includes('Basispreis fehlt'));
assert(c.renderProductIdentity({ko:true}).includes('Ausgeknockt'));
console.log('ISIN badges share heading states and explain qualified, missing, paused and excluded data');

assert.equal(heading([good,{...good,venueStatus:{required:true,current:false}}]),'Gold-Hebelprodukte');
assert(heading([good,{...good,venueStatus:{required:true,current:true}}]).includes('confirmed'));
