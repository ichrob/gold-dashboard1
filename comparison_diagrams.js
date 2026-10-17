/* Read-only charts of saved prospective evidence. No inferred fills or trading hooks. */
(function(root){
'use strict';
const finite=Number.isFinite,NS='http://www.w3.org/2000/svg';
function series(study,currency,mode){
 const source=mode==='exit'?(study?.lifecycle?.comparisons||[]):(study?.comparisons||[]);
 return source.filter(c=>c.currency===currency).map(c=>{
  const o=mode==='exit'?c:c.outcome,at=mode==='exit'?c.slot:c.at;
  const other=o?.returns?.[o.alternativeIsin]?.grossPct;
  const valid=o?.complete===true&&finite(o.chosenPct)&&finite(other)&&finite(at);
  return {at,chosen:valid?o.chosenPct:null,alternative:valid?other:null,
   chosenIsin:o?.chosenIsin||c.chosen||null,alternativeIsin:valid?o.alternativeIsin:null,
   status:valid?'vollständig':(o?.status==='pending'||!o)?'noch offen':'nicht vollständig',
   missing:o?.missing||c.missing||[],valid};
 }).filter(c=>finite(c.at)).sort((a,b)=>a.at-b.at);
}
function bounds(rows){const values=rows.flatMap(r=>[r.chosen,r.alternative]).filter(finite);let low=Math.min(0,...values),high=Math.max(0,...values);const pad=Math.max((high-low)*.12,.1);return {low:low-pad,high:high+pad};}
function segments(rows,key,x,y){const out=[];let part=[],previous=null;for(const r of rows){if(previous!==null&&r.at-previous>7500000){if(part.length)out.push(part);part=[];}previous=r.at;if(!finite(r[key])){if(part.length)out.push(part);part=[];}else part.push([x(r.at),y(r[key])]);}if(part.length)out.push(part);return out;}
function proofs(study,currency){const s=study?.states?.[currency];if(!s)return [];return Object.entries(s.progress||{}).map(([variant,p])=>({variant,phase:s.phase,active:study.policy?.variants?.[currency]===variant,samples:p.samples,days:p.days,coverage:p.coverage,
 before:p.scenarios?.stress?.mean?.baseline,after:p.scenarios?.stress?.mean?.candidate,delta:p.scenarios?.stress?.improvementPct}));}
// Transform only saved observations. Every chart retains its own units and scope.
function capitalRows(account){
 let peak=account?.control?.initialCapital,unknownPeak=false;
 return (account?.daily||[]).slice().sort((a,b)=>a.day.localeCompare(b.day)).map(d=>{
  const valid=d.valuationKnown===true&&finite(d.capital)&&finite(d.initialCapital)&&d.initialCapital>0;
  if(!valid)unknownPeak=true;
  if(valid)peak=Math.max(finite(peak)?peak:d.initialCapital,d.capital);
  return {at:finite(d.capitalAt)?d.capitalAt:Date.parse(d.day+'T12:00:00Z'),profit:valid?d.capital-d.initialCapital:null,
   percent:valid?(d.capital/d.initialCapital-1)*100:null,
   drawdown:valid&&peak>0?100*(d.capital/peak-1):null,
   observedMax:finite(d.observedMaxDrawdownPct)?-d.observedMaxDrawdownPct:null,unknownPeak};
 });
}
function signalRows(metrics){return ['15','60','240'].map(h=>{const m=metrics?.[h];const n=m?.evaluated;return {label:h+' Minuten',n:n||0,missing:m?.missing||0,neutral:m?.neutral||0,
 hit:n>0&&finite(m.favorable)?100*m.favorable/n:null,mean:n>0&&finite(m.directionalSumPct)?m.directionalSumPct/n:null};});}
function regimeRows(study,currency,mode){
 const groups=new Map(),exits=new Map((study?.lifecycle?.comparisons||[]).map(c=>[c.currency+':'+c.slot,c]));
 for(const c of study?.comparisons||[]){if(c.currency!==currency)continue;
  const key=[c.regime?.trend||'unknown',c.regime?.volatility||'unknown',c.direction||'unknown'].join(' · ');
  if(!groups.has(key))groups.set(key,{label:key,n:0,total:0,sum:0});const g=groups.get(key);g.total++;
  const o=mode==='exit'?exits.get(c.currency+':'+c.slot):c.outcome;
  if(o?.complete&&finite(o.chosenPct)){g.n++;g.sum+=o.chosenPct;}
 }return [...groups.values()].map(g=>({...g,value:g.n?g.sum/g.n:null}));
}
function stopRows(study,currency){return (study?.lifecycle?.comparisons||[]).filter(c=>c.currency===currency).map(c=>{
 const s=c.stopComparison,isin=c.chosenIsin,b=s?.bobReturns?.[isin],f=s?.fixedReturns?.[isin];
 const ok=s?.complete===true&&finite(b?.grossPct)&&finite(f?.grossPct);
 return {at:c.slot,bob:ok?b.grossPct:null,fixed:ok?f.grossPct:null,
 giveback:ok&&finite(b.peakPct)?Math.max(0,b.peakPct)-Math.max(0,b.grossPct):null};
 }).sort((a,b)=>a.at-b.at);}

const api={series,bounds,segments,proofs,capitalRows,signalRows,regimeRows,stopRows};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(!root?.document)return;
const doc=root.document;let audit=null,portfolio=null,portfolioAt=0,portfolioFailed=false,extraBox,accountId='',priceId='';let study=null,received=0,failed=false,host=null,currency='EUR',mode='horizon',status,chart,proofBox,detail,counts;
const pct=v=>finite(v)?v.toFixed(2)+' %':'offen';
const stamp=v=>new Date(v).toLocaleString('de-CH',{timeZone:'Europe/Zurich',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
function node(tag,text){const e=doc.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
function svgNode(tag,attrs,text){const e=doc.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs||{}))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
function freshness(){if(!status)return;status.textContent=!received?(failed?'Vergleichsdaten derzeit nicht verfügbar. Bitte erneut aktualisieren.':'Vergleichsdaten werden geladen …'):(failed||Date.now()-received>420000?'Datenstand veraltet · ':'Daten zuletzt geladen · ')+stamp(received)+' · Quellenzeiten stehen beim jeweiligen Vergleich.';status.style.color=failed||received&&Date.now()-received>420000?'#92400e':'#475569';}
function showDetail(r){detail.textContent=stamp(r.at)+' · '+(mode==='exit'?'Start des virtuellen Trades':'Start des 60-Minuten-Vergleichs')+' · '+r.status+(r.valid?'\nDamals bevorzugt: '+r.chosenIsin+' · '+pct(r.chosen)+'\nBeste Alternative im Rückblick: '+r.alternativeIsin+' · '+pct(r.alternative)+'\nVorsprung: '+(r.alternative-r.chosen).toFixed(2)+' Prozentpunkte':r.missing.length?'\nFehlende Nachweise: '+r.missing.join(', '):'');}
function draw(){
 if(!host)return;freshness();chart.replaceChildren();proofBox.replaceChildren();detail.textContent='Tippe auf einen Punkt oder öffne die Wertetabelle.';
 const rows=series(study,currency,mode),valid=rows.filter(r=>r.valid);
 counts.textContent=valid.length+' vollständige von '+rows.length+' gespeicherten Gruppen · '+(rows.length-valid.length)+' offen oder unvollständig. Jüngste maximal 100 Gruppen über beide Währungen.';
 if(!valid.length){chart.append(node('p','Noch keine vollständigen Vergleichsdaten für diese Auswahl. Neue Beobachtungen entstehen während der Handelszeiten.'));}
 else{
  const W=680,H=300,L=62,R=22,T=20,B=48,{low,high}=bounds(rows);
  const first=rows[0].at,last=rows.at(-1).at;
  const x=t=>L+(last===first ? .5 : (t-first)/(last-first))*(W-L-R),y=v=>T+(high-v)/(high-low)*(H-T-B);
  const svg=svgNode('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Beobachtete Bruttorendite pro Vergleich: damalige Auswahl und beste Alternative. Lücken sind fehlende Werte.',style:'width:100%;height:auto;min-height:200px;display:block;background:#f8fafc;border-radius:12px'});
  for(let i=0;i<=4;i++){const v=low+(high-low)*i/4;svg.append(svgNode('line',{x1:L,x2:W-R,y1:y(v),y2:y(v),stroke:'#dbe3ec'}));svg.append(svgNode('text',{x:L-7,y:y(v)+4,'text-anchor':'end','font-size':12,fill:'#475569'},v.toFixed(1)+' %'));}
  svg.append(svgNode('line',{x1:L,x2:W-R,y1:y(0),y2:y(0),stroke:'#64748b','stroke-dasharray':'4 4'}));
  for(const [key,color]of [['chosen','#1d4ed8'],['alternative','#b45309']]){
   for(const part of segments(rows,key,x,y))svg.append(svgNode('polyline',{points:part.map(p=>p.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':2.5}));
   for(const r of valid){const p=svgNode('circle',{cx:x(r.at),cy:y(r[key]),r:5,fill:color,tabindex:0,role:'button','aria-label':stamp(r.at)+' '+(key==='chosen'?'damals bevorzugt':'Alternative')+' '+pct(r[key]),style:'cursor:pointer'});p.append(svgNode('title',{},stamp(r.at)+' · '+pct(r[key])));p.addEventListener('click',()=>showDetail(r));p.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showDetail(r);}});svg.append(p);}
  }
  svg.append(svgNode('text',{x:L,y:H-18,'font-size':12,fill:'#475569'},stamp(first)));
  if(last!==first)svg.append(svgNode('text',{x:W-R,y:H-18,'text-anchor':'end','font-size':12,fill:'#475569'},stamp(last)));
  chart.append(svg);
 }
 const tableDetails=node('details'),summary=node('summary','Alle Vergleichswerte anzeigen');tableDetails.append(summary);const wrap=node('div');wrap.style.overflowX='auto';const table=node('table');table.style.width='100%';const header=node('tr');for(const t of ['Start (Zürich)','Damals bevorzugt','Beste Alternative','Status'])header.append(node('th',t));const thead=node('thead');thead.append(header);table.append(thead);const body=node('tbody');
 for(const r of rows){const tr=node('tr');for(const t of [stamp(r.at),r.valid?r.chosenIsin+' · '+pct(r.chosen):'offen',r.valid?r.alternativeIsin+' · '+pct(r.alternative):'offen',r.status])tr.append(node('td',t));body.append(tr);}table.append(body);wrap.append(table);tableDetails.append(wrap);chart.append(tableDetails);
 const phases={selection:'Auswahl läuft',validation:'unabhängige Prüfung läuft',monitoring:'laufende Nachkontrolle',cooldown:'Grundrangfolge aktiv',paused:'pausiert'};
 const ps=proofs(study,currency);proofBox.append(node('p','Prüfung mit 0,3 Prozentpunkten angenommenen Zusatzkosten. Gleiche Vergleichsfälle für Grundrangfolge und Kandidat; kein tatsächlicher Nettogewinn.'));
 if(!ps.length)proofBox.append(node('p','Noch kein Prüfstand verfügbar.'));
 for(const p of ps){
  const name=p.variant==='second'?'Zweiten Rang vorziehen':'Dritten Rang vorziehen',card=node('div');card.style.cssText='padding:12px;margin-top:12px;background:#f8fafc;border-radius:12px';card.append(node('h4',name+' · '+(phases[p.phase]||p.phase)));
  card.append(node('p',p.samples+' vollständige Lerngruppen an '+p.days+' Tagen · Abdeckung '+(finite(p.coverage)?(p.coverage*100).toFixed(1)+' %':'offen')));
  if(p.samples>0&&finite(p.before)&&finite(p.after)){
   const W=600,H=120,L=150,R=70,low=Math.min(0,p.before,p.after),high=Math.max(0,p.before,p.after),range=high-low||1,x=v=>L+(v-low)/range*(W-L-R);
   const svg=svgNode('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Mittlere Rendite unter Kostenstress: Grundrangfolge '+pct(p.before)+', Kandidat '+pct(p.after),style:'width:100%;height:auto;display:block'});
   svg.append(svgNode('line',{x1:x(0),x2:x(0),y1:12,y2:105,stroke:'#64748b'}));
   for(const [label,value,color,y]of [['Grundrangfolge',p.before,'#64748b',25],['Kandidat',p.after,'#1d4ed8',75]]){svg.append(svgNode('text',{x:5,y:y+15,'font-size':15},label));svg.append(svgNode('rect',{x:Math.min(x(0),x(value)),y,width:Math.max(1,Math.abs(x(value)-x(0))),height:24,fill:color}));svg.append(svgNode('text',{x:W-5,y:y+16,'text-anchor':'end','font-size':14},pct(value)));}card.append(svg);
   card.append(node('p','Unterschied: '+(finite(p.delta)?p.delta.toFixed(2)+' Prozentpunkte':'offen')+' · '+(p.active?'Diese Variante ist derzeit übernommen.':'Diese Variante ist derzeit nicht übernommen.')));
  }else card.append(node('p','Noch keine vollständigen Lerngruppen. Es wird keine Verbesserung dargestellt.'));
  proofBox.append(card);
 }
 drawExtras();
}
function mount(panel){host=panel;const controls=node('div');controls.style.cssText='display:flex;gap:12px;flex-wrap:wrap;margin:12px 0';
 const cc=node('select');for(const v of ['EUR','CHF']){const opt=node('option',v+'-Produkte');opt.value=v;cc.append(opt);}cc.value=currency;cc.addEventListener('change',()=>{currency=cc.value;draw();});const cl=node('label','Produktwährung ');cl.append(cc);controls.append(cl);
 const md=node('select');for(const [v,t]of [['horizon','Nach 60 Minuten'],['exit','Mit Bobs Stopp- und Zielregeln']]){const opt=node('option',t);opt.value=v;md.append(opt);}md.value=mode;md.addEventListener('change',()=>{mode=md.value;draw();});const ml=node('label','Vergleich ');ml.append(md);controls.append(ml);
 const refresh=node('button','Aktualisieren');refresh.type='button';refresh.addEventListener('click',()=>doc.dispatchEvent(new Event('bob-diagrams-refresh')));controls.append(refresh);host.append(controls);
 status=node('p');status.setAttribute('role','status');host.append(status,node('h3','Titelvergleich · damalige Auswahl und Alternativen'));
 host.append(node('p','Blau: damals bevorzugtes Produkt. Orange: beste andere Alternative im Rückblick. Jeder Punkt ist ein eigener Vergleich; die Linien sind kein Kontostand und kein Kursverlauf. Fehlende Werte unterbrechen die Linien.'));
 host.append(node('p','Bruttorenditen aus beobachteten Geld-/Briefkursen, keine echten Ausführungen. Beim Bob-Ausstieg: jeweils 100 EUR inklusive Restgeld; CHF-Produkte werden dafür in EUR umgerechnet. Der spätere Gewinner war beim Einstieg nicht bekannt.'));
 counts=node('p');chart=node('div');detail=node('p');detail.style.whiteSpace='pre-line';detail.setAttribute('aria-live','polite');host.append(counts,chart,detail,node('h3','Optimierungsvergleich · Grundrangfolge und Kandidat'));
 proofBox=node('div');extraBox=node('div');host.append(proofBox,extraBox);draw();
}
function section(title,note){const box=node('section');box.style.cssText='margin:24px 0;padding-top:12px;border-top:1px solid #cbd5e1';box.append(node('h3',title),node('p',note));extraBox.append(box);return box;}
function choose(box,label,values,current,onchange){const l=node('label',label+' '),select=node('select');for(const [value,text]of values){const option=node('option',text);option.value=value;select.append(option);}select.value=current;select.addEventListener('change',()=>onchange(select.value));l.append(select);box.append(l);}
function table(box,headers,rows){const d=node('details'),wrap=node('div'),t=node('table'),head=node('tr');d.append(node('summary','Messwerte und Stichproben anzeigen'));wrap.style.overflowX='auto';t.style.width='100%';for(const h of headers)head.append(node('th',h));t.append(head);for(const r of rows){const tr=node('tr');for(const v of r)tr.append(node('td',String(v)));t.append(tr);}wrap.append(t);d.append(wrap);box.append(d);}
function lineChart(box,rows,keys,unit,gap=7500000){
 const usable=rows.filter(r=>finite(r.at)),values=usable.flatMap(r=>keys.map(([k])=>r[k])).filter(finite);
 if(!values.length){box.append(node('p','Noch keine auswertbaren Messwerte. Fehlende Nachweise werden nicht als null gewertet.'));return;}
 const low=Math.min(0,...values),high=Math.max(0,...values),pad=Math.max((high-low)*.08,.01),W=680,H=260,L=70,R=22,T=15,B=45;
 const first=usable[0].at,last=usable.at(-1).at,x=t=>L+(first===last ? .5 : (t-first)/(last-first))*(W-L-R),y=v=>T+(high+pad-v)/(high-low+2*pad)*(H-T-B);
 const svg=svgNode('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':keys.map(k=>k[1]).join(', ')+', Einheit '+unit,style:'width:100%;height:auto;display:block;background:#f8fafc;border-radius:12px'});
 for(let i=0;i<5;i++){const v=low+(high-low)*i/4;svg.append(svgNode('line',{x1:L,x2:W-R,y1:y(v),y2:y(v),stroke:'#cbd5e1'}),svgNode('text',{x:L-6,y:y(v)+4,'text-anchor':'end','font-size':12},v.toFixed(2)));}
 for(const [key,label,color] of keys){let part=[],previous=null;const flush=()=>{if(part.length)svg.append(svgNode('polyline',{points:part.join(' '),fill:'none',stroke:color,'stroke-width':2}));part=[];};
  for(const r of usable){if(previous!==null&&r.at-previous>gap)flush();previous=r.at;if(!finite(r[key])){flush();continue;}part.push(x(r.at)+','+y(r[key]));const dot=svgNode('circle',{cx:x(r.at),cy:y(r[key]),r:3,fill:color});dot.append(svgNode('title',{},stamp(r.at)+' · '+label+' '+r[key].toFixed(3)+' '+unit));svg.append(dot);}flush();
 }
 svg.append(svgNode('text',{x:L,y:H-15,'font-size':12},stamp(first)),svgNode('text',{x:W-R,y:H-15,'text-anchor':'end','font-size':12},stamp(last)));const legend=node('p');for(const [,label,color] of keys){const item=node('span','● '+label+'  ');item.style.color=color;legend.append(item);}box.append(legend);box.append(svg,node('p',keys.map(k=>k[1]).join(' / ')+' · '+unit+' · '+usable.length+' gespeicherte Zeitpunkte; Lücken unterbrechen die Linien.'));
 table(box,['Zeit (Zürich)',...keys.map(k=>k[1]+' ('+unit+')')],usable.map(r=>[stamp(r.at),...keys.map(([k])=>finite(r[k])?r[k].toFixed(3):'nicht belegt')]));
}
function bars(box,rows,unit){const valid=rows.filter(r=>finite(r.value));if(!valid.length){box.append(node('p','Noch keine auswertbaren Fälle.'));return;}
 const W=680,L=260,R=80,H=valid.length*48+20,lo=Math.min(0,...valid.map(r=>r.value)),hi=Math.max(0,...valid.map(r=>r.value)),x=v=>L+(v-lo)/(hi-lo||1)*(W-L-R);
 const svg=svgNode('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Vergleich in '+unit,style:'width:100%;height:auto;display:block'});
 svg.append(svgNode('line',{x1:x(0),x2:x(0),y1:5,y2:H,stroke:'#64748b'}));valid.forEach((r,i)=>{const y=10+i*48;svg.append(svgNode('text',{x:0,y:y+18,'font-size':12},r.label),svgNode('rect',{x:Math.min(x(0),x(r.value)),y,width:Math.max(1,Math.abs(x(r.value)-x(0))),height:25,fill:r.value<0?'#b45309':'#1d4ed8'}),svgNode('text',{x:W-3,y:y+18,'text-anchor':'end','font-size':13},r.value.toFixed(2)+' '+unit));});box.append(svg);
}
function drawExtras(){
 if(!extraBox)return;extraBox.replaceChildren();
 const accounts=portfolio?.realOrders===false?portfolio.accounts||[]:[];
 if(!accounts.some(a=>a.profile===accountId))accountId=accounts[0]?.profile||'';
 const account=accounts.find(a=>a.profile===accountId),cap=capitalRows(account);
 const capital=section('Kapitalentwicklung · Simulation','Bis zu 366 tägliche gespeicherte Kapitalstände einschließlich bewertbarer offener Positionen. Bruttomodell ohne vollständige Gebühren, Finanzierung und Slippage. Keine echten Trades.');
 capital.append(node('p',portfolioAt?(portfolioFailed||Date.now()-portfolioAt>420000?'Kontodaten veraltet · ':'Kontodaten geladen · ')+stamp(portfolioAt):portfolioFailed?'Kontodaten nicht verfügbar.':'Kontodaten werden geladen …'));
 choose(capital,'Testkonto',accounts.map(a=>[a.profile,a.title]),accountId,value=>{accountId=value;drawExtras();});
 lineChart(capital,cap,[['profit','Gewinn / Verlust','#1d4ed8']],'EUR',4*86400000);
 lineChart(capital,cap,[['percent','Rendite seit Kontostart','#1d4ed8']],'%',4*86400000);
 const dd=section('Drawdown · Rückgang vom Höchststand','Blau: Rückgang gegenüber dem höchsten gespeicherten Tagesstand. Orange: bis dahin größter vom Hintergrundlauf beobachteter Rückgang. Tagespunkte können zwischenzeitliche Verluste auslassen; Datenlücken können weitere Tiefs verbergen.');
 lineChart(dd,cap,[['drawdown','Rückgang der Tagesstände','#1d4ed8'],['observedMax','Maximal beobachteter Rückgang','#b45309']],'%',4*86400000);
 const price=section('Kursgenauigkeit · Original und Modell','Zeitlich passende Geldkurse derselben ISIN, Währung, Quelle und Modellidentität. Korrekturen werden nur auf späteren, noch nicht zur Anpassung verwendeten Messwerten gezeigt. Eine geprüfte Variante ist nicht automatisch aktiv.');
 const states=(audit?.precisionLearning?.states||[]).filter(s=>s.currency===currency);
 if(!states.some((s,i)=>String(i)===priceId))priceId=states.length?'0':'';
 choose(price,'Messreihe',states.map((s,i)=>[String(i),s.isin+' · '+s.source+' · Reihe '+(i+1)]),priceId,value=>{priceId=value;drawExtras();});
 const state=states[Number(priceId)],history=state?.chartHistory||[],errors=history.map(r=>({...r,rawError:r.original>0?(r.raw/r.original-1)*100:null,correctedError:r.original>0&&finite(r.corrected)?(r.corrected/r.original-1)*100:null}));
 lineChart(price,history,[['original','Originalkurs','#64748b'],['raw','Rohmodell','#1d4ed8'],['corrected','Vorab festgelegte Korrektur','#b45309']],currency,120000);
 lineChart(price,errors,[['rawError','Abweichung Rohmodell','#1d4ed8'],['correctedError','Abweichung Korrektur','#b45309']],'%',120000);
 const paired=errors.filter(r=>finite(r.rawError)&&finite(r.correctedError)),mae=k=>paired.length?paired.reduce((v,r)=>v+Math.abs(r[k]),0)/paired.length:null;
 price.append(node('p',history.length+' von maximal 240 jüngsten Messwerten dieser Identität · '+paired.length+' spätere Korrekturvergleiche · mittlere absolute Abweichung auf denselben Fällen: vorher '+pct(mae('rawError'))+' / nachher '+pct(mae('correctedError'))+' · letzte Messung '+(history.length?stamp(history.at(-1).at):'offen')+' · aktuell '+(state?.usable?'Korrektur aktiv':'Rohmodell aktiv')));
 const stops=section('Stoppvergleich · ursprünglicher Plan und Bob','Neue parallele Simulationen mit je 100 EUR: unveränderter ursprünglicher Stopp und Ziel gegen Bobs Teilgewinn- und Stoppverwaltung. Beide mit denselben KO-, Kurslücken- und Zeitgrenzen. Brutto, keine echten Ausführungen.');
 const sr=stopRows(study,currency);lineChart(stops,sr,[['fixed','Ursprünglicher Plan','#64748b'],['bob','Bob-Ausstieg','#1d4ed8']],'%',7500000);
 lineChart(stops,sr,[['giveback','Vom beobachteten Buchgewinn wieder abgegeben','#b45309']],'Prozentpunkte',7500000);
 stops.append(node('p',sr.filter(r=>finite(r.bob)).length+' vollständig gepaarte von '+sr.length+' Gruppen. Frühere Gruppen ohne parallelen Originalplan bleiben offen. Buchgewinnspitzen sind beobachtete Stichproben, keine garantierten Ausstiegskurse.'));
 const regimes=section('Marktphasen · LONG und SHORT','Beim Einstieg festgehaltene Phase, getrennt nach Richtung und Produktwährung. Durchschnittliche Rendite der damaligen Auswahl; nur vollständige Gruppen. Keine nachträgliche Umklassifizierung.');
 const names={'strong-trend':'Trend',sideways:'Seitwärts',transition:'Übergang',unknown:'unbekannt',high:'hoch',normal:'normal',low:'niedrig'};
 const rr=regimeRows(study,currency,mode).map(g=>({...g,label:g.label.split(' · ').map(k=>names[k]||k).join(' · ')}));bars(regimes,rr,'%');table(regimes,['Phase / Richtung','vollständig / erfasst','mittlere Rendite'],rr.map(r=>[r.label,r.n+' / '+r.total,pct(r.value)]));
 const signals=section('Signalqualität · 15, 60 und 240 Minuten','Spätere Goldbewegung in Signalrichtung. Trefferquote und mittlere Bewegung gemeinsam betrachten. ABWARTEN ist keine Fehlprognose. Keine Produktrendite und keine Berücksichtigung von Handelskosten; überlappende Signale sind keine unabhängigen Versuche.');
 const sig=signalRows(audit?.metrics);signals.append(node('p',(audit?.scope||'Zeitraum noch nicht verfügbar.')+(finite(audit?.signalChartScope?.firstAt)?' · Beobachtungen '+stamp(audit.signalChartScope.firstAt)+' bis '+stamp(audit.signalChartScope.lastAt):'')));
 bars(signals,sig.map(r=>({...r,value:r.hit})),'% Treffer');bars(signals,sig.map(r=>({...r,value:r.mean})),'% Bewegung');
 table(signals,['Horizont','Fälle','offen / fehlend','ABWARTEN','Trefferquote','mittlere Bewegung'],sig.map(r=>[r.label,r.n,r.missing,r.neutral,pct(r.hit),pct(r.mean)]));
}

root.BobDiagrams={mount,update(data,report){study=data;audit=report||null;received=Date.now();failed=false;draw();},portfolios(data){portfolio=data;portfolioAt=Date.now();portfolioFailed=false;drawExtras();},portfoliosUnavailable(){portfolioFailed=true;drawExtras();},unavailable(){failed=true;freshness();}};
setInterval(freshness,30000);
})(typeof window==='undefined'?null:window);
