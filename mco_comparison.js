/* Time-aligned MCO/Bob comparison. Read-only; no trading or learning hooks. */
(function(root){
'use strict';
const channel='UCsl6Z6p7GOkczo8Cv-GH6Dg',keys=['r382','r500','r618','r786','e1272','e1618'];
function compare(item,histories,calculate,now=Date.now()){
 const marks=(item?.mcoFibonacci||[]).filter(m=>keys.includes(m.key)&&Number.isFinite(m.price)&&m.price>0).slice(0,12);
 return marks.map(m=>{
  const c=m.comparisonContext||{};let reason='';
  if(item.channelId!==channel||item.trustedTranscript!==true)reason='Bestätigtes MCO-Transkript fehlt';
  else if(!Number.isFinite(c.analysisAt)||c.analysisAt<=0||c.analysisAt>now)reason='Analysezeit mit Datum und Zeitzone im Video nicht eindeutig belegt';
  else if(c.instrument!=='XAU/USD'||c.currency!=='USD')reason='Gleiche Goldpreisart (XAU/USD Spot) nicht belegt';
  else if(!['1m','5m','15m','30m','1h','4h'].includes(c.timeframe))reason='Zeitebene im Video nicht eindeutig belegt';
  let snapshot=null;
  if(!reason){for(const history of histories){const s=calculate(history?.[c.timeframe]||[],c.analysisAt,c.timeframe);snapshot=s;if(s?.available)break;}
   if(!snapshot?.available)reason=snapshot?.reason||'Historische Bob-Daten fehlen';}
  const bob=!reason?snapshot?.levels?.[m.key]:null;
  if(!reason&&(!Number.isFinite(bob)||bob<=0))reason='Historische Bob-Kursmarke fehlt';
  return {...m,context:c,bob:reason?null:bob,snapshot:reason?null:snapshot,reason,delta:reason?null:bob-m.price,percent:reason?null:100*(bob-m.price)/m.price};
 });
}
if(typeof module!=='undefined'&&module.exports)module.exports={compare};
if(!root?.document)return;
const d=root.document,ns='http://www.w3.org/2000/svg',num=n=>Number(n).toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2}),signed=n=>(n>0?'+':'')+num(n),stamp=t=>new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich'});
const el=(tag,text)=>{const n=d.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
function svgEl(tag,attrs,text){const n=d.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;}
function mount(host){
 host.style.cssText='margin:24px 0;padding-top:12px;border-top:1px solid #cbd5e1';
 host.append(el('h3','Fibonacci-Vergleich · MCO Markets ↔ Bob'));
 host.append(el('p','Gleicher Analysezeitpunkt und gleiche Zeitebene. Blau: MCO-Kursmarke · Orange: Bob-Kursmarke · Grau: letzter damals geschlossener Goldkurs. 0 % Abweichung bedeutet identische Kursmarken.'));
 const status=el('p'),select=el('select'),label=el('label','Video '),refresh=el('button','MCO-Vergleich aktualisieren'),body=el('div');label.append(select);refresh.type='button';status.setAttribute('role','status');host.append(label,refresh,status,body);
 let items=[],histories=[],busy=false,loadedAt=0;
 function draw(){
  body.replaceChildren();const item=items[Number(select.value)||0];if(!item){body.append(el('p','Keine MCO-Videos verfügbar.'));return;}
  const link=el('a',item.title||'MCO-Video');try{const u=new URL(item.url);if(u.protocol==='https:'&&['www.youtube.com','youtube.com'].includes(u.hostname)&&u.pathname==='/watch'){link.href=u.href;link.target='_blank';link.rel='noopener noreferrer';}}catch(_){}body.append(link);
  body.append(el('p',item.publishedAt?'Video veröffentlicht: '+stamp(item.publishedAt*1000)+'. Die Uploadzeit ersetzt nicht die Analysezeit.':'Veröffentlichungszeit nicht bestätigt; Reihenfolge laut vorhandener Kanalliste.'));
  const rows=compare(item,histories,(bars,at,tf)=>root.BobMcoHistoricalFib?.(bars,at,tf)||{available:false,reason:'Bob-Berechnung nicht verfügbar'});
  if(!rows.length)body.append(el('p','Keine eindeutig zugeordneten Fibonacci-Kursmarken im Transkript gefunden.'));
  const valid=rows.filter(r=>!r.reason);
  if(valid.length){
   const values=valid.flatMap(r=>[r.price,r.bob,r.snapshot.goldPrice]),low=Math.min(...values)-5,high=Math.max(...values)+5,x=p=>95+(p-low)/(high-low)*430;
   const svg=svgEl('svg',{viewBox:`0 0 640 ${valid.length*65+40}`,role:'img','aria-label':'MCO und Bob: Goldkursmarken in USD zum gleichen Analysezeitpunkt',style:'width:100%;height:auto;display:block'});
   valid.forEach((r,i)=>{const y=35+i*65;svg.append(svgEl('text',{x:5,y:y+5,'font-size':12},r.ratio||r.key),svgEl('line',{x1:x(r.price),x2:x(r.bob),y1:y,y2:y,stroke:'#64748b','stroke-width':2}),svgEl('circle',{cx:x(r.price),cy:y,r:6,fill:'#2563eb'}),svgEl('circle',{cx:x(r.bob),cy:y,r:6,fill:'#c2410c'}),svgEl('line',{x1:x(r.snapshot.goldPrice),x2:x(r.snapshot.goldPrice),y1:y-12,y2:y+12,stroke:'#64748b','stroke-width':2}),svgEl('text',{x:632,y:y+5,'text-anchor':'end','font-size':13},signed(r.percent)+' %'),svgEl('text',{x:95,y:y+25,'font-size':11},'MCO '+num(r.price)+' · Bob '+num(r.bob)+' USD'));});body.append(svg);
  }
  for(const r of rows){const card=el('div');card.style.cssText='padding:12px;margin:12px 0;background:#f8fafc;border-radius:10px';card.append(el('b',(r.ratio||r.key)+' · MCO '+num(r.price)+' USD'));
   if(r.reason)card.append(el('p','Nicht vergleichbar: '+r.reason+'.'));
   else {card.append(el('p','Bob '+num(r.bob)+' USD · Unterschied '+signed(r.delta)+' USD / '+signed(r.percent)+' %'),el('p','Analysezeit: '+stamp(r.context.analysisAt)+' (Zürich) · '+r.context.timeframe),el('p','Goldkurs: '+num(r.snapshot.goldPrice)+' USD · Kerzenschluss '+stamp(r.snapshot.asOf)+' (Zürich)'),el('small','Bob historisch nachberechnet mit dem heutigen Bob-Algorithmus und ausschließlich damals geschlossenen Kerzen. Quelle: '+r.snapshot.source+'. Kein gespeichertes damaliges Signal.'));}
   const evidence=el('details');evidence.append(el('summary','Beleg aus dem Video'),el('p',String(r.quote||'Kein Textbeleg')),el('p','Videostelle: '+Math.floor((r.at||0)/60)+':'+String(Math.floor((r.at||0)%60)).padStart(2,'0')));if(r.context.timeEvidence)evidence.append(el('p',r.context.timeEvidence));card.append(evidence);body.append(card);
  }
  body.append(el('small','Differenz = Bob − MCO. Prozent = Differenz ÷ MCO × 100. Gleiche Fibonacci-Prozente können auf unterschiedlichen Swing-Punkten beruhen. Nähe belegt weder Richtigkeit noch profitable Signale. Fehlende Daten werden nicht als 0 % dargestellt.'));
 }
 async function read(url,signal){const r=await root.fetch(url,{cache:'no-store',signal});if(!r.ok)throw Error('Abruf fehlgeschlagen');return r.json();}
 async function load(){if(busy)return;busy=true;refresh.disabled=true;status.textContent='MCO-Vergleich wird geladen …';const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),20000);
  try{const report=await read('/api/gold-research',ctl.signal);if(!Array.isArray(report.items))throw Error();items=report.items.filter(x=>x.channelId===channel).slice(0,3);const previous=select.value;select.replaceChildren();items.forEach((item,i)=>{const o=el('option',(i===0?'Neuester gelisteter Eintrag · ':'')+String(item.title||'MCO-Video'));o.value=String(i);select.append(o);});select.value=Number(previous)<items.length?previous:'0';histories=[];
   if(items.some(i=>(i.mcoFibonacci||[]).some(m=>Number.isFinite(m.comparisonContext?.analysisAt)))){const results=await Promise.allSettled([read('/api/live',ctl.signal),read('/api/weekend-archive',ctl.signal)]);for(const r of results)if(r.status==='fulfilled')histories.push(r.value?.history?.bars_by_tf||r.value?.history||{});}
   loadedAt=Date.now();status.textContent=(report.fresh?'':'MCO-Auswertung nicht aktuell · ')+'Geladen: '+stamp(loadedAt)+' (Zürich)';draw();
  }catch(_){status.textContent='MCO-Vergleich derzeit nicht erreichbar.'+(loadedAt?' Angezeigte Daten sind vom '+stamp(loadedAt)+'.':'');}
  finally{clearTimeout(timer);busy=false;refresh.disabled=false;}
 }
 select.addEventListener('change',draw);refresh.addEventListener('click',load);d.addEventListener('bob-diagrams-refresh',load);load();
}
root.BobMcoComparison={mount};
})(typeof window==='undefined'?null:window);
