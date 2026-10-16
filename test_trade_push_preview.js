"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const html=fs.readFileSync("Bob.html","utf8");
const start=html.indexOf("function initMobile(){");
const end=html.indexOf("if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initMobile)",start);
assert(start>=0&&end>start);
const mobile=html.slice(start,end);
for(const required of [
 "move(push,'trade');",
 "cardSpecs=[",
 "bob-push-card-icon",
 "bob-push-card-description",
 "Marktsignale ein-/ausschalten",
 "Trade-Warnungen ein-/ausschalten",
 "label.before(icon);label.after(description);",
 "names[0].textContent='Marktbeobachtung'",
 "names[1].textContent='Aktiver Trade'",
 "registrationRow.append(refreshButton)",
 "await syncPushPreferences()"
]) assert(mobile.includes(required),"Missing mobile card feature: "+required);
assert(mobile.indexOf("move(push,'trade');")<mobile.indexOf("move(card('tradeStateBtn'),'trade');"));
assert.equal((html.match(/id="generalPushBtn"/g)||[]).length,1);
assert.equal((html.match(/id="tradePushBtn"/g)||[]).length,1);
assert(html.includes('id="generalPushBtn" onclick="togglePush(\'general\')"'));
assert(html.includes('id="tradePushBtn" onclick="togglePush(\'trade\')"'));
assert(html.includes("gb.setAttribute('aria-pressed',String(!!pushState.general))"));
assert(html.includes("tb.setAttribute('aria-pressed',String(!!pushState.trade))"));
assert(html.includes("gb.setAttribute('aria-label','Marktbeobachtung: '"));
assert(html.includes("tb.setAttribute('aria-label','Aktiver Trade: '"));
const css=html.slice(html.indexOf("/* Mein Trade: preview-style cards"),html.indexOf("</style>"));
assert(css.includes("repeat(2,minmax(0,1fr))"),"Two responsive side-by-side cards");
assert(css.includes(".bob-trade-push-toggles .metric button"));
assert(css.includes("button[aria-pressed=\"true\"]"));
assert(css.includes("button[aria-pressed=\"false\"]"));
assert(css.includes("width:auto;min-width:92px"),"Compact status controls, not large full-width colored panels");
assert(css.includes("background:#fff"),"White preview cards");
assert(css.includes("color:#15803d"),"Outline icon");
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
for(const script of scripts.filter(x=>x[1].includes("function initMobile(){")||x[1].includes("async function togglePush(kind){")))
 new vm.Script(script[1],{filename:"Bob-inline.js"});
console.log("Mein Trade: two preview-style icon cards with real push controls, mobile CSS, accessibility and syntax OK");
