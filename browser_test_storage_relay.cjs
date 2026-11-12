'use strict';

function createStorageRelay(pages){
 const values={};
 let delivery=Promise.resolve();
 function write(sourcePage,key,value,remove=false){
  if(remove)delete values[key];else values[key]=value;
  delivery=delivery.then(()=>Promise.all(pages().filter(page=>page!==sourcePage).map(page=>
   page.evaluate(({key,value,remove})=>window.gmRemote(key,value,remove),
    {key,value,remove}).catch(()=>{}))));
 }
 async function flush(){
  let pending;
  do{pending=delivery;await pending;}while(pending!==delivery);
 }
 return {values,write,flush};
}

module.exports={createStorageRelay};
