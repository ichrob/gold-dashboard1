"use strict";
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");

const html=fs.readFileSync("Bob.html","utf8");
const mobileStart=html.indexOf("function initMobile(){");
const mobileEnd=html.indexOf("if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initMobile)",mobileStart);
assert(mobileStart>0&&mobileEnd>mobileStart,"mobile layout missing");
const mobile=html.slice(mobileStart,mobileEnd);

assert(mobile.includes("move(push,'trade');"),"Original push card must be moved into Mein Trade");
assert(!mobile.includes("card('sourceSummary'),push"),"Push controls cannot remain hidden in overview's system details");
assert(mobile.indexOf("move(push,'trade');")<mobile.indexOf("move(card('tradeStateBtn'),'trade');"),
       "Push toggles must appear before trade status");
assert(mobile.indexOf("move(push,'trade');")<mobile.indexOf("panels.trade.append(guide)"),
       "Push toggles must appear before trade entry form");
assert(mobile.includes("names[0].textContent='Marktbeobachtung'"));
assert(mobile.includes("names[1].textContent='Aktiver Trade'"));
assert(mobile.includes("pushGrid?.classList.add('bob-trade-push-toggles')"));
assert(mobile.includes("registrationRow.append(refreshButton)"));
assert(mobile.includes("refreshButton.textContent='↻ Push aktualisieren'"));
assert(mobile.includes("await registerNotifications()"));
assert(mobile.includes("await syncPushPreferences()"));
assert(mobile.includes("push.append(advanced)"),"Advanced notification controls must remain accessible");
assert(mobile.includes("push.append(pushStatus)"),"Visible feedback must be preserved");
assert(mobile.includes("if(testButton)advanced.append(testButton)"),"Existing test action must remain accessible");
assert(html.includes("id=\"generalPushBtn\" onclick=\"togglePush('general')\""));
assert(html.includes("id=\"tradePushBtn\" onclick=\"togglePush('trade')\""));
assert.equal((html.match(/id=\"generalPushBtn\"/g)||[]).length,1,"No cloned buttons");
assert.equal((html.match(/id=\"tradePushBtn\"/g)||[]).length,1,"No cloned buttons");
assert(html.includes("gb.setAttribute('aria-pressed',String(!!pushState.general))"));
assert(html.includes("tb.setAttribute('aria-pressed',String(!!pushState.trade))"));
assert(html.includes("if(note)note.textContent=synced?"),"Toggling should report server-sync success/failure");
assert(html.includes("#bobTradePushControls .bob-trade-push-toggles"));

const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
const mobileScript=scripts.find(x=>x[1].includes("function initMobile(){"));
const pushScript=scripts.find(x=>x[1].includes("async function togglePush(kind){"));
assert(mobileScript&&pushScript,"Required inline scripts not found");
new vm.Script(mobileScript[1],{filename:"Bob-mobile.js"});
new vm.Script(pushScript[1],{filename:"Bob-push.js"});

console.log("Mein Trade: push toggles on top, original handlers, server refresh, feedback and JS syntax OK");
