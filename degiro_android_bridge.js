/* Bob Android screenshot OCR handoff – device-local, read-only, never eligible for trading. */
(function(root){
'use strict';
const HEADER='BOB OCR-ENTWURF – NICHT VERIFIZIERT';
const FIELDS=Object.freeze({
  'Geld':'bid', 'Brief':'ask', 'Hebel':'leverage',
  'KO-Schwelle':'ko', 'Handelsplatz':'venue', 'Zuletzt':'last', 'Anzeigezeit':'displayedTime'
});
function validIsin(value){
 const s=String(value||'').trim().toUpperCase();
 if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(s))return false;
 const digits=s.replace(/[A-Z]/g,c=>String(c.charCodeAt(0)-55));
 let sum=0;
 [...digits].reverse().forEach((c,i)=>{
  let n=Number(c)*(i%2?2:1);sum+=Math.floor(n/10)+(n%10);
 });
 return sum%10===0;
}
function readDraft(value){
 if(typeof value!=='string'||value.length>8000)throw Error('OCR-Entwurf fehlt oder ist zu groß (maximal 8.000 Zeichen).');
 const appRead=value.startsWith('BOB APP-LESEENTWURF – NICHT VERIFIZIERT\n');
 if(appRead)return readAppDraft(value);
 const lines=value.replace(/\r/g,'').split('\n').map(x=>x.trim()).filter(Boolean);
 if(lines.length<3||lines.length>30||lines[0]!==HEADER)throw Error('Kein gültiger Bob-Android-OCR-Entwurf.');
 const id=lines.filter(s=>s.startsWith('ISIN:'));
 if(id.length!==1)throw Error('Der OCR-Entwurf braucht genau eine ISIN-Zeile.');
 const isins=id[0].slice(5).split(',').map(x=>x.trim()).filter(Boolean);
 if(isins.length!==1||!validIsin(isins[0]))throw Error('Nur ein einzelnes Produkt mit gültiger ISIN wird übernommen.');
 const out={isin:isins[0],fields:{},verified:false,tradeApproved:false,sourceTime:null};
 for(const line of lines){
  if(line===HEADER||line===id[0])continue;
  if(line.startsWith('Bildzeit/Originalquelle')||line.startsWith('Kein automatischer Handelsnachweis'))continue;
  const group=line.match(/^Bildserie \(OCR ungeprüft\): ([1-4]) Bilder, ([1-4]) mit gültiger ISIN$/);
  if(group){
   if(out.series)throw Error('Doppelte Bildserien-Angabe.');
   const imageCount=Number(group[1]),anchorCount=Number(group[2]);
   if(anchorCount>imageCount)throw Error('Ungültige Bildserien-Zuordnung.');
   out.series={imageCount,anchorCount,provisional:anchorCount<imageCount};
   continue;
  }
  const m=line.match(/^(Geld|Brief|Hebel|KO-Schwelle|Handelsplatz|Zuletzt|Anzeigezeit) \(OCR ungeprüft\): (.{1,55})$/);
  if(!m)throw Error('Unbekanntes oder unzulässiges OCR-Feld; keine Übernahme.');
  const key=FIELDS[m[1]];
  if(Object.prototype.hasOwnProperty.call(out.fields,key))throw Error('Doppelte OCR-Angabe für '+m[1]+'.');
  const val=m[2].trim();
  if(key==='venue'){
   if(!/^[\p{L}0-9 ._\/-]{2,48}$/u.test(val))throw Error('Ungültiges OCR-Handelsplatzformat.');
   out.fields[key]=val;
  }else if(key==='displayedTime'){
   if(!/^\d{2}\/\d{2}\/20\d{2} \d{2}:\d{2}$/.test(val))throw Error('Ungültiges Screenshot-Zeitformat.');
   // Visible screenshot label only; NEVER a validated bid/ask source timestamp.
   out.fields[key]=val;
  }else{
   if(!/^[0-9][0-9., ]{0,18}$/.test(val))throw Error('Ungültiges OCR-Zahlenformat.');
   // Preserve exact screenshot spelling: no currency, FX, or execution quote inferred.
   out.fields[key]=val;
  }
 }
 return out;
}
// Separate provenance: receipt time is never promoted to a quote timestamp.
function readAppDraft(value){
 const lines=value.replace(/\r/g,'').split('\n').map(x=>x.trim()).filter(Boolean);
 const unique=prefix=>{const found=lines.filter(x=>x.startsWith(prefix));if(found.length!==1)throw Error('App-Leseentwurf: Pflichtangabe fehlt oder doppelt.');return found[0].slice(prefix.length);};
 if(unique('Quelle: ')!=='DEGIRO-App')throw Error('Unbekannte App-Quelle.');
 const observedAt=unique('Erfasst: ');
 if(!/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$/.test(observedAt)||!Number.isFinite(Date.parse(observedAt)))throw Error('Ungültige Erfassungszeit.');
 const currency=unique('Währung (Anzeige ungeprüft): ');
 if(!['EUR','CHF'].includes(currency))throw Error('Unklare Produktwährung.');
 const warning=unique('Hinweis (Anzeige ungeprüft): ');
 if(!['Handel eingeschränkt','Kurse verzögert','Keine Aussage zur Handelbarkeit'].includes(warning))throw Error('Unbekannter App-Hinweis.');
 const stripped=lines.filter(x=>!x.startsWith('Quelle: ')&&!x.startsWith('Erfasst: ')&&!x.startsWith('Währung (')&&!x.startsWith('Hinweis ('));
 stripped[0]=HEADER;
 const result=readDraft(stripped.map(x=>x.replace('(Anzeige ungeprüft)', '(OCR ungeprüft)')).join('\n'));
 return {...result,sourceKind:'app-screen',observedAt,currency,warning};
}
// A user's shared DEGIRO screen is useful comparison evidence, not an
// executable order quote or confirmation of an actual fill. This function is
// deliberately local-only; no price is sent to analysis, paper or broker APIs.
function displayedPairStatus(draft){
 if(!draft||draft.verified!==false||draft.tradeApproved!==false||draft.sourceTime!==null
    ||typeof draft.isin!=='string'||!validIsin(draft.isin))
   throw Error('Nur ungeprüfte, lokale DEGIRO-Bildschirmbeobachtungen.');
 const f=draft.fields||{};
 const parse=(s)=>{
  if(typeof s!=='string'||!/^(?:[1-9][0-9]{0,6}|0)(?:,[0-9]{1,4})?$/.test(s))return null;
  const n=Number(s.replace(',','.'));return Number.isFinite(n)&&n>0?n:null;
 };
 const bid=parse(f.bid),ask=parse(f.ask);
 if(bid===null||ask===null)
  return {state:'incomplete',label:'Kein vollständiges Geld-/Briefpaar aus dem Bild',broker:'DEGIRO',
   executable:false,canTrade:false,sourceTime:null};
 if(bid>ask)
  return {state:'conflict',label:'Geldpreis größer als Briefpreis: Bild prüfen',broker:'DEGIRO',
   executable:false,canTrade:false,sourceTime:null};
 return {state:'screen-observation',label:'DEGIRO-Bildschirmwerte für manuellen Vergleich',
  broker:'DEGIRO',isin:draft.isin,bid,ask,
  displayedTime:f.displayedTime||null,venue:f.venue||null,
  sourceTime:null,originalQuoteTimeVerified:false,executable:false,canTrade:false,
  permissions:'comparison-only',note:'OCR ungeprüft; keine bestätigte Kurszeit, Stückzahl, Ordervorschau oder Ausführung'};
}
function takeTransferFragment(location,history){
 const hash=String(location?.hash||'');
 if(!hash.startsWith('#bob-ocr='))return null;
 // Remove sensitive fragment before parsing or rendering: never persist it in history.
 history.replaceState(null,'',String(location.pathname||'/')+String(location.search||''));
 if(hash.length>8000)throw Error('Android-Übergabe ist zu lang.');
 const draft=decodeURIComponent(hash.slice('#bob-ocr='.length));
 readDraft(draft); // Strict parser rejects missing/multiple/invalid ISINs and unknown fields.
 return draft;
}
const api={validIsin,readDraft,displayedPairStatus,takeTransferFragment};
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
function mount(){
 const host=root.document.getElementById('bob-view-degiro');
 if(!host||root.document.getElementById('bobAndroidEvidence'))return;
 const box=root.document.createElement('details');box.className='card bob-disclosure';box.id='bobAndroidEvidence';
 const heading=root.document.createElement('summary');heading.textContent='Android-Bildschirmdaten · OCR-Entwurf prüfen';
 const introduction=root.document.createElement('p');introduction.textContent='Ein bis vier bewusst geteilte Bilder desselben Produkts. Die Android-App liest diese lokal und übergibt nur ausdrücklich als ungeprüft markierte Angaben. Ein sichtbares Geld-/Briefpaar dient ausschliesslich zur manuellen Gegenprüfung. Kein echter DEGIRO-Ausführungskurs, kein automatischer Brokerabruf.';
 const textarea=root.document.createElement('textarea');
 textarea.id='bobAndroidDraft';textarea.rows=8;textarea.maxLength=8000;textarea.placeholder='BOB OCR-ENTWURF – NICHT VERIFIZIERT\nISIN: ...';
 textarea.style.width='100%';textarea.style.boxSizing='border-box';textarea.setAttribute('aria-label','Ungeprüften OCR-Entwurf einfügen');
 const analyze=root.document.createElement('button');analyze.type='button';analyze.textContent='Entwurf lokal prüfen';
 const clear=root.document.createElement('button');clear.type='button';clear.textContent='Eingabe entfernen';
 const status=root.document.createElement('p');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const preview=root.document.createElement('div');preview.id='bobAndroidEvidencePreview';
 const safety=root.document.createElement('p');safety.textContent='OCR-Nachweise werden hier nicht gespeichert oder an den Server übertragen. Kein Einfluss auf Top 3, MyTrade, Simulationen oder Produktfreigaben.';
 box.append(heading,introduction,textarea,analyze,clear,status,preview,safety);
 host.append(box);
 function reset(){preview.replaceChildren();status.textContent='';}
 textarea.addEventListener('input',reset);
 clear.onclick=()=>{textarea.value='';reset();status.textContent='Entwurf lokal entfernt.';};
 analyze.onclick=()=>{
  reset();
  try{
   const draft=readDraft(textarea.value);
   const title=root.document.createElement('h4');title.textContent='ISIN '+draft.isin+(draft.sourceKind==='app-screen'?' · ungeprüfte App-Beobachtung':' · ungeprüfte OCR-Beobachtung');
   const list=root.document.createElement('ul');
   const labels={bid:'Geld',ask:'Brief',leverage:'Hebel',ko:'KO-Schwelle',venue:'Handelsplatz',last:'Zuletzt (kein ausführbarer Kurs)',displayedTime:'Anzeigezeit (keine bestätigte Kurszeit)'};
   for(const [name,label] of Object.entries(labels)){
    const item=root.document.createElement('li');
    item.textContent=label+': '+(draft.fields[name]||'nicht erkannt')+' (nicht bestätigt)';
    list.append(item);
   }
   preview.append(title,list);
   if(draft.sourceKind==='app-screen'){
    const source=root.document.createElement('p');
    source.textContent='DEGIRO-App · Währung '+draft.currency+' · erfasst '+draft.observedAt+' (keine Kurszeit) · '+draft.warning;
    preview.append(source);
   }
   const pair=displayedPairStatus(draft);
   const note=root.document.createElement('p');
   note.setAttribute('data-degiro-screen-quote',pair.state);
   note.textContent=pair.label+(pair.state==='screen-observation'?' · Geld '+draft.fields.bid+' / Brief '+draft.fields.ask:'')+
     ' · kein direkt angebundener DEGIRO-Ausführungskurs.';
   preview.append(note);
   if(draft.series){
    const seriesNote=root.document.createElement('p');
    seriesNote.textContent=draft.series.imageCount+' Bilder gemeinsam ausgewählt · ISIN auf '+draft.series.anchorCount+
     ' Bild(ern) eindeutig per OCR erkannt. '+
     (draft.series.provisional?'Die übrigen Bilder sind als Serie vorläufig zugeordnet.':'Alle Bilder zeigen dieselbe erkannte ISIN.')+
     ' Keine unabhängige Bestätigung der zusammengehörigen Produkte.';
    preview.append(seriesNote);
   }
   status.textContent='Lokal geprüft: nur ISIN-Prüfziffer; keine verifizierte Kurszeit, Handelsplatzfreigabe oder Originalbildprüfung.';
   const existing=root.BobDegiro?.tradeTestProducts?.();
   if(Array.isArray(existing)){
    const match=existing.some(p=>p?.isin===draft.isin);
    const note=root.document.createElement('p');
    note.textContent=match?'ISIN in einer vorhandenen Bob-Produktidentitätenliste gefunden. Das beweist keine aktuelle DEGIRO-Handelbarkeit.':'Keine Zuordnung in der verfügbaren lokalen Bob-Vergleichsliste. Das sagt nichts darüber aus, ob DEGIRO dieses Produkt anbietet oder handeln lässt.';
    preview.append(note);
   }
  }catch(e){status.textContent='Nicht übernommen: '+e.message;}
 };
 // Automatic navigation is only a user-initiated image share from our Android app.
 // The URL fragment is local browser navigation; no API request or trade approval.
 try{
  const incoming=takeTransferFragment(root.location,root.history);
  if(incoming!==null){
   textarea.value=incoming;
   box.open=true;
   analyze.click();
   const navButton=root.document.querySelector('#bob-view-more [data-view="degiro"]')||
                   root.document.querySelector('[data-view="degiro"]');
   if(navButton)navButton.click();
   else host.hidden=false;
   box.scrollIntoView({block:'start'});
  }
 }catch(e){
  box.open=true;
  status.textContent='Android-Übergabe abgelehnt: '+e.message;
 }
}
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof window==='undefined'?globalThis:window);
