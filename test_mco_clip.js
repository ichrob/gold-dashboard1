const assert=require('assert'),fs=require('fs');
const {prepare,DURATION}=require('./mco_clip.js');
assert.strictEqual(DURATION,60);
const valid={title:'Gold – MCO erklärt die Lage',transcriptAnalyzed:true,trustedTranscript:true,
 outlook:'LONG',mcoFibonacci:[{key:'r618',ratio:'61,8 %',price:4100,at:144,quote:'61,8 Prozent bei 4100'},
 {key:'r382',ratio:'38,2 %',price:4040,at:189},
 {key:'invalid',ratio:'1 %',price:4300,at:200}],
 overview:{sections:[{key:'overview',evidenceIds:['e1']},{key:'bullish',evidenceIds:['e2']},{key:'bearish',evidenceIds:['e3']},{key:'conditions',evidenceIds:['e4']}],
 evidence:[{id:'e1',at:10,text:'Der Goldmarkt bleibt volatil.'},
 {id:'e2',at:50,text:'Wenn Gold den Widerstand überwindet, könnte der Kurs steigen.'},
 {id:'e3',at:98,text:'Falls die Unterstützung fällt, droht ein Rückgang.'},
 {id:'e4',at:220,text:'Bei Unsicherheit keinen vorschnellen Einstieg vornehmen.'}]}};
assert.strictEqual(prepare(valid,{available:false}).scenes.length,5);
const noData=prepare(valid,{available:false});
assert.strictEqual(noData.bars.length,0);
assert.strictEqual(noData.levels.length,2);
assert.strictEqual(noData.levels[0].bob,null);
assert(noData.scenes.some(s=>s.at===144));
assert.strictEqual(prepare({...valid,trustedTranscript:false},{available:true}),null);
assert.strictEqual(prepare({...valid,transcriptAnalyzed:false},null),null);
assert.strictEqual(prepare({...valid,mcoFibonacci:[]},null).levels.length,0);
assert(/Keine eindeutig belegte/.test(prepare({...valid,mcoFibonacci:[]},null).scenes[2].text));
const matched=prepare(valid,{available:true,fresh:true,asOf:123,levels:{r618:4104,r382:4070},bars:[{close:4080},{close:4081},{close:4082}]});
assert.strictEqual(matched.levels[0].near,true);
assert.strictEqual(matched.levels[1].near,false);
assert.strictEqual(matched.bars.length,3);
const stale=prepare(valid,{available:true,fresh:false,asOf:123,levels:{r618:4100},bars:[{close:4100}]});
assert.strictEqual(stale.levels[0].bob,4100,'Older real prices must remain accessible but visibly dated');
assert.strictEqual(stale.marketFresh,false);
assert.strictEqual(stale.bars.length,1);
const independentlyCalculated=prepare({...valid,mcoFibonacci:[]},{available:true,fresh:false,levels:{r382:4041},bars:[{close:4050}]});
assert.strictEqual(independentlyCalculated.levels.length,0,'Never invent MCO marks');
assert.strictEqual(independentlyCalculated.bobLevels.length,1,'Show verified Bob levels even when MCO speaks no explicit Fibonacci marks');
const clip=fs.readFileSync('mco_clip.js','utf8');
assert(clip.includes('voiced=supportsVoice'),'Sound enabled by default with device TTS');
assert(clip.includes('window.speechSynthesis.speak(utter)'),'Free device narration required');
assert(clip.includes('uiContainer.requestFullscreen')&&clip.includes('fullOverlay=true'),'Android fullscreen with fallback');
assert(clip.includes("progress.type='range'")&&clip.includes("progress.addEventListener('input'"),'Seek bar must actually scrub');
assert(clip.includes('toFib.addEventListener'),'Direct seek to price/Fibonacci scene');
assert(clip.includes("window.fetch('/api/live'"),'Reuse existing authenticated Bob gold feed, no new external vendor');
assert(clip.includes('spot.is_genuine_xauusd_spot===true'),'Only verified gold spot quotes');
assert(clip.includes("ctx.fillText(num(value)"),'Display exact chart axis prices');
assert(!clip.includes('canvas.toDataURL('),'Never scrape copyrighted frames');
const html=fs.readFileSync('Bob.html','utf8'),server=fs.readFileSync('server.py','utf8');
assert(html.includes('src="/mco_clip.js?v=20261010-60s-v2"'));
assert(html.includes('window.BobMcoClip.mount(box,x,url'));
assert(html.includes('x.trustedTranscript&&window.BobMcoClip?.mount'));
assert(server.includes('if path == "/mco_clip.js"'));
assert(!html.includes('canvas.toDataURL('),'No video frame scraping');
console.log('Bob MCO clip verified: 60s, speech, mobile fullscreen, timeline seeking, factual gold + independent Fibonacci values.');
