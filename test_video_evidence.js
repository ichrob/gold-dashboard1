const assert=require('node:assert/strict');
const {match,plan,difference}=require('./video_evidence.js');
const image={at:20,lines:[{text:'RSI 61.8'}]};
assert.equal(match(image,[{at:21,text:'Der RSI liegt bei 61.8.'}]).matched,true);
assert.equal(match(image,[{at:21,text:'Gold liegt bei 61.8.'}]).matched,false);
assert.equal(match(image,[{at:80,text:'RSI 61.8'}]),null);
for(const duration of [1,60,7200]){
 const p=plan(duration,[{at:20},{at:200},{at:400}]);assert(p.times.length<=57);assert(p.times.every(t=>t>=0&&t<duration));
}
assert.equal(difference(new Uint8Array([0,0,0,255]),new Uint8Array([255,255,255,255])),255);
console.log('Video evidence matching and bounded sampling passed');
{
const {quality,selectFrames}=require('./video_evidence.js');
const flat=new Uint8ClampedArray(64*36*4).fill(120),sharp=new Uint8ClampedArray(64*36*4);
for(let i=0;i<sharp.length;i+=4){const v=((i/4)%2)*255;sharp[i]=sharp[i+1]=sharp[i+2]=v;sharp[i+3]=255;}
assert.equal(quality(flat,64,36).usable,false);assert.equal(quality(sharp,64,36).usable,true);
const frame=(at,pixels)=>({at,pixels,quality:quality(pixels,64,36),change:0});
const chosen=selectFrames([frame(1,flat),frame(2,sharp),frame(3,sharp)],[1]);
assert.equal(chosen.length,1);assert.equal(chosen[0].at,2);
console.log('Flat frames excluded, sharp evidence preferred, near-duplicates removed');
}
