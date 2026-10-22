/* Bob unified mobile workflow. Read-only orchestration; no broker write. */
(function(root){
'use strict';
const ORDER_KEY='bob.degiro2.plan.v1';
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
const api={zurichDay,originalAge,validIsin,analyzeInputs,validateDraftBackup,serializeDraftBackup};
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
 '<label>Produkt aus Bobs bestehender Liste <select id="bobUnifiedProduct" style="width:100%;min-height:42px"><option value="">Bitte Produkt wählen</option></select></label>'+
 '<p class="small" id="bobUnifiedProductNote">Nur Produktidentität, keine automatische Freigabe.</p>'+
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
