const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8');
const structure=html.slice(html.indexOf('function structureLevels('),html.indexOf('function stopModel('));
const obstacle=html.slice(html.indexOf('function targetObstacle('),html.indexOf('function targetModel('));
const env={};vm.createContext(env);vm.runInContext(structure+obstacle,env);
const bars=Array.from({length:40},()=>({high:105,low:95}));bars[20]={high:112,low:88};
for(const [dir,target,expected] of [['LONG',120,112],['SHORT',80,88]]){
 const check=env.targetObstacle(dir,100,target,10,2,{available:true,bars});
 assert.equal(check.obstacle,expected);assert.equal(check.obstacleRR,1.2);assert.equal(check.entrySuitable,false);
 assert.equal(env.targetObstacle(dir,100,dir==='LONG'?110:90,10,2,{available:true,bars}).obstacle,null);
}
assert.equal(env.targetObstacle('LONG',100,120,10,2,{available:false}).available,false);
console.log('Confirmed LONG/SHORT obstacles, opportunity to first barrier and unavailable data passed.');
