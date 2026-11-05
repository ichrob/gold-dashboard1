const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('Bob.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).find(s=>s.includes('function describe(event,current'));
let listener,interval,nav=0,scroll=0;
const nodes={pushOpened:{hidden:true,scrollIntoView(){scroll++;}},pushOpenedText:{},pushOpenedDismiss:{addEventListener(k,f){this.close=f;}}};
const warning={available:true,state:'active',direction:'SHORT'},trend={available:true,direction:'LONG'};
let fresh=true;
const env={Date,Number,JSON,decodeURIComponent,location:{hash:'#push='+encodeURIComponent(JSON.stringify({eventKind:'early-warning',direction:'SHORT',generatedAt:Date.now()-600000,expiresAt:Date.now()-1,receiptProof:'NEVER DISPLAY'}))},
 document:{hidden:false,getElementById:id=>nodes[id],querySelector:()=>({click(){nav++;}}),addEventListener(){}},
 navigator:{serviceWorker:{addEventListener(k,f){listener=f;}}},window:{addEventListener(){}},setInterval(f){interval=f;},
 earlyWarningContext:()=>warning,sustainedTrendContext:()=>trend,currentSpotUsable:()=>fresh,analysisAgeWarnings:()=>[],liveBundleCache:{history:{bars_by_tf:{"5m":[{openTime:Date.now()-300000,isOpen:false}]}}},A:{ready:true},signalState:{dir:'NEUTRAL',reason:'Keine bestätigte Einstiegsrichtung'}};
vm.runInNewContext(script,env);
assert.equal(nodes.pushOpened.hidden,false);assert.equal(nav,1);assert.equal(scroll,1);
let text=nodes.pushOpenedText.textContent;
for(const term of ['FRÜHWARNUNG · SHORT','abgelaufen','Haupttrend: LONG','Einstieg: ABWARTEN'])assert(text.includes(term),term);
assert(!text.includes('NEVER DISPLAY'));
listener({data:{type:'BOB_PUSH_CLICK',data:{kind:'general',eventKind:'signal-change',direction:'LONG',generatedAt:Date.now()}}});
assert(nodes.pushOpenedText.textContent.includes('BESTÄTIGTES EINSTIEGSSIGNAL · LONG'));
fresh=false;env.signalState.dir='LONG';interval();
assert(nodes.pushOpenedText.textContent.includes('Einstieg: ABWARTEN'));
assert(nodes.pushOpenedText.textContent.includes('Datenaktualität nicht bestätigt'));
assert.equal(env.signalState.dir,'LONG','display must not mutate strategy');
nodes.pushOpenedDismiss.close();interval();assert.equal(nodes.pushOpened.hidden,true);
listener({data:{type:'BOB_PUSH_CLICK',data:{kind:'trade',eventKind:'signal-change'}}});assert.equal(nodes.pushOpened.hidden,true);
listener({data:{type:'BOB_PUSH_CLICK',data:{kind:'general',eventKind:'<script>'}}});assert.equal(nodes.pushOpened.hidden,true);
console.log('Push context: cold/warm open, expiry, conflicting directions, stale data, dismissal and isolation passed');
