/* Regression: KO and issuer-ended instruments are compact and never display
   ordinary quote/leveraging gaps. Terminal is not automatically a KO. */
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('degiro_assistant.js','utf8');
const panel=fs.readFileSync('degiro_product_audit_panel.py','utf8');
const first=source.indexOf('function terminalProductCard(');
const last=source.indexOf('function evaluateProduct(',first);
assert(first>0&&last>first);
const ui={knockoutStatus:p=>p.verifiedKo===true?{}:null,esc:x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;'),
 renderIsinCopy:isin=>'<button data-copy-product-isin="'+isin+'">copy</button>'};
vm.runInNewContext(source.slice(first,last),ui);
const isin='DE000FD0S0G4';
assert.equal(ui.knockoutCard({isin,verifiedKo:false}),'');
const knocked=ui.knockoutCard({isin,verifiedKo:true});
assert(knocked.includes(isin+' · Produkt ausgeknockt'));
assert(knocked.includes('data-product-knocked-out'));
assert(!knocked.includes('✗')&&!knocked.includes('Offen:')&&!knocked.includes('Geld:')&&!knocked.includes('Brief:')&&!knocked.includes('Hebel:'));
assert(knocked.includes('data-copy-product-isin'));
assert(!knocked.includes('data-selection-approved'));
const ended=ui.terminalProductCard({isin},'Produkt beendet');
assert(ended.includes(isin+' · Produkt beendet'));
assert(ended.includes('data-product-ended')&&!ended.includes('data-product-knocked-out'));
assert(!ended.includes('✗'));
const base=source.indexOf('function serverIssuerTerminated('),tail=source.indexOf('function additionalProductsComplete(',base);
assert(base>0&&tail>base);
const at=Date.parse('2026-10-22T17:12:00Z'),stamp='2026-10-22T06:58:34.572Z';
const terminal={isin,state:'terminated',sourceStatusEvidence:{issuerTerminal:true,issuerStatus:2}};
class Clock extends Date {constructor(...x){super(...(x.length?x:[at]));}static now(){return at;}}
const ctx={Date:Clock,window:{BobProductAuditReport:{status:'ok',lastCheckedAt:new Date(at-2000).toISOString(),listUploadedAt:stamp,items:[terminal]}},listArchive:{storedAt:stamp}};
vm.runInNewContext(source.slice(base,tail),ctx);
assert(ctx.serverIssuerTerminated({isin},at));
assert.equal(ctx.compactProductExclusion({isin},at),'Produkt beendet – ausgeschlossen');
assert(!ctx.serverIssuerTerminated({isin:'DE000OTHER'},at));
assert(!ctx.serverIssuerTerminated({isin},at+181000));
ctx.window.BobProductAuditReport.listUploadedAt='other';
assert(!ctx.serverIssuerTerminated({isin},at));
ctx.window.BobProductAuditReport.listUploadedAt=stamp;
ctx.window.BobProductAuditReport.items=[{...terminal,sourceStatusEvidence:{issuerTerminal:false,issuerStatus:1}}];
assert(!ctx.serverIssuerTerminated({isin},at));
assert(source.includes("return terminalProductCard(p,'Produkt beendet')"));
assert(panel.includes("if(ended){\n    summary.textContent=(item.isin||'ISIN unbekannt')+' · Produkt beendet';"));
assert(panel.includes('node.append(summary);out.append(node);continue;'));

// Same-list, current server analysis can correct stale handset presentation;
// it must never become broker execution or override a stale/source-conflicted row.
const h0=source.indexOf('function serverAnalysisEvidence(');
const h1=source.indexOf('// Only evidence failures belong beside the ISIN',h0);
assert(h0>0&&h1>h0);
const qAt=new Date(at-10000).toISOString();
const proof={isin,direction:'LONG',state:'analysis-evidence-complete',missing:[],tradeApproved:false,
 nativeCurrency:'EUR',quoteSourceAt:qAt,source:'comdirect',
 sourceStatusEvidence:{issuerStatus:1},
 leverageObservation:{current:true,kind:'calculated-gearing',value:27.1,at:qAt},
 sourceObservations:[{isinBound:true,current:true,degiroExecutable:false,
  bid:12.8,ask:12.81,currency:'EUR',label:'Vorhandene Vergleichsquelle',venue:'LT Societe Generale',source:'comdirect · SG LiveTrading',bidAt:qAt,askAt:qAt}]};
const displayContext={Date:Clock,window:{BobProductAuditReport:{
 status:'ok',listUploadedAt:stamp,lastCheckedAt:new Date(at-2000).toISOString(),items:[proof]}},
 listArchive:{storedAt:stamp},n:x=>Number.isFinite(Number(x))?Number(x):null,
 esc:x=>String(x).replaceAll('<','&lt;')};
vm.runInNewContext(source.slice(h0,h1),displayContext);
assert(displayContext.serverAnalysisEvidence({isin,productDirection:'LONG'},at));
const html=displayContext.renderServerAnalysisEvidence({isin,productDirection:'LONG'});
assert(html.includes('12,8')||html.includes('12.8'));
assert(html.includes('keine DEGIRO-Ausführungszusage'));
assert(!html.includes('data-selection-approved'));
displayContext.window.BobProductAuditReport.items=[{...proof,sourceObservations:[{...proof.sourceObservations[0],label:'SG-Chart',venue:''}]}];
assert(!displayContext.serverAnalysisEvidence({isin,productDirection:'LONG'},at),'A chart dot is not a bid/ask');
displayContext.window.BobProductAuditReport.items=[proof];
assert(!displayContext.serverAnalysisEvidence({isin,productDirection:'SHORT'},at));
assert(!displayContext.serverAnalysisEvidence({isin,productDirection:'LONG'},at+100000));
displayContext.window.BobProductAuditReport.items=[{...proof,missing:['quote']}];
assert(!displayContext.serverAnalysisEvidence({isin,productDirection:'LONG'},at));
displayContext.window.BobProductAuditReport.items=[{...proof,sourceStatusEvidence:{issuerStatus:2}}];
assert(!displayContext.serverAnalysisEvidence({isin,productDirection:'LONG'},at));
assert(source.includes("if(server)return {kind:'qualified',serverEvidence:server,state};"));
displayContext.window.BobProductAuditReport.items=[proof];
const conflicted={...displayContext,productTermsStatus:()=>({reasons:['KO-Barriere: aktuelle Nachweise widersprechen sich']})};
vm.runInNewContext(source.slice(h0,h1),conflicted);
assert(!conflicted.serverAnalysisEvidence({isin,productDirection:'LONG'},at),'Conflicting KO terms must not be silently hidden');

console.log('Compact gold KO/end cards, historic and conflicting server evidence, original ISIN copy and no legacy X passed');
