/* Dated personal trade evidence. No orders and no invented quote precision. */
(function(){
const KEY='bobTradeEvidenceV1',esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function number(v){let s=String(v||'').trim();if(s.includes(','))s=s.replace(/\./g,'').replace(',','.');return /^\d+(?:\.\d+)?$/.test(s)?Number(s):null;}
function parse(text){
 const raw=String(text||''),ids=[...new Set(raw.toUpperCase().match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])].filter(x=>window.BobDegiro.validIsin(x));
 if(ids.length!==1)return{ok:false,reason:'Genau eine gültige ISIN muss im Bild sichtbar sein. Kursbild bitte mit ISIN erneut aufnehmen.'};
 const match=re=>{const m=raw.match(re);return m?m[1].trim():null;},val=label=>number(match(new RegExp('\\b(?:'+label+')(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR|CHF)?\\s*([0-9]+(?:[.,][0-9]+)?)','i')));
 const time=match(/\b(\d{2}[/.]\d{2}[/.]\d{4},?\s+\d{2}:\d{2}(?::\d{2})?)\b/),direction=/\b(?:CALL|LONG)\b/i.test(raw)?'LONG':/\b(?:PUT|SHORT)\b/i.test(raw)?'SHORT':null;
 const explicit=raw.match(/(?:Kurs|Geld|Brief|Bid|Ask)\s*[:=]?\s*(EUR|CHF)\b/i);
 const currency=explicit?explicit[1].toUpperCase():/\bEUR\b|€/.test(raw)?'EUR':null;
 if(!currency&&/\bGeld\b|\bBid\b|\bKauf\b/i.test(raw))return{ok:false,reason:'Produktwährung EUR oder CHF am Original nachweisen.'};
 if(/\b(?:CALL|LONG)\b/i.test(raw)&&/\b(?:PUT|SHORT)\b/i.test(raw))return{ok:false,reason:'Produktrichtung widersprüchlich.'};
 if((raw.match(/\b(?:Geld|Bid)(?!\s*(?:Vol|Volumen))/gi)||[]).length>1)return{ok:false,reason:'Mehrere Geldkurse: ein einziges Geld-/Briefpaar zeigen.'};
 const purchase=/\bKauf\b/i.test(raw)&&/Ausf.hrungsdatum|Transaktions.ID|Order.[I1l]?D/i.test(raw);
 const x={ok:true,isin:ids[0],currency:currency||raw.match(/Produktwährung\s+(EUR|CHF)/)?.[1]||'EUR',direction,time,kind:purchase?'entry':/\bGeld\b|\bBid\b/i.test(raw)?'quote':'details'};
 if(purchase){x.entry=val('Kurs');x.quantity=val('Anzahl|Anz\\.');x.orderId=match(/Order.ID\s*[:=]?\s*([a-z0-9-]+(?:\s*\n\s*[a-z0-9-]+)?)/i)||match(/Transaktions.ID\s*[:=]?\s*(\d+)/i);x.feesChf=number(match(/(?:Gesamte Kosten|Gesamtgebühr)\s*CHF\s*-?\s*([0-9]+(?:[.,][0-9]+)?)/i));if(!(x.entry>0&&Number.isInteger(x.quantity)&&x.quantity>0&&time))return{ok:false,reason:'Kaufpreis, ganzzahlige Stückzahl oder Ausführungsdatum fehlt. OCR-Text am Original korrigieren.'};}
 else if(x.kind==='quote'){x.bid=val('Geld|Bid');x.ask=val('Brief|Ask');if(!(x.bid>0&&x.ask>=x.bid&&time))return{ok:false,reason:'Zusammengehörige Geld-/Briefkurse und originales Kursdatum fehlen.'};}
 x.ko=val('BAR|KO|K\\.O\\.-Schwelle|KO-Barriere');x.strike=val('BP|Basispreis');x.ratio=val('Bezugsverhältnis');return x;
}
const PRODUCT_REFERENCES={DE000FG5GUX2:{ratio:0.1,source:'Société Générale Produktseite, recherchiert 02.10.2026',url:'https://www.sg-zertifikate.de/product-details/fg5gux'}};
function draft(raw){
 const ids=[...new Set(String(raw).toUpperCase().match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])];
 const candidate=ids.length===1?ids[0]:'';
 const fallback=parse(String(raw).replace(candidate,'DE000FG5GUX2'));
 const val=label=>{const m=raw.match(new RegExp('\\b(?:'+label+')(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR|CHF)?\\s*([0-9]+(?:[.,][0-9]+)?)','i'));return m?m[1]:'';};
 return {isin:candidate,currency:(raw.match(/(?:Kurs|Geld|Brief|Bid|Ask)\s*[:=]?\s*(EUR|CHF)\b/i)?.[1]||(/\bEUR\b|€/.test(raw)?'EUR':/\bCHF\b/.test(raw)?'CHF':'EUR')).toUpperCase(),kind:/\bKauf\b/i.test(raw)?'entry':/\bGeld\b|\bBid\b/i.test(raw)?'quote':'details',direction:/\bCall\b|\bLong\b/i.test(raw)?'LONG':/\bPut\b|\bShort\b/i.test(raw)?'SHORT':'',time:(raw.match(/\b\d{2}[/.]\d{2}[/.]\d{4},?\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||'',entry:val('Kurs'),quantity:val('Anzahl'),feesChf:fallback.ok?fallback.feesChf??'':'',bid:val('Geld|Bid'),ask:val('Brief|Ask'),ko:val('BAR|KO|KO-Barriere'),strike:val('BP|Basispreis'),ratio:val('Bezugsverhältnis')};
}
function reviewed(v){
 if(!window.BobDegiro.validIsin(v.isin))return{ok:false,reason:'ISIN am Original korrigieren; eine unsichere OCR-ISIN wird nicht übernommen.'};
 if(v.currency&&!['EUR','CHF'].includes(v.currency))return{ok:false,reason:'Produktwährung EUR oder CHF wählen.'};
 const currency=v.currency||'EUR';
 const keys=['entry','quantity','feesChf','bid','ask','ko','strike','ratio'];
 for(const k of keys)if(String(v[k]??'').trim()!==''&&number(v[k])===null)return{ok:false,reason:'Ungültige Zahl: '+k};
 const lines=['ISIN '+v.isin,v.direction||'',v.time||'','Produktwährung '+currency];
 if(v.kind==='entry')lines.push('Auftrag Kauf','Ausführungsdatum '+v.time,'Anzahl '+v.quantity,'Kurs '+currency+' '+v.entry,'Gesamte Kosten CHF '+v.feesChf);
 else if(v.kind==='quote')lines.push('Geld '+currency+' '+v.bid,'Brief '+currency+' '+v.ask);
 else if(v.kind!=='details')return{ok:false,reason:'Bildtyp wählen.'};
 if(v.ko)lines.push('KO '+v.ko);if(v.strike)lines.push('Basispreis '+v.strike);if(v.ratio)lines.push('Bezugsverhältnis '+v.ratio);
 return parse(lines.join('\n'));
}
function merge(old,x,source){
 const out=JSON.parse(JSON.stringify(old||{isin:x.isin}));
 if(out.isin!==x.isin)throw Error('ISIN stimmt nicht überein');
 if(old&&(old.currency||'EUR')!==(x.currency||'EUR'))throw Error('Produktwährung widerspricht gespeicherten Belegen; keine Beträge ersetzt.');
 out.currency=x.currency||'EUR';
 if(x.kind==='entry'){
  if(out.entry&&JSON.stringify([out.entry.price,out.entry.quantity,out.entry.at])!==JSON.stringify([x.entry,x.quantity,x.time]))throw Error('Weiterer oder abweichender Kauf: Einstieg bleibt erhalten. Mehrere Ausführungen müssen gesondert zusammengeführt werden.');
  out.entry={price:x.entry,quantity:x.quantity,at:x.time,feesChf:x.feesChf,source,orderId:x.orderId};
 }
 if(x.kind==='quote'){
  const date=t=>{const m=String(t).match(/(\d{2})[/.](\d{2})[/.](\d{4}),?\s+(\d{2}):(\d{2})(?::(\d{2}))?/);return m?m[3]+m[2]+m[1]+m[4]+m[5]+(m[6]||''):'';};
  if(out.quote&&date(x.time)<date(out.quote.at))throw Error('Älteres Kursbild: bestehende Kursmomentaufnahme bleibt erhalten.');
  out.quote={bid:x.bid,ask:x.ask,at:x.time,source};
 }
 for(const k of ['direction','ko','strike','ratio'])if(x[k]!==null&&x[k]!==undefined)out[k]=x[k];return out;
}
// A confirmed screenshot may prepare observation, never a broker order.
const AUTO_KEY='bobConfirmedScreenshotSetupV1';
let automatic=null,automaticBusy=false,automaticStatus={state:'idle',message:'Screenshot hochladen. Bob ergänzt danach die verfügbaren Daten.'};
try{automatic=JSON.parse(localStorage.getItem(AUTO_KEY)||'null');}catch(_){}
function autoSave(){try{localStorage.setItem(AUTO_KEY,JSON.stringify(automatic));}catch(_){}}
function autoStatus(state,message){automaticStatus={state,message,at:new Date().toISOString()};if(typeof document!=='undefined')document.dispatchEvent(new Event('bob-trade-automation'));}
function screenshotDay(at){const m=String(at||'').match(/^(\d{2})[/.](\d{2})[/.](\d{4})/);return m?m[3]+'-'+m[2]+'-'+m[1]:null;}
function setupCandidate(t,today){
 if(!t?.entry||!window.BobDegiro.validIsin(t.isin)||!['EUR','CHF'].includes(t.currency)||!(t.entry.price>0)||!Number.isInteger(t.entry.quantity)||t.entry.quantity<=0)return {ok:false,reason:'Kaufpreis, Stückzahl, ISIN und Produktwährung am Original ergänzen.'};
 if(screenshotDay(t.entry.at)!==today)return {ok:false,reason:'Historischer Kauf: Bitte bestätigen, dass diese Position noch offen ist, und manuell erfassen.'};
 return {ok:true,key:JSON.stringify([t.isin,t.currency,t.entry.price,t.entry.quantity,t.entry.at]),isin:t.isin,currency:t.currency,entry:t.entry.price,quantity:t.entry.quantity,direction:t.direction||'',at:t.entry.at};
}
async function requestHelp(code){
 try{const r=await fetch('/api/assistance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code}),signal:AbortSignal.timeout(10000)});const x=await r.json();return r.ok&&x.ok===true;}catch(_){return false;}
}
function todayZurich(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich'}).format(new Date());}
function queueSetup(t){
 const candidate=setupCandidate(t,todayZurich());
 if(!candidate.ok){autoStatus('needs-user',candidate.reason);return;}
 if(automatic?.key===candidate.key&&['done','consumed'].includes(automatic.state)){autoStatus('done','Dieser Kauf wurde bereits verarbeitet. Er wird nicht erneut aktiviert.');return;}
 if(window.BobTradeSync?.current()?.active){autoStatus('active','Eine Position wird bereits überwacht. Der Screenshot ersetzt keinen laufenden Trade.');return;}
 automatic={...candidate,state:'pending',attempts:0,nextAt:0,createdAt:Date.now()};autoSave();runSetup();
}
async function runSetup(){
 if(automaticBusy||!automatic||automatic.state!=='pending'||Date.now()<automatic.nextAt)return;
 const task=automatic;
 if(Date.now()-task.createdAt>3600000||screenshotDay(task.at)!==todayZurich()){task.state='expired';autoSave();autoStatus('needs-user','Kauf blieb ohne bestätigte Überwachung. Bitte prüfen, ob die Position noch offen ist.');return;}
 if(window.BobTradeSync?.current()?.active){task.state='consumed';autoSave();return;}
 const field=k=>document.querySelector('[data-exit="'+k+'"]');
 const same=()=>['isin','currency','entry','quantity'].every(k=>field(k)&&(k==='entry'||k==='quantity'?Number(field(k).value)===task[k]:field(k).value.trim()===task[k]));
 if(!same()){task.state='conflict';autoSave();autoStatus('needs-user','Die Kaufangaben wurden geändert. Bitte die richtige Position bestätigen.');return;}
 automaticBusy=true;task.attempts++;autoStatus('checking','Kauf bestätigt. Bob prüft Produktdaten, Quellen und Stopp-/Zielplan automatisch …');
 try{
  // Reconcile server positions before attempting local observation setup.
  const response=await fetch('/api/real-trades/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('Serverabgleich noch offen');
  const server=await response.json();if(!Array.isArray(server.trades))throw Error('Serverabgleich unvollständig');
  if(server.trades.some(t=>t.active||t.snapshot?.recordOnly&&!t.snapshot?.consumed)){
   task.state='consumed';autoSave();autoStatus('checking','Ein gespeicherter Kauf ist vorhanden. Bob gleicht ihn ab; keine zweite Position wird angelegt.');return;
  }
  const values=await window.BobExitEstimate.automaticTradeReference();
  if(!values||!same()||automatic!==task)throw Error('Produktdaten oder Quellenprüfung noch offen');
  if(task.direction&&values.direction!==task.direction){task.state='conflict';autoSave();autoStatus('needs-user','Produktrichtung widerspricht dem bestätigten Kauf. Bitte Original prüfen.');return;}
  if(typeof window.loadData==='function')await window.loadData(true);
  if(!same()||automatic!==task||window.BobTradeSync?.current()?.active)throw Error('Position oder Eingaben haben sich geändert');
  // Consume BEFORE activation, so an interrupted page cannot reopen a closed trade.
  task.state='consumed';autoSave();
  await window.activateProductTrade(values);
  if(!window.BobTradeSync?.current()?.active)throw Error('Start nicht bestätigt');
  task.state='done';autoSave();autoStatus('done','Überwachung lokal eingerichtet. Serverbestätigung wird gesondert angezeigt.');
 }catch(_){
  if(automatic!==task)return;
  if(window.BobTradeSync?.current()?.active){task.state='done';autoSave();autoStatus('checking','Trade lokal aktiv. Bob prüft die Server-Synchronisierung.');}
  else{
   task.state='pending';task.nextAt=Date.now()+Math.min(300000,30000*2**Math.min(task.attempts-1,4));autoSave();
   let queued=false;if(task.attempts>=3)queued=await requestHelp('trade-setup-stalled');
   autoStatus('waiting',queued?'Datenprüfung noch offen. Technische KI-Prüfung vorgemerkt; Bob versucht es weiter.':'Datenprüfung noch offen. Bob versucht es automatisch erneut; Überwachung noch nicht bestätigt.');
  }
 }finally{automaticBusy=false;}
}

function init(){
 const exit=document.getElementById('bobExitEstimate');if(!exit||document.getElementById('bobTradeUpload'))return;
 const p=document.createElement('div');p.id='bobTradeUpload';p.className='card';p.innerHTML='<h3>Mein Trade · Screenshots</h3><p class="small">Kaufbestätigung einmal, Kursbilder bei Aktualisierung. Produktkopf/Details gemeinsam ergänzen. Jedes Bild braucht die ISIN. Originalzeiten bleiben erhalten. Speicherung auf diesem Gerät.</p><label for="trade-images">Trade erfassen / Kurs aktualisieren</label><input id="trade-images" type="file" accept="image/*" multiple><div id="trade-ocr-status" class="small"></div><label for="trade-select">Gespeichertes Produkt</label><select id="trade-select"></select><div id="trade-review"></div><div id="trade-result" class="small"></div>';exit.before(p);
 const research=document.createElement('button');research.dataset.tradeReferenceRetry='';research.textContent='Gold-/FX-Referenz zur Kurszeit suchen';research.addEventListener('click',()=>window.BobExitEstimate.researchReference());exit.querySelector('[data-exit-calculate]').before(research);
 const details=document.createElement('details');details.innerHTML='<summary>Produktbedingungen und Zeitbezug bestätigen</summary>';const grid=exit.querySelector('.grid');if(grid&&!grid.querySelector('#exit-entry'))details.append(grid);for(const el of [...exit.children])if(el.tagName==='LABEL'||el.tagName==='BR')details.append(el);exit.querySelector('h3').after(details);p.append(exit);exit.className='';
 let all={};try{all=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(_){}let drafts=[];
 const select=p.querySelector('select'),review=p.querySelector('#trade-review'),result=p.querySelector('#trade-result');
 const fill=(lookup=false)=>{const t=all[select.value];if(!t)return;const set=(k,v)=>{const e=exit.querySelector('[data-exit="'+k+'"]');if(e)e.value=v??'';};
  // A different product must never inherit another product's model/reference.
  for(const e of exit.querySelectorAll('[data-exit]')){if(e.type==='checkbox')e.checked=false;else e.value='';}
  const r=window.BobDegiro.exitReference?.(t.isin),catalog=PRODUCT_REFERENCES[t.isin];if(r)for(const [k,v]of Object.entries(r))set(k,v);
  set('isin',t.isin);set('currency',t.currency||'EUR');set('direction',t.direction);set('entry',t.entry?.price);set('quantity',t.entry?.quantity);set('ko',t.ko??r?.ko);set('strike',t.strike??r?.strike);set('ratio',t.ratio??r?.ratio??catalog?.ratio);
  if(t.quote){set('bid',t.quote.bid);set('source',t.quote.source);set('referenceAt',t.quote.at);set('goldReference','');set('fxReference','');set('fxScenario','');}
  const fields={entry:'Kaufbestätigung mit Preis und Stückzahl',quote:'Kursbild mit ISIN, Geld/Brief und Datum',direction:'Produktkopf mit Long/Short',ratio:'Produktdetails: Bezugsverhältnis',strike:'Produktdetails: Basispreis',ko:'Produktkopf: Barriere'};
  const missing=Object.entries(fields).filter(([k])=>!t[k]&&!(r&&r[k])&&!(catalog&&catalog[k])).map(([,v])=>v);
  result.innerHTML='<b>'+esc(t.isin)+'</b> · '+esc(t.direction||'Richtung offen')+'<br>Einstieg: '+(t.entry?esc(t.entry.price)+' '+esc(t.currency||'EUR')+' × '+esc(t.entry.quantity)+' · '+esc(t.entry.at):'offen')+(t.entry?.feesChf!==null&&t.entry?.feesChf!==undefined?'<br>Kaufgebühren: '+esc(t.entry.feesChf)+' CHF':'')+'<br>Kursmomentaufnahme: '+(t.quote?esc(t.quote.bid)+' '+esc(t.currency||'EUR')+' Geld · '+esc(t.quote.at):'offen')+(t.entry&&t.quote?'<br>Rechnerischer G/V vor Kosten und FX: '+((t.quote.bid-t.entry.price)*t.entry.quantity).toFixed(2)+' '+esc(t.currency||'EUR'):'')+'<br>'+esc(missing.length?'Benötigtes Bild: '+missing.join(' · '):'Produktnachweise vorhanden.')+(catalog?'<br>Bezugsverhältnis: '+esc(catalog.ratio)+' · '+esc(catalog.source)+' <a target="_blank" rel="noopener" href="'+esc(catalog.url)+'">Quelle</a>':'')+'<br>Für die Ausstiegsschätzung: Gold-/FX-Referenz in Produktwährung prüfen und Ziel/Stop übernehmen. Minutenzeiten sind keine sekundengenauen Echtzeitnachweise.';
  exit.querySelector('[data-exit-output]').textContent='Trade übernommen. Fehlende Referenzen prüfen; Verkaufskurse darunter schätzen.';
  exit.dispatchEvent(new Event('change',{bubbles:true}));
  window.BobExitEstimate.restoreReference();
  if(lookup&&t.quote)window.BobExitEstimate.researchReference();
 };
 const refresh=isin=>{select.innerHTML=Object.keys(all).map(id=>'<option>'+esc(id)+'</option>').join('');if(isin)select.value=isin;fill(!!isin);};select.addEventListener('change',fill);refresh();
 p.querySelector('input').addEventListener('change',async e=>{const files=[...e.target.files];autoStatus('checking','Bilder werden erkannt …');drafts=[];let saleSeen=false;review.innerHTML='';if(files.length>4){result.textContent='Bitte höchstens vier Bilder gleichzeitig auswählen.';return;}
  for(const file of files){try{const o=await window.BobDegiro.recognizeOcr(file,'trade-ocr-status');
   if(/\bVerkauf\b/i.test(o.data.text)&&!/\bKauf\b/i.test(o.data.text)){
    saleSeen=true;
    if(!window.BobTradeSale?.prepareFile)throw Error('Verkauf erkannt. Verkaufsprüfung unter Details öffnen.');
    await window.BobTradeSale.prepareFile(file);autoStatus('needs-user','Verkauf erkannt. Vorausgefüllten Beleg prüfen und den vollständigen Verkauf bestätigen.');continue;
   }
   drafts.push({source:file.name,raw:o.data.text});}catch(err){result.textContent='Bild '+file.name+': '+err.message;autoStatus('needs-user','Bild konnte nicht sicher zugeordnet werden. Bitte lesbares Original prüfen.');requestHelp('screenshot-import-failed');}}
  const fields=[['isin','ISIN'],['currency','Produktwährung EUR oder CHF'],['time','Originaldatum und Uhrzeit'],['entry','Kaufpreis in Produktwährung/Stück'],['quantity','Stückzahl'],['feesChf','Kaufgebühren CHF'],['bid','Geldkurs in Produktwährung'],['ask','Briefkurs in Produktwährung'],['ko','Angezeigte Barriere USD'],['strike','Basispreis USD'],['ratio','Bezugsverhältnis']];
  if(drafts.length)autoStatus('needs-user','Bilder erkannt. Kaufdaten am Original prüfen und bestätigen; danach übernimmt Bob die Einrichtung.');
  review.innerHTML=drafts.map((d,i)=>{const v=draft(d.raw);return '<fieldset data-trade-card="'+i+'"><legend>'+esc(d.source)+'</legend><label>Bildtyp<select data-review="kind"><option value="entry" '+(v.kind==='entry'?'selected':'')+'>Kaufbestätigung</option><option value="quote" '+(v.kind==='quote'?'selected':'')+'>Kursdaten</option><option value="details" '+(v.kind==='details'?'selected':'')+'>Produktdetails</option></select></label><label>Richtung<select data-review="direction"><option value="">Offen</option><option '+(v.direction==='LONG'?'selected':'')+'>LONG</option><option '+(v.direction==='SHORT'?'selected':'')+'>SHORT</option></select></label><div class="grid">'+fields.map(([k,l])=>'<label data-review-field="'+k+'">'+l+'<input data-review="'+k+'" value="'+esc(v[k])+'"></label>').join('')+'</div><div class="small">Leere oder unsichere Werte am Original ergänzen. Sekunden nicht erfinden. Barriere und Basispreis dürfen bei Produktdetails offen bleiben.</div><details><summary>Original-OCR-Text anzeigen</summary><pre style="white-space:pre-wrap">'+esc(d.raw)+'</pre></details></fieldset>';}).join('')+(drafts.length?'<label><input type="checkbox" id="trade-confirm"> ISIN, Preise, Stückzahl und Originalzeiten geprüft; ein gezeigter Kauf ist tatsächlich noch offen</label><button id="trade-save">Geprüfte Bilder übernehmen</button>':'');
  for(const card of review.querySelectorAll('[data-trade-card]')){const type=card.querySelector('[data-review="kind"]');const show=()=>{for(const el of card.querySelectorAll('[data-review-field]')){const k=el.dataset.reviewField;el.hidden=['entry','quantity','feesChf'].includes(k)?type.value!=='entry':['bid','ask'].includes(k)?type.value!=='quote':false;}};type.addEventListener('change',show);show();}
  review.querySelector('#trade-save')?.addEventListener('click',()=>{if(!review.querySelector('#trade-confirm').checked){result.textContent='Bitte erkannte Werte am Original prüfen und bestätigen.';return;}
   let next=JSON.parse(JSON.stringify(all)),last='',reviewedItems=[];try{for(const [i,d]of drafts.entries()){const card=review.querySelector('[data-trade-card="'+i+'"]'),values=Object.fromEntries([...card.querySelectorAll('[data-review]')].map(e=>[e.dataset.review,e.value.trim()])),x=reviewed(values);if(!x.ok)throw Error(d.source+': '+x.reason);reviewedItems.push(x);next[x.isin]=merge(next[x.isin],x,'DEGIRO-Screenshot: '+d.source);last=x.isin;}localStorage.setItem(KEY,JSON.stringify(next));all=next;refresh(last);review.innerHTML='';p.querySelector('#trade-ocr-status').textContent='Gespeichert. Einstieg bleibt bei Kursaktualisierungen erhalten.';
   if(!saleSeen&&reviewedItems.some(x=>x.kind==='entry')&&new Set(reviewedItems.map(x=>x.isin)).size===1)queueSetup(all[last]);
   else autoStatus('checking','Nachweise gespeichert. Vorhandene Überwachung wird weiter abgeglichen.');}catch(err){result.textContent=err.message;}});
 });
}
window.BobTradeUpload={parse,draft,reviewed,merge,init,setupCandidate,queueSetup,runSetup,status:()=>({...automaticStatus}),requestHelp};
if(typeof document!=='undefined'&&typeof setInterval==='function'){setInterval(runSetup,30000);window.addEventListener?.('online',runSetup);}if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();}
})();
