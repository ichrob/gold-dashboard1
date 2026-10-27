/* MCO source summary with original frames and explicitly schematic explanations. */
(function(root){
'use strict';
const valid=f=>f&&!f.isCover&&Number.isFinite(f.at)&&f.at>=0&&f.at<=86400&&/^data:image\/jpeg;base64,[A-Za-z0-9+/=]{100,140000}$/.test(f.dataUrl||'');
function sections(item){
 const ai=item.enhancements?.summary;
 if(ai?.kind==='ai')return (ai.sections||[]).filter(s=>s.text&&s.evidence?.some(e=>Number.isFinite(e.at)&&e.text)).slice(0,7).map(s=>({...s,sectionIndex:ai.sections.indexOf(s),kind:'summary'}));
 const byId=new Map((item.overview?.evidence||[]).map(e=>[e.id,e]));const seen=new Set(),out=[];
 for(const s of item.overview?.sections||[]){const evidence=(s.evidenceIds||[]).map(id=>byId.get(id)).filter(e=>e?.text&&Number.isFinite(e.at));const key=evidence.map(e=>e.id||e.text).join('|');if(!evidence.length||seen.has(key))continue;seen.add(key);out.push({label:s.label,text:evidence.map(e=>e.text).join(' '),evidence,kind:'quote'});}
 return out.slice(0,7);
}
function choose(item,section){
 const times=section.evidence.map(e=>e.at).filter(Number.isFinite),images=item.enhancements?.ocr?.images||[];
 const frames=item.enhancements?.frames||[],aiFrames=frames.slice(0,5).filter(f=>valid(f)&&!f.userProvided);
 const notes=item.enhancements?.summary?.visualNotes||[];
 return frames.map((frame,index)=>{
  const ocr=images.find(i=>i.index===index),distance=valid(frame)&&times.length?Math.min(...times.map(t=>Math.abs(t-frame.at))):Infinity;
  const note=notes.find(n=>Number.isInteger(n.frameId)&&aiFrames[n.frameId]===frame&&n.frameAt===frame.at&&
   ['chart','slide'].includes(n.kind)&&Number.isInteger(section.sectionIndex)&&n.sectionIds?.includes(section.sectionIndex)&&
   typeof n.description==='string'&&n.description.length>0&&n.description.length<=240&&!/\d/.test(n.description));
  return {frame,index,ocr,distance,note};
 }).filter(x=>valid(x.frame)&&(x.frame.sourceKind==='screenshot'?x.frame.sectionAt===times[0]:x.distance<=15))
 .sort((a,b)=>Number(b.frame.sourceKind==='screenshot')-Number(a.frame.sourceKind==='screenshot')||Number(!!b.note)-Number(!!a.note)||Number(!!b.ocr?.illustrationRecommended)-Number(!!a.ocr?.illustrationRecommended)||a.distance-b.distance)[0]||null;
}
function market(image){const text=(image?.lines||[]).map(l=>l.text).join(' ');return /\b(?:futures?|COMEX)\b|GC1!/i.test(text)?'future':/XAU\s*\/\s*USD/i.test(text)?'xau':'unknown';}
// These pictures explain cited words only. They never enter a price/strategy model.
function illustrationPlan(item,section){
 if(item?.transcriptAnalyzed!==true||item.trustedTranscript!==true)return null;
 const evidence=(section?.evidence||[]).filter(e=>typeof e?.text==='string'&&Number.isFinite(e.at)&&e.at>=0&&e.at<=86400);
 if(!evidence.length||typeof section.text!=='string'||!section.text.trim())return null;
 function concepts(text){
  const found=new Set();
  for(const sentence of text.split(/(?<=[.!?])\s+|[;\n]/u)){
   // Withhold directional drawings when the source negates a proposition.
   if(/\b(?:not|no|never|cannot|can't|doesn't|won't|nicht|kein\w*|ohne|weder)\b/i.test(sentence))continue;
   const patterns={
    up:/\b(?:bullish|upside|rally|rise|rising|aufwärts|anstieg|steigen)\b|(?:move|turn|push|go|trade|break)\b.{0,20}\b(?:higher|above)\b|ausbruch.{0,25}(?:nach oben|über)/i,
    down:/\b(?:bearish|downside|fall|falling|decline|abwärts|fallen|rückgang)\b|(?:move|turn|push|go|trade|break)\b.{0,20}\b(?:lower|below)\b|ausbruch.{0,25}(?:nach unten|unter)/i,
    range:/\b(?:sideways|range|consolidation|seitwärts|konsolidierung|handelsspanne)\b/i,
    pullback:/\b(?:pullback|retracement|correction|rücksetzer|rücklauf|korrektur)\b/i,
    breakout:/\b(?:breakout|ausbruch|durchbruch)\b|break\b.{0,16}\b(?:above|below|out)\b/i,
    support:/\b(?:support|unterstützung)\b/i,
    resistance:/\b(?:resistance|widerstand)\b/i
   };
   for(const [key,pattern] of Object.entries(patterns))if(pattern.test(sentence))found.add(key);
  }
  return found;
 }
 const source=evidence.map(e=>e.text).join(' '),original=concepts(source),summary=concepts(section.text);
 const has=key=>original.has(key)&&summary.has(key);
 let kind='statement',direction=null,title='Aussage im Überblick';
 if(has('up')&&has('down')){kind='scenarios';title='Zwei mögliche Richtungen';}
 else if(has('range')){kind='range';title='Seitwärtsbewegung';}
 else if(has('pullback')){kind='pullback';title='Rücksetzer / Korrektur';}
 else if(has('breakout')&&(has('up')||has('down'))){kind='breakout';direction=has('up')?'up':'down';title='Möglicher Ausbruch '+(direction==='up'?'nach oben':'nach unten');}
 else if(has('up')||has('down')){kind='direction';direction=has('up')?'up':'down';title='Mögliches '+(direction==='up'?'Aufwärts-':'Abwärts-')+'szenario';}
 else if(has('support')||has('resistance')){kind='levels';title='Besprochene Kurszone';}
 const instruments=[];
 if(/\b(?:XAU\s*\/\s*USD|gold[ -]?spot|spot gold)\b/i.test(source))instruments.push('Gold Spot / XAU/USD');
 if(/\b(?:futures?|COMEX|GC1!)\b/i.test(source))instruments.push('Future (Kontrakt laut Text prüfen)');
 if(/\b(?:GDX|gold miners|goldminen)\b/i.test(source))instruments.push('Goldminen / GDX');
 const instrument=instruments.length>1?'Mehrere Instrumente im Abschnitt':instruments[0]||'Instrument nicht eindeutig benannt';
 const levels=[];
 // Keep the exact written amount and unit: no locale conversion or invented axis.
 // Mixed-instrument passages never share one set of price labels.
 if(instruments.length<=1)for(const e of evidence){
  if(/\b(?:not|no|never|cannot|can't|doesn't|won't|nicht|kein\w*|ohne|weder)\b/i.test(e.text))continue;
  const pattern=/\b(support|unterstützung|resistance|widerstand|target|kursziel|ziel)\b[^\d.!?]{0,24}((?:\$\s*\d[\d.,’']*|\d[\d.,’']*\s*(?:USD|EUR|CHF)))(?!\w)/gi;
  for(const m of e.text.matchAll(pattern)){
   const label=/support|unterstützung/i.test(m[1])?'Unterstützung':/resistance|widerstand/i.test(m[1])?'Widerstand':'Genanntes Ziel';
   if(!levels.some(x=>x.label===label&&x.amount===m[2]))levels.push({label,amount:m[2],at:e.at});
   if(levels.length>=3)break;
  }
  if(levels.length>=3)break;
 }
 return {kind,direction,title,instrument,levels,at:evidence[0].at,
  support:has('support'),resistance:has('resistance'),
  conditional:/\b(?:if|unless|provided|wenn|falls|solange|sofern)\b/i.test(source+' '+section.text),
  sourceText:section.text.replace(/\s+/g,' ').trim().slice(0,117)+(section.text.replace(/\s+/g,' ').trim().length>117?'…':'')};
}


// Presentation only: never contributes votes or modifies Bob's market signal.
function researchGuide(item,bob={},now=Date.now()){
 const exact=typeof item.publishedAt==='number'?item.publishedAt*1000:
  typeof item.publishedDate==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(item.publishedDate)?Date.parse(item.publishedDate):NaN;
 const dated=Number.isFinite(exact)&&exact>0&&exact<=now;
 const recent=dated&&now-exact<=86400000;
 const dayOnly=typeof item.publishedDate==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(item.publishedDate);
 const age=item.publicFallback?'Ersatzvideo · neuere Inhalte fehlen':recent?'Aktuelles Video · höchstens 24 Stunden alt':dated?'Älteres Video':dayOnly?'Veröffentlichungstag bekannt · Uhrzeit unbekannt':'Datum unbekannt · Aktualität nicht bestätigt';
 const status=item.transcriptAnalyzed!==true?'Noch nicht ausgewertet':item.trustedTranscript!==true?'Manuelle oder unbestätigte Textübernahme':
  item.enhancements?.summary?.partial===true?'Teilweise ausgewertet · unbelegte Abschnitte verworfen':
  item.enhancements?.summary?.kind==='ai'?'Zusammenfassung mit Untertitelbelegen':'Untertitel ausgewertet · keine KI-Gesamtzusammenfassung';
 const evidence=new Map((item.overview?.evidence||[]).map(e=>[e.id,e]));
 const conditionSections=(item.overview?.sections||[]).filter(s=>s.key==='conditions');
 const seen=new Set(),conditions=[];
 for(const section of conditionSections)for(const id of section.evidenceIds||[]){
  const e=evidence.get(id);
  if(!e||typeof e.text!=='string'||!e.text.trim()||!Number.isFinite(e.at)||e.at<0||e.at>86400||seen.has(e.text))continue;
  seen.add(e.text);conditions.push({text:e.text,at:e.at,trusted:item.trustedTranscript===true});
 }
 const direction=item.trustedTranscript===true&&item.transcriptAnalyzed===true&&['LONG','SHORT'].includes(item.outlook)?item.outlook:'UNKLAR';
 const bobAt=typeof bob.at==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(bob.at)?Date.parse(bob.at):NaN;
 const bobFresh=bob.fresh===true&&Number.isFinite(bobAt)&&now>=bobAt&&now-bobAt<=60000;
 return {age,status,dated,recent,publication:dated?new Date(exact).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' (Zürich)':dayOnly?item.publishedDate+' · Uhrzeit unbekannt':'Datum und Uhrzeit nicht bestätigt',
  conditions:conditions.slice(0,3),direction,bobDirection:bobFresh&&['LONG','SHORT','NEUTRAL'].includes(bob.direction)?bob.direction:'NICHT_AKTUELL',
  horizon:item.horizon||'unbekannt',bobAt:bobFresh?bob.at:null,bobReason:bobFresh?bob.reason||'Einstiegsbedingungen separat prüfen':'Aktuelle Bob-Analyse fehlt',
  comparison:'Keine direkte Signalbestätigung: Videozeit, betrachteter Zeitraum und Voraussetzungen müssen übereinstimmen. Bobs Intraday-Plan gilt für etwa 1–3 Stunden.',
  chartEvidence:item.trustedTranscript===true?'Gesprochene Kursmarken nur mit Originaluntertitel und Videostelle; kein Beweis für einen Chartwert.':'Keine bestätigten Kursmarken aus diesem Transkript.',
  previewNote:'Vorschaubilder und OCR bleiben ungeprüft. Keine Übernahme von Chartzahlen in Stopps, Ziele oder Produktfreigaben.'};
}
function sourceFibMarks(item){
 const permitted=new Set(['r382','r500','r618','r786','e1272','e1618']);
 if(item.trustedTranscript!==true||item.transcriptAnalyzed!==true)return [];
 return (Array.isArray(item.mcoFibonacci)?item.mcoFibonacci:[]).filter(m=>m&&permitted.has(m.key)&&Number.isFinite(m.price)&&m.price>=500&&m.price<=25000&&typeof m.quote==='string'&&m.quote.trim()&&Number.isInteger(m.at)&&m.at>=0&&m.at<=86400).slice(0,12);
}
if(typeof module!=='undefined')module.exports={sections,choose,market,illustrationPlan,researchGuide,sourceFibMarks};
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
 const {frame,ocr,note}=selected,fig=el('figure'),button=el('button'),img=el('img');button.type='button';button.setAttribute('aria-label','Chartbild vergrößern');button.style.cssText='display:block;width:100%;padding:0;border:0;background:#10151e';img.src=frame.dataUrl;img.alt='Videobild zur MCO-Aussage bei '+stamp(frame.at);img.loading='lazy';img.style.cssText='display:block;width:100%;height:auto;max-width:none;object-fit:contain';button.append(img);button.onclick=()=>enlarge(frame,button);
 fig.style.cssText='margin:12px 0';fig.append(button,el('figcaption','Antippen zum Vergrößern · Videoposition '+stamp(frame.at)+(frame.userProvided?' · Bild und Videoposition vom Nutzer zugeordnet':' · angenäherte YouTube-Vorschau')));card.append(fig);
 const matched=root.BobVideoEvidence?.match(ocr||{at:frame.at,lines:[]},evidence);
 card.append(el('small',frame.sourceKind==='screenshot'?'Screenshot diesem Abschnitt manuell zugeordnet; Inhalt und Videoposition nicht automatisch bestätigt.':matched?.matched?'Bild und Untertitel teilen Begriff und Zahl; Zuordnung plausibel, nicht bestätigt.':'Bild aus derselben Videopassage; inhaltliche Zuordnung nicht bestätigt.'));
 if(note){card.append(el('p','Zum Bild · KI-Einordnung: '+note.description));}
 const closest=[...evidence].filter(e=>Number.isFinite(e.at)).sort((a,b)=>Math.abs(a.at-frame.at)-Math.abs(b.at-frame.at))[0];
 if(closest)card.append(el('p','Zugehörige Aussage bei '+stamp(closest.at)+' · Bildabstand '+Math.round(Math.abs(frame.at-closest.at))+' Sekunden.'));
 const kind=market(ocr);
 if(kind==='future')card.append(el('p','Gold-Future im Bild erkannt (ungeprüfte Bildlesung). Ein direkter Vergleich dieser Kursmarken mit Gold Spot wäre nicht passend; Future-Kontrakt und Zeitrahmen müssen übereinstimmen.'));
 else if(kind==='xau')card.append(el('p','XAU/USD im Bild erkannt (ungeprüfte Bildlesung). Spot/CFD, Währung und Zeitebene müssen für einen Vergleich zusätzlich geklärt sein.'));
 const values=ocr?.typed?.values||[];
 if(values.length){const details=el('details');details.append(el('summary','Kursbereiche und Indikatoren aus diesem Bild · ungeprüft'));for(const v of values)details.append(el('p',v.label+(v.period!=null?' '+v.period:'')+(v.ratio!=null?' '+v.ratio+' %':'')+': '+v.value+' '+v.unit+' · '+(v.timeframe||'Zeitebene offen')));card.append(details);}
 const original=link(item,closest?.at??frame.at);if(original){const line=el('p');line.append(original);card.append(line);}
}
function illustration(card,item,section){
 const plan=illustrationPlan(item,section);if(!plan)return;
 const fig=el('figure');fig.dataset.mcoIllustration=plan.kind;
 fig.style.cssText='margin:14px 0;padding:12px;border:1px solid #bfd3e8;border-radius:12px;background:#eff6ff;overflow-wrap:anywhere';
 fig.append(el('strong','Bobs Schaubild · '+plan.title));
 const svg=d.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('viewBox','0 0 480 230');svg.setAttribute('role','img');
 svg.setAttribute('aria-label',plan.title+' · schematische Illustration zur MCO-Aussage, keine Kursdaten');
 svg.style.cssText='display:block;width:100%;max-width:620px;height:auto;margin:8px auto';
 function shape(tag,attrs,text){const n=d.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;svg.append(n);return n;}
 const blue='#2563eb',green='#15803d',red='#b91c1c',ink='#17324d';
 shape('rect',{x:0,y:0,width:480,height:230,rx:14,fill:'#fff'});
 shape('text',{x:24,y:29,fill:ink,'font-size':14,'font-family':'sans-serif'},'SCHEMA · KEINE KURSDATEN');
 const path=(points,color,dashed=false)=>shape('path',{d:points,fill:'none',stroke:color,'stroke-width':4,'stroke-linecap':'round','stroke-linejoin':'round',...(dashed?{'stroke-dasharray':'9 7'}:{})});
 const line=(y,label,color)=>{shape('line',{x1:35,x2:445,y1:y,y2:y,stroke:color,'stroke-width':2,'stroke-dasharray':'5 5'});shape('text',{x:38,y:y-9,fill:color,'font-size':14,'font-family':'sans-serif'},label);};
 if(plan.kind==='range'){
  line(78,plan.resistance?'Widerstand':'Obere Begrenzung',red);line(180,plan.support?'Unterstützung':'Untere Begrenzung',green);
  path('M45 140 L90 100 L140 160 L190 105 L245 155 L300 105 L350 160 L405 120',blue);
 }else if(plan.kind==='scenarios'){
  path('M40 145 L100 125 L150 145 L215 120',blue);
  path('M215 120 L300 85 L400 58',green,true);path('M215 120 L300 160 L400 190',red,true);
  shape('text',{x:305,y:65,fill:green,'font-size':14,'font-family':'sans-serif'},'Aufwärts');
  shape('text',{x:305,y:212,fill:red,'font-size':14,'font-family':'sans-serif'},'Abwärts');
 }else if(plan.kind==='direction'||plan.kind==='breakout'){
  const up=plan.direction==='up';
  if(plan.kind==='breakout')line(125,up?'Besprochene obere Grenze':'Besprochene untere Grenze',ink);
  path(up?'M40 180 L95 150 L145 165 L200 140':'M40 70 L95 100 L145 85 L200 110',blue);
  path(up?'M200 140 L280 110 L345 75 L420 55':'M200 110 L280 140 L345 175 L420 195',up?green:red,true);
  shape('text',{x:235,y:up?205:65,fill:ink,'font-size':14,'font-family':'sans-serif'},'Möglicher Verlauf laut Aussage');
 }else if(plan.kind==='pullback'){
  for(const [x,label] of [[24,'Bewegung'],[174,'Korrektur'],[324,'Verlauf offen']]){
   shape('rect',{x,y:88,width:132,height:70,rx:10,fill:'#eaf2fb',stroke:'#bfd3e8'});
   shape('text',{x:x+66,y:129,fill:ink,'font-size':14,'font-family':'sans-serif','text-anchor':'middle'},label);
  }
  path('M158 123 L170 123 M163 117 L170 123 L163 129',blue);
  path('M308 123 L320 123 M313 117 L320 123 L313 129',blue);
  shape('text',{x:35,y:195,fill:ink,'font-size':14,'font-family':'sans-serif'},'Richtung und Ausmaß nur wie im Text beschrieben');
 }else if(plan.kind==='levels'){
  if(plan.resistance)line(85,'Widerstand',red);
  if(plan.support)line(175,'Unterstützung',green);
  shape('text',{x:65,y:133,fill:ink,'font-size':17,'font-family':'sans-serif'},'Im Text besprochene Kurszone');
 }else{
  shape('rect',{x:28,y:55,width:424,height:145,rx:16,fill:'#eaf2fb',stroke:'#bfd3e8'});
  shape('text',{x:45,y:82,fill:blue,'font-size':18,'font-family':'sans-serif'},'MCO-Aussage');
  const words=plan.sourceText.split(' ');let rows=[''];
  for(const word of words){if((rows.at(-1)+' '+word).trim().length>43&&rows.length<3)rows.push('');rows[rows.length-1]=(rows.at(-1)+' '+word).trim();}
  rows.slice(0,3).forEach((t,i)=>shape('text',{x:45,y:115+i*24,fill:ink,'font-size':15,'font-family':'sans-serif'},t.length>46?t.slice(0,43)+'…':t));
 }
 fig.append(svg,el('figcaption','Illustration zur MCO-Aussage – kein Originalbild aus dem Video. '+plan.instrument+'. Geometrie und Abstände sind schematisch; keine Vorhersage oder Handelsfreigabe.'));
 if(plan.conditional)fig.append(el('p','Wenn-dann-Szenario: Die Bedingungen stehen in der Aussage und den Originalbelegen.'));
 for(const level of plan.levels){const row=el('p',level.label+' laut Transkript: '+level.amount+' · ');const a=link(item,level.at);if(a)row.append(a);fig.append(row);}
 card.append(fig);
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
function profileControl(host,item){
 let videoId=item.videoId;try{videoId=videoId||new URL(item.url).searchParams.get('v');}catch(_){return;}
 if(!/^[A-Za-z0-9_-]{11}$/.test(videoId||''))return;
 const box=el('details'),title=el('summary','Automatische Chartbilder · YouTube-Anmeldung'),a=el('a','YouTube-Anmeldung einrichten'),test=el('button','Anmeldung prüfen und Bildtest starten'),status=el('p');
 a.href='https://www.browserless.io/account/profiles';a.target='_blank';a.rel='noopener noreferrer';a.referrerPolicy='no-referrer';test.type='button';status.setAttribute('role','status');
 box.append(title,el('p','Die Anmeldung erfolgt direkt im Browserless-Fernbrowser. Browserless speichert den Anmeldestatus; Bob verwendet nur das Profil. Kein Google-Passwort in Bob eingeben.'),a,
 el('p','1. Bei Browserless „New Profile“ wählen. 2. „Sign in via remote browser“ wählen, Profilname bob-mco-youtube und Startadresse https://www.youtube.com eingeben. 3. Im Fernbrowser selbst anmelden und „Save profile“ drücken. 4. Hier den Bildtest starten.'),
 el('p','Kostenloser Tarif: Die Browsersitzung ist auf zwei Minuten begrenzt. Bei einer Upgrade-Aufforderung abbrechen; Bob bucht nichts kostenpflichtig. YouTube kann die Anmeldung oder Wiedergabe trotzdem ablehnen. Das Profil muss für denselben API-Schlüssel wie Bob verfügbar sein.'),
 test,status,el('p','Höchstens drei Bildtests in 24 Stunden, je Profilstand und Video nur ein Versuch. Keine automatische Endlosschleife. Das Profil kannst du bei Browserless jederzeit löschen.'));
 host.append(box);
 const call=async action=>{const r=await fetch('/api/research/video-evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({videoId,action})});const x=await r.json();if(!r.ok||x.error)throw new Error(x.error||'Prüfung nicht erreichbar');return x;};
 const show=x=>{status.textContent=x.message+(x.images?' Bilder: '+x.images:'');};
 test.onclick=async()=>{test.disabled=true;status.textContent='Profil wird geprüft …';
  try{let x=await call('browserless-test');show(x);
   for(let n=0;n<30&&x.status==='running'&&box.isConnected;n++){await new Promise(r=>setTimeout(r,4000));if(!box.isConnected)break;x=await call('browserless-status');show(x);}
   if(x.status==='saved'){const r=await fetch('/api/research/video-evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({videoId,action:'read'})});if(r.ok){item.enhancements={...item.enhancements,...await r.json()};update(item);}}
  }catch(e){status.textContent=e.message;}finally{test.disabled=false;}
 };
}
function draw(host,item){
 host.replaceChildren();host.append(el('h4',item.enhancements?.summary?.partial?'MCO: Teilweise ausgewertet · belegte Abschnitte':'MCO: Chartbilder und Erklärung'),el('p','MCO-Aussagen mit der zugehörigen Videopassage. Bobs eigene Berechnungen stehen getrennt im Wertevergleich.'));
 profileControl(host,item);
 const parts=sections(item),used=new Set();
 for(const [i,s] of parts.entries()){
  const card=el('section');card.style.cssText='margin:18px 0;padding:12px;border:1px solid #cbd5e1;border-radius:12px;background:#fff';card.append(el('h5',(i+1)+'. '+s.label));
  const selected=choose(item,s);if(selected){figure(card,selected,item,s.evidence);used.add(selected.index);}
  else {card.append(el('p','Noch kein passendes Originalbild für diese Passage gespeichert.'));const a=link(item,s.evidence[0].at);if(a){card.append(a);const identity=new URL(a.href).searchParams.get('v');if(/^[A-Za-z0-9_-]{11}$/.test(identity||'')){
   const play=el('button','Originalstelle in Bob ansehen');play.type='button';play.onclick=()=>{const iframe=el('iframe');iframe.title='MCO-Originalstelle '+stamp(s.evidence[0].at);iframe.src='https://www.youtube-nocookie.com/embed/'+identity+'?start='+Math.floor(s.evidence[0].at)+'&autoplay=0&rel=0';iframe.style.cssText='display:block;width:100%;aspect-ratio:16/9;min-height:200px;border:0';iframe.referrerPolicy='strict-origin-when-cross-origin';iframe.allowFullscreen=true;play.replaceWith(iframe);};card.append(play);
  }}}
  screenshotControl(card,item,s);
  card.append(el('strong',s.kind==='summary'?'Zusammenfassung der MCO-Aussage':'MCO-Originalaussage aus den Untertiteln'),el(s.kind==='quote'?'blockquote':'p',s.text));
  illustration(card,item,s);
  if(s.kind==='summary'){const details=el('details');details.append(el('summary','Gesprochene Begründung nachlesen'));for(const e of s.evidence){details.append(el('blockquote',e.text));const a=link(item,e.at);if(a)details.append(a);}card.append(details);}
  card.append(el('small','Eine im Chart eingezeichnete Möglichkeit ist keine bestätigte Vorhersage. Der Marktzeitpunkt wird nicht aus der Videoposition abgeleitet.'));host.append(card);
 }
 if(!parts.length)host.append(el('p','Noch keine zeitlich belegten Aussagen verfügbar. Ohne passende Untertitel ergänzt Bob keine vermeintliche MCO-Begründung.'));
 const others=(item.enhancements?.frames||[]).map((frame,index)=>({frame,index,ocr:item.enhancements?.ocr?.images?.find(i=>i.index===index)})).filter(x=>valid(x.frame)&&!used.has(x.index));
 if(others.length){const extra=el('details');extra.append(el('summary','Weitere Chartbilder · Aussage noch nicht zugeordnet'));for(const entry of others)figure(extra,entry,item);host.append(extra);}
 if(!(item.enhancements?.frames||[]).some(valid))host.append(el('p','Bisher fehlt ein zeitlich zugeordnetes Videobild. Bei jedem Abschnitt kannst du ein Chartbild hinzufügen; alternativ unten eine Videodatei. Titelbilder ersetzen keine Chartbelege.'));
}

const guideViews=new Set();
function renderGuide(host,item,bob){
 const g=researchGuide(item,bob),box=el('section');box.className='research-guide';
 box.style.cssText='margin:10px 0;padding:12px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;overflow-wrap:anywhere';
 box.append(el('h4','Für deinen Intraday-Plan'),el('strong',g.age),el('p','Veröffentlicht: '+g.publication),el('p',g.status));
 const table=el('table');table.style.cssText='width:100%;table-layout:fixed;font-size:13px';
 for(const cells of [['Vergleich','MCO im Video','Bob jetzt'],['Richtung',g.direction,g.bobDirection==='NEUTRAL'?'ABWARTEN':g.bobDirection==='NICHT_AKTUELL'?'Nicht aktuell bestätigt':g.bobDirection],['Zeitraum',g.horizon,'Intraday · etwa 1–3 Stunden'],['Zeitbezug',g.publication,g.bobAt?new Date(g.bobAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' (Zürich)':'Unbestätigt']]){
  const row=el('tr');cells.forEach((value,i)=>row.append(el(i===0?'th':'td',value)));table.append(row);
 }
 box.append(table,el('p',g.comparison),el('p','Bob-Voraussetzung: '+g.bobReason),el('h5','Bedingungen aus dem gesprochenen Text'));
 if(!g.conditions.length)box.append(el('p','Keine eindeutige Bedingung mit Originalstelle identifiziert. Das bedeutet nicht, dass die Aussage bedingungslos gilt.'));
 for(const c of g.conditions){const row=el('div');row.append(el('b',c.trusted?'Bedingtes Szenario · keine bestätigte Richtung':'Unbestätigte Übernahme · keine Richtungsstimme'),el('blockquote',c.text));const a=link(item,c.at);if(a)row.append(a);box.append(row);}
 box.append(el('p','Bedingungen wie „erst oberhalb“, „falls Unterstützung hält“ oder „bei Bruch“ müssen zuerst erfüllt sein. Die Originalstelle bleibt maßgeblich.'),el('h5','Belegstatus der Kursmarken'),el('p',g.chartEvidence),el('p',g.previewNote));
 host.append(box);
 guideViews.add({box,item});
}
setInterval(()=>{
 if(d.visibilityState==='hidden')return;
 for(const view of [...guideViews]){
  guideViews.delete(view);if(!view.box.isConnected)continue;
  const holder=el('div');renderGuide(holder,view.item,root.BobResearchContext?.());view.box.replaceWith(holder.firstElementChild);
 }
},10000);
function render(host,item){
 const section=el('section');host.append(section);views.set(item,section);draw(section,item);
 let videoId=item.videoId;try{videoId=videoId||new URL(item.url).searchParams.get('v');}catch(_){return;}
 if(!/^[A-Za-z0-9_-]{11}$/.test(videoId||''))return;
 // Read persisted images when reopening, even if the research report is cached.
 fetch('/api/research/video-evidence',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({videoId,action:'read'})})
 .then(async response=>{if(!response.ok)return;const result=await response.json();
  if(!section.isConnected||!Array.isArray(result.frames)||!result.frames.some(valid))return;
  if([...section.querySelectorAll('input[type=file]')].some(input=>input.files?.length))return;
  item.enhancements={...item.enhancements,...result};draw(section,item);
 }).catch(()=>{});
}
function update(item){const host=views.get(item);if(host?.isConnected)draw(host,item);}
root.BobVideoBrief={render,update,researchGuide,renderGuide,sourceFibMarks};
})(typeof window==='undefined'?null:window);
