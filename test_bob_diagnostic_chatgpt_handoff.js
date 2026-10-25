const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('bob_problems.py','utf8');
assert(source.includes("if(latest)latest={...latest,status:'stale'}"),'Failed refresh must mark the old snapshot stale');
const start=source.indexOf(' function diagnosticShareText(');
const end=source.indexOf(' async function copy(',start);
assert(start>0 && end>start,'Privacy-filtered mobile diagnostic helpers exist');
const nodes={
 bobProblemsShareStatus:{textContent:''},
 bobProblemsShareFallback:{hidden:true},
 bobProblemsShareText:{value:''}
};
let shares=[],clipboardWrites=0;
const navigator={
 clipboard:{writeText:()=>{clipboardWrites++;throw Error('unexpected clipboard write')}},
 share:async payload=>{shares.push(payload);}
};
const document={getElementById:id=>nodes[id]};
const context={navigator,document};
vm.createContext(context);
vm.runInContext(
 'const publicCodes={"scanner-unreachable":"Scanner nicht erreichbar","push-unreachable":"Push-Service nicht erreichbar"};'+
 'const kiStatusLabels={"new":"Noch nicht geprüft","testing":"Reparatur in technischer Prüfung"};'+
 'let latest=null,lastStats=null;\n'+source.slice(start,end)+
 '\nglobalThis.build=diagnosticShareText;globalThis.share=shareToChatGPT;'+
 'globalThis.setData=(a,b)=>{latest=a;lastStats=b;};',
 context
);
const sample={
 status:'ok',checkedAt:'2026-10-25T03:20:01Z',count:2,
 password:'SHOULD_NEVER_EXPORT',
 problems:[
 {number:124,code:'scanner-unreachable',kiStatus:'testing',message:'SECRET_MUST_NOT_EXPORT',bid:515.50},
 {number:125,code:'manual-125',kiStatus:'new',message:'user private email NEVER_EXPOSE'},
 {number:126,code:'not-allowed',message:'OTHER_PRIVATE_TEXT'},
 ]
};
const stats={status:'ok',detected:4,verifiedRepairs:2,account:'ACCOUNT_PRIVATE'};
const body=context.build(sample,stats);
for(const expected of ['BOB-FEHLERDIAGNOSE/1','BOB_KI_REVIEW','BOB_DIAGNOSTIC_CHATGPT_HANDOFF.md','Fall BOB-124-scanner-unreachable','Fall BOB-125-manual-125',
 'Offene technische KI-Hilfeanfragen laut Index: 2','Bestätigte Reparaturen: 2'])
 assert(body.includes(expected),expected);
for(const hidden of ['SHOULD_NEVER_EXPORT','SECRET_MUST_NOT_EXPORT','user private email',
 'NEVER_EXPOSE','OTHER_PRIVATE_TEXT','ACCOUNT_PRIVATE','515.5'])
 assert(!body.includes(hidden),hidden);
assert(!body.includes('#126'));
const stale=context.build({...sample,status:'stale'},stats);
assert(stale.includes('Indexstatus: stale') && stale.includes('nicht als aktuell bestätigen'));
const unavailable=context.build({...sample,status:'unavailable',count:0},null);
assert(unavailable.includes('Indexstatus: unavailable'));
assert(unavailable.includes('Fehlerliste derzeit nicht verfügbar'));
assert(!unavailable.includes('Offene technische KI-Hilfeanfragen laut Index: 0'));
context.setData(sample,stats);
context.share();
assert.strictEqual(shares.length,1,'One user click starts exactly one Android share');
assert.strictEqual(shares[0].text,body);
assert.strictEqual(clipboardWrites,0);
assert.strictEqual(nodes.bobProblemsShareFallback.hidden,false,'Visible backup stays available');
delete navigator.share;
context.share();
assert(nodes.bobProblemsShareStatus.textContent.includes('nicht verfügbar'));
assert.strictEqual(shares.length,1,'Missing share support never silently exports');
assert.strictEqual(clipboardWrites,0);
console.log('Bob technical diagnostic handoff: sanitized issue codes, stale/unavailable truth, direct share and explicit copy fallback passed');
