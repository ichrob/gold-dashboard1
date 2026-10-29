/* Authenticated browser relay for the offline Android morning-list reader. */
(function(root){
'use strict';
const KEY='bobMorningReadPendingV1';
function ids(values,evidence){
 if(!Array.isArray(values)||values.length<1||values.length>12||values.some(x=>typeof x!=='string'||!evidence.validIsin(x)||x!==x.trim().toUpperCase())||new Set(values).size!==values.length)throw Error('Keine eindeutige Produktliste (1–12 ISINs).');
 return values;
}
function listPayload(list,evidence,now=Date.now()){
 const at=Date.parse(list?.listUploadedAt);
 if(!Number.isFinite(at)||now-at<0||now-at>86400000)throw Error('Morgenliste fehlt oder ist älter als 24 Stunden. Liste in Bob aktualisieren.');
 return {listUploadedAt:new Date(at).toISOString(),isins:ids(list.products?.map(p=>p.isin),evidence)};
}
function validateRun(run,evidence){
 if(!run||typeof run!=='object'||JSON.stringify(run).length>65536||!/^[a-f0-9]{32}$/.test(run.batchId)||!Number.isInteger(run.revision)||run.revision<1||run.revision>10000||!Number.isFinite(Date.parse(run.listUploadedAt)))throw Error('Ungültiger Leselauf.');
 ids(run.isins,evidence);
 if(run.listSource!==undefined&&!['bob-saved-list','degiro-gold-search'].includes(run.listSource))throw Error('Unbekannte Listenquelle.');
 if(!Array.isArray(run.results)||run.results.length>12||!Array.isArray(run.events)||run.events.length>48)throw Error('Ungültiges Leseprotokoll.');
 const seen=new Set();
 for(const row of run.results){
  if(!row||!run.isins.includes(row.isin)||seen.has(row.isin)||![1,2].includes(row.attempts))throw Error('Uneindeutige Produktzuordnung.');
  seen.add(row.isin);
  if(row.draft){const parsed=evidence.readDraft(row.draft);if(parsed.isin!==row.isin||parsed.sourceKind!=='app-screen')throw Error('Produktkennung im Entwurf stimmt nicht.');}
 }
 return run;
}
function keep(storage,run){
 const text=JSON.stringify(run),old=storage.getItem(KEY);
 if(old){const prior=JSON.parse(old);if(prior.batchId!==run.batchId)throw Error('Vorheriger Leselauf wartet noch auf Übertragung. Bitte zuerst erneut übertragen.');if(prior.revision>run.revision)return prior;if(prior.revision===run.revision&&old!==text)throw Error('Widersprüchliche Speicherversion.');}
 storage.setItem(KEY,text);if(storage.getItem(KEY)!==text)throw Error('Lokaler Speicher nicht bestätigt. Ergebnisse bleiben in Bob Handy.');return run;
}
function acknowledge(storage,run,response){
 if(!response?.ok||response.saved!==true||response.batchId!==run.batchId||response.revision!==run.revision)throw Error('Bob hat diese Speicherversion noch nicht bestätigt.');
 const pending=storage.getItem(KEY);
 if(pending&&JSON.stringify(JSON.parse(pending))===JSON.stringify(run))storage.removeItem(KEY);
 return 'bobhandy://list-reader/ack?batch='+run.batchId+'&revision='+run.revision;
}
function encode(value){return btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(value)))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}
function decode(text){if(text.length>100000||!/^[\w-]+$/.test(text))throw Error('Übergabe zu groß oder ungültig.');return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(atob(text.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0))));}
const api={listPayload,validateRun,keep,acknowledge,encode,decode,KEY};
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
root.addEventListener('hashchange',()=>{if(/^#bob-read-(list|results)=/.test(root.location.hash))root.location.reload();});
let incoming=null,transferError=null;
try{
 const hash=root.location.hash;
 if(/^#bob-read-(list|results)=/.test(hash)){
  root.history.replaceState(null,'',root.location.pathname+root.location.search);
  incoming=hash.startsWith('#bob-read-list=')?{nonce:hash.slice(15)}:{run:decode(hash.slice(18))};
 }
}catch(e){transferError=e;}
function mount(){
 const evidence=root.BobAndroidEvidence;
 if(!evidence||!root.BobDegiro||root.document.getElementById("bobMorningReader"))return;
 const panel=root.document.createElement('details');panel.id='bobMorningReader';
 const title=root.document.createElement('summary');title.textContent='Morgenliste automatisch lesen · Bob Handy';panel.append(title);
 const info=root.document.createElement('p');info.textContent='Bob Handy holt deine gespeicherte Morgenliste und liest die Produkte nacheinander in der angemeldeten DEGIRO-App. Fehlende Felder werden erneut geprüft. Lesebeobachtungen und Fehler werden getrennt von bestätigten Kursen gespeichert.';panel.append(info);
 const status=root.document.createElement('p');status.setAttribute('role','status');panel.append(status);
 const rows=root.document.createElement('div');panel.append(rows);
 const handoff=root.document.createElement('a');handoff.textContent='Bob Handy öffnen';handoff.href='bobhandy://list-reader/open';panel.append(handoff);
 const retry=root.document.createElement('button');retry.type='button';retry.textContent='Gespeicherte Ergebnisse erneut übertragen';panel.append(retry);
 const history=root.document.createElement('button');history.type='button';history.textContent='Gespeicherte Leseläufe und Fehler laden';panel.append(history);
 const host=root.document.getElementById('bobAndroidEvidence')?.parentElement||root.document.getElementById('bob-view-degiro')||root.document.querySelector('main')||root.document.body;
 host.prepend(panel);
 if(incoming||transferError){const nav=root.document.querySelector('[data-bob-target="degiro"]')||root.document.querySelector('[data-view="degiro"]');if(nav)nav.click();else host.hidden=false;}
 let busy=false;
 function show(run){
  rows.replaceChildren();
  if(run.listSource==='degiro-gold-search'){const note=root.document.createElement('p');note.textContent='Kandidaten aus sichtbaren Gold-Suchtreffern · unvollständige Stichprobe. Getrennte Lesebeobachtungen; die bestätigte Produktliste bleibt unverändert.';rows.append(note);}
  for(const isin of run.isins){const row=run.results.find(x=>x.isin===isin),p=root.document.createElement('p');const missing=row?.observation?.missingFields||row?.missingFields||[];p.textContent=isin+' · '+(row?.code||'noch nicht gelesen')+(missing.length?' · fehlt: '+missing.join(', '):'');rows.append(p);}
  if(run.events?.length){const p=root.document.createElement('p');p.textContent='Letzter Protokolleintrag: '+run.events.at(-1).code+' · '+run.events.at(-1).isin;rows.append(p);}
 }
 function openApp(url,text){handoff.href=url;handoff.textContent=text;status.textContent+=' Falls Bob Handy nicht automatisch öffnet, den Link antippen.';try{root.location.assign(url);}catch(_){/* Visible link is the fallback. */}}
 async function request(action,run){
  const response=await root.fetch('/api/degiro/android-observations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,...(run?{run}:{})}),signal:AbortSignal.timeout(15000)});
  if(!response.ok){const e=Error(response.status===401?'Bitte in Bob anmelden und erneut übertragen.':'Bob-Speicherung fehlgeschlagen (HTTP '+response.status+').');e.retryable=[408,429,502,503,504].includes(response.status);throw e;}
  return response.json();
 }
 async function upload(){
  if(busy)return;busy=true;retry.disabled=true;
  try{
   const raw=root.localStorage.getItem(KEY);if(!raw){status.textContent='Keine offene Browser-Übertragung. In Bob Handy Morgenliste starten oder gespeicherten Lauf übertragen.';return;}
   const run=validateRun(JSON.parse(raw),evidence);show(run);
   for(const row of run.results)if(row.draft)evidence.storeObservation(root.localStorage,row.draft,run.isins.map(isin=>({isin})));
   for(let n=1;n<=3;n++){
    status.textContent='Leselauf lokal gesichert. Übertragung an Bob · Versuch '+n+'/3 …';
    try{const answer=await request('save',run);const url=acknowledge(root.localStorage,run,answer);status.textContent='Leselauf mit '+run.results.length+' Produktergebnissen in Bob gespeichert.';openApp(url,'Speicherung in Bob Handy bestätigen');return;}
    catch(e){if(n===3||!(e.retryable||['TimeoutError','AbortError','TypeError'].includes(e.name)))throw e;await new Promise(resolve=>setTimeout(resolve,n===1?1500:4000));}
   }
  }catch(e){status.textContent=e.message+' Ergebnisse bleiben für den nächsten Versuch gespeichert.';panel.open=true;}
  finally{busy=false;retry.disabled=false;}
 }
 retry.onclick=upload;
 history.onclick=async()=>{try{const result=await request('read');if(!result.ok||!Array.isArray(result.runs))throw Error('Kein gültiges Protokoll.');if(!result.runs.length){status.textContent='Noch kein Leselauf auf Bob gespeichert.';return;}show(result.runs[0]);status.textContent=result.runs.length+' gespeicherte Versionen. Neuester Lauf: '+result.runs[0].receivedAt;}catch(e){status.textContent=e.message;}};
 async function begin(){
  if(transferError)throw transferError;
  if(incoming?.nonce){
   if(!/^[a-f0-9]{32}$/.test(incoming.nonce))throw Error('Ungültige Listenanforderung.');
   status.textContent='Gespeicherte Morgenliste wird von Bob geladen …';panel.open=true;
   const list=listPayload(await root.BobDegiro.readServerProductList({onRetry:n=>{status.textContent='Morgenliste laden · Versuch '+n+'/3 …';}}),evidence);
   status.textContent=list.isins.length+' Produkte aus der gespeicherten Morgenliste bereit.';
   openApp('bobhandy://list-reader/list?nonce='+incoming.nonce+'#'+encode(list),'Morgenliste an Bob Handy übergeben');return;
  }
  if(incoming?.run){validateRun(incoming.run,evidence);keep(root.localStorage,incoming.run);panel.open=true;}
  if(root.localStorage.getItem(KEY)){panel.open=true;await upload();}
  else status.textContent='In Bob Handy „Morgenliste automatisch von Bob holen und lesen“ starten.';
 }
 begin().catch(e=>{status.textContent=e.message;panel.open=true;});
}
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof globalThis==='object'?globalThis:this);
