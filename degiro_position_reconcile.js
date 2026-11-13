/* DEGIRO evidence comparison: local CSV snapshot + local transaction CSV + staged email.
   Never log raw emails, upload CSV, change real trades, submit orders, or claim live holdings. */
(function(root){
'use strict';
const STORE='bob.degiro.transactions.csv.v1', MAX_ROWS=5000, MAX_EMAILS=30;
const validIsin=x=>typeof x==='string'&&
  (root.BobDegiroPortfolio?.validIsin?.(x)===true ||
   (typeof require==='function'&&require('./degiro_portfolio_store.js').validIsin(x)===true));
const text=(x,n=120)=>String(x??'').trim().slice(0,n);
const amount=v=>{
 if(typeof v==='number')return Number.isFinite(v)?v:null;
 let s=text(v,64).replace(/[\u00a0\s’']/g,'').replace(/(?:EUR|CHF|€)/gi,'');
 if(s.includes(','))s=s.replace(/\./g,'').replace(',','.');
 const n=Number(s);return s&&Number.isFinite(n)?n:null;
};
const side=v=>/^(Kauf|Buy)$/i.test(text(v))?'BUY':/^(Verkauf|Sell)$/i.test(text(v))?'SELL':null;
const day=v=>{
 const s=text(v,32);
 let m=s.match(/^(\d{4})[-/](\d{2})[-/](\d{2})$/);
 if(m)return +m[2]>=1&&+m[2]<=12&&+m[3]>=1&&+m[3]<=31?s.slice(0,10).replace(/\//g,'-'):null;
 m=s.match(/^(\d{2})[.\-/](\d{2})[.\-/](\d{4})$/);
 if(m)return +m[2]>=1&&+m[2]<=12&&+m[1]>=1&&+m[1]<=31?m[3]+'-'+m[2]+'-'+m[1]:null;
 return null;
};
const clock=v=>{
 const m=text(v,20).match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
 if(!m||+m[1]>23||+m[2]>59||+(m[3]||0)>59)return null;
 return m[1].padStart(2,'0')+':'+m[2]+(m[3]?':'+m[3]:'');
};
const isoMs=v=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(v)?
 Date.parse(v):NaN;
function receiptLocal(r){
 if(typeof r?.executedLocal==='string'){
  const m=r.executedLocal.match(/^(\d{2})[.\-/](\d{2})[.\-/](\d{4})[ ,]+(\d{2}):(\d{2}):(\d{2})$/);
  if(m&&day(m[1]+'.'+m[2]+'.'+m[3])&&clock(m[4]+':'+m[5]+':'+m[6]))
   return {day:m[3]+'-'+m[2]+'-'+m[1],time:m[4]+':'+m[5]+':'+m[6],clockKind:'source-local'};
 }
 const ms=isoMs(r?.executedAt);
 if(!Number.isFinite(ms))return null;
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Zurich',
  year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',
  second:'2-digit',hourCycle:'h23'}).formatToParts(new Date(ms));
 const p=k=>parts.find(x=>x.type===k)?.value;
 const result={day:p('year')+'-'+p('month')+'-'+p('day'),
  time:p('hour')+':'+p('minute')+':'+p('second'),clockKind:'explicit-zone'};
 return day(result.day)&&clock(result.time)?result:null;
}
function normalTransactions(data,importedAt){
 if(data?.kind!=='transactions'||!Array.isArray(data.records)||!data.records.length||
   data.records.length>MAX_ROWS||!Number.isFinite(Date.parse(importedAt)))
  throw Error('Vollständigen DEGIRO-Transaktions-CSV-Export mit gültigem Importzeitpunkt wählen.');
 let incomplete=0;
 const rows=[];
 for(const original of data.records){
  const isin=text(original?.isin,12).toUpperCase(),
   rawQty=amount(original?.quantity),price=amount(original?.price),
   direction=side(original?.side),date=day(original?.date),time=clock(original?.time),
   currency=text(original?.currency,3).toUpperCase();
  // Broker exports may express a SALE as negative units; side label must
  // independently say SELL. Do not let a negative BUY silently flip direction.
  const qty=direction==='SELL'&&rawQty!==null?Math.abs(rawQty):rawQty;
  if(direction==='BUY'&&rawQty!==null&&rawQty<=0){incomplete++;continue;}
  if(!validIsin(isin)||!Number.isSafeInteger(qty)||qty<=0||
     !direction||!date||!['EUR','CHF'].includes(currency)||!price||price<=0){
   incomplete++;continue;
  }
  // Preserve the fee amount and the separately declared fee currency
  // only when both are explicitly present in the DEGIRO user-export.
  // Never infer 0 fees from missing cells or guess a fee currency.
  const feePresent=original.fee!==null&&original.fee!==undefined&&
   String(original.fee).trim()!=='';
  const fee=feePresent?amount(original.fee):null;
  const feeCurrency=text(original.feeCurrency,3).toUpperCase();
  const feeState=!feePresent?'not-provided':
   fee===null||Math.abs(fee)>1000000?'invalid':
   !['CHF','EUR','USD'].includes(feeCurrency)?'currency-unconfirmed':'reported';
  rows.push({isin,side:direction,quantity:qty,price,currency,date,time,
   fee:feeState==='reported'?fee:null,
   feeCurrency:feeState==='reported'?feeCurrency:null,feeState});
 }
 if(!rows.length)throw Error('Keine eindeutig lesbare Transaktion mit ISIN, Kauf/Verkauf, Anzahl, Kurs und Datum.');
 return {version:1,kind:'transactions',importedAt:new Date(importedAt).toISOString(),
  rows,incomplete:incomplete+(data.invalidRows?.length||0),
  csvOnly:true,accountSynced:false};
}
function saveTransactions(storage,data,now=new Date().toISOString()){
 if(!storage?.setItem||!storage?.getItem)throw Error('Lokaler Speicher fehlt.');
 const clean=normalTransactions(data,now);
 storage.setItem(STORE,JSON.stringify(clean));
 const verified=loadTransactions(storage);
 if(!verified||verified.importedAt!==clean.importedAt||verified.rows.length!==clean.rows.length)
  throw Error('Transaktions-CSV konnte nicht überprüft gespeichert werden.');
 notify();return verified;
}
function loadTransactions(storage){
 try{
  const raw=storage?.getItem?.(STORE);
  if(!raw||raw.length>1600000)return null;
  const x=JSON.parse(raw);
  if(x?.version!==1||x.kind!=='transactions'||x.csvOnly!==true||
    x.accountSynced!==false||!Number.isFinite(Date.parse(x.importedAt))||
    !Array.isArray(x.rows)||x.rows.length>MAX_ROWS)return null;
  // Revalidate storage on every read instead of trusting modified localStorage.
  return normalTransactions({kind:'transactions',records:x.rows.map(r=>({
   ...r,side:r.side==='BUY'?'Buy':r.side==='SELL'?'Sell':'',
   date:r.date,time:r.time})),invalidRows:[]},x.importedAt);
 }catch(_){return null;}
}
function clearTransactions(storage){
 storage?.removeItem?.(STORE);notify();
}
function notify(){
 if(root.document&&typeof root.Event==='function')
  root.document.dispatchEvent(new root.Event('bob-degiro-csv-changed'));
}
function stableMail(item){
 const r=item?.result||{},isin=text(r.isin,12).toUpperCase(),
  quantity=r.quantity,price=r.priceEur,kind=r.side,source=receiptLocal(r),
  digest=text(r.orderIdDigest,64);
 if(r.status!=='pending-review'||!validIsin(isin)||!['BUY','SELL'].includes(kind)||
   !Number.isSafeInteger(quantity)||quantity<=0||
   typeof price!=='number'||!Number.isFinite(price)||price<=0||!source)return null;
 return {isin,side:kind,quantity,price,currency:'EUR',date:source.day,time:source.time,
  digest:/^[a-f0-9]{64}$/.test(digest)?digest:null,
  orderTimeSource:source.clockKind,executedAt:Number.isFinite(isoMs(r.executedAt))?isoMs(r.executedAt):null};
}
// Existing Mein Trade screenshot review writes parsed BUY evidence into
// bobTradeEvidenceV1 only after the owner reviewed the OCR fields. We read
// its reduced values; no screenshot bytes and no new storage keys.
function screenshotPurchases(storage){
 let raw;
 try{raw=storage?.getItem?.('bobTradeEvidenceV1');}
 catch(_){return [];}
 if(!raw||raw.length>500000)return [];
 let data;try{data=JSON.parse(raw);}catch(_){return [];}
 if(!data||typeof data!=='object'||Array.isArray(data))return [];
 const entries=Object.entries(data).slice(0,100);
 const results=[];
 for(const [key,r] of entries){
  const isin=text(r?.isin||key,12).toUpperCase();
  const p=r?.entry;
  const quantity=Number(p?.quantity),price=Number(p?.price);
  const matched=String(p?.at||'').match(/^(\d{2})[.\-/](\d{2})[.\-/](\d{4})[, ]+(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if(!validIsin(isin)||key!==isin||!['EUR','CHF'].includes(r.currency)||
    !Number.isSafeInteger(quantity)||quantity<=0||!Number.isFinite(price)||price<=0||!matched)continue;
  const date=day(matched[1]+'.'+matched[2]+'.'+matched[3]);
  const time=clock(matched[4]+':'+matched[5]+(matched[6]?':'+matched[6]:''));
  if(!date||!time)continue;
  results.push({isin,side:'BUY',quantity,price,currency:r.currency,
   date,time,source:'reviewed-screenshot',hasSeconds:!!matched[6]});
 }
 return results;
}
// Previously user-confirmed SALE screenshots are stored in Bob's existing
// real-trade journal. Extract only the explicitly confirmed receipt.
function confirmedSaleScreenshots(trades){
 if(!Array.isArray(trades))return [];
 const result=[],seen=new Set();
 for(const row of trades.slice(0,150)){
  const r=row?.snapshot?.exitReceipt,p=row?.snapshot?.product;
  if(row?.snapshot?.closureSource!=='confirmed-screenshot'||r?.side!=='SELL')continue;
  const isin=text(r?.isin,12).toUpperCase(),quantity=r?.quantity,price=r?.price;
  const transactionId=text(r?.transactionId,80);
  if(!validIsin(isin)||p?.isin!==isin||!['EUR','CHF'].includes(r?.productCurrency)||
    !Number.isSafeInteger(quantity)||quantity<=0||!Number.isFinite(price)||price<=0||
    !/^[0-9a-f]{64}$/.test(text(r?.imageSha256,64))||!transactionId||seen.has(transactionId))continue;
  const execution=receiptLocal({executedLocal:r.executedLocal});
  if(!execution)continue;
  seen.add(transactionId);
  result.push({isin,side:'SELL',quantity,price,currency:r.productCurrency,
   date:execution.day,time:execution.time,hasSeconds:execution.time.length===8,
   source:'user-confirmed-sale-screenshot'});
 }
 return result;
}
function compare(csv,transactions,emailReport,now=Date.now(),screenshots=[]){
 const snapshot=csv?.kind==='portfolio'&&Array.isArray(csv.records)&&
  Number.isFinite(Date.parse(csv.importedAt))?csv:null;
 const journal=transactions?.kind==='transactions'&&Array.isArray(transactions.rows)?transactions:null;
 const inbox=Array.isArray(emailReport?.items)?emailReport.items.slice(0,MAX_EMAILS):[];
 const rows=new Map(),allMail=[];
 const ensure=isin=>{
  if(!rows.has(isin))rows.set(isin,{isin,csvQuantity:null,tradeRows:0,
   matched:0,partialMatches:0,unmatched:0,ambiguous:0,duplicateMails:0,
   emailBuys:0,emailSells:0,emailNet:0,csvAfterEmailUnknown:true,
   screenshotBuys:0,screenshotSells:0,screenshotMailMatched:0,screenshotCsvMatched:0,
   screenshotUnmatched:0,screenshotTimeUncertain:0,
   csvFeeRows:0,csvFeeUnknown:0,matchedFeeRows:0,matchedFeesByCurrency:{}});
  return rows.get(isin);
 };
 if(snapshot)for(const r of snapshot.records){
  const isin=text(r?.isin,12).toUpperCase();
  if(!validIsin(isin)||!Number.isFinite(Number(r.quantity)))continue;
  ensure(isin).csvQuantity=Number(r.quantity);
 }
 const journalRows=[];
 if(journal)for(const r of journal.rows){
  const isin=text(r?.isin,12).toUpperCase();if(!validIsin(isin))continue;
  const out=ensure(isin);out.tradeRows++;
  if(r.feeState==='reported')out.csvFeeRows++;else out.csvFeeUnknown++;
  journalRows.push({...r,_used:false});
 }
 let invalidMail=0,anonymous=0;
 const groups=new Map();
 for(const item of inbox){
  const r=stableMail(item);
  if(!r){if(item?.result?.status==='pending-review')invalidMail++;continue;}
  const out=ensure(r.isin);
  if(!r.digest){out.ambiguous++;anonymous++;continue;}
  if(!groups.has(r.digest))groups.set(r.digest,[]);
  groups.get(r.digest).push(r);
 }
 for(const [digest,occurrences] of groups){
  const first=occurrences[0],row=ensure(first.isin);
  const identical=occurrences.every(x=>JSON.stringify([x.isin,x.side,x.quantity,x.price,x.date,x.time])===
   JSON.stringify([first.isin,first.side,first.quantity,first.price,first.date,first.time]));
  if(!identical){
   for(const x of occurrences)ensure(x.isin).ambiguous++;
   continue; // Same order ID with potentially distinct partial fills: no invented net inventory.
  }
  row.duplicateMails+=occurrences.length-1;
  if(first.side==='BUY')row.emailBuys+=first.quantity;
  else row.emailSells+=first.quantity;
  allMail.push(first);
 }
 for(const mail of allMail){
  const out=ensure(mail.isin);
  const candidates=journalRows.filter(x=>!x._used&&x.isin===mail.isin&&
   x.side===mail.side&&x.quantity===mail.quantity&&x.currency==='EUR'&&
   Math.abs(x.price-mail.price)<=0.0001&&x.date===mail.date);
  // Missing or truncated time gives evidence similarity, not an exact execution pair.
  const exact=candidates.filter(x=>x.time?.length===8&&x.time===mail.time);
  if(exact.length===1){
   exact[0]._used=true;out.matched++;
   // Unique source-to-email match only. Preserve signed original amounts
   // by currency; never claim this predicts another order's fees.
   if(exact[0].feeState==='reported'){
    out.matchedFeeRows++;
    const ccy=exact[0].feeCurrency;
    out.matchedFeesByCurrency[ccy]=(out.matchedFeesByCurrency[ccy]||0)+exact[0].fee;
   }
  }else if(exact.length>1){out.ambiguous++;}
  else if(candidates.length===1){out.partialMatches++;}
  else if(candidates.length>1){out.ambiguous++;}
  else out.unmatched++;
  if(snapshot&&mail.executedAt!==null&&mail.executedAt>Date.parse(snapshot.importedAt))
   out.csvAfterEmailUnknown=false;
 }
 // Screenshots corroborate original purchase evidence, but never add
 // quantities to holdings, manufacture a sale or replace actual broker fills.
 for(const shot of (Array.isArray(screenshots)?screenshots.slice(0,100):[])){
  if(!['BUY','SELL'].includes(shot?.side)||!validIsin(shot.isin)||
    !Number.isSafeInteger(shot.quantity)||shot.quantity<=0||
    !Number.isFinite(shot.price)||shot.price<=0||!day(shot.date)||!clock(shot.time))continue;
  const out=ensure(shot.isin);
  if(shot.side==='BUY')out.screenshotBuys++;else out.screenshotSells++;
  const same=x=>x.isin===shot.isin&&x.side===shot.side&&x.quantity===shot.quantity&&
   x.currency===shot.currency&&Math.abs(x.price-shot.price)<=0.0001&&x.date===shot.date;
  const matchesCsv=journalRows.filter(same);
  const matchesMail=allMail.filter(same);
  // The original screenshot can have only minute precision. Then a
  // match is a hint rather than a verified one-to-one execution.
  if(!shot.hasSeconds||shot.time.length!==8){
   out.screenshotTimeUncertain++;continue;
  }
  if(matchesCsv.filter(x=>x.time===shot.time&&x.time.length===8).length===1)
   out.screenshotCsvMatched++;
  if(matchesMail.filter(x=>x.time===shot.time).length===1)
   out.screenshotMailMatched++;
  if(!matchesCsv.some(x=>x.time===shot.time) &&
     !matchesMail.some(x=>x.time===shot.time))out.screenshotUnmatched++;
 }
 for(const out of rows.values()){
  out.emailNet=out.emailBuys-out.emailSells;
  out.state=out.ambiguous?'needs-review':
   !snapshot?'csv-missing':
   !journal?(out.screenshotMailMatched?'screenshot-mail-corroborated':'transactions-optional'):
   out.matched?'partial-verified':
   (out.unmatched||out.partialMatches)?'unreconciled':
   'csv-only';
 }
 return {status:emailReport?.configured===true?'observed':'email-not-configured',
  snapshotAt:snapshot?.importedAt||null,
  transactionImportAt:journal?.importedAt||null,
  mailWindowLimited:true,sourceComplete:false,brokerCurrent:false,activeTradesModified:false,
  invalidMail,anonymous,items:[...rows.values()].sort((a,b)=>a.isin.localeCompare(b.isin)),
  note:'E-Mail-Ausschnitt (max. 30), CSV-Importzeit ist nicht der DEGIRO-Exportzeitpunkt. Gebühren aus Original-CSV sind nur historische, unter Umständen unvollständige Angaben. Fehlende Werte bedeuten nicht null Gebühren. Keine vollständige Transaktionshistorie, kein Live-Depot- oder Orderkostennachweis.'};
}
function mount(){
 if(!root.document||root.document.getElementById('bobPositionReconcile'))return;
 const doc=root.document,host=doc.getElementById('bobTradeUpload')||
  doc.getElementById('bobExitEstimate')||doc.getElementById('bob-view-trade');
 if(!host?.parentNode)return;
 const wrapper=doc.createElement('details');wrapper.id='bobPositionReconcile';
 wrapper.style.cssText='margin:12px 0;padding:13px;border:1px solid #cbd5e1;border-radius:13px;background:#fff';
 const title=doc.createElement('summary');title.textContent='Positionsabstimmung · DEGIRO CSV + Bestätigungsmails';
 const explain=doc.createElement('p');explain.className='small';
 explain.textContent='Bestehende Quellen: Portfolio-CSV, AgentMail-Bestätigungen und geprüfte Mein-Trade-Screenshots. Transaktions-CSV ist eine optionale Zusatzprüfung. CSV bleibt auf diesem Gerät, E-Mail-Belege werden nur lesend verglichen. Keine Brokerorders oder automatischen Bestandsänderungen.';
 const refresh=doc.createElement('button');refresh.type='button';refresh.textContent='CSV und E-Mail jetzt abgleichen';
 const status=doc.createElement('p');status.className='small';status.setAttribute('role','status');
 const list=doc.createElement('div');wrapper.append(title,explain,refresh,status,list);host.after(wrapper);
 let inbox=null,saleScreenshots=[],busy=false,lastRead=0;
 const row=(parent,value,strong=false)=>{
  const el=doc.createElement(strong?'strong':'p');el.className=strong?'':'small';
  el.textContent=value;parent.append(el);
 };
 function paint(){
  let csv=null,transactions=null;
  try{csv=root.BobDegiroPortfolio?.load(root.localStorage)||null;
      transactions=loadTransactions(root.localStorage);}catch(_){}
  let screenshots=[];
  try{screenshots=screenshotPurchases(root.localStorage);}catch(_){}
  const report=compare(csv,transactions,inbox,Date.now(),screenshots.concat(saleScreenshots));
  list.replaceChildren();
  row(list,report.snapshotAt?'Portfolio-CSV importiert: '+new Date(report.snapshotAt).toLocaleString('de-CH'):
   'Portfolio-CSV fehlt. Unter Mehr → DEGIRO den Portfolioexport einlesen.');
  row(list,report.transactionImportAt?'Transaktions-CSV importiert: '+new Date(report.transactionImportAt).toLocaleString('de-CH'):
   'Transaktions-CSV optional: Mit Portfolio-CSV, E-Mail und geprüftem Screenshot ist bereits ein eingeschränkter Abgleich möglich.');
  row(list,inbox?.configured?'E-Mail-Weiterleitung als konfiguriert gemeldet; Belege bleiben ungeprüfte Beobachtungen.':
   'E-Mail-Eingang nicht konfiguriert oder noch nicht abgefragt.');
  row(list,report.note);
  for(const r of report.items.slice(0,35)){
   const card=doc.createElement('div');card.style.cssText='margin:9px 0;padding:10px;border:1px solid #e2e8f0;border-radius:10px';
   row(card,r.isin,true);
   row(card,'CSV-Bestand: '+(r.csvQuantity===null?'nicht vorhanden':r.csvQuantity+' Stück')+
    ' · Transaktions-CSV: '+r.tradeRows+' Zeilen');
   row(card,'E-Mail-Ausführungen (begrenzter Ausschnitt): Kauf '+r.emailBuys+
    ', Verkauf '+r.emailSells+' · Differenz '+r.emailNet+' Stück');
   row(card,'Geprüfte Screenshots: Kauf '+r.screenshotBuys+', Verkauf '+r.screenshotSells+
    ' · passt zu Mail: '+r.screenshotMailMatched+
    ' · passt zu Transaktions-CSV: '+r.screenshotCsvMatched+
    ' · unklarer Zeitbezug: '+r.screenshotTimeUncertain+
    ' · nicht zuordenbar: '+r.screenshotUnmatched);
   if(r.tradeRows){
    const matched=Object.entries(r.matchedFeesByCurrency).map(([ccy,v])=>
     v.toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:4})+' '+ccy
    ).join(' / ');
    row(card,'Historische DEGIRO-CSV-Gebührenangaben: '+r.csvFeeRows+
     ' mit Betrag und Originalwährung, '+r.csvFeeUnknown+
     ' ohne vollständigen Gebührenbeleg. Eindeutig zu Ausführungsmail zugeordnet: '+
     r.matchedFeeRows+(matched?' · Originalwerte mit Vorzeichen: '+matched:'')+
     '. Keine bestätigten künftigen Orderkosten und kein Nachweis gebührenfreier Orders.');
   }
   row(card,'Eindeutige Zeilenpaare CSV ↔ Mail: '+r.matched+
    ' · nur ähnlich: '+r.partialMatches+
    ' · nicht zugeordnet: '+r.unmatched+
    ' · mehrdeutig: '+r.ambiguous+
    (r.duplicateMails?' · doppelte Mails ignoriert: '+r.duplicateMails:''));
   if(!r.csvAfterEmailUnknown)row(card,'Mindestens eine Mailausführung ist neuer als der CSV-Import: neuen Portfolioexport prüfen.');
   else row(card,r.matched?
    'Übereinstimmende Ausführungsdaten. Bestand trotzdem nicht als live bestätigt.':
    'Noch kein ausreichender Ausführungsabgleich. Keine Positionsänderung.');
   list.append(card);
  }
  if(report.items.length>35)row(list,'Weitere Positionen nicht angezeigt; vollständigen CSV-Ausschnitt prüfen.');
  if(!report.items.length)row(list,'Noch kein abgleichbarer Depotbestand oder Mailbeleg.');
  if(report.invalidMail||report.anonymous)row(list,
   report.invalidMail+' unvollständige Ausführungsmails und '+report.anonymous+
   ' Mails ohne eindeutige Orderkennung bleiben in manueller Prüfung.');
 }
 async function load(){
  if(busy||doc.hidden||!wrapper.open)return;
  busy=true;refresh.disabled=true;status.textContent='Aktuelle gespeicherte Mailbelege werden gelesen …';
  try{
   const res=await fetch('/api/trade-email/read',{method:'POST',credentials:'same-origin',
    cache:'no-store',headers:{'Content-Type':'application/json'},body:'{}'});
   if(!res.ok)throw Error('Mailbericht nicht erreichbar ('+res.status+')');
   const data=await res.json();
   if(!Array.isArray(data?.items))throw Error('Mailbericht unvollständig');
   inbox={configured:data.configured===true,items:data.items.slice(0,MAX_EMAILS)};
   // Optional read of previously confirmed sale screenshots. A failure here
   // cannot block the email/CSV reconciliation; previous observations are
   // discarded instead of claiming they are current.
   saleScreenshots=[];
   try{
    const receiptResponse=await fetch('/api/real-trades/read',{method:'POST',credentials:'same-origin',
     cache:'no-store',headers:{'Content-Type':'application/json'},body:'{}'});
    if(receiptResponse.ok){
     const receiptData=await receiptResponse.json();
     saleScreenshots=confirmedSaleScreenshots(receiptData?.trades);
    }
   }catch(_){}
   lastRead=Date.now();status.textContent='Abgleich geprüft '+new Date(lastRead).toLocaleTimeString('de-CH')+
    ' · CSV und E-Mails bleiben Belege, keine Live-Depotabfrage.';
  }catch(_){inbox=null;status.textContent='E-Mail-Eingang derzeit nicht erreichbar. CSV bleibt erhalten; keine Bestandsbestätigung.';}
  finally{busy=false;refresh.disabled=false;paint();}
 }
 refresh.addEventListener('click',load);
 wrapper.addEventListener('toggle',()=>{if(wrapper.open){paint();load();}});
 doc.addEventListener('bob-degiro-csv-changed',()=>{if(wrapper.open)paint();});
 doc.addEventListener('bob-trade-evidence-changed',()=>{if(wrapper.open)paint();});
 root.addEventListener?.('storage',e=>{if(e.key===STORE||e.key===root.BobDegiroPortfolio?.KEY)if(wrapper.open)paint();});
 root.setInterval?.(()=>{if(wrapper.open&&!doc.hidden&&Date.now()-lastRead>=60000)load();},60000);
 paint();
}
const api={STORE,normalTransactions,saveTransactions,loadTransactions,clearTransactions,
 screenshotPurchases,confirmedSaleScreenshots,receiptLocal,stableMail,compare,mount};
root.BobDegiroPositionReconcile=api;
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);
else mount();
})(typeof window!=='undefined'?window:globalThis);
