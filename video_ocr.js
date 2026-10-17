/* Display only: OCR text never becomes a trusted quote, time or trading input. */
(function(root){
'use strict';
if(!root?.document)return;
const d=root.document,el=(t,s)=>{const n=d.createElement(t);if(s!==undefined)n.textContent=s;return n;};
function render(host,item,withControls=true){
 if(withControls&&root.BobVideoEvidence){
  const display=el('div');host.append(display);render(display,item,false);
  root.BobVideoEvidence.controls(host,item,result=>{item.enhancements={...item.enhancements,...result};display.replaceChildren();render(display,item,false);});return;
 }
 const result=item.enhancements?.ocr,frames=item.enhancements?.frames||[],box=el('details');box.append(el('summary','Automatisch gelesene Videobilder · kostenlose OCR'));
 const labels={pending:'Hintergrundprüfung steht aus',error:'Lesung fehlgeschlagen; automatische Wiederholung frühestens nach 24 Stunden',unavailable:'Ergebnis derzeit nicht abrufbar','no-timed-images':'Keine zeitlich zugeordneten Videobilder verfügbar',complete:'Vorhandene Videobilder geprüft'};
 box.append(el('p',labels[result?.status]||'Noch kein gespeichertes OCR-Ergebnis'),el('small','Bildzahlen sind ungeprüfte Lesungen. Eine Videosekunde ist kein Marktzeitpunkt. Zahlen werden nicht automatisch als bestätigte Kurswerte oder Handelssignale übernommen.'));
 for(const image of result?.images||[]){
  const frame=frames[image.index];if(!frame||frame.isCover||typeof frame.dataUrl!=='string'||!/^data:image\/jpeg;base64,[A-Za-z0-9+/=]{100,140000}$/.test(frame.dataUrl))continue;
  const pane=el('details');pane.append(el('summary','Bild ca. '+Math.floor(image.at/60)+':'+String(Math.floor(image.at%60)).padStart(2,'0')+' · '+(image.lines||[]).filter(l=>l.numeric).length+' Textstellen mit Zahlen'));
  const img=el('img');img.src=frame.dataUrl;img.alt='Original-Videovorschau zur OCR-Lesung';img.loading='lazy';img.style.cssText='width:100%;max-width:480px;height:auto';pane.append(img);
  pane.append(el('small',frame.userProvided?'Quelle: vom Nutzer zugeordnete Videodatei · Videoidentität nicht automatisch bestätigt.':'Quelle: öffentliche YouTube-Videovorschau · Videoposition angenähert.'));
  let source;try{source=new URL(item.url);}catch(_){}
  if(source&&source.protocol==='https:'&&['www.youtube.com','youtube.com'].includes(source.hostname)){
   source.searchParams.set('t',String(Math.floor(image.at)));const link=el('a','Originalstelle auf YouTube öffnen');link.href=source.href;link.target='_blank';link.rel='noopener noreferrer';pane.append(link);
  }
  const evidence=root.BobVideoEvidence?.match(image,item.overview?.evidence||[]);
  if(evidence){pane.append(el('p',evidence.matched?'Bild und Untertitel: gemeinsamer Begriff und Zahl erkannt; Zuordnung plausibel, ungeprüft.':'Zeitlich nahe Aussage; inhaltliche Zuordnung unsicher.'),el('blockquote',evidence.text));}
  else pane.append(el('p','Keine passende Untertitelstelle für dieses Bild vorhanden.'));

  if(image.status==='too-small')pane.append(el('p','Videovorschau zu klein für einen sinnvollen Leseversuch.'));
  if(!(image.lines||[]).length&&image.status!=='too-small')pane.append(el('p','Keine ausreichend lesbare Textstelle erkannt.'));
  for(const line of image.lines||[]){
   const row=el('div');row.style.cssText='padding:8px;margin:8px 0;border:1px solid #cbd5e1;border-radius:8px';row.append(el('b',line.text),el('small',' · Bildlesung ungeprüft'));
   if(line.readingStatus)row.append(el('p',line.readingStatus==='conflict'?'⚠ Unterschiedliche Werte in Nachbarbildern: Lesefehler oder tatsächliche Wertänderung; ungeklärt.':line.readingStatus==='repeated'?'Übereinstimmend in '+line.agreementCount+' benachbarten Bildern gelesen; kein unabhängiger Genauigkeitsnachweis.':'Nur einmal gelesen.'));
   const bounds=line.bounds;
   if(Array.isArray(bounds)&&bounds.length===4&&bounds.every(Number.isFinite)&&bounds[2]>0&&bounds[3]>0){
    const ns='http://www.w3.org/2000/svg',svg=d.createElementNS(ns,'svg'),source=d.createElementNS(ns,'image');svg.setAttribute('viewBox',bounds.join(' '));svg.setAttribute('role','img');svg.setAttribute('aria-label','Bildbeleg für '+line.text);svg.style.cssText='display:block;max-width:100%;width:320px;max-height:100px;margin-top:6px';source.setAttribute('href',frame.dataUrl);source.setAttribute('width',String(image.width));source.setAttribute('height',String(image.height));svg.append(source);row.append(svg);
   }
   pane.append(row);
  }
  box.append(pane);
 }
 box.append(el('p','Lokal auf Bobs bestehendem Server, ohne zusätzliche OCR-API-Gebühren. Je Video werden höchstens fünf verfügbare Vorschauen gelesen. Kleine, verdeckte oder unscharfe Zahlen können fehlen oder falsch erkannt werden.'));
 host.append(box);
}
root.BobVideoOCR={render};
})(typeof window==='undefined'?null:window);
