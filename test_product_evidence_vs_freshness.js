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

// Isolate just the status mapper with controlled diagnostic reasons.
// A numeric value can exist while its independent clock or trade evidence is missing.
const fragment=source.slice(source.indexOf("function productProblemLabels("),source.indexOf("function renderProductProblemSummary("));
const helper={
 knockoutStatus:()=>false,compactProductExclusion:()=>false,
 finalProductStatus:()=>({complete:false,reasons:["Hebel mit Zeitstempel fehlt","Geld-/Briefkurs Nachweis nicht ausreichend","Produktwerte mit Originalquellenzeit nicht geprüft"]}),
 productFieldStates:()=>({bid:{value:16.14},ask:{value:16.15},leverage:{value:23.05}}),
 n:v=>typeof v==="number"&&Number.isFinite(v)?v:null
};
vm.createContext(helper);vm.runInContext(fragment,helper);
const labels=Array.from(helper.productProblemLabels(product));
assert(labels.includes("Hebelzeit / Quellenprüfung"));
assert(labels.includes("Kursart / DEGIRO-Handelsnachweis"));
assert(!labels.includes("Kursnachweis"),JSON.stringify(labels));
assert(!labels.includes("Produktnachweis"),JSON.stringify(labels));
helper.productFieldStates=()=>({bid:{value:null},ask:{value:null},leverage:{value:null}});
const noValues=Array.from(helper.productProblemLabels(product));
assert(noValues.includes("Hebel")&&noValues.includes("Kursnachweis"));
console.log("Evidence status: correct 90s BNP clock, native CHF research 300s, values versus proofs distinguishable.");
