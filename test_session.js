const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1].split('/* Bob runtime probe:')[0];
async function run(){
 const calls=[],notice={hidden:true};
 let sessionStatus=200;
 const env={URL,Response,JSON,AbortController,setTimeout:()=>0,clearTimeout(){},setInterval(){},location:{href:'https://bob.example/',origin:'https://bob.example'},document:{getElementById:()=>notice,addEventListener(){},visibilityState:"visible"},fetch:async(input,options)=>{calls.push({input,options});return new Response(String(input)==='/api/collection-status'?JSON.stringify({enabled:true,running:true}):'{}',{status:String(input)==='/api/collection-status'?sessionStatus:String(input).includes('external')?401:200});}};
 env.window=env;vm.createContext(env);vm.runInContext(script,env);
 await env.fetch('https://external.example/api/live');
 assert.equal(env.BobSession.expired(),false,'external 401 must not invalidate Bob session');
 await env.fetch('/api/live',{signal:undefined});
 assert.equal(calls.at(-1).options.credentials,'same-origin');
 env.location.href='https://bob.example/external';
 const nativeCall=calls.length;
 // Use a same-origin URL that the fixture rejects.
 await env.fetch('/api/external');
 assert.equal(env.BobSession.expired(),true);assert.equal(notice.hidden,false);
 const after=calls.length;
 const r=await env.fetch('/api/mtf');
 assert.equal(r.status,401);assert.equal(calls.length,after,'expired session must not repeat protected network requests');
 await env.fetch('/api/diag');assert.equal(calls.length,after+1);
 assert(nativeCall<after);
 sessionStatus=503;await env.BobSession.recheck();assert(env.BobSession.expired());
 sessionStatus=401;await env.BobSession.recheck();assert(env.BobSession.expired());
 sessionStatus=200;await env.BobSession.recheck();assert(!env.BobSession.expired());assert(notice.hidden);
 const count=calls.length;await env.BobSession.recheck();assert.equal(calls.length,count);
 await env.fetch('/api/mtf');assert.equal(calls.length,count+1);
 console.log('Session recovery: origin isolation, credentials, 401 gate and retry suppression OK');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
