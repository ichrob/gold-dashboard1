"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const source=fs.readFileSync("degiro_assistant.js","utf8");
// Export pure display/read-only helpers in this test context; production API is unchanged.
const exposed=source.replace("window.BobDegiro={","window.BobDegiro={renderPrimaryProductValues,productFieldStates,productProblemLabels,");
assert.notEqual(exposed,source);
const context={window:{},navigator:{userAgent:"Android"},console};
vm.createContext(context);
vm.runInContext(exposed,context,{filename:"degiro_assistant.js"});
const api=context.window.BobDegiro;

const observedAt="2026-10-16T09:25:30+00:00";
const product={
 isin:"DE000PJ9NB98",name:"BNP GOLD",productDirection:"LONG",
 index:1,price:16.15,leverage:23.05,ko:4100,isinConfirmed:true,
 quote:{isin:"DE000PJ9NB98",productVerified:true,found:true,
  currency:"EUR",direction:"LONG",source:"BNP Paribas · Emittent OTC",
  marketOpen:true,priceKind:"issuer-observation",bid:16.14,ask:16.15,
  bidAt:observedAt,askAt:observedAt,quoteAt:observedAt,
  leverage:23.05,leverageAt:observedAt,
  metadata:{status:1,currency:"EUR",direction:"LONG",underlying:"XAU/USD",underlyingType:"SPOT",
   ratio:.1,strike:4000,ko:4100,termsFixed:true}}
};
const near=Date.parse("2026-10-16T09:26:00Z");
const delayed=Date.parse("2026-10-16T09:30:00Z");
const old=api.renderPrimaryProductValues(product,delayed);
assert(old.includes("Gespeicherter Anbieterwert · Originalzeit abgelaufen"),old.slice(0,500));
assert(!old.includes("<b>Aktueller Anbieterwert</b>"));
assert(old.includes("16.14")||old.includes("16,14"));
assert(old.includes("16.15")||old.includes("16,15"));
const current=api.renderPrimaryProductValues(product,near);
assert(current.includes("<b>Aktueller Anbieterwert</b>"));
assert(api.productFieldStates(product,delayed).leverage.state.includes("veraltet"));

const chart={...product,isin:"DE000FG14AV8",productDirection:"LONG",quote:{
 isin:"DE000FG14AV8",productVerified:true,found:false,
 metadata:{status:1,currency:"CHF",issuerExchangeCode:"CBSW",direction:"LONG",underlyingType:"SPOT",underlying:"XAU/USD"},
 nativeChartEvidence:{currency:"CHF",bid:20.21,ask:20.22,pointAt:observedAt,source:"SG CHF chart"}}};
const rendered=api.renderPrimaryProductValues(chart,delayed);
assert(rendered.includes("Aktuelle SG-Chartbeobachtung · nur Analyse"));
assert(rendered.includes("CHF"));
assert.equal(api.productFieldStates(chart,delayed).bid.state,"innerhalb Altersgrenze (300 s)");
assert.equal(api.productFieldStates(chart,Date.parse(observedAt)+300001).bid.state,"veraltet");

// Isolate just the status mapper with controlled diagnostic reasons.
// A numeric value can exist while its independent clock or trade evidence is missing.
const fragment=source.slice(source.indexOf("function productProblemLabels("),source.indexOf("function renderProductProblemSummary("));
const helper={
 degiroVenueObserved:()=>false,degiroVenueInferred:()=>null,
 knockoutStatus:()=>false,compactProductExclusion:()=>false,
 finalProductStatus:()=>({complete:false,reasons:["Hebel mit Zeitstempel fehlt","Geld-/Briefkurs Nachweis nicht ausreichend","Produktwerte mit Originalquellenzeit nicht geprüft"]}),
 productFieldStates:()=>({bid:{value:16.14},ask:{value:16.15},leverage:{value:23.05}}),
 n:v=>typeof v==="number"&&Number.isFinite(v)?v:null
};
vm.createContext(helper);vm.runInContext(fragment,helper);
const labels=Array.from(helper.productProblemLabels(product));
assert(labels.includes("Hebelzeit / Quellenprüfung"));
assert(labels.includes("Kursart / DEGIRO-Handelsplatznachweis"));
assert(!labels.includes("Kursnachweis"),JSON.stringify(labels));
assert(!labels.includes("Produktnachweis"),JSON.stringify(labels));
helper.productFieldStates=()=>({bid:{value:null},ask:{value:null},leverage:{value:null}});
const noValues=Array.from(helper.productProblemLabels(product));
assert(noValues.includes("Hebel")&&noValues.includes("Kursnachweis"));
const helpPart=source.slice(source.indexOf("function productHelpState("),source.indexOf("function renderProductHelp("));
const helper2={
 productProblemLabels:()=>["Kursart / DEGIRO-Handelsplatznachweis","Hebelzeit / Quellenprüfung"],
 productFieldStates:()=>({bid:{value:16.14},ask:{value:16.15},leverage:{value:23.05}}),
 researchResults:new Map(),pendingQuotes:new Set(),
 n:v=>typeof v==="number"&&Number.isFinite(v)?v:null
};
vm.createContext(helper2);vm.runInContext(helpPart,helper2);
const help=helper2.productHelpState({...product,quote:{...product.quote,sourceFailure:true}});
assert.equal(help.manual,false,"Do not demand new screenshots merely because a current issuer retry failed");
assert(help.status.includes("Kurs und Hebel vorhanden"));
assert(help.action.includes("automatisch"));
console.log("Evidence status: correct 90s BNP clock, native CHF research 300s, values versus proofs distinguishable.");

// A valid issuer analysis observation satisfies the analysis clock, while the
// independent broker evidence and contradictory/contract diagnostics remain.
helper.currentSgChfAnalysisProof=()=>({analysisOnly:true});
helper.finalProductStatus=()=>({complete:false,reasons:[
 "Detailbild mit derselben ISIN",
 "Aktuelles Kursbild mit Geld/Brief in EUR",
 "Kurszeit mit Datum: höchstens 14 Stunden alt; keine ergänzten Sekunden",
 "Aktuelles Detailbild mit Hebel und zugehöriger Zeit",
 "KO-Barriere mit gültigem Nachweis oder festen Screenshotwert bestätigen",
 "Widersprüchliche oder ungültige Geldzeit am Original prüfen"
]});
const analysisLabels=Array.from(helper.productProblemLabels(product));
assert(analysisLabels.includes("DEGIRO-Handelsplatznachweis"));
assert(analysisLabels.includes("KO-Nachweis"));
assert(!analysisLabels.includes("Produktnachweis"));
assert(!analysisLabels.includes("Hebelzeit / Quellenprüfung"));
assert(analysisLabels.includes("Kursnachweis"),"Conflicting original quote evidence must remain visible");
helper.degiroVenueObserved=()=>true;
assert(!Array.from(helper.productProblemLabels(product)).includes("DEGIRO-Handelsplatznachweis"));
assert(Array.from(helper.productProblemLabels(product)).includes("KO-Nachweis"));
helper.currentSgChfAnalysisProof=()=>null;
assert(Array.from(helper.productProblemLabels(product)).includes("Produktnachweis"),"Unconfirmed or expired analysis must retain screenshot requirements");

// Stale FX is an automatic data dependency, not a request to re-upload images.
const fxContext={Date};vm.createContext(fxContext);
vm.runInContext(source.slice(source.indexOf('function productFxIssue('),source.indexOf('// Only evidence failures')),fxContext);
helper2.productFxIssue=fxContext.productFxIssue;
const fxProduct={...product,quote:{...product.quote,isin:product.isin,productVerified:true,leverageCalculation:{inputs:{fxDataAt:'2020-01-01T00:00:00Z',fxEffectiveAt:'2020-01-01T00:00:00Z'}}}};
const fxHelp=helper2.productHelpState(fxProduct);
assert.equal(fxHelp.status,'Wechselkursprüfung offen');assert.equal(fxHelp.manual,false);
assert(fxHelp.action.includes('Neue Produktbilder beheben'));
assert(!fxContext.productFxIssue({...fxProduct,quote:{...fxProduct.quote,isin:'other'}}));
assert(fxContext.productFxIssue({...fxProduct,quote:{isin:product.isin,productVerified:true,nativeChartEvidence:{currency:'CHF'}}}));
