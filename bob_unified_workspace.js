/* Bob unified mobile workflow. Read-only orchestration; no broker write. */
(function(root){
'use strict';
const ORDER_KEY='bob.degiro2.plan.v1';
const VISIBLE_IDS_KEY='bob.unified.visible-products.v1';
const UPLOADED_LIST_KEY='bob.unified.uploaded-list.v1';
const PRODUCT_STORE_KEY='bobDegiroProductsV2';
function zurichDay(date=new Date()){
 return new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
}
function originalAge(value,now=Date.now()){
 if(typeof value!=='string'||!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value))return null;
 const at=Date.parse(value);
 return Number.isFinite(at)&&at<=now&&now-at>=0?now-at:null;
}
function analyzeInputs(snapshot,now=Date.now()){
 const expired=snapshot?.expired===true;
 const raw=String(snapshot?.signal||'');
 const reason=String(snapshot?.reason||'');
 const age=originalAge(snapshot?.spotAt,now);
 const signal=expired?'UNBEKANNT':/\bABWARTEN\b/i.test(raw)?'ABWARTEN':/\bSHORT\b/i.test(raw)?'SHORT':/\bLONG\b/i.test(raw)?'LONG':'UNBEKANNT';
 // Same 60s spot freshness boundary as existing decision input; no heuristic
 // "fresh" fallback from app refresh timestamps.
 const spot=age!==null&&age<=60000&&snapshot?.spotGenuine===true&&!snapshot?.spotError&&!expired;
 const analysis=spot&&snapshot?.analysisReady===true&&!/veraltet|fehl|nicht aktuell|zeitstempel|anmeldung|gesperrt/i.test(reason)&&signal!=='UNBEKANNT';
 const products=Number.isSafeInteger(snapshot?.productCount)&&snapshot.productCount>=0?snapshot.productCount:null;
 const trade=snapshot?.tradeActive===true;
 return {
   signal,spot:{ok:spot,label:spot?'Originalzeit bestätigt':age===null?'Quellenzeit fehlt':age>60000?'Spot älter als 60 Sekunden':'Spot/Anmeldung prüfen'},
   analysis:{ok:analysis,label:analysis?'Signal anzeigen; keine Handelsfreigabe':'Analyse/Quelle nicht bestätigt'},
   products:{ok:products!==null&&products>0,label:products===null?'Produktliste nicht geladen':products===0?'Keine identifizierten Produkte':products+' identifizierte Produkte – Handelsnachweise separat prüfen'},
   trade:{ok:trade,label:trade?'Erfasster Trade vorhanden; Status der Überwachung separat prüfen':'Kein aktiver Trade erfasst'},
   date:zurichDay(new Date(now)),tradeable:false,canTradeAutomatically:false
 };
}
function validIsin(value){
 if(typeof value!=='string'||!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(value))return false;
 const expanded=value.replace(/[A-Z]/g,c=>String(c.charCodeAt(0)-55));
 let total=0;
 [...expanded].reverse().forEach((ch,i)=>{
  const v=Number(ch)*(i%2===1?2:1);
  total+=v>9?v-9:v;
 });
 return total%10===0;
}
function visibleChange(previous,current){
 const normalize=x=>[...new Set((Array.isArray(x)?x:[]).filter(validIsin))].sort();
 const latest=normalize(current);
 if(!Array.isArray(previous))return {known:false,added:[],removed:[],unchanged:[],current:latest};
 const before=normalize(previous),was=new Set(before),is=new Set(latest);
 return {known:true,added:latest.filter(x=>!was.has(x)),removed:before.filter(x=>!is.has(x)),
  unchanged:latest.filter(x=>was.has(x)),current:latest};
}

function uploadedList(raw,now=Date.now()){
 let d;try{d=typeof raw==='string'?JSON.parse(raw):raw;}catch(_){return null;}
 if(d?.version!==2||!Array.isArray(d.products)||!d.products.length||d.products.length>500)return null;
 if(typeof d.listUploadedAt!=='string'||!/(Z|[+-]\d{2}:\d{2})$/i.test(d.listUploadedAt))return null;
 const at=Date.parse(d.listUploadedAt);
 if(!Number.isFinite(at)||at>now||at<0)return null;
 if(d.products.some(p=>!validIsin(p?.isin)))return null;
 const ids=d.products.map(x=>x.isin);
 if(new Set(ids).size!==ids.length)return null;
 return {at:d.listUploadedAt,ids:ids.sort()};
}
function compareUploadedList(previous,current){
 if(!current)return {state:'unknown',reason:'Kein vollständig lesbarer gespeicherter DEGIRO-Listenstand.'};
 if(!previous)return {state:'baseline',current,reason:'Gespeicherte Screenshot-Liste als Ausgangsstand erkannt.'};
 const past=Date.parse(previous.at),latest=Date.parse(current.at);
 if(!Number.isFinite(past)||latest<past)return {state:'older',reason:'Gespeicherte Liste ist älter als der zuletzt geprüfte Stand; kein Überschreiben.'};
 if(latest===past)return previous.ids?.join('|')===current.ids.join('|')?
  {state:'same',reason:'Dieselbe gespeicherte Listenfassung; kein neuer Upload.'}:
  {state:'conflict',reason:'Gleiche Uploadzeit mit abweichenden ISINs. Nicht automatisch übernehmen.'};
 const diff=visibleChange(previous.ids,current.ids);
 return {state:'changed',current,added:diff.added,removed:diff.removed,unchanged:diff.unchanged};
}
function operationalSnapshot(audit,problems,simulationText='',now=Date.now()){
 const ago=originalAge(audit?.lastCheckedAt,now);
 const actualAudit=audit?.status==='ok'&&Array.isArray(audit.items)&&
  Number.isInteger(audit.incomplete)&&audit.incomplete>=0&&
  ago!==null&&ago<=300000&&audit.items.length>0;
 const productStatus=!actualAudit?
  {state:'unknown',text:'Produktprüfung fehlt, ist nicht aktuell oder hat keine auswertbaren Produkte.'}:
  audit.incomplete>0?
  {state:'warning',text:audit.incomplete+(audit.incomplete===1?' Produkt':' Produkte')+' mit fehlenden Nachweisen. Details unter Gold-Hebelprodukte.'}:
  {state:'checked',text:audit.items.length+(audit.items.length===1?' Produkt':' Produkte')+' ohne gemeldete Nachweislücke im aktuellen Prüfbericht. Keine Handelsfreigabe.'};
 const counts=problems?.status==='ok'&&Array.isArray(problems.problems)&&
  Number.isInteger(problems.count)&&problems.count>=0&&problems.count===problems.problems.length;
 const problemStatus=!counts?
  {state:'unknown',text:'Technisches Problemarchiv nicht aktuell bestätigt.'}:
  problems.count?
  {state:'warning',text:problems.count+' offene technische KI-Hilfeanfragen (öffentliche Diagnosecodes).'}:
  {state:'checked',text:'Keine offenen technischen KI-Hilfeanfragen im öffentlichen Diagnosearchiv. Private Produktprobleme separat prüfen.'};
 const simulation=typeof simulationText==='string'&&simulationText.trim()?
  {state:'unknown',text:'Simulation laut bestehender Anzeige: '+simulationText.trim().slice(0,140)+'. Kein bestätigter Gewinn oder Brokerstatus.'}:
  {state:'unknown',text:'Simulation noch nicht in dieser Ansicht bestätigt. Details unter Simulation.'};
 return {productStatus,problemStatus,simulation,tradeable:false,automaticOrders:false};
}

function validateDraftBackup(raw,today=zurichDay()){
 if(typeof raw!=='string'||raw.length>100000)throw Error('Sicherungsdatei fehlt oder ist zu groß.');
 let data;try{data=JSON.parse(raw);}catch(_){throw Error('Ungültiges JSON.');}
 if(!data||data.format!=='bob-order-drafts-v1'||!data.drafts||!data.exportedAt||!Array.isArray(data.drafts.orders))
  throw Error('Keine kompatible Bob-Entwurfsicherung.');
 const d=data.drafts;
 if(d.day!==today||data.day!==today)throw Error('Nur Entwürfe des aktuellen Schweizer Tages wiederherstellen.');
 if(!['EUR','CHF'].includes(d.currency)||!Number.isSafeInteger(d.budget)||d.budget<=0||d.budget>1e11)
  throw Error('Währung oder Budget ungültig.');
 if(d.orders.length>50)throw Error('Zu viele Entwürfe.');
 let used=0;
 for(const o of d.orders){
  if(!validIsin(o.isin))
   throw Error('ISIN ungültig.');
  if(!['Kauf','Verkauf'].includes(o.side)||!Number.isSafeInteger(o.qty)||o.qty<=0||
    ![o.price,o.fees,o.cost].every(x=>Number.isSafeInteger(x)&&x>=0)||
    o.price<=0||o.price>1e11||o.cost!==o.qty*o.price+o.fees)
    throw Error('Entwurf enthält widersprüchliche Mengen, Kurse oder Gebühren.');
  if(o.stop!==null&&o.stop!==undefined&&(!Number.isSafeInteger(o.stop)||o.stop<=0||o.stop>=o.price||o.side!=='Kauf'))
   throw Error('Stopp ungültig.');
  if(o.target!==null&&o.target!==undefined&&(!Number.isSafeInteger(o.target)||o.target<=o.price||o.side!=='Kauf'))
   throw Error('Ziel ungültig.');
  if(o.side==='Kauf')used+=o.cost;
 }
 if(!Number.isSafeInteger(used)||used>d.budget)throw Error('Entwürfe überschreiten das Tagesbudget.');
 // Drop unrecognised fields and potentially stale observations. No credential import.
 return {day:d.day,currency:d.currency,budget:d.budget,orders:d.orders.map(o=>({
  isin:o.isin,side:o.side,qty:o.qty,price:o.price,fees:o.fees,cost:o.cost,
  stop:o.stop??null,target:o.target??null
 }))};
}
function serializeDraftBackup(drafts,now=new Date()){
 if(!drafts||drafts.day!==zurichDay(now)||!Array.isArray(drafts.orders))
  throw Error('Keine aktuelle Tagesplanung zum Sichern.');
 // Strict round-trip verification, stripping non-order/credential fields.
 const content={format:'bob-order-drafts-v1',day:drafts.day,exportedAt:now.toISOString(),drafts};
 const clean=validateDraftBackup(JSON.stringify(content),drafts.day);
 return JSON.stringify({...content,drafts:clean},null,2);
}
const api={zurichDay,originalAge,validIsin,visibleChange,uploadedList,compareUploadedList,analyzeInputs,operationalSnapshot,validateDraftBackup,serializeDraftBackup};
if(typeof module!=='undefined'&&module.exports)module.exports=api;
root.BobUnifiedWorkspace=api;
if(!root.document)return;

function mount(){
 const doc=root.document,overview=doc.getElementById('bob-view-overview');
 if(!overview||doc.getElementById('bobUnifiedWorkspace'))return;
 const section=doc.createElement('section');
 section.id='bobUnifiedWorkspace';section.className='card';
 section.innerHTML='<h3>Bob · Alles an einem Ort</h3>'+
 '<p class="small">Einmal prüfen, dann den passenden Bereich öffnen. Quellen- und Handelsnachweise bleiben getrennt; keine automatische Order oder Änderung der Risikoregeln.</p>'+
 '<button type="button" id="bobPrepareReadOnly" class="bob-primary">Bob, bereite alles vor</button>'+
 '<p class="small" id="bobPrepareStatus" role="status" aria-live="polite">Noch nicht geprüft.</p>'+
 '<div id="bobUnifiedChecks" class="small"></div>'+
 '<button type="button" id="bobUnifiedCheckOperations">Produktnachweise und Probleme prüfen</button>'+ 
 '<div id="bobUnifiedOperations" class="small" role="status" aria-live="polite">Noch keine gemeinsame Statusprüfung.</div>'+
 '<label>Produkt aus Bobs bestehender Liste <select id="bobUnifiedProduct" style="width:100%;min-height:42px"><option value="">Bitte Produkt wählen</option></select></label>'+
 '<p class="small" id="bobUnifiedProductNote">Nur Produktidentität, keine automatische Freigabe.</p>'+
 '<p class="small" id="bobUnifiedVisibleDiff">Änderungsvergleich nach der nächsten bewussten Produktprüfung verfügbar.</p>'+ 
 '<p class="small" id="bobUnifiedUploadedDiff">Gespeicherte Screenshotliste wird bei der nächsten bewussten Prüfung verglichen.</p>'+
 '<button type="button" id="bobUnifiedToDraft">Produkt für Orderentwurf übernehmen</button>'+
 '<div class="row" style="display:flex;flex-wrap:wrap;gap:8px">'+
 '<button type="button" data-view="products">Gold-Hebelprodukte</button>'+
 '<button type="button" data-view="trade">Mein Trade</button>'+
 '<button type="button" data-view="degiro2">Orderentwurf</button>'+
 '<button type="button" data-view="simulation">Simulation</button>'+
 '<button type="button" data-view="problems">Probleme</button></div>'+
 '<details class="bob-disclosure" id="bobDataProvenance"><summary>Nachweise und Speicherung</summary>'+
 '<p class="small">Die Kontrollübersicht liest bestehende Ansichten und denselben aktuellen Markt-Datensatz. Ein Haken gilt nur für die bezeichnete Prüfung. Bei ausgewählten Produkten wird der vorhandene Emittentenabruf einmal angestoßen. DEGIRO-Listenbilder, SnapTrade, Emittentenkurse und Simulationen sind keine austauschbaren Handelsnachweise.</p>'+
 '<button type="button" id="bobBackupOrders">Heutige Orderentwürfe sichern</button>'+
 '<button type="button" id="bobRestoreOrders">Gesicherte Entwürfe wiederherstellen</button>'+
 '<input id="bobRestoreOrdersFile" type="file" accept="application/json,.json" hidden>'+
 '<p class="small" id="bobBackupStatus" role="status" aria-live="polite">Nur manuelle Orderentwürfe auf diesem Gerät. Keine Kontozugänge, Screenshots, Trades oder Echtgeldorders im Export.</p>'+
 '</details>';
 const title=overview.querySelector(':scope > h2');
 if(title)title.after(section);else overview.prepend(section);
 const status=doc.getElementById('bobPrepareStatus'),checks=doc.getElementById('bobUnifiedChecks');
 const chosen=doc.getElementById('bobUnifiedProduct'),productNote=doc.getElementById('bobUnifiedProductNote');
 let working=false;
 function refreshProducts(){
  const old=chosen.value,items=root.BobDegiro?.tradeTestProducts?.()||[];
  chosen.replaceChildren();
  const first=doc.createElement('option');first.value='';first.textContent='Bitte Produkt wählen';chosen.append(first);
  for(const p of Array.isArray(items)?items:[]){
   if(!validIsin(p?.isin))continue;
   const item=doc.createElement('option');item.value=p.isin;
   item.textContent=p.isin+' · '+(p.direction||'Richtung offen')+' · '+String(p.name||'').slice(0,40);
   chosen.append(item);
  }
  if(old&&Array.from(chosen.options).some(x=>x.value===old))chosen.value=old;
  if(chosen.value!==old)productNote.textContent='Nur Produktidentität. Keine automatische Handelsfreigabe.';
 }
 chosen.addEventListener('change',()=>{
  const p=(root.BobDegiro?.tradeTestProducts?.()||[]).find(x=>x.isin===chosen.value);
  if(!p){productNote.textContent='Kein Produkt gewählt.';return;}
  const q=p.quote,at=q?.askAt||q?.bidAt||null,age=originalAge(at);
  const label=age===null?'Originalzeit fehlt':age>90000?'Originalkurs älter als 90 Sekunden':'Beobachtungszeit innerhalb von 90 Sekunden';
  productNote.textContent='ISIN '+p.isin+' · '+(p.direction||'Richtung offen')+
   ' · '+label+' · '+(q?.source||'Quelle nicht belegt')+
   '. Kein bestätigter DEGIRO-Kurs oder Handelsplatz.';
 });
 doc.getElementById('bobUnifiedToDraft').addEventListener('click',()=>{
  const isin=chosen.value;
  if(!validIsin(isin)){productNote.textContent='Zuerst ein Produkt aus der Bob-Liste wählen.';return;}
  const available=(root.BobDegiro?.tradeTestProducts?.()||[]).some(x=>x.isin===isin);
  const target=doc.getElementById('dg2-product');
  if(!available||!target||!Array.from(target.options).some(x=>x.value===isin)){
   productNote.textContent='Produkt im Handy-Assistenten nicht bestätigt. Öffne den Orderentwurf und aktualisiere die Produktliste.';
   doc.querySelector('#bobUnifiedWorkspace [data-view="degiro2"]')?.click();return;
  }
  target.value=isin;
  target.dispatchEvent(new Event('change',{bubbles:true}));
  doc.querySelector('#bobUnifiedWorkspace [data-view="degiro2"]')?.click();
  productNote.textContent='ISIN in Orderentwurf übergeben. Limit, Stückzahl und aktuelle DEGIRO-Handelbarkeit selbst prüfen.';
 });

 function text(id){return doc.getElementById(id)?.textContent?.trim()||'';}
 function snapshot(){
  const bundle=root.liveBundleCache,products=root.BobDegiro?.tradeTestProducts?.();
  return {
   expired:root.BobSession?.expired?.()===true,
   signal:text('quickSignal'),reason:text('quickReason'),
   spotAt:bundle?.spots?.spot_price_as_of,
   spotGenuine:bundle?.spots?.is_genuine_xauusd_spot===true,
   spotError:bundle?.spots?.spot_error,
   analysisReady:root.A?.ready===true,
   productCount:Array.isArray(products)?products.length:null,
   tradeActive:root.BobTradeSync?.current?.()?.active===true
  };
 }
 function present(value){
  refreshProducts();
  checks.replaceChildren();
  const rows=[
   ['Gold-Spot',value.spot],['Marktanalyse',value.analysis],
   ['Produktidentitäten',value.products],['Mein Trade',value.trade]
  ];
  for(const [name,item] of rows){
   const p=doc.createElement('p');p.textContent=(item.ok?'✓ ':'? ')+name+': '+item.label;
   checks.append(p);
  }
  const p=doc.createElement('p');
  p.textContent='Aktuelle Richtung laut Ansicht: '+value.signal+'. Diese Übersicht führt keine Broker- oder Handelsfreigabe durch.';
  checks.append(p);
 }
 let checkingOperations=false;
 doc.getElementById('bobUnifiedCheckOperations').addEventListener('click',async()=>{
  if(checkingOperations)return;
  checkingOperations=true;
  const button=doc.getElementById('bobUnifiedCheckOperations');
  const box=doc.getElementById('bobUnifiedOperations');
  button.disabled=true;box.textContent='Lese vorhandene Produkt- und Problemberichte …';
  try{
   const paths=['/api/degiro/audit','/api/problems'];
   const response=await Promise.all(paths.map(async path=>{
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),12000);
    try{
     const r=await fetch(path,{credentials:'same-origin',cache:'no-store',signal:controller.signal});
     return r.ok?await r.json():null;
    }catch(_){return null;}finally{clearTimeout(timer);}
   }));
   const snapshot=operationalSnapshot(response[0],response[1],text('bobProfilesStatus'));
   box.replaceChildren();
   for(const [name,entry] of [['Produkte',snapshot.productStatus],['Probleme',snapshot.problemStatus],['Simulation',snapshot.simulation]]){
    const p=doc.createElement('p');p.textContent=(entry.state==='checked'?'✓ ':entry.state==='warning'?'⚠ ':'? ')+name+': '+entry.text;
    box.append(p);
   }
   const footer=doc.createElement('p');footer.textContent='Unabhängige Handels-, KO- und Risikofreigaben bleiben erforderlich. Keine Echtgeldorder.';
   box.append(footer);
  }finally{checkingOperations=false;button.disabled=false;}
 });
 doc.getElementById('bobPrepareReadOnly').addEventListener('click',async()=>{
  if(working)return;working=true;
  const button=doc.getElementById('bobPrepareReadOnly');button.disabled=true;
  try{
   status.textContent='Gemeinsame Marktdaten werden über Bobs bestehenden Abruf aktualisiert …';
   if(root.BobSession?.expired?.())throw Error('Anmeldung abgelaufen. Bitte erneut anmelden.');
   if(typeof root.loadData==='function')await root.loadData(true);
   const earlier=root.BobDegiro?.tradeTestProducts?.();
   // The existing bounded issuer refresh is explicit and only triggered here by a user click.
   if(Array.isArray(earlier)&&earlier.length&&typeof root.BobDegiro?.refreshTradeTestQuotes==='function')
    await root.BobDegiro.refreshTradeTestQuotes();
   const assessment=analyzeInputs(snapshot());present(assessment);
   status.textContent=assessment.analysis.ok?
    'Marktdaten geprüft. Produkte und Orderentwurf als Nächstes öffnen; keine automatische Freigabe.':
    'Prüfung unvollständig: '+assessment.spot.label+'; '+assessment.analysis.label+'. Keine Ordervorbereitung mit unbekanntem Kurs.';
   const target=doc.getElementById('bobUnifiedUploadedDiff');
   const currentUpload=uploadedList(root.localStorage.getItem(PRODUCT_STORE_KEY));
   let previousUpload=null;
   try{previousUpload=JSON.parse(root.localStorage.getItem(UPLOADED_LIST_KEY)||'null');}catch(_){}
   const previousValid=previousUpload?.version===1&&uploadedList({
    version:2,listUploadedAt:previousUpload.at,
    products:(Array.isArray(previousUpload.ids)?previousUpload.ids:[]).map(isin=>({isin}))
   });
   const comparison=compareUploadedList(previousValid?{at:previousUpload.at,ids:previousValid.ids}:null,currentUpload);
   if(comparison.state==='changed'){
    target.textContent='Neue Screenshot-Listenfassung '+currentUpload.at+': '+
      comparison.added.length+' neue ISIN · '+comparison.removed.length+' in der neuen Liste fehlende ISIN · '+
      comparison.unchanged.length+' unverändert. Kein aktueller DEGIRO-Handelsnachweis.';
   }else target.textContent=comparison.reason+' Die Liste ist kein aktueller Handelsplatz-/Kursnachweis.';
   if(['baseline','changed'].includes(comparison.state)){
    try{root.localStorage.setItem(UPLOADED_LIST_KEY,JSON.stringify({version:1,at:currentUpload.at,ids:currentUpload.ids}));}
    catch(_){target.textContent+=' Merkliste konnte nicht gespeichert werden.';}
   }
   const current=root.BobDegiro?.tradeTestProducts?.()||[];
   const ids=(Array.isArray(current)?current:[]).map(x=>x.isin);
   if(ids.length){
    let old=null,previousAt=null;
    try{const saved=JSON.parse(root.localStorage.getItem(VISIBLE_IDS_KEY)||'null');
     if(saved?.version===1&&Array.isArray(saved.ids)){old=saved.ids;previousAt=saved.at;}
    }catch(_){}
    const diff=visibleChange(old,ids);
    const row=doc.getElementById('bobUnifiedVisibleDiff');
    row.textContent=!diff.known?
     diff.current.length+' sichtbare Produktidentitäten als Ausgangsstand gespeichert (keine vollständige DEGIRO-Liste).':
     'Seit sichtbarem Stand '+(previousAt||'ohne Zeit')+': '+diff.added.length+' hinzugekommen · '+
      diff.removed.length+' nicht mehr sichtbar · '+diff.unchanged.length+
      ' unverändert. Nur sichtbare Bob-Identitäten, keine Bestätigung einer DEGIRO-Listung oder Delistung.';
    root.localStorage.setItem(VISIBLE_IDS_KEY,JSON.stringify({version:1,at:new Date().toISOString(),ids:diff.current}));
   }
  }catch(e){present(analyzeInputs(snapshot()));status.textContent='Prüfung noch unvollständig: '+String(e?.message||'Datenquelle nicht erreichbar').slice(0,160);}
  finally{working=false;button.disabled=false;}
 });
 const backupStatus=doc.getElementById('bobBackupStatus');
 doc.getElementById('bobBackupOrders').addEventListener('click',()=>{
  try{
   const json=serializeDraftBackup(JSON.parse(root.localStorage.getItem(ORDER_KEY)||'null'));
   const url=URL.createObjectURL(new Blob([json],{type:'application/json'}));
   const a=doc.createElement('a');a.href=url;a.download='bob-orderentwuerfe-'+zurichDay()+'.json';
   doc.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
   backupStatus.textContent='Lokale Sicherung erstellt. Bewahre die Datei geschützt auf.';
  }catch(e){backupStatus.textContent='Sicherung nicht möglich: '+e.message;}
 });
 const picker=doc.getElementById('bobRestoreOrdersFile');
 doc.getElementById('bobRestoreOrders').addEventListener('click',()=>picker.click());
 picker.addEventListener('change',async()=>{
  try{
   const file=picker.files?.[0];
   if(!file||file.size>100000)throw Error('Bitte eine JSON-Datei bis 100 KB auswählen.');
   const existing=root.localStorage.getItem(ORDER_KEY);
   if(existing){
    let previous=null;try{previous=JSON.parse(existing);}catch(_){}
    if(!previous||previous.day===zurichDay())throw Error('Es gibt bereits gespeicherte Entwürfe für heute. Sie werden nicht überschrieben.');
   }
   const restored=validateDraftBackup(await file.text());
   root.localStorage.setItem(ORDER_KEY,JSON.stringify(restored));
   root.dispatchEvent(new Event('bob-order-drafts-restored'));
   backupStatus.textContent='Heutige Entwürfe wiederhergestellt und zur bestehenden Orderansicht übertragen. Alle Werte erneut prüfen; keine Order gesendet.';
  }catch(e){backupStatus.textContent='Wiederherstellung nicht erfolgt: '+e.message;}
  finally{picker.value='';}
 });
 present(analyzeInputs(snapshot()));
}
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);
else mount();
})(typeof window!=='undefined'?window:globalThis);
