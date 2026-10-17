/* Local video decoding: the full file never leaves the device. */
(function(root){
'use strict';
const numeric=s=>(String(s).match(/\d+(?:[.,]\d+)*/g)||[]);
const words=s=>new Set((String(s).toLowerCase().match(/[a-zäöüß]{3,}/g)||[]).filter(w=>!['der','die','das','und','bei','mit','the','and','for'].includes(w)));
function match(image,evidence){
 const text=(image.lines||[]).map(l=>l.text).join(' '),tokens=words(text),numbers=numeric(text);
 return (evidence||[]).filter(e=>Number.isFinite(e.at)&&Math.abs(e.at-image.at)<=15).map(e=>{
  const common=[...words(e.text)].filter(w=>tokens.has(w)),same=numeric(e.text).filter(n=>numbers.includes(n));
  return {at:e.at,text:e.text,matched:common.length>=1&&same.length>=1,score:common.length+same.length*2};
 }).sort((a,b)=>Number(b.matched)-Number(a.matched)||b.score-a.score)[0]||null;
}
function difference(a,b){if(!a||a.length!==b.length)return 0;let n=0;for(let i=0;i<a.length;i+=4)n+=Math.abs(a[i]-b[i])+Math.abs(a[i+1]-b[i+1])+Math.abs(a[i+2]-b[i+2]);return n/(a.length/4*3);}
function plan(duration,moments){
 const targets=(moments||[]).map(m=>m.at).filter(t=>Number.isFinite(t)&&t>=0&&t<duration).slice(0,3);
 if(!targets.length)targets.push(duration*.15,duration*.5,duration*.85);
 return {targets,times:[...new Set([...Array.from({length:Math.min(48,Math.ceil(duration/10))},(_,i)=>Math.min(duration-.1,i*duration/Math.min(48,Math.ceil(duration/10)))),...targets.flatMap(t=>[Math.max(0,t-2),t,Math.min(duration-.1,t+2)])].map(t=>Math.round(t*1000)/1000))].sort((a,b)=>a-b)};
}
if(typeof module!=='undefined')module.exports={match,difference,plan};
if(!root?.document)return;
const d=root.document,el=(t,s)=>{const n=d.createElement(t);if(s!==undefined)n.textContent=s;return n;};
function event(target,name,operation){return new Promise((resolve,reject)=>{
 const timeout=setTimeout(()=>done(new Error('Videolesung dauert zu lange')),12000);
 const ok=()=>done(),bad=()=>done(new Error('Videodatei auf diesem Gerät nicht lesbar'));
 function done(error){clearTimeout(timeout);target.removeEventListener(name,ok);target.removeEventListener('error',bad);error?reject(error):resolve();}
 target.addEventListener(name,ok,{once:true});target.addEventListener('error',bad,{once:true});operation();
});}
async function extract(file,moments,status,cancel){
 const video=el('video');video.muted=true;video.playsInline=true;video.preload='auto';
 const url=URL.createObjectURL(file),canvas=el('canvas'),tiny=el('canvas');tiny.width=64;tiny.height=36;
 const small=tiny.getContext('2d',{willReadFrequently:true}),ctx=canvas.getContext('2d');
 try{
  await event(video,'loadeddata',()=>{video.src=url;});
  const duration=video.duration;if(!Number.isFinite(duration)||duration<1||duration>7200)throw new Error('Bitte ein Video von höchstens zwei Stunden wählen');
  const scale=Math.min(1,800/video.videoWidth,600/video.videoHeight);canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
  if(canvas.width<200||canvas.height<100)throw new Error('Videoauflösung zu klein');
  const {targets,times}=plan(duration,moments),near=[],scenes=[];let previous=null;
  for(let i=0;i<times.length;i++){
   if(cancel.stop)throw new Error('Abgebrochen');
   const at=times[i];if(Math.abs(video.currentTime-at)>.001)await event(video,'seeked',()=>{video.currentTime=at;});
   ctx.drawImage(video,0,0,canvas.width,canvas.height);small.drawImage(video,0,0,64,36);
   const pixels=small.getImageData(0,0,64,36).data,change=difference(previous,pixels);previous=pixels;
   let quality=.85,dataUrl=canvas.toDataURL('image/jpeg',quality);
   while(dataUrl.length>139000&&quality>.3){quality-=.1;dataUrl=canvas.toDataURL('image/jpeg',quality);}
   if(dataUrl.length>139000)continue;
   const frame={at:video.currentTime,dataUrl,change};
   if(targets.some(t=>Math.abs(t-at)<=2.01))near.push(frame);
   scenes.push(frame);scenes.sort((a,b)=>b.change-a.change);scenes.splice(5);
   status.textContent='Videobilder prüfen: '+Math.round((i+1)/times.length*100)+' %';
  }
  // Prefer exact evidence positions; add two distinct neighboring frames to the first.
  const selected=[];const add=f=>{if(f&&!selected.some(x=>Math.abs(x.at-f.at)<.01))selected.push(f);};
  for(const target of targets.slice(0,2))add([...near].sort((a,b)=>Math.abs(a.at-target)-Math.abs(b.at-target))[0]);
  for(const frame of near.filter(f=>Math.abs(f.at-targets[0])<=2.01))if(selected.length<4)add(frame);
  for(const frame of scenes)if(selected.length<5)add(frame);
  return selected.slice(0,5).sort((a,b)=>a.at-b.at).map(({at,dataUrl})=>({at,dataUrl}));
 }finally{video.removeAttribute('src');video.load();URL.revokeObjectURL(url);}
}
async function api(payload){const r=await fetch('/api/research/video-evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok||data.error)throw new Error(data.error||'Speichern nicht möglich');return data;}
function controls(host,item,onResult){
 let id=item.videoId;try{id=id||new URL(item.url).searchParams.get('v');}catch(_){return;}
 if(!/^[A-Za-z0-9_-]{11}$/.test(id||''))return;
 const box=el('details'),status=el('p'),input=el('input'),assigned=el('input'),label=el('label'),start=el('button','Videobilder auswählen'),save=el('button','Diese Bilder in Bob speichern'),stop=el('button','Abbrechen'),refresh=el('button','Gespeicherte Bildprüfung aktualisieren'),preview=el('div');
 box.append(el('summary','Videodatei für bessere Bilder hinzufügen'),el('p','Die Datei bleibt auf deinem Gerät. Bob prüft bis zu 57 Videostellen und speichert höchstens fünf ausgewählte Bilder. Diagrammwechsel werden stichprobenartig erkannt; keine vollständige Bild-für-Bild-Auswertung.'));
 input.type='file';input.accept='video/*';assigned.type='checkbox';label.append(assigned,d.createTextNode(' Diese Datei gehört zum angezeigten MCO-Video und beginnt am gleichen Videoanfang.'));
 for(const b of [start,save,stop,refresh])b.type='button';save.hidden=true;stop.hidden=true;
 let pending=[],cancel={stop:false};
 input.onchange=()=>{pending=[];save.hidden=true;preview.replaceChildren();assigned.checked=false;};
 start.onclick=async()=>{
  if(!input.files?.[0]||!assigned.checked){status.textContent='Bitte Datei wählen und Zuordnung bestätigen.';return;}
  start.disabled=true;input.disabled=true;save.hidden=true;stop.hidden=false;cancel={stop:false};preview.replaceChildren();
  try{pending=await extract(input.files[0],item.overview?.moments||[],status,cancel);
   if(cancel.stop)throw new Error('Abgebrochen');
   for(const f of pending){const figure=el('figure'),img=el('img');img.src=f.dataUrl;img.style.cssText='width:100%;max-width:480px';figure.append(img,el('figcaption','Videoposition '+f.at.toFixed(1)+' Sekunden · vom Nutzer zugeordnete Datei'));preview.append(figure);}
   status.textContent=pending.length+' Bilder ausgewählt. Bitte prüfen und speichern.';save.hidden=!pending.length;
  }catch(e){status.textContent=e.message;}finally{start.disabled=false;input.disabled=false;stop.hidden=true;}
 };
 stop.onclick=()=>{cancel.stop=true;};
 save.onclick=async()=>{if(!assigned.checked)return;save.disabled=true;try{const result=await api({videoId:id,action:'write',assignedByUser:true,frames:pending});onResult(result);status.textContent='Gespeichert. Die kostenlose OCR läuft im Hintergrund. Nach etwa zwei Minuten „Bildprüfung aktualisieren“ drücken.';save.hidden=true;}catch(e){status.textContent=e.message;}finally{save.disabled=false;}};
 refresh.onclick=async()=>{refresh.disabled=true;try{onResult(await api({videoId:id,action:'read'}));status.textContent='Gespeicherte Bildprüfung aktualisiert.';}catch(e){status.textContent=e.message;}finally{refresh.disabled=false;}};
 box.append(input,label,start,stop,status,preview,save);host.append(box,refresh);
}
root.BobVideoEvidence={controls,match};
})(typeof window==='undefined'?null:window);
