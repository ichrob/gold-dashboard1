const assert=require('assert'),fs=require('fs'),vm=require('vm');
async function scenario(mode){
 const stored={},fields={isin:'DE000FG5GUX2',currency:'EUR',entry:'2',quantity:'10'};let activations=0,calls=0,current=null;
 const document={readyState:'loading',addEventListener(){},dispatchEvent(){},querySelector:s=>({value:fields[s.match(/"(.*?)"/)[1]]})};
 const window={addEventListener(){},BobDegiro:{validIsin:x=>x==='DE000FG5GUX2'},BobTradeSync:{current:()=>current},BobExitEstimate:{automaticTradeReference:async()=>({isin:fields.isin,direction:'LONG'})},activateProductTrade:async()=>{activations++;current={active:true};}};
 const c={window,document,localStorage:{getItem:k=>stored[k],setItem:(k,v)=>stored[k]=v},setInterval(){},Event:class{},AbortSignal,Intl,Date,fetch:async()=>{calls++;if(mode==='offline')throw Error('offline');return {ok:true,json:async()=>({trades:mode==='existing'?[{active:true}]:[]})};}};
 vm.createContext(c);vm.runInContext(fs.readFileSync('trade_upload.js','utf8'),c);const api=window.BobTradeUpload;
 const day=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich'}).format(new Date()).split('-').reverse().join('.');
 const t={isin:fields.isin,currency:'EUR',direction:'LONG',entry:{price:2,quantity:10,at:day+' 09:00'}};
 assert.equal(api.setupCandidate(t,'2000-01-01').ok,false);
 if(mode==='conflict')fields.quantity='11';
 api.queueSetup(t);await new Promise(resolve=>setImmediate(resolve));await api.runSetup();
 assert.equal(activations,mode==='ok'?1:0);
 if(mode==='ok'){api.queueSetup(t);await api.runSetup();assert.equal(activations,1);}
 if(mode==='offline'){assert.equal(calls,1);assert.equal(api.status().state,'waiting');}
 if(mode==='conflict'){assert.equal(calls,0);assert.equal(api.status().state,'needs-user');}
}
(async()=>{for(const mode of ['ok','existing','offline','conflict'])await scenario(mode);console.log('Screenshot setup: single activation, server duplicate guard, offline backoff, edited fields and historical dates passed');})().catch(e=>{console.error(e);process.exit(1)});
