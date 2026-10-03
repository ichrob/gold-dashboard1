const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,now=Date.parse('2026-10-03T18:00:00Z'),isin='DE000FG7MTA6';
const conditions=Object.fromEntries(Object.entries({ratio:.1,underlying:'XAU/USD',currency:'EUR',type:'Knock-out Turbo',maturity:'Open End'}).map(([k,value])=>[k,{value,source:'https://www.boerse-stuttgart.de/',conditionVerified:true,reviewedAt:'2026-10-03T17:59:00Z'}]));
const p={isin,isinConfirmed:true,productDirection:'LONG',ko:4143.437,quote:{isin,source:'Börse Stuttgart',checkedAt:'2026-10-03T17:59:00Z',productVerified:true,conditions,metadata:{status:2,ko:4143.437,direction:'LONG',termsDated:false}}};
const status=b.productTermsStatus(p,now);
assert.equal(status.values.ratio,.1);assert.equal(status.values.underlying,'XAU/USD');
assert(!status.complete);assert(status.reasons.some(x=>x.includes('nicht aktiv')));
assert(status.reasons.some(x=>x.includes('datierter Basispreis')));
assert(status.reasons.some(x=>x.includes('datierter Produktnachweis')));
console.log('Stuttgart terms/status/freshness tests passed');

assert(!b.evaluateProduct({...p,spot:4200,direction:"LONG",leverage:10}).ok);

// SG table transcription from supplied screenshots: decimal comma, ratio and date-only evidence.
const sgText='ISIN DE000FG309G0\nTyp Put\nBezugsverhältnis 10:1\nBasispreis 4.635,8091 USD (02.10.2026)\nKnock-Out-Barriere 4.635,8091 USD (02.10.2026)';
const parsed=b.detailScreenshotData(sgText,'DE000FG309G0');
assert(parsed.ok,parsed.reason);assert.equal(parsed.terms.ratio.value,.1);
assert.equal(parsed.terms.strike.value,4635.8091);assert.equal(parsed.ko,'4635.8091');
assert.equal(parsed.terms.strike.dateText,'02.10.2026');assert.equal(parsed.terms.strike.at,null);
const merged=b.mergeScreenshotEvidence(null,parsed,'SG-Stammdaten.jpg');
assert.equal(merged.evidence.KO.dateText,'02.10.2026');assert.equal(merged.evidence.KO.at,null);
assert(!b.detailScreenshotData(sgText,'DE000FG4JXV7').ok);
assert(!b.detailScreenshotData('Basispreis 4.635,8091 USD (02.10.2026)','DE000FG309G0').ok);
const mismatch=b.productTermsStatus({...p,ko:4143.44},now);
assert(mismatch.reasons.some(x=>x.includes('gespeichert 4143.44 USD')&&x.includes('Quelle 4143.437 USD')));
console.log('SG numeric/date-only import, identity rejection and KO conflict explanation passed');
