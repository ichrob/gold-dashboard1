/* Time-aligned MCO/Bob comparison. Read-only; no trading or learning hooks. */
(function(root){
'use strict';
const channel='UCsl6Z6p7GOkczo8Cv-GH6Dg',keys=['r382','r500','r618','r786','e1272','e1618'];
const steps={'1m':60000,'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'4h':14400000};
function estimateTime(c,item,histories,now=Date.now()){
 const fail=reason=>({kind:'unavailable',reason,ranges:[]});
 if(c.timeConflict)return fail('Widersprüchliche Originalzeitpunkte; keine automatische Zuordnung');
 const q=c.currentGoldQuote;
 if(!Number.isFinite(q?.price)||q.price<=0)return fail('Kein eindeutig genannter damaliger aktueller Goldkurs für eine Zeitschätzung');
 let from,to,basis;
 const published=Number.isFinite(item.publishedAt)&&item.publishedAt>0&&item.publishedAt*1000<=now?item.publishedAt*1000:null;
 if(/^\d{4}-\d{2}-\d{2}$/.test(c.analysisDay||'')){
  const day=Date.parse(c.analysisDay+'T00:00:00Z');from=day-14*3600000;to=day+36*3600000;basis='Genanntes Analysedatum; Zeitzone unbekannt';
 }else if(published){from=published-72*3600000;to=published;basis='Annahme: Aufnahme innerhalb 72 Stunden vor Veröffentlichung';}
 else return fail('Datum oder bestätigte Veröffentlichungszeit fehlt zur Eingrenzung der Schätzung');
 to=Math.min(to,now,published??now);if(!Number.isFinite(from)||to<=from)return fail('Kein gültiges Suchzeitfenster');
 let selected=null;
 // Use the finest available original OHLC series, never sampled or future bars.
 for(const [tf,step] of Object.entries(steps)){
  const candidates=histories.map(h=>(h?.[tf]||[]).filter(b=>b?.instrument==='XAU/USD'&&b.isOpen===false&&!b.observedOnly&&Number.isFinite(b.openTime)&&b.openTime>=from&&b.openTime+step<=to&&['open','high','low','close'].every(k=>Number.isFinite(b[k])&&b[k]>0)&&b.low<=Math.min(b.open,b.close)&&b.high>=Math.max(b.open,b.close)).sort((a,b)=>a.openTime-b.openTime));
  const bars=candidates.sort((a,b)=>b.length-a.length)[0];if(bars?.length){selected={tf,step,bars:[...new Map(bars.map(b=>[b.openTime,b])).values()]};break;}
 }
 if(!selected)return fail('Keine passenden historischen Originalkerzen für die Zeitschätzung');
 const {tf,step,bars}=selected,tolerance=Number.isFinite(q.tolerance)&&q.tolerance>0?Math.min(q.tolerance,.5):.5;
 const matches=bars.filter(b=>b.low-tolerance<=q.price&&b.high+tolerance>=q.price),ranges=[];
 for(const b of matches){const last=ranges.at(-1);if(last&&b.openTime===last.to)last.to=b.openTime+step;else ranges.push({from:b.openTime,to:b.openTime+step});}
 const result={kind:'ambiguous',ranges,searchFrom:from,searchTo:to,basis,timeframe:tf,price:q.price,tolerance,coverage:Math.min(1,bars.length*step/(to-from)),reason:''};
 if(!ranges.length)return {...result,kind:'unavailable',reason:'Der genannte Goldkurs wurde im verfügbaren Suchfenster nicht gefunden'};
 if(ranges.length!==1||ranges[0].to-ranges[0].from>1800000)return {...result,reason:'Mehrere oder zu breite mögliche Zeitbereiche; keine eindeutige Zeitschätzung'};
 return {...result,kind:'estimated',at:Math.floor((ranges[0].from+ranges[0].to)/2),reason:'Preisabgleich im verfügbaren Archiv; Zeitpunkt nicht bestätigt'};
}
function compare(item,histories,calculate,now=Date.now()){
 const fib=(item?.mcoFibonacci||[]).filter(m=>keys.includes(m.key)&&Number.isFinite(m.price)&&m.price>0).slice(0,12).map(m=>({...m,unit:'USD'}));
 const other=(item?.mcoValues?.values||[]).filter(m=>m&&typeof m.metric==='string'&&Number.isFinite(m.price)&&['USD','EUR','CHF','Einheit offen','Punkte'].includes(m.unit)).slice(0,200);
 const marks=[...fib,...other];
 return marks.map(m=>{
  const c={...(m.comparisonContext||{})};let reason='',timing=null;
  if(item.channelId!==channel||item.trustedTranscript!==true)reason='Bestätigtes MCO-Transkript fehlt';
  else if(c.instrument!=='XAU/USD'||c.currency!=='USD')reason='Gleiche Goldpreisart (XAU/USD Spot) nicht belegt';
  else if(m.unit!=='USD'&&m.unit!=='Punkte')reason='Währung der Kursmarke passt nicht zum USD-Goldvergleich';
  else if(!['1m','5m','15m','30m','1h','4h'].includes(c.timeframe))reason='Zeitebene im Video nicht eindeutig belegt';
  if(!reason){
   if(Number.isFinite(c.analysisAt)&&c.analysisAt>0&&c.analysisAt<=now)timing={kind:'confirmed',at:c.analysisAt};
   else if(c.analysisAt!=null)reason='Originalzeitpunkt ungültig; keine Ersetzung durch einen Schätzwert';
   else {timing=estimateTime(c,item,histories,now);if(timing.kind==='estimated')c.analysisAt=timing.at;else reason=timing.reason;}
  }
  let snapshot=null;
  if(!reason){for(const history of histories){const s=calculate(history?.[c.timeframe]||[],c.analysisAt,c.timeframe,m);snapshot=s;if(s?.available)break;}
   if(!snapshot?.available)reason=snapshot?.reason||'Historische Bob-Daten fehlen';}
  const bob=!reason?(m.metric?snapshot?.value:snapshot?.levels?.[m.key]):null;
  const relative=!m.metric||['goldPrice','ema','sma','boll','support','resistance','target','stop','entry','dayHigh','dayLow','vwap'].includes(m.metric);
  if(!reason&&(!Number.isFinite(bob)||relative&&bob<=0))reason='Historische Bob-Kursmarke fehlt';
  return {...m,context:c,timing,bob:reason?null:bob,snapshot:reason?null:snapshot,reason,delta:reason?null:bob-m.price,percent:reason||!relative||m.price===0?null:100*(bob-m.price)/Math.abs(m.price)};
 });
}
if(typeof module!=='undefined'&&module.exports)module.exports={compare,estimateTime};
if(!root?.document)return;
const d=root.document,ns='http://www.w3.org/2000/svg',num=n=>Number(n).toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2}),signed=n=>(n>0?'+':'')+num(n),stamp=t=>new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich'});
const el=(tag,text)=>{const n=d.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
function svgEl(tag,attrs,text){const n=d.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;}
function metricChart(card,r){
 const lo=Math.min(r.price,r.bob),hi=Math.max(r.price,r.bob),pad=Math.max((hi-lo)*.2,Math.abs(hi)*.001,.01),x=v=>35+(v-lo+pad)/(hi-lo+2*pad)*430;
 const svg=svgEl('svg',{viewBox:'0 0 500 65',role:'img','aria-label':r.label+': MCO '+num(r.price)+', Bob '+num(r.bob)+' '+r.unit,style:'width:100%;height:auto;display:block'});
 svg.append(svgEl('line',{x1:x(r.price),x2:x(r.bob),y1:20,y2:20,stroke:'#64748b','stroke-width':2,'stroke-dasharray':r.timing?.kind==='estimated'?'4 3':'none'}),svgEl('circle',{cx:x(r.price),cy:20,r:6,fill:'#2563eb'}),svgEl('circle',{cx:x(r.bob),cy:20,r:6,fill:'#c2410c'}),svgEl('text',{x:8,y:55,'font-size':12},'MCO '+num(r.price)+' · Bob '+num(r.bob)+' '+r.unit));card.append(svg);
}
function mount(host){
 host.style.cssText='margin:24px 0;padding-top:12px;border-top:1px solid #cbd5e1';
 host.append(el('h3','Wertevergleich · MCO Markets ↔ Bob'));
 host.append(el('p','Originalzeitpunkt bevorzugt; sonst deutlich markierte Zeitschätzung. Gleiche Zeitebene. Blau: MCO-Kursmarke · Orange: Bob-Kursmarke · Grau: letzter damals geschlossener Goldkurs. 0 % Abweichung bedeutet identische Kursmarken.'));
 const media=el('div'),progress=el('p');
 const status=el('p'),select=el('select'),label=el('label','Video '),refresh=el('button','MCO-Vergleich aktualisieren'),body=el('div');label.append(select);refresh.type='button';status.setAttribute('role','status');host.append(label,refresh,status,progress,media,body);
 let items=[],histories=[],busy=false,loadedAt=0,mediaId=null,failures=0,nextAttempt=0;
 function draw(updateMedia=false){
  const opened=new Set([...body.querySelectorAll('details[data-evidence-key][open]')].map(n=>n.dataset.evidenceKey));
  body.replaceChildren();const item=items[Number(select.value)||0];if(!item){body.append(el('p','Keine MCO-Videos verfügbar.'));return;}
  const link=el('a',item.title||'MCO-Video');try{const u=new URL(item.url);if(u.protocol==='https:'&&['www.youtube.com','youtube.com'].includes(u.hostname)&&u.pathname==='/watch'){link.href=u.href;link.target='_blank';link.rel='noopener noreferrer';}}catch(_){}body.append(link);
  body.append(el('p',item.publishedAt?'Video veröffentlicht: '+stamp(item.publishedAt*1000)+'. Die Uploadzeit ersetzt nicht die Analysezeit.':'Veröffentlichungszeit nicht bestätigt; Reihenfolge laut vorhandener Kanalliste.'));
  const identity=item.videoId||item.url;
  if(identity!==mediaId||(updateMedia&&!media.querySelector('input[type=file]')?.files?.length)){media.replaceChildren();root.BobVideoOCR?.render(media,item);mediaId=identity;}
  const rows=compare(item,histories,(bars,at,tf,m)=>(m.metric?root.BobMcoHistoricalMetric?.(bars,at,tf,m):root.BobMcoHistoricalFib?.(bars,at,tf))||{available:false,reason:'Bob-Berechnung nicht verfügbar'});
  progress.textContent='Vergleiche: '+rows.filter(r=>!r.reason).length+' abgeschlossen · '+rows.filter(r=>r.reason).length+' offen. Automatische Nachprüfung alle 30 Sekunden, solange diese Ansicht sichtbar ist. Beim erneuten Öffnen werden verfügbare historische Daten erneut geprüft.';
  if(!rows.length)body.append(el('p','Keine eindeutig zugeordneten Zahlenwerte im Transkript gefunden.'));
  const valid=rows.filter(r=>!r.reason&&!r.metric); // Fibonacci chart retains a single price scale.
  if(valid.length){
   const values=valid.flatMap(r=>[r.price,r.bob,r.snapshot.goldPrice]),low=Math.min(...values)-5,high=Math.max(...values)+5,x=p=>95+(p-low)/(high-low)*430;
   const svg=svgEl('svg',{viewBox:`0 0 640 ${valid.length*65+40}`,role:'img','aria-label':'MCO und Bob: Goldkursmarken in USD zum gleichen Analysezeitpunkt',style:'width:100%;height:auto;display:block'});
   valid.forEach((r,i)=>{const y=35+i*65;svg.append(svgEl('text',{x:5,y:y+5,'font-size':12},r.ratio||r.key),svgEl('line',{x1:x(r.price),x2:x(r.bob),y1:y,y2:y,stroke:'#64748b','stroke-width':2,'stroke-dasharray':r.timing?.kind==='estimated'?'4 3':'none'}),svgEl('circle',{cx:x(r.price),cy:y,r:6,fill:'#2563eb'}),svgEl('circle',{cx:x(r.bob),cy:y,r:6,fill:'#c2410c'}),svgEl('line',{x1:x(r.snapshot.goldPrice),x2:x(r.snapshot.goldPrice),y1:y-12,y2:y+12,stroke:'#64748b','stroke-width':2}),svgEl('text',{x:632,y:y+5,'text-anchor':'end','font-size':13},(r.timing?.kind==='estimated'?'≈ ':'')+signed(r.percent)+' %'),svgEl('text',{x:95,y:y+25,'font-size':11},'MCO '+num(r.price)+' · Bob '+num(r.bob)+' USD'));});body.append(svg);
  }
  for(const r of rows){const card=el('div');card.style.cssText='padding:12px;margin:12px 0;background:#f8fafc;border-radius:10px';card.append(el('b',(r.label||r.ratio||r.key)+' · MCO '+num(r.price)+' '+r.unit));
   if(r.timing?.kind==='confirmed')card.append(el('b','✓ Originalzeitpunkt im Transkript belegt: '+stamp(r.timing.at)+' (Zürich)'));
   else if(r.timing){const t=r.timing;card.append(el('b',t.kind==='estimated'?'≈ Zeitpunkt geschätzt: '+stamp(t.at)+' (Zürich)':'Zeitschätzung: '+(t.kind==='ambiguous'?'mehrdeutig':'nicht möglich')));
    if(t.ranges?.length)card.append(el('p','Mögliche Zeitbereiche (Zürich): '+t.ranges.slice(0,8).map(x=>stamp(x.from)+' bis '+stamp(x.to)).join(' · ')+(t.ranges.length>8?' · weitere Treffer: '+(t.ranges.length-8):'')));
    if(t.basis)card.append(el('small',t.basis+'. Suchfenster '+stamp(t.searchFrom)+' bis '+stamp(t.searchTo)+'. Archivabdeckung '+num(t.coverage*100)+' %. Preisabgleich mit '+num(t.price)+' USD; keine Zeitbestätigung.'));
   }
   if(r.reason)card.append(el('p','Nicht vergleichbar: '+r.reason+'.'));
   else {card.append(el('p',(r.timing?.kind==='estimated'?'Schätzvergleich · Bob ':'Bob ')+num(r.bob)+' '+r.unit+' · Unterschied '+signed(r.delta)+' '+r.unit+(Number.isFinite(r.percent)?' / '+signed(r.percent)+' %':' · kein Prozentvergleich')),el('p','Analysezeit: '+stamp(r.context.analysisAt)+' (Zürich) · '+r.context.timeframe),el('p','Goldkurs: '+num(r.snapshot.goldPrice)+' USD · Kerzenschluss '+stamp(r.snapshot.asOf)+' (Zürich)'),el('small','Bob historisch nachberechnet mit dem heutigen Bob-Algorithmus und ausschließlich damals geschlossenen Kerzen. Quelle: '+r.snapshot.source+'. Kein gespeichertes damaliges Signal.'));}
   if(!r.reason&&r.metric){card.append(el('p',r.snapshot.method||''));metricChart(card,r);}
   const evidence=el('details');evidence.dataset.evidenceKey=String(r.metric||r.key)+'|'+r.at+'|'+r.price;evidence.open=opened.has(evidence.dataset.evidenceKey);evidence.append(el('summary','Beleg aus dem Video'),el('p',String(r.quote||'Kein Textbeleg')),el('p','Videostelle: '+Math.floor((r.at||0)/60)+':'+String(Math.floor((r.at||0)%60)).padStart(2,'0')));if(r.context.currentGoldQuote?.evidence)evidence.append(el('p','Aktueller Goldkurs laut Video: '+r.context.currentGoldQuote.evidence));if(r.context.timeEvidence)evidence.append(el('p',r.context.timeEvidence));card.append(evidence);body.append(card);
  }
  const statements=item.mcoValues?.numericStatements||[];const extra=el('details');extra.append(el('summary','Weitere Zahlen und Originalaussagen · '+statements.length+' von '+(item.mcoValues?.totalNumericStatements||0)));for(const e of statements)extra.append(el('p',Math.floor(e.at/60)+':'+String(Math.floor(e.at%60)).padStart(2,'0')+' · '+e.text));body.append(extra,el('p',item.mcoValues?.scope||'Nur aus Untertiteln erkannte Werte. Rein eingeblendete Zahlen werden nicht automatisch gelesen.'));if(item.mcoValues?.totalValues>200)body.append(el('p','Anzeige auf 200 erkannte Zusatzwerte begrenzt. Weitere Aussagen stehen im Originalvideo.'));
  body.append(el('small','Differenz = Bob − MCO. Prozent = Differenz ÷ MCO × 100. Gleiche Fibonacci-Prozente können auf unterschiedlichen Swing-Punkten beruhen. Zeitschätzungen beziehen sich nur auf das verfügbare Archiv und sind keine gesicherten historischen Zuordnungen. Nähe belegt weder Richtigkeit noch profitable Signale. Fehlende Daten werden nicht als 0 % dargestellt.'));
 }
 async function read(url,signal){const r=await root.fetch(url,{cache:'no-store',signal});if(!r.ok)throw Error('Abruf fehlgeschlagen');return r.json();}
 async function load(automatic=false){if(busy)return;busy=true;refresh.disabled=true;status.textContent='MCO-Vergleich wird geladen …';const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),20000);
  try{const report=await read('/api/gold-research',ctl.signal);if(!Array.isArray(report.items))throw Error();const previous=items[Number(select.value)||0]?.videoId||items[Number(select.value)||0]?.url;items=report.items.filter(x=>x.channelId===channel).slice(0,3);select.replaceChildren();items.forEach((item,i)=>{const o=el('option',(i===0?'Neuester gelisteter Eintrag · ':'')+String(item.title||'MCO-Video'));o.value=String(i);select.append(o);});select.value=String(Math.max(0,items.findIndex(i=>(i.videoId||i.url)===previous)));histories=[];
   if(items.some(i=>[...(i.mcoFibonacci||[]),...(i.mcoValues?.values||[])].some(m=>Number.isFinite(m.comparisonContext?.analysisAt)||Number.isFinite(m.comparisonContext?.currentGoldQuote?.price)))){const results=await Promise.allSettled([read('/api/live',ctl.signal),read('/api/weekend-archive',ctl.signal)]);for(const r of results)if(r.status==='fulfilled')histories.push(r.value?.history?.bars_by_tf||r.value?.history||{});}
   loadedAt=Date.now();failures=0;nextAttempt=loadedAt+30000;status.textContent=(report.fresh?'':'MCO-Auswertung nicht aktuell · ')+'Geladen: '+stamp(loadedAt)+' (Zürich)';draw(!automatic);
  }catch(_){failures++;nextAttempt=Date.now()+Math.min(300000,30000*2**failures);status.textContent='MCO-Vergleich derzeit nicht erreichbar.'+(loadedAt?' Angezeigte Daten sind vom '+stamp(loadedAt)+'.':'');}
  finally{clearTimeout(timer);busy=false;refresh.disabled=false;}
 }
 const manual=()=>load(false),visible=()=>{if(host.isConnected&&d.visibilityState!=='hidden'&&host.getClientRects().length&&Date.now()>=nextAttempt)load(true);};
 select.addEventListener('change',()=>draw(true));refresh.addEventListener('click',manual);d.addEventListener('bob-diagrams-refresh',manual);d.addEventListener('visibilitychange',visible);
 const interval=setInterval(()=>{if(!host.isConnected){clearInterval(interval);d.removeEventListener('bob-diagrams-refresh',manual);d.removeEventListener('visibilitychange',visible);return;}visible();},30000);load();
}
root.BobMcoComparison={mount};
})(typeof window==='undefined'?null:window);
