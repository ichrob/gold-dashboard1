/* Illustrated MCO source summary. No generated chart, market-time inference or trade input. */
(function(root){
'use strict';
const valid=f=>f&&!f.isCover&&Number.isFinite(f.at)&&f.at>=0&&f.at<=86400&&/^data:image\/jpeg;base64,[A-Za-z0-9+/=]{100,140000}$/.test(f.dataUrl||'');
function sections(item){
 const ai=item.enhancements?.summary;
 if(ai?.kind==='ai')return (ai.sections||[]).filter(s=>s.text&&s.evidence?.some(e=>Number.isFinite(e.at)&&e.text)).slice(0,7).map(s=>({...s,kind:'summary'}));
 const byId=new Map((item.overview?.evidence||[]).map(e=>[e.id,e]));const seen=new Set(),out=[];
 for(const s of item.overview?.sections||[]){const evidence=(s.evidenceIds||[]).map(id=>byId.get(id)).filter(e=>e?.text&&Number.isFinite(e.at));const key=evidence.map(e=>e.id||e.text).join('|');if(!evidence.length||seen.has(key))continue;seen.add(key);out.push({label:s.label,text:evidence.map(e=>e.text).join(' '),evidence,kind:'quote'});}
 return out.slice(0,7);
}
function choose(item,section){
 const times=section.evidence.map(e=>e.at),images=item.enhancements?.ocr?.images||[];
 return (item.enhancements?.frames||[]).map((frame,index)=>({frame,index,ocr:images.find(i=>i.index===index),distance:valid(frame)?Math.min(...times.map(t=>Math.abs(t-frame.at))):Infinity}))
 .filter(x=>valid(x.frame)&&(x.frame.sourceKind==='screenshot'?x.frame.sectionAt===times[0]:x.distance<=15)).sort((a,b)=>Number(b.frame.sourceKind==='screenshot')-Number(a.frame.sourceKind==='screenshot')||Number(!!b.ocr?.illustrationRecommended)-Number(!!a.ocr?.illustrationRecommended)||a.distance-b.distance)[0]||null;
}
function market(image){const text=(image?.lines||[]).map(l=>l.text).join(' ');return /\b(?:futures?|COMEX)\b|GC1!/i.test(text)?'future':/XAU\s*\/\s*USD/i.test(text)?'xau':'unknown';}
if(typeof module!=='undefined')module.exports={sections,choose,market};
if(!root?.document)return;
const d=root.document,views=new WeakMap(),el=(t,s)=>{const n=d.createElement(t);if(s!==undefined)n.textContent=s;return n;},stamp=t=>Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');
function link(item,at){try{const url=new URL(item.url);if(url.protocol!=='https:'||!['youtube.com','www.youtube.com'].includes(url.hostname)||url.pathname!=='/watch')return null;url.searchParams.set('t',String(Math.floor(at)));const a=el('a','Originalstelle '+stamp(at)+' auf YouTube');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch(_){return null;}}
function enlarge(frame,trigger){
 const dialog=el('dialog'),title=el('h3','Original-Chartbild · '+stamp(frame.at)),close=el('button','Schließen'),zoom=el('button','2× vergrößern'),area=el('div'),img=el('img');
 dialog.setAttribute('aria-label','Vergrößertes Videobild');dialog.style.cssText='width:96vw;max-width:1600px;max-height:95vh;padding:12px;border:0;border-radius:12px';
 area.style.cssText='overflow:auto;max-height:75vh;touch-action:pan-x pan-y';img.src=frame.dataUrl;img.alt='Vollständiges Originalbild aus der Videostelle '+stamp(frame.at);img.style.cssText='display:block;width:100%;max-width:none;height:auto';
 close.type=zoom.type='button';let large=false;zoom.onclick=()=>{large=!large;img.style.width=large?'200%':'100%';zoom.textContent=large?'Auf Bildschirm einpassen':'2× vergrößern';};
 close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>{dialog.remove();trigger.focus();},{once:true});
 area.append(img);dialog.append(title,close,zoom,el('p','Vergrößerung zeigt vorhandene Bilddetails; fehlende Auflösung wird nicht ergänzt.'),area);d.body.append(dialog);dialog.showModal();close.focus();
}
function figure(card,selected,item,evidence=[]){
 const {frame,ocr}=selected,fig=el('figure'),button=el('button'),img=el('img');button.type='button';button.setAttribute('aria-label','Chartbild vergrößern');button.style.cssText='display:block;width:100%;padding:0;border:0;background:#10151e';img.src=frame.dataUrl;img.alt='Videobild zur MCO-Aussage bei '+stamp(frame.at);img.loading='lazy';img.style.cssText='display:block;width:100%;height:auto;max-width:none;object-fit:contain';button.append(img);button.onclick=()=>enlarge(frame,button);
 fig.style.cssText='margin:12px 0';fig.append(button,el('figcaption','Antippen zum Vergrößern · Videoposition '+stamp(frame.at)+(frame.userProvided?' · Bild und Videoposition vom Nutzer zugeordnet':' · angenäherte YouTube-Vorschau')));card.append(fig);
 const matched=root.BobVideoEvidence?.match(ocr||{at:frame.at,lines:[]},evidence);
 card.append(el('small',frame.sourceKind==='screenshot'?'Screenshot diesem Abschnitt manuell zugeordnet; Inhalt und Videoposition nicht automatisch bestätigt.':matched?.matched?'Bild und Untertitel teilen Begriff und Zahl; Zuordnung plausibel, nicht bestätigt.':'Bild aus derselben Videopassage; inhaltliche Zuordnung nicht bestätigt.'));
 const kind=market(ocr);
 if(kind==='future')card.append(el('p','Gold-Future im Bild erkannt (ungeprüfte Bildlesung). Ein direkter Vergleich dieser Kursmarken mit Gold Spot wäre nicht passend; Future-Kontrakt und Zeitrahmen müssen übereinstimmen.'));
 else if(kind==='xau')card.append(el('p','XAU/USD im Bild erkannt (ungeprüfte Bildlesung). Spot/CFD, Währung und Zeitebene müssen für einen Vergleich zusätzlich geklärt sein.'));
 const values=ocr?.typed?.values||[];
 if(values.length){const details=el('details');details.append(el('summary','Kursbereiche und Indikatoren aus diesem Bild · ungeprüft'));for(const v of values)details.append(el('p',v.label+(v.period!=null?' '+v.period:'')+(v.ratio!=null?' '+v.ratio+' %':'')+': '+v.value+' '+v.unit+' · '+(v.timeframe||'Zeitebene offen')));card.append(details);}
 const original=link(item,frame.at);if(original)card.append(original);
}
function screenshotControl(card,item,section){
 let videoId=item.videoId;try{videoId=videoId||new URL(item.url).searchParams.get('v');}catch(_){return;}
 if(!/^[A-Za-z0-9_-]{11}$/.test(videoId||''))return;
 const open=el('button','Chartbild hinzufügen'),form=el('div'),file=el('input'),preview=el('img'),time=el('input'),agree=el('input'),label=el('label'),save=el('button','Chartbild speichern'),status=el('p');
 open.type=save.type='button';form.hidden=true;file.type='file';file.accept='image/jpeg,image/png,image/webp';file.setAttribute('aria-label','Screenshot auswählen');
 time.type='text';time.inputMode='numeric';time.value=stamp(section.evidence[0].at);time.setAttribute('aria-label','Videoposition Minuten:Sekunden');
 agree.type='checkbox';label.append(agree,d.createTextNode(' Das Bild gehört zu diesem MCO-Video und Abschnitt; die Videoposition stimmt.'));
 preview.style.cssText='display:block;max-width:100%;max-height:400px;object-fit:contain';preview.hidden=true;save.disabled=true;status.setAttribute('role','status');
 form.append(el('p','Screenshot auswählen, tatsächliche Videoposition prüfen und speichern. Nur das gewählte Bild wird an Bob gesendet.'),file,preview,el('p','Videoposition (Minuten:Sekunden, keine Markt-Uhrzeit)'),time,label,save,status);card.append(open,form);
 let dataUrl='',generation=0;
 open.onclick=()=>{form.hidden=!form.hidden;};
 file.onchange=async()=>{const run=++generation;dataUrl='';save.disabled=true;agree.checked=false;preview.hidden=true;status.textContent='';const chosen=file.files?.[0];if(!chosen)return;
  if(!['image/jpeg','image/png','image/webp'].includes(chosen.type)||chosen.size>20*1024*1024){status.textContent='Bitte JPG, PNG oder WebP bis 20 MB wählen.';return;}
  const url=URL.createObjectURL(chosen),img=el('img');
  try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(new Error('Bild nicht lesbar'));img.src=url;});
   if(run!==generation)return;
   const scale=Math.min(1,800/img.naturalWidth,600/img.naturalHeight),canvas=el('canvas');canvas.width=Math.round(img.naturalWidth*scale);canvas.height=Math.round(img.naturalHeight*scale);
   if(canvas.width<200||canvas.height<100)throw new Error('Bild zu klein. Bitte einen größeren Screenshot wählen.');
   canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);let quality=.85;dataUrl=canvas.toDataURL('image/jpeg',quality);
   while(dataUrl.length>139000&&quality>.3){quality-=.1;dataUrl=canvas.toDataURL('image/jpeg',quality);}
   if(dataUrl.length>139000)throw new Error('Bild zu groß. Bitte auf den Chart zuschneiden.');
   preview.src=dataUrl;preview.hidden=false;save.disabled=false;
  }catch(e){dataUrl='';status.textContent=e.message;}finally{URL.revokeObjectURL(url);}
 };
 save.onclick=async()=>{const match=/^(\d{1,4}):([0-5]\d)$/.exec(time.value.trim());const at=match?Number(match[1])*60+Number(match[2]):NaN;
  if(!dataUrl||!agree.checked||!Number.isFinite(at)||at>86400){status.textContent='Bitte Bild wählen, Videoposition als Minuten:Sekunden eingeben und Zuordnung bestätigen.';return;}
  save.disabled=true;file.disabled=true;
  try{const response=await fetch('/api/research/video-evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({videoId,action:'append-screenshot',assignedByUser:true,frames:[{at,dataUrl,sourceKind:'screenshot',sectionAt:section.evidence[0].at}]})});const result=await response.json();if(!response.ok||result.error)throw new Error(result.error||'Speichern fehlgeschlagen');
   item.enhancements={...item.enhancements,...result};update(item);
  }catch(e){status.textContent=e.message;}finally{save.disabled=false;file.disabled=false;}
 };
}
function draw(host,item){
 host.replaceChildren();host.append(el('h4','MCO: Chartbilder und Erklärung'),el('p','MCO-Aussagen mit der zugehörigen Videopassage. Bobs eigene Berechnungen stehen getrennt im Wertevergleich.'));
 const parts=sections(item),used=new Set();
 for(const [i,s] of parts.entries()){
  const card=el('section');card.style.cssText='margin:18px 0;padding:12px;border:1px solid #cbd5e1;border-radius:12px;background:#fff';card.append(el('h5',(i+1)+'. '+s.label));
  const selected=choose(item,s);if(selected){figure(card,selected,item,s.evidence);used.add(selected.index);}
  else {card.append(el('p','Noch kein passendes Chartbild für diese Passage gespeichert.'));const a=link(item,s.evidence[0].at);if(a){card.append(a);const identity=new URL(a.href).searchParams.get('v');if(/^[A-Za-z0-9_-]{11}$/.test(identity||'')){
   const play=el('button','Originalstelle in Bob ansehen');play.type='button';play.onclick=()=>{const iframe=el('iframe');iframe.title='MCO-Originalstelle '+stamp(s.evidence[0].at);iframe.src='https://www.youtube-nocookie.com/embed/'+identity+'?start='+Math.floor(s.evidence[0].at)+'&autoplay=0&rel=0';iframe.style.cssText='display:block;width:100%;aspect-ratio:16/9;min-height:200px;border:0';iframe.referrerPolicy='strict-origin-when-cross-origin';iframe.allowFullscreen=true;play.replaceWith(iframe);};card.append(play);
  }}}
  screenshotControl(card,item,s);
  card.append(el('strong',s.kind==='summary'?'Zusammenfassung der MCO-Aussage':'MCO-Originalaussage aus den Untertiteln'),el(s.kind==='quote'?'blockquote':'p',s.text));
  if(s.kind==='summary'){const details=el('details');details.append(el('summary','Gesprochene Begründung nachlesen'));for(const e of s.evidence){details.append(el('blockquote',e.text));const a=link(item,e.at);if(a)details.append(a);}card.append(details);}
  card.append(el('small','Eine im Chart eingezeichnete Möglichkeit ist keine bestätigte Vorhersage. Der Marktzeitpunkt wird nicht aus der Videoposition abgeleitet.'));host.append(card);
 }
 if(!parts.length)host.append(el('p','Noch keine zeitlich belegten Aussagen verfügbar. Ohne passende Untertitel ergänzt Bob keine vermeintliche MCO-Begründung.'));
 const others=(item.enhancements?.frames||[]).map((frame,index)=>({frame,index,ocr:item.enhancements?.ocr?.images?.find(i=>i.index===index)})).filter(x=>valid(x.frame)&&!used.has(x.index));
 if(others.length){const extra=el('details');extra.append(el('summary','Weitere Chartbilder · Aussage noch nicht zugeordnet'));for(const entry of others)figure(extra,entry,item);host.append(extra);}
 if(!(item.enhancements?.frames||[]).some(valid))host.append(el('p','Bisher fehlt ein zeitlich zugeordnetes Videobild. Bei jedem Abschnitt kannst du ein Chartbild hinzufügen; alternativ unten eine Videodatei. Titelbilder ersetzen keine Chartbelege.'));
}
function render(host,item){
 const section=el('section');host.append(section);views.set(item,section);draw(section,item);
 let videoId=item.videoId;try{videoId=videoId||new URL(item.url).searchParams.get('v');}catch(_){return;}
 if(!/^[A-Za-z0-9_-]{11}$/.test(videoId||''))return;
 // Read persisted images when reopening, even if the research report is cached.
 fetch('/api/research/video-evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({videoId,action:'read'})})
 .then(async response=>{if(!response.ok)return;const result=await response.json();
  if(!section.isConnected||!Array.isArray(result.frames)||!result.frames.some(f=>f.sourceKind==='screenshot'))return;
  if([...section.querySelectorAll('input[type=file]')].some(input=>input.files?.length))return;
  item.enhancements={...item.enhancements,...result};draw(section,item);
 }).catch(()=>{});
}
function update(item){const host=views.get(item);if(host?.isConnected)draw(host,item);}
root.BobVideoBrief={render,update};
})(typeof window==='undefined'?null:window);
