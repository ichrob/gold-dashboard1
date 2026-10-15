"use strict";
const fs=require("node:fs");
const assert=require("node:assert/strict");
const vm=require("node:vm");
const html=fs.readFileSync("Bob.html","utf8");
const sectionStart=html.indexOf("const mobileHelp=document.createElement('section')");
assert(sectionStart>0, "Mobile KI help must exist in the Problem screen");
const sectionEnd=html.indexOf("const disclaimer=main.querySelector", sectionStart);
assert(sectionEnd>sectionStart, "The KI help code must stay inside the mobile app initialization");
const block=html.slice(sectionStart,sectionEnd);
for(const marker of ["panels.problems.prepend(mobileHelp)","bobMobileHelpShare","bobMobileHelpOpen","https://chatgpt.com/","navigator.share","copyMobileHelp","role=\"status\""]){
 assert(block.includes(marker),"Missing mobile action: "+marker);
}
assert(block.includes("Es werden keine Zugangsdaten oder privaten Produktwerte übertragen."));
assert(block.includes("Nur Desktop"),"Explicitly explain the native plugin restriction");
assert(!block.includes("localStorage")&&!block.includes("Authorization"),"Do not copy authentication material to ChatGPT");
assert(!block.includes("fetch("),"Never automatically upload private diagnostics");
assert(block.includes("Ändere keine Echtgeldorders"),"Trade safety reminder required");
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
const mobileScript=scripts.find(s=>s[1].includes("const mobileHelp=document.createElement"));
assert(mobileScript, "Mobile handoff must be in a script tag");
new vm.Script(mobileScript[1],{filename:"Bob.mobile-inline.js"});
console.log("Bob smartphone KI handoff: markup, privacy and syntax OK");
