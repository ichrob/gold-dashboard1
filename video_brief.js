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
 .filter(x=>x.distance<=15).sort((a,b)=>Number(!!b.ocr?.illustrationRecommended)-Number(!!a.ocr?.illustrationRecommended)||a.distance-b.distance)[0]||null;
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
 fig.style.cssText='margin:12px 0';fig.append(button,el('figcaption','Antippen zum Vergrößern · Videoposition '+stamp(frame.at)+(frame.userProvided?' · Datei vom Nutzer zugeordnet':' · angenäherte YouTube-Vorschau')));card.append(fig);
 const matched=root.BobVideoEvidence?.match(ocr||{at:frame.at,lines:[]},evidence);
 card.append(el('small',matched?.matched?'Bild und Untertitel teilen Begriff und Zahl; Zuordnung plausibel, nicht bestätigt.':'Bild aus derselben Videopassage; inhaltliche Zuordnung nicht bestätigt.'));
 const kind=market(ocr);
 if(kind==='future')card.append(el('p','Gold-Future im Bild erkannt (ungeprüfte Bildlesung). Ein direkter Vergleich dieser Kursmarken mit Gold Spot wäre nicht passend; Future-Kontrakt und Zeitrahmen müssen übereinstimmen.'));
 else if(kind==='xau')card.append(el('p','XAU/USD im Bild erkannt (ungeprüfte Bildlesung). Spot/CFD, Währung und Zeitebene müssen für einen Vergleich zusätzlich geklärt sein.'));
 const values=ocr?.typed?.values||[];
 if(values.length){const details=el('details');details.append(el('summary','Kursbereiche und Indikatoren aus diesem Bild · ungeprüft'));for(const v of values)details.append(el('p',v.label+(v.period!=null?' '+v.period:'')+(v.ratio!=null?' '+v.ratio+' %':'')+': '+v.value+' '+v.unit+' · '+(v.timeframe||'Zeitebene offen')));card.append(details);}
 const original=link(item,frame.at);if(original)card.append(original);
}
function draw(host,item){
 host.replaceChildren();host.append(el('h4','MCO: Chartbilder und Erklärung'),el('p','MCO-Aussagen mit der zugehörigen Videopassage. Bobs eigene Berechnungen stehen getrennt im Wertevergleich.'));
 const parts=sections(item),used=new Set();
 for(const [i,s] of parts.entries()){
  const card=el('section');card.style.cssText='margin:18px 0;padding:12px;border:1px solid #cbd5e1;border-radius:12px;background:#fff';card.append(el('h5',(i+1)+'. '+s.label));
  const selected=choose(item,s);if(selected){figure(card,selected,item,s.evidence);used.add(selected.index);}
  else {card.append(el('p','Noch kein passendes Chartbild für diese Passage gespeichert.'));const a=link(item,s.evidence[0].at);if(a)card.append(a);}
  card.append(el('strong',s.kind==='summary'?'Zusammenfassung der MCO-Aussage':'MCO-Originalaussage aus den Untertiteln'),el(s.kind==='quote'?'blockquote':'p',s.text));
  if(s.kind==='summary'){const details=el('details');details.append(el('summary','Gesprochene Begründung nachlesen'));for(const e of s.evidence){details.append(el('blockquote',e.text));const a=link(item,e.at);if(a)details.append(a);}card.append(details);}
  card.append(el('small','Eine im Chart eingezeichnete Möglichkeit ist keine bestätigte Vorhersage. Der Marktzeitpunkt wird nicht aus der Videoposition abgeleitet.'));host.append(card);
 }
 if(!parts.length)host.append(el('p','Noch keine zeitlich belegten Aussagen verfügbar. Ohne passende Untertitel ergänzt Bob keine vermeintliche MCO-Begründung.'));
 const others=(item.enhancements?.frames||[]).map((frame,index)=>({frame,index,ocr:item.enhancements?.ocr?.images?.find(i=>i.index===index)})).filter(x=>valid(x.frame)&&!used.has(x.index));
 if(others.length){const extra=el('details');extra.append(el('summary','Weitere Chartbilder · Aussage noch nicht zugeordnet'));for(const entry of others)figure(extra,entry,item);host.append(extra);}
 if(!(item.enhancements?.frames||[]).some(valid))host.append(el('p','Bisher fehlt ein zeitlich zugeordnetes Videobild. Unten kannst du eine passende Videodatei hinzufügen. Titelbilder ersetzen keine Chartbelege.'));
}
function render(host,item){const section=el('section');host.append(section);views.set(item,section);draw(section,item);}
function update(item){const host=views.get(item);if(host?.isConnected)draw(host,item);}
root.BobVideoBrief={render,update};
})(typeof window==='undefined'?null:window);
