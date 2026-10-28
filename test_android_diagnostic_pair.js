const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync('android_diagnostic_pair.html','utf8').match(/<script>([\s\S]*?)<\/script>/i)[1];
function mount(hash,storage){
 const nodes={};const calls=[];
 const context={document:{getElementById:id=>nodes[id]??=( {disabled:id==='approve',textContent:''})},
 location:{hash,pathname:'/handy/diagnostics'},history:{replaceState:()=>{}},sessionStorage:{getItem:k=>storage[k],setItem:(k,v)=>storage[k]=v},
 Date,JSON,Error,AbortSignal:{timeout:()=>null},confirm:()=>true,
 fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {status:200,ok:true,json:async()=>({ok:true,paired:true})}}};
 vm.runInNewContext(script,context);return {nodes,calls};
}
(async()=>{
 const storage={};let page=mount('#'+'a'.repeat(64),storage);
 assert.equal(page.nodes.approve.disabled,false);await page.nodes.approve.onclick();
 assert.deepEqual(page.calls[0].body,{action:'register',tokenHash:'a'.repeat(64)});
 page=mount('',storage);assert.equal(page.nodes.approve.disabled,false);
 await page.nodes.approve.onclick();assert.equal(page.calls[0].body.tokenHash,'a'.repeat(64));
 page=mount('#<script>',{});assert.equal(page.nodes.approve.disabled,true);
 page=mount('',{bobDiagnosticPairV1:JSON.stringify({digest:'b'.repeat(64),at:Date.now()-700000})});assert.equal(page.nodes.approve.disabled,true);
 console.log('Pairing page: hash-only consent, login reload recovery and expiry passed');
})().catch(e=>{console.error(e);process.exit(1)});
