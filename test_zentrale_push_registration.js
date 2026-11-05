'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('push_manager.js','utf8');
const block=source.slice(source.indexOf('  async function registration(){'),source.indexOf('  const defaults='));
(async()=>{
 const root={scope:'/'},central={scope:'/zentrale/'};
 for(const pathname of ['/','/zentrale/workspace','/zentrale/']){
  const paths=[];const ctx={location:{pathname},navigator:{serviceWorker:{ready:Promise.resolve(central),getRegistration:async path=>{paths.push(path);return root;}}}};
  vm.createContext(ctx);vm.runInContext(block,ctx);
  assert.equal(await ctx.registration(),pathname==='/'?central:root);
  assert.deepEqual(paths,pathname==='/'?[]:['/']);
 }
 const ctx={location:{pathname:'/zentrale/workspace'},navigator:{serviceWorker:{getRegistration:async()=>undefined}}};
 vm.createContext(ctx);vm.runInContext(block,ctx);
 await assert.rejects(ctx.registration(),/Gerät registrieren/);
 console.log('Zentrale uses existing root push registration; missing registration is explicit.');
})().catch(e=>{console.error(e);process.exitCode=1;});
