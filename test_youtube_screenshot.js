const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).find(s=>s.includes('async function screenshotVideo'));
const els=new Map(),events=new Map();
function element(id){if(!els.has(id))els.set(id,{value:'',textContent:'',disabled:false,files:[],children:[],addEventListener:(k,f)=>events.set(id+':'+k,f),replaceChildren(...x){this.children=x;},append(){},click(){}});return els.get(id);}
let retained=false,calls=[],fail=false;
const env={document:{getElementById:element,createElement:tag=>({tag,textContent:'',append(){}}),addEventListener(){},visibilityState:'hidden'},window:{BobDegiro:{retainSelectedImages:async input=>{assert(input.files.length);assert.equal(input.value,'selected');retained=true;return [{copied:true}]},recognizePlainOcr:async file=>{assert(retained&&file.copied);assert.equal(element('youtubeScreenshotInput').value,'');if(fail)throw Error('OCR unavailable');return {data:{text:'Gold price outlook for today explained\nWorld Gold Council'}}}}},fetch:async(url,args)=>{calls.push(JSON.parse(args.body));return {ok:true,status:200,json:async()=>({ok:false,resolved:{url:'https://www.youtube.com/watch?v=abcdefghijk',title:'Gold outlook',channel:'World Gold Council'},error:'Video erkannt, Untertitel fehlen'})}},setTimeout:()=>1,clearTimeout(){},setInterval(){},AbortController,URL,Date,Math,String,Error};
vm.createContext(env);vm.runInContext(script,env);
(async()=>{
 const input=element('youtubeScreenshotInput');input.files=[{size:100}];input.value='selected';
 await events.get('youtubeScreenshotInput:change')();
 assert.equal(calls.length,1);assert(calls[0].screenshotText.includes('Gold'));assert(!('url' in calls[0]));
 assert.equal(element('youtubeResearchUrl').value,'https://www.youtube.com/watch?v=abcdefghijk');
 assert.equal(element('youtubeResearchStatus').textContent,'Video erkannt, Untertitel fehlen');
 assert(!element('youtubeScreenshotButton').disabled);
 fail=true;input.value='selected';await events.get('youtubeScreenshotInput:change')();
 assert.equal(calls.length,1);assert.equal(element('youtubeResearchStatus').textContent,'OCR unavailable');
 input.files=[];await events.get('youtubeScreenshotInput:change')();assert.equal(calls.length,1);
 console.log('YouTube screenshot: retained before Android picker reset, automatic lookup, caption failure disclosure, OCR failure and cancel OK');
})().catch(e=>{console.error(e);process.exitCode=1});
