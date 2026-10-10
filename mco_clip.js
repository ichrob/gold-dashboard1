/* Bob MCO 60-second client-side explainer. No external video, TTS or AI service. */
(function(root){
 'use strict';
 const DURATION=60, EDGES=[0,12,25,39,51,60];
 const BLUE='#60a5fa',ORANGE='#fb923c',GREEN='#4ade80';
 const cap=(value,n=210)=>{const s=String(value??'').replace(/\s+/g,' ').trim();return s.length<=n?s:s.slice(0,n-1).replace(/\s+\S*$/,'')+' …';};
 const atOk=n=>Number.isFinite(n)&&n>=0&&n<=86400;
 const markOk=m=>m&&['r382','r500','r618','r786','e1272','e1618'].includes(m.key)&&typeof m.price==='number'&&Number.isFinite(m.price)&&m.price>=500&&m.price<=25000;
 const num=n=>Number(n).toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2});
 const timestamp=n=>Math.floor(n/60)+':'+String(Math.floor(n%60)).padStart(2,'0');
 function prepare(item,snapshot){
  if(!item||item.transcriptAnalyzed!==true||item.trustedTranscript!==true)return null;
  const summary=item.enhancements?.summary;
  const ai=summary?.kind==='ai'&&Array.isArray(summary.sections)?summary.sections.filter(s=>s&&s.text&&Array.isArray(s.evidence)&&s.evidence.some(e=>atOk(e.at)&&e.text)): [];
  const overview=item.overview;
  const overviewEvidence=Array.isArray(overview?.evidence)?overview.evidence.filter(e=>e&&atOk(e.at)&&typeof e.text==='string'): [];
  const original=(key)=>{const section=(overview?.sections||[]).find(s=>s.key===key);const ids=section?.evidenceIds||[];return overviewEvidence.find(e=>ids.includes(e.id));};
  function pick(pattern,key){
   const found=ai.find(x=>pattern.test(String(x.label)));
   if(found){const ref=found.evidence.find(e=>atOk(e.at)&&typeof e.text==='string');return {text:cap(found.text,200),at:ref?.at??null,method:'Belegte KI-Zusammenfassung'};}
   const ev=original(key);
   return ev?{text:cap(ev.text,200),at:ev.at,method:'Originalsatz aus Untertiteln'}:null;
  }
  const initial=pick(/fazit|kurz|markt|einordnung/i,'overview');
  const bullish=pick(/long|bull|aufwärts/i,'bullish');
  const bearish=pick(/short|bär|abwärts/i,'bearish');
  const condition=pick(/beding|risik|ungültig|horizont/i,'conditions')||pick(/risik/i,'horizon');
  const levels=Array.isArray(item.mcoFibonacci)?item.mcoFibonacci.filter(markOk).slice(0,5):[];
  const good=!!(snapshot&&snapshot.available===true);
  const bars=good&&Array.isArray(snapshot.bars)?snapshot.bars.map(b=>Number(b.close)).filter(v=>Number.isFinite(v)&&v>0).slice(-100):[];
  const bobLevels=good?Object.entries(snapshot.levels||{}).filter(([key,price])=>['r382','r500','r618','r786','e1272','e1618'].includes(key)&&Number.isFinite(Number(price))&&Number(price)>0).map(([key,price])=>({key,price:Number(price)})):[];
  const matched=levels.map(m=>{
   const v=good?Number(snapshot.levels?.[m.key]):NaN;
   const bob=Number.isFinite(v)&&v>0?v:null,diff=bob==null?null:Math.abs(m.price-bob);
   return {key:m.key,ratio:String(m.ratio||m.key),price:m.price,bob,diff,
           near:diff!==null&&diff<=Math.max(5,m.price*.0015),at:atOk(m.at)?m.at:null};
  });
  const levelText=levels.length
    ? levels.slice(0,2).map(l=>String(l.ratio||'Fibonacci')+' bei '+num(l.price)+' USD').join(' · ')
    : 'Keine eindeutig belegte Fibonacci-Kursmarke in den Untertiteln.';
  const fallback='In den bestätigten Untertiteln ist hierzu keine eindeutige Aussage belegt.';
  const source=cap(item.title||'MCO Markets: Goldanalyse',88);
  return {title:source, videoId:String(item.id||''), from:'MCO Markets · geprüfte Untertitel',
   scenes:[
    {type:'intro',title:'Goldmarkt – Überblick',text:initial?.text||fallback,at:initial?.at??null},
    {type:'direction',title:'Long- und Short-Szenario',text:'Belegte Aussagen zu möglichen Marktbewegungen.',at:bullish?.at??bearish?.at??null,
     long:bullish?.text||'Kein eindeutiges Long-Szenario belegt.',short:bearish?.text||'Kein eindeutiges Short-Szenario belegt.'},
    {type:'fib',title:'Kursmarken – MCO und Bob',text:levelText,at:levels.find(l=>atOk(l.at))?.at??null},
    {type:'conditions',title:'Bedingungen und Risiken',text:condition?.text||fallback,at:condition?.at??null},
    {type:'closing',title:'Fazit und Einordnung',text:initial?.text||fallback,at:initial?.at??null}
   ],levels:matched,bobLevels,bars,marketAt:good?snapshot.asOf:null,marketFresh:good?snapshot.fresh===true:false,quote:null,
   disclaimer:'Illustration aus Transkript und Bobs Daten · kein MCO-Originalchart · keine Handelsfreigabe'};
 }
 function mount(parent,item,url,snapshotProvider){
  if(typeof document==='undefined'||!parent||!item)return null;
  const valid=/^https:\/\/(?:www\.)?youtube\.com\/watch\?/.test(String(url));
  const id=new URL(String(url)).searchParams.get('v');
  if(!valid||!/^[A-Za-z0-9_-]{11}$/.test(id||''))return null;
  if(item.trustedTranscript!==true||item.transcriptAnalyzed!==true)return null;
  const mk=(tag,text)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;return e;};
  const section=mk('section'),label=mk('h4','60-Sekunden-Erklärclip · Bob erstellt die Bilder');
  section.style.cssText='margin:12px 0;padding:12px;border:1px solid #d9e2ef;border-radius:12px;';
  const intro=mk('p','Kostenloser animierter Kurzfilm aus belegten MCO-Aussagen und Bobs eigenen Diagrammen. Starte den Clip für Audio und verifizierte Goldpreise.');
  const canvas=mk('canvas');canvas.width=800;canvas.height=450;canvas.setAttribute('aria-label','Animierter 60-Sekunden-Erklärclip mit Untertiteln zu MCO Markets');
  canvas.style.cssText='display:block;width:100%;max-width:800px;aspect-ratio:16/9;border-radius:9px;background:#101a2b';
  const actions=mk('div');actions.style.cssText='display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px';
  const toggle=mk('button','▶ Clip mit Ton abspielen');toggle.type='button';
  const again=mk('button','↻ Neu starten');again.type='button';
  const voice=mk('button','Ton: an');voice.type='button';
  const supportsVoice=typeof window.speechSynthesis!=='undefined'&&typeof window.SpeechSynthesisUtterance==='function';
  if(!supportsVoice){voice.disabled=true;voice.textContent='Ton nicht verfügbar';voice.title='Keine Gerätevorlesestimme verfügbar';}
  const progress=mk('input');progress.type='range';progress.min='0';progress.max=String(DURATION);progress.step='0.1';progress.value='0';
  progress.setAttribute('aria-label','Videoposition in Sekunden verschieben');progress.style.cssText='display:block;width:100%;min-height:44px;margin-top:8px;touch-action:pan-y;accent-color:#2563eb';
  const backwards=mk('button','−10 s'),forwards=mk('button','+10 s'),toFib=mk('button','Kurse / Fibonacci'),fullscreen=mk('button','⛶ Vollbild');
  for(const btn of [backwards,forwards,toFib,fullscreen])btn.type='button';
  const status=mk('p','Bereit · 00:00 / 01:00');status.setAttribute('role','status');status.style.cssText='font-size:.9em;margin:6px 0';
  const evidence=mk('a','Originalvideo öffnen');evidence.href=String(url);evidence.target='_blank';evidence.rel='noopener noreferrer';
  const note=mk('small','Der Clip wird kostenlos auf deinem Gerät gezeichnet. Die Audioausgabe ist eine Gerätevorlesestimme; bitte Medienlautstärke und Android-Sprachausgabe prüfen, falls stumm. Im Bereich 00:25 erscheinen MCO-Marken in Blau und bestätigte Bob-Fibonacci-Werte in Orange. Fehlen die Daten, werden keine Kurszahlen erfunden.');
  note.style.cssText='display:block;margin-top:8px';
  actions.append(toggle,again,backwards,forwards,toFib,fullscreen,voice,evidence);
  section.append(label,intro,canvas,actions,progress,status,note);parent.append(section);
  let prepared=null,elapsed=0,started=0,running=false,ended=false,voiced=supportsVoice,lastScene=-1,handle=0;
  let fullOverlay=false,fullNative=false,priorOverflow='',marketFetching=false,speechIssue=false;
  const uiContainer=section;
  const fullStyle='position:fixed;inset:0;width:100vw;height:100dvh;z-index:2147483000;box-sizing:border-box;overflow:auto;background:#091421;color:#f0f5ff;padding:10px;display:flex;flex-direction:column;gap:4px';
  const defaultStyle=section.style.cssText;
  const canvasStyle=canvas.style.cssText;
  const updateScreen=()=>{const expanded=fullOverlay||document.fullscreenElement===uiContainer;
   if(expanded){section.style.cssText=fullStyle;canvas.style.cssText='display:block;width:100%;max-width:none;max-height:65dvh;height:auto;object-fit:contain;aspect-ratio:16/9;border-radius:8px;background:#101a2b';fullscreen.textContent='⤡ Klein';}
   else{section.style.cssText=defaultStyle;canvas.style.cssText=canvasStyle;fullscreen.textContent='⛶ Vollbild';}
  };
  async function setFull(){
   if(fullOverlay||document.fullscreenElement===uiContainer){
    if(document.fullscreenElement===uiContainer&&document.exitFullscreen)await document.exitFullscreen().catch(()=>{});
    if(fullOverlay){fullOverlay=false;document.body.style.overflow=priorOverflow;}
    updateScreen();return;
   }
   if(uiContainer.requestFullscreen){
    try{await uiContainer.requestFullscreen();fullNative=true;updateScreen();return;}catch(_){}
   }
   priorOverflow=document.body.style.overflow;document.body.style.overflow='hidden';fullOverlay=true;updateScreen();
  }
  fullscreen.addEventListener('click',()=>{setFull();});
  document.addEventListener('fullscreenchange',()=>{if(fullNative&&!document.fullscreenElement){fullNative=false;updateScreen();}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&fullOverlay){fullOverlay=false;document.body.style.overflow=priorOverflow;updateScreen();}});
  voice.textContent=supportsVoice?'Ton: an':'Ton nicht verfügbar';
  const ctx=canvas.getContext('2d');
  if(!ctx){status.textContent='Video-Zeichnung wird von diesem Browser nicht unterstützt.';toggle.disabled=again.disabled=true;return section;}
  const wrap=(text,x,y,maxWidth,maxLines=3,lineHeight=29,color='#ecf2ff',font='22px sans-serif')=>{
   ctx.font=font;ctx.fillStyle=color;let line='',row=0;
   for(const word of String(text).split(/\s+/)){
    const next=line?line+' '+word:word;
    if(ctx.measureText(next).width>maxWidth&&line){
     ctx.fillText(line,x,y+row*lineHeight);row++;line=word;
     if(row>=maxLines)return;
    }else line=next;
   }
   if(row<maxLines)ctx.fillText(line,x,y+row*lineHeight);
  };
  const rect=(x,y,w,h,col)=>{ctx.fillStyle=col;ctx.fillRect(x,y,w,h);};
  const line=(x1,y1,x2,y2,color,w=2)=>{ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.strokeStyle=color;ctx.lineWidth=w;ctx.stroke();};
  const rounded=(x,y,w,h,r,color)=>{ctx.fillStyle=color;ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill();};
  function art(scene,p){
   if(scene.type==='intro'||scene.type==='closing'){
    for(let i=0;i<4;i++){const x=130+i*128,h=58+(i%3)*31;rounded(x,245-h/2,68,h,12,scene.type==='intro'?'#29435d':'#1e4a48');}
    for(let i=0;i<4;i++)line(163+i*128,245-(58+(i%3)*31)/2,163+i*128,245+(58+(i%3)*31)/2,'#e3b95d',2);
    ctx.font='bold 24px sans-serif';ctx.fillStyle='#f5ce78';ctx.fillText(scene.type==='intro'?'MCO MARKETS → BOB':'QUELLE PRÜFEN · RISIKEN BEACHTEN',145,317);
   }
   if(scene.type==='direction'){
    rounded(46,157,340,176,12,'#1e3146');rounded(414,157,340,176,12,'#352a37');
    ctx.font='bold 23px sans-serif';ctx.fillStyle=GREEN;ctx.fillText('LONG-SZENARIO',67,191);
    ctx.fillStyle='#f9a2a0';ctx.fillText('SHORT-SZENARIO',437,191);
    wrap(scene.long,66,224,300,3,28,'#f3f6ff','19px sans-serif');
    wrap(scene.short,435,224,290,3,28,'#f3f6ff','19px sans-serif');
   }
   if(scene.type==='fib'){
    // Use only the values from sourced transcript marks and validated Bob candles.
    // Never imply that Bob's independently computed levels were spoken by MCO.
    const levels=prepared.levels||[],bobList=prepared.bobLevels||[],current=prepared.quote?.price??prepared.bars.at(-1)??null;
    const values=[...levels.map(v=>v.price),...bobList.map(v=>v.price),...prepared.bars];
    if(current!==null)values.push(current);
    const min0=values.length?Math.min(...values):null,max0=values.length?Math.max(...values):null;
    const spread=values.length?Math.max(15,max0-min0):1;
    const min=min0===null?0:min0-spread*.15,max=max0===null?1:max0+spread*.15,Y=v=>313-(v-min)/(max-min)*162;
    rounded(17,132,550,217,10,'#15263c');
    for(let i=0;i<4;i++){const value=min+(max-min)*i/3,y=Y(value);line(80,y,552,y,'#30445c',1);
     if(values.length){ctx.fillStyle='#d9e4f4';ctx.font='14px sans-serif';ctx.fillText(num(value),20,y+5);}
    }
    if(prepared.bars.length>1){
     ctx.beginPath();prepared.bars.forEach((v,i)=>{const x=82+i/(prepared.bars.length-1)*460,y=Y(v);if(!i)ctx.moveTo(x,y);else ctx.lineTo(x,y);});
     ctx.strokeStyle='#c1ccd9';ctx.lineWidth=2.7;ctx.stroke();
    }
    if(current!==null&&Number.isFinite(current)){rounded(583,134,201,42,6,'#22423f');
     ctx.fillStyle='#eafff4';ctx.font='bold 23px sans-serif';ctx.fillText(num(current),590,163);
     ctx.font='13px sans-serif';ctx.fillStyle='#d8f4e8';ctx.fillText(prepared.bars.length?'Bobs 15m · USD/oz':'Spotquelle · USD/oz',589,189);}
    else {ctx.fillStyle='#f4c4a9';ctx.font='16px sans-serif';ctx.fillText('Kein belegter Goldkurs',580,156);}
    const selected=levels.length?levels.slice(0,3).map(m=>({label:m.ratio,price:m.price,kind:'MCO',key:m.key,near:m.near})):
      bobList.slice(0,4).map(m=>({label:({'r382':'38,2 %','r500':'50 %','r618':'61,8 %','r786':'78,6 %','e1272':'127,2 %','e1618':'161,8 %'})[m.key]||m.key,price:m.price,kind:'Bob',key:m.key}));
    const display=selected.length?selected:[],
          bobPartner=levels.length?bobList:[]; // independent values are never MCO evidence.
    for(const [i,m] of display.entries()){
     const y=Y(m.price),color=m.kind==='MCO'?BLUE:ORANGE;
     ctx.setLineDash(m.kind==='MCO'?[7,4]:[3,5]);line(80,y,552,y,color,2.3);ctx.setLineDash([]);
     const v=m.kind+' '+m.label;
     ctx.font='bold 17px sans-serif';ctx.fillStyle=color;ctx.fillText(v,581,225+i*40);
     ctx.fillStyle='#fff';ctx.font='bold 16px sans-serif';ctx.fillText(num(m.price)+' USD',581,245+i*40);
     if(m.near){ctx.fillStyle=GREEN;ctx.fillText('≈',755,245+i*40);}
    }
    if(!display.length){wrap('Keine ausdrücklich genannten MCO-Fibonacci-Werte und derzeit keine bestätigten Bob-Berechnungen.',110,224,630,2,30,'#fff','20px sans-serif');}
    else if(levels.length&&bobPartner.length){
     const bob=bobPartner.find(v=>v.key===display[0].key);
     if(bob){ctx.fillStyle=ORANGE;ctx.font='16px sans-serif';ctx.fillText('Bob '+num(bob.price)+' USD',581,351);}
    }
    if(!levels.length){ctx.fillStyle='#e3bd75';ctx.font='14px sans-serif';ctx.fillText('Keine MCO-Level im Transkript belegt – orange zeigt nur Bobs Berechnung.',21,356);}
    if(prepared.marketAt){ctx.fillStyle='#d4e2ee';ctx.font='12px sans-serif';ctx.fillText((prepared.marketFresh?'Bobs 15m-Daten':'Ältere 15m-Daten'),23,341);}
   }
   if(scene.type==='conditions'){
    rounded(68,182,660,139,14,'#243747');
    line(95,247,152,247,'#f5ce78',5);line(143,237,153,247,'#f5ce78',5);line(143,257,153,247,'#f5ce78',5);
    wrap(scene.text,172,222,522,3,30,'#edf2fc','22px sans-serif');
   }
  }
  function render(seconds){
   const index=Math.min(4,EDGES.findIndex((v,i)=>i<EDGES.length-1&&seconds>=v&&seconds<EDGES[i+1]));
   const current=index<0?4:index,scene=prepared.scenes[current];
   const local=(seconds-EDGES[current])/(EDGES[current+1]-EDGES[current]);
   ctx.clearRect(0,0,800,450);
   const bg=ctx.createLinearGradient(0,0,800,450);bg.addColorStop(0,'#0d1829');bg.addColorStop(1,'#203349');
   rect(0,0,800,450,bg);
   rect(0,0,800*seconds/DURATION,6,'#e3b95d');
   ctx.font='bold 17px sans-serif';ctx.fillStyle='#f3d083';ctx.fillText('BOB  ·  GOLDMARKT IN 60 SEKUNDEN',31,41);
   ctx.font='15px sans-serif';ctx.fillStyle='#b7c8d9';ctx.fillText('MCO Markets · selbst erstellte Erklärgrafiken',31,67);
   ctx.font='bold 31px sans-serif';ctx.fillStyle='#fff';ctx.fillText(scene.title,31,119);
   art(scene,local);
   rect(0,366,800,84,'#0a1320');
   wrap(scene.type==='direction'?'MCO-Szenarien laut geprüften Untertiteln · keine Bob-Prognose':scene.text,30,393,745,2,25,'#f3f5f9','19px sans-serif');
   ctx.font='14px sans-serif';ctx.fillStyle='#b9c6d5';
   ctx.fillText('Kein MCO-Originalchart · kein Handelssignal · '+timestamp(Math.floor(seconds))+' / 1:00',30,438);
   if(scene.at!==null&&scene.at!==undefined&&atOk(scene.at)){
    const target=new URL(String(url));target.searchParams.set('t',String(Math.floor(scene.at)));evidence.href=target.href;
    evidence.textContent='MCO-Originalstelle '+timestamp(scene.at);
   }else{evidence.href=String(url);evidence.textContent='MCO-Originalvideo';}
   if(voiced&&lastScene!==current&&running){lastScene=current;speak(scene);}
   progress.value=String(seconds);status.textContent=(running?'Läuft':'Bereit')+' · '+timestamp(Math.floor(seconds)).padStart(5,'0')+' / 01:00'+(speechIssue?' · Sprachausgabe nicht verfügbar':'');
  }
  function cancelVoice(){if(supportsVoice)window.speechSynthesis.cancel();}
  function speak(scene){
   if(!supportsVoice)return;
   cancelVoice();
   const phrase=scene.type==='direction'?('Long: '+scene.long+'. Short: '+scene.short):
    ('MCO Markets. '+scene.title+'. '+scene.text);
   const utter=new window.SpeechSynthesisUtterance(cap(phrase,195));utter.lang='de-DE';utter.rate=1.18;
   utter.onerror=()=>{speechIssue=true;voice.textContent='Ton nicht verfügbar';status.textContent='Ton auf diesem Gerät nicht gestartet. Bitte Medienlautstärke / Android-Vorlesestimme prüfen.';};
   utter.onstart=()=>{speechIssue=false;voice.textContent='Ton: an';};
   const voices=window.speechSynthesis.getVoices?.()||[];
   const german=voices.find(v=>String(v.lang).toLowerCase().startsWith('de'));
   if(german)utter.voice=german;
   try{window.speechSynthesis.resume();window.speechSynthesis.speak(utter);}catch(_){utter.onerror();}
  }
  function stop(){if(handle)cancelAnimationFrame(handle);handle=0;running=false;cancelVoice();document.removeEventListener('visibilitychange',backgroundPause);}
  function tick(t){
   if(!running)return;
   if(!canvas.isConnected){stop();return;}
   elapsed=Math.min(DURATION,(t-started)/1000);
   render(elapsed);
   if(elapsed>=DURATION){stop();ended=true;toggle.textContent='▶ Erneut abspielen';status.textContent='Fertig · 01:00 / 01:00';return;}
   handle=requestAnimationFrame(tick);
  }
  async function refreshMarket(){
   if(marketFetching||typeof window.fetch!=='function')return;
   marketFetching=true;
   const ctl=typeof AbortController==='function'?new AbortController():null;
   const tm=setTimeout(()=>ctl?.abort(),12000);
   try{
    const response=await window.fetch('/api/live',{cache:'no-store',...(ctl?{signal:ctl.signal}:{})});
    if(!response.ok)throw Error('Bob Marktdaten nicht erreichbar');
    const payload=await response.json(),spot=payload?.spots||{};
    const bars=payload?.history?.bars_by_tf?.['15m'];
    const snap=Array.isArray(bars)&&typeof snapshotProvider==='function'?snapshotProvider(bars):snapshotProvider?.();
    const next=prepare(item,snap);
    if(!next)return;
    const spotPrice=Number(spot.xaus),spotAt=Date.parse(spot.spot_price_as_of);
    if(spot.is_genuine_xauusd_spot===true&&Number.isFinite(spotPrice)&&spotPrice>0&&Number.isFinite(spotAt))
     next.quote={price:spotPrice,asOf:spotAt,source:String(spot.primary||'XAU/USD Spot')};
    prepared=next;
    render(elapsed);
    if(elapsed>=25&&elapsed<39&&!prepared.bobLevels.length&&!prepared.levels.length)
     status.textContent='Keine belegten Fibonacci-Kurswerte verfügbar; Bob erfindet keine Level.';
   }catch(_){
    if(prepared&&!prepared.bars.length&&!prepared.levels.length)
     status.textContent='Marktdaten momentan nicht abrufbar. Fibonacci-Kurswerte nicht verfügbar.';
   }finally{clearTimeout(tm);marketFetching=false;}
  }
  function play(){
   if(!prepared||elapsed===0||ended){
    let snapshot=null;try{snapshot=typeof snapshotProvider==='function'?snapshotProvider():null;}catch(_){}
    prepared=prepare(item,snapshot);
   }
   if(!prepared){status.textContent='Nur mit bestätigter MCO-Untertitelanalyse verfügbar.';return;}
   if(root.BobMcoClip.active&&root.BobMcoClip.active!==stop)root.BobMcoClip.active();
   root.BobMcoClip.active=stop;
   if(ended){elapsed=0;ended=false;lastScene=-1;}
   running=true;started=performance.now()-elapsed*1000;toggle.textContent='Ⅱ Pause';
   document.addEventListener('visibilitychange',backgroundPause);
   if(voiced){lastScene=sceneIndex(elapsed);speak(prepared.scenes[lastScene]);}
   refreshMarket();
   handle=requestAnimationFrame(tick);
  }
  function sceneIndex(seconds){const at=EDGES.findIndex((v,i)=>i<5&&seconds>=v&&seconds<EDGES[i+1]);return at<0?4:at;}
  function seek(seconds){elapsed=Math.max(0,Math.min(DURATION,Number(seconds)||0));ended=elapsed>=DURATION;lastScene=sceneIndex(elapsed);
   if(running){started=performance.now()-elapsed*1000;if(voiced)speak(prepared.scenes[lastScene]);}
   render(elapsed);
   if(ended&&running){stop();toggle.textContent='▶ Erneut abspielen';}
  }
  progress.addEventListener('input',()=>seek(progress.value));
  backwards.addEventListener('click',()=>seek(elapsed-10));
  forwards.addEventListener('click',()=>seek(elapsed+10));
  toFib.addEventListener('click',()=>{seek(25);refreshMarket();});
  toggle.addEventListener('click',()=>{
   if(running){stop();toggle.textContent='▶ Fortsetzen';status.textContent='Pausiert · '+timestamp(Math.floor(elapsed))+' / 01:00';}
   else play();
  });
  again.addEventListener('click',()=>{stop();elapsed=0;ended=false;lastScene=-1;play();});
  voice.addEventListener('click',()=>{
   voiced=!voiced;voice.textContent=voiced?'Ton: an':'Ton: aus';
   if(!voiced)cancelVoice();else if(running&&prepared){lastScene=sceneIndex(elapsed);speak(prepared.scenes[lastScene]);}
  });
  function backgroundPause(){if(document.hidden&&running){stop();toggle.textContent='▶ Fortsetzen';status.textContent='Pausiert (App im Hintergrund)';}}
  prepared=prepare(item,typeof snapshotProvider==='function'?snapshotProvider():null);
  if(prepared){render(0);}
  else {status.textContent='Noch kein bestätigtes Transkript für diesen Clip.';toggle.disabled=true;again.disabled=true;}
  return section;
 }
 root.BobMcoClip={DURATION,prepare,mount,active:null};
 if(typeof module!=='undefined'&&module.exports)module.exports={DURATION,prepare};
})(typeof window!=='undefined'?window:globalThis);
