/* Opt-in local export bridge. Data is user-provided, never a trading permission. */
(function(root){
'use strict';
const TTL=600000,HELPER_VERSION='1.2.0';
function validate(offer,store,now=Date.now()){
 if(!offer||typeof offer.id!=='string'||!/^[a-f0-9-]{36}$/i.test(offer.id)||
    !Number.isFinite(offer.createdAt)||offer.createdAt>now+5000||offer.createdAt<now-TTL)
  throw Error('Export abgelaufen oder ungültig. Bitte neu exportieren.');
 const data=offer.report;
 if(!data||data.kind!=='portfolio'||!Array.isArray(data.invalidRows)||data.invalidRows.length)
  throw Error('Nur vollständige, gültige Portfolioexporte werden übernommen.');
 if(!Array.isArray(data.records)||data.records.some(r=>!r||typeof r.quantity!=='number'||
    !Number.isFinite(r.quantity)||
    typeof r.currency!=='string'||!/^([A-Z]{3})?$/.test(r.currency)))
  throw Error('Ungültige Stückzahl oder Währung im Portfolioexport.');
 if(data.accountCurrency!==null&&data.accountCurrency!==undefined&&
    !/^([A-Z]{3})?$/.test(data.accountCurrency))throw Error('Ungültige Kontowährung.');
 // prepare allowlists the saved fields and resets every permission to false.
 return store.prepare({...data,sourceKind:'browser-export'},new Date(offer.createdAt).toISOString());
}
function mount(){
 const doc=root.document,host=doc.getElementById('bob-view-degiro');
 if(!host||doc.getElementById('bobBrowserBridge'))return;
 const el=(tag,text)=>{const n=doc.createElement(tag);if(text)n.textContent=text;return n;};
 const panel=el('section');panel.id='bobBrowserBridge';panel.className='card';
 panel.style.cssText='padding:16px;min-width:0;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere';
 panel.append(el('h3','DEGIRO → Bob mit Firefox'));
 panel.append(el('p','Kostenlose Export-Brücke: In Bob die Übernahme aktivieren, dann in DEGIRO Portfolio → Export → CSV wählen. Beide Seiten müssen im selben Firefox geöffnet sein.'));
 const setup=el('details');setup.append(el('summary','Einmalig auf Android einrichten'));
 const steps=el('ol');
 const links=[
  ['Firefox für Android installieren','https://www.mozilla.org/de/firefox/browsers/mobile/android/'],
  ['Violentmonkey in Firefox installieren','https://addons.mozilla.org/de/android/addon/violentmonkey/'],
  ['Bob-Exportscript in Firefox installieren','/bob_degiro_export.user.js']
 ];
 for(const [text,url]of links){const li=el('li'),a=el('a',text);a.href=url;a.target='_blank';a.rel='noopener noreferrer';li.append(a);steps.append(li);}
 steps.append(el('li','Bob und trader.degiro.nl in Firefox öffnen. Bei DEGIRO selbst anmelden. Danach beide Seiten neu laden.'));
 setup.append(steps,el('p','Violentmonkey verlangt weitreichende Seitenberechtigungen. Das Bob-Script ist auf diese Bob-Adresse und trader.degiro.nl begrenzt. Prüfe diese beiden Adressen im Installationsdialog.'));
 panel.append(setup);
 const update=el('a','Export-Helfer auf Version '+HELPER_VERSION+' aktualisieren');
 update.id='bobBridgeUpdate';update.href='/bob_degiro_export.user.js?v='+HELPER_VERSION;update.target='_blank';update.rel='noopener noreferrer';
 update.style.cssText='display:block;margin:12px 0;min-height:44px';panel.append(update);
 const brokerStatus=el('p','DEGIRO-Helfer noch nicht bestätigt. DEGIRO nach der Installation im selben Firefox neu laden.');
 brokerStatus.id='bobBridgeBrokerStatus';brokerStatus.setAttribute('role','status');panel.append(brokerStatus);
 const status=el('p','Export-Helfer noch nicht erkannt. Einrichtung öffnen oder beide Seiten neu laden.');
 status.id='bobBridgeStatus';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const start=el('button','Übernahme für 10 Minuten aktivieren');start.id='bobBridgeStart';start.type='button';start.disabled=true;
 const stop=el('button','Übernahme beenden');stop.id='bobBridgeStop';stop.type='button';stop.disabled=true;
 for(const b of[start,stop])b.style.cssText='display:block;min-height:44px;width:100%;margin:8px 0;white-space:normal';
 panel.append(status,start,stop,el('p','Die Momentaufnahme wird nur in diesem Firefox gespeichert. Die Bob-App in Chrome und Bobs Server erhalten diese Daten nicht. Für einen neuen Stand erneut CSV exportieren. Keine unbeaufsichtigte Synchronisation und keine Livekurse. Falls die Brücke den Download nicht erkennt, kannst du die CSV unten wie bisher auswählen.'));
 host.prepend(panel);
 const CONSENT='bob-export-tab-consent-v1';
 let until=0,helper=false,timer=null,probeTimer=null,ackTimer=null,confirmed=false;const seen=new Set();
 let resumeUntil=0;
 try{const saved=Number(root.sessionStorage.getItem(CONSENT));if(Number.isFinite(saved)&&saved>Date.now()&&saved<=Date.now()+TTL)resumeUntil=saved;else root.sessionStorage.removeItem(CONSENT);}catch(_){}
 const post=(type,extra={})=>root.postMessage({type,...extra},root.location.origin);
 function end(text){try{root.sessionStorage.removeItem(CONSENT);}catch(_){}resumeUntil=0;until=0;confirmed=false;clearTimeout(timer);clearTimeout(probeTimer);clearTimeout(ackTimer);start.disabled=!helper;stop.disabled=true;post('BOB_EXPORT_DISARM');status.textContent=text;}
 function activate(deadline){
  until=deadline;try{root.sessionStorage.setItem(CONSENT,String(until));}catch(_){}confirmed=false;start.disabled=true;stop.disabled=true;
  status.textContent='Übernahme wird aktiviert. Bestätigung des Export-Helfers wird geprüft …';
  ackTimer=setTimeout(()=>end('Übernahme nicht bestätigt. Export-Helfer aktualisieren und Bob neu laden.'),3000);
  brokerStatus.textContent='Verbindung zum DEGIRO-Helfer wird geprüft …';
  probeTimer=setTimeout(()=>{if(brokerStatus.textContent==='Verbindung zum DEGIRO-Helfer wird geprüft …')brokerStatus.textContent='DEGIRO-Helfer nicht erreicht. DEGIRO im selben Firefox neu laden und danach Portfolio → Export → CSV wählen.';},8000);
  post('BOB_EXPORT_ARM',{until});timer=setTimeout(()=>end('Übernahme abgelaufen. Bei Bedarf erneut aktivieren.'),Math.max(0,until-Date.now()));
 }
 start.addEventListener('click',()=>activate(Date.now()+TTL));
 stop.addEventListener('click',()=>end('Übernahme beendet. Bereits gespeicherte Depotdaten bleiben erhalten.'));
 root.addEventListener('message',event=>{
  if(event.source!==root||event.origin!==root.location.origin||!event.data)return;
  const d=event.data;
  if(d.type==='BOB_EXPORT_HELPER_READY'){
   if(d.version!==HELPER_VERSION){helper=false;start.disabled=true;update.hidden=false;update.style.display='block';status.textContent='Export-Helfer veraltet. Über den Aktualisierungslink oben aktualisieren, dann Bob und DEGIRO neu laden.';return;}
   const first=!helper;helper=true;update.hidden=true;update.style.display='none';
   if(!until&&resumeUntil>Date.now()){const deadline=resumeUntil;resumeUntil=0;activate(deadline);return;}
   if(!until){start.disabled=false;if(first)status.textContent='Export-Helfer '+HELPER_VERSION+' erkannt. Übernahme bei Bedarf aktivieren.';}return;
  }
  if(d.type==='BOB_EXPORT_ARMED'){
   if(!until||Date.now()>=until||d.version!==HELPER_VERSION)return;
   confirmed=true;clearTimeout(ackTimer);stop.disabled=false;
   status.textContent='Übernahme aktiv für 10 Minuten. Jetzt in DEGIRO im selben Firefox Portfolio → Export → CSV wählen und zu Bob zurückkehren.';return;
  }
  if(d.type==='BOB_EXPORT_BROKER_STATUS'){
   if(d.version!==HELPER_VERSION||!Number.isFinite(d.at)||d.at>Date.now()+5000||d.at<Date.now()-30000)return;
   const labels={ready:'DEGIRO-Helfer erreichbar. Jetzt im DEGIRO-Tab Portfolio → Export → CSV wählen.',reading:'DEGIRO-Export erkannt. Datei wird geprüft …',staged:'DEGIRO-Export erkannt und für Bob bereitgestellt.',error:'DEGIRO-Export erkannt, konnte aber nicht vollständig gelesen werden. Die Meldung im DEGIRO-Tab erklärt den Fehler. Der bisherige Depotstand wird dadurch nicht ersetzt.'};
   if(labels[d.state]){clearTimeout(probeTimer);brokerStatus.textContent=labels[d.state];}return;
  }
  if(d.type!=='BOB_EXPORT_OFFER')return;
  const reply=(ok,count=0)=>post('BOB_EXPORT_RESULT',{id:d.id,ok,count});
  if(!until||Date.now()>=until||!confirmed)return;
  if(seen.has(d.id)){reply(true);return;}
  try{
   const snapshot=validate(d,root.BobDegiroPortfolio);
   root.BobDegiroPortfolio.save(root.localStorage,snapshot,snapshot.importedAt);
   seen.add(d.id);if(seen.size>64)seen.delete(seen.values().next().value);
   root.BobDegiroPortfolio.refresh?.();root.BobDegiroAllProducts?.rebuild?.();root.BobDegiroReport?.refresh?.();
   status.textContent='✓ '+snapshot.records.length+' Depotprodukte aus dem Export gespeichert. Unter Produkte sichtbar. Export-Momentaufnahme, keine Live-Kontoverbindung.';
   reply(true,snapshot.records.length);
  }catch(_){status.textContent='Export abgelehnt oder lokales Speichern fehlgeschlagen. Bisherigen Depotstand prüfen; erneut vollständige Portfolio-CSV exportieren.';reply(false);}
 });
 // document-start helpers can announce before Bob's UI is mounted.
 post('BOB_EXPORT_PROBE');
 root.addEventListener('pagehide',()=>{clearTimeout(timer);clearTimeout(probeTimer);clearTimeout(ackTimer);});
}
const api={validate,mount};
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
