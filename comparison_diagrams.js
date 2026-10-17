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
const api={series,bounds,segments,proofs};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
if(!root?.document)return;
const doc=root.document;let study=null,received=0,failed=false,host=null,currency='EUR',mode='horizon',status,chart,proofBox,detail,counts;
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
}
function mount(panel){host=panel;const controls=node('div');controls.style.cssText='display:flex;gap:12px;flex-wrap:wrap;margin:12px 0';
 const cc=node('select');for(const v of ['EUR','CHF']){const opt=node('option',v+'-Produkte');opt.value=v;cc.append(opt);}cc.value=currency;cc.addEventListener('change',()=>{currency=cc.value;draw();});const cl=node('label','Produktwährung ');cl.append(cc);controls.append(cl);
 const md=node('select');for(const [v,t]of [['horizon','Nach 60 Minuten'],['exit','Mit Bobs Stopp- und Zielregeln']]){const opt=node('option',t);opt.value=v;md.append(opt);}md.value=mode;md.addEventListener('change',()=>{mode=md.value;draw();});const ml=node('label','Vergleich ');ml.append(md);controls.append(ml);
 const refresh=node('button','Aktualisieren');refresh.type='button';refresh.addEventListener('click',()=>doc.dispatchEvent(new Event('bob-diagrams-refresh')));controls.append(refresh);host.append(controls);
 status=node('p');status.setAttribute('role','status');host.append(status,node('h3','Rendite der damaligen Auswahl und ihrer Alternativen'));
 host.append(node('p','Blau: damals bevorzugtes Produkt. Orange: beste andere Alternative im Rückblick. Jeder Punkt ist ein eigener Vergleich; die Linien sind kein Kontostand und kein Kursverlauf. Fehlende Werte unterbrechen die Linien.'));
 host.append(node('p','Bruttorenditen aus beobachteten Geld-/Briefkursen, keine echten Ausführungen. Beim Bob-Ausstieg: jeweils 100 EUR inklusive Restgeld; CHF-Produkte werden dafür in EUR umgerechnet. Der spätere Gewinner war beim Einstieg nicht bekannt.'));
 counts=node('p');chart=node('div');detail=node('p');detail.style.whiteSpace='pre-line';detail.setAttribute('aria-live','polite');host.append(counts,chart,detail,node('h3','Wird die automatische Optimierung besser?'));
 proofBox=node('div');host.append(proofBox);draw();
}
root.BobDiagrams={mount,update(data){study=data;received=Date.now();failed=false;draw();},unavailable(){failed=true;freshness();}};
setInterval(freshness,30000);
})(typeof window==='undefined'?null:window);
