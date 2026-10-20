/* DEGIRO user-export reader. Local browser parsing only: no broker HTTP, credentials or orders. */
(function(root){
'use strict';
function parseRows(text){
 if(typeof text!=='string'||text.length>2_000_000)throw Error('Datei ist leer oder über 2 MB groß.');
 text=text.replace(/^\uFEFF/,'');
 const first=(text.split(/\r?\n/).slice(0,12).find(line=>/ISIN/i.test(line))||text.split(/\r?\n/,1)[0]||'');
 const delimiter=[';',',','\t'].map(d=>({d,n:(first.match(new RegExp(d==='\t'?'\\t':d===';'?';':',','g'))||[]).length})).sort((a,b)=>b.n-a.n)[0];
 if(!delimiter||!delimiter.n)throw Error('Kein CSV-Trennzeichen gefunden.');
 const rows=[],row=[];let cell='',quoted=false;
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(quoted){
   if(ch==='"'&&text[i+1]==='"'){cell+='"';i++;}
   else if(ch==='"')quoted=false;
   else cell+=ch;
  }else if(ch==='"'){if(cell.trim())throw Error('Ungültige CSV-Anführungszeichen.');quoted=true;}
  else if(ch===delimiter.d){row.push(cell.trim());cell='';}
  else if(ch==='\n'||ch==='\r'){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(cell.trim());cell='';if(row.some(Boolean))rows.push(row.slice());row.length=0;}
  else cell+=ch;
  if(rows.length>10001)throw Error('Maximal 10.000 Zeilen pro Datei.');
 }
 if(quoted)throw Error('Nicht geschlossene Anführungszeichen.');
 row.push(cell.trim());if(row.some(Boolean))rows.push(row);
 if(rows.length<2)throw Error('Keine Datensätze gefunden.');
 return rows;
}
function normalize(s){return String(s||'').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/g,'');}
function getIndex(headers,aliases){const wanted=new Set(aliases.map(normalize));return headers.findIndex(x=>wanted.has(normalize(x)));}
function readReport(text){
 const rows=parseRows(text);let start=-1,indexes;
 for(let i=0;i<Math.min(rows.length,12);i++){
  const h=rows[i];const isin=getIndex(h,['ISIN','ISIN-Code','ISIN Code','Symbol/ISIN','Symbol / ISIN','Symbol / ISIN-Code']);
  const qty=getIndex(h,['Anzahl','Stückzahl','Stuckzahl','Quantity','Stücke','Stucke','Anzahl Stück','Number','Aantal']);
  if(isin>=0&&qty>=0){start=i;indexes={isin,qty};break;}
 }
 if(start<0)throw Error('Kein unterstützter DEGIRO-Bericht: Spalten ISIN und Anzahl/Quantity fehlen.');
 const h=rows[start], ix={
  ...indexes,
  name:getIndex(h,['Produkt','Product','Produktname','Product Name','Name','Beschreibung','Description']),
  currency:getIndex(h,['Währung','Wahrung','Currency','Valuta']),
  price:getIndex(h,['Kurs','Preis','Price','Schlusskurs','Schlußkurs','Closing price']),
  value:getIndex(h,['Wert','Market value','Marktwert','Value','Gesamtwert','Total value']),
  side:getIndex(h,['Kauf/Verkauf','Buy/Sell','Buy / Sell','Transaktion','Type','Art']),
  date:getIndex(h,['Datum','Date','Handelsdatum','Trade date'])
 };
 const kind=(ix.side>=0||ix.date>=0)?'transactions':'portfolio';
 // DEGIRO Swiss exports split "Wert" across currency + unlabeled amount,
 // followed by a separate "Wert in CHF" conversion column.
 const splitCurrencyValue=kind==='portfolio' && ix.currency<0 && ix.value>=0 &&
   ix.value+1<h.length && !String(h[ix.value+1]||'').trim() &&
   h.some(label=>/^wert in [A-Z]{3}$/i.test(String(label||'').trim()));
 if(splitCurrencyValue){ix.currency=ix.value;ix.value+=1;}
 const accountValueHeader=h.findIndex(label=>/^wert in [A-Z]{3}$/i.test(String(label||'').trim()));
 const accountCurrency=accountValueHeader>=0?String(h[accountValueHeader]).trim().slice(-3).toUpperCase():null;
 const records=[],invalid=[],cashBalances=[];
 for(let i=start+1;i<rows.length;i++){
  const row=rows[i],isin=(row[ix.isin]||'').trim().toUpperCase();
  if(!isin){
   // Cash rows lack an ISIN; keep them separate from security holdings.
   if(splitCurrencyValue && /^CASH\b/i.test(String(row[ix.name]||''))){
    const currency=cell(row,ix.currency),amount=parseNumber(row[ix.value]),
          accountValue=accountValueHeader>=0?parseNumber(row[accountValueHeader]):null;
    if(/^[A-Z]{3}$/.test(currency)&&amount!==null){
     cashBalances.push({currency,amount,accountValue,accountCurrency});
    }
   }
   continue;
  }
  if(!validISIN(isin)){invalid.push(i+1);continue;}
  const rawQty=(row[ix.qty]||'').trim();
  const qty=parseNumber(rawQty);
  if(qty===null){invalid.push(i+1);continue;}
  records.push({isin,quantity:qty,product:cell(row,ix.name),currency:cell(row,ix.currency),price:cell(row,ix.price),value:cell(row,ix.value),accountValue:accountValueHeader>=0?cell(row,accountValueHeader):'',side:cell(row,ix.side),date:cell(row,ix.date)});
 }
 if(!records.length)throw Error('Keine gültigen ISIN- und Mengenzeilen im Export gefunden.');
 return {kind,records,cashBalances,accountCurrency,invalidRows:invalid,source:'DEGIRO export (user-provided)',realtime:false,brokerVerified:false,ordersEnabled:false};
}
function validISIN(isin){
 if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))return false;
 const digits=isin.replace(/[A-Z]/g,ch=>String(ch.charCodeAt(0)-55));
 let sum=0;[...digits].reverse().forEach((ch,i)=>{const n=Number(ch)*(i%2?2:1);sum+=Math.floor(n/10)+n%10;});
 return sum%10===0;
}
function cell(row,idx){return idx<0?'':String(row[idx]||'').trim().slice(0,120);}
function parseNumber(raw){
 let s=String(raw).replace(/\s/g,'').replace(/\u00a0/g,'');
 if(!s||!/^[+-]?[\d.,]+$/.test(s))return null;
 const comma=s.lastIndexOf(','),dot=s.lastIndexOf('.');
 if(comma>=0&&dot>=0)s=comma>dot?s.replace(/\./g,'').replace(',','.'):s.replace(/,/g,'');
 else if(comma>=0)s=s.replace(',','.');
 else if((s.match(/\./g)||[]).length>1)s=s.replace(/\./g,'');
 const v=Number(s);return Number.isFinite(v)&&Math.abs(v)<1e10?v:null;
}

function node(doc,tag,className,content){
 const element=doc.createElement(tag);
 if(className)element.className=className;
 if(content!==undefined)element.textContent=String(content);
 return element;
}
function displayAmount(value,currency){
 return value?String(value)+(currency?' '+currency:''):'Nicht angegeben';
}
function renderResults(doc,out,data,onCopy){
 out.replaceChildren();
 if(data.cashBalances.length){
  const cash=node(doc,'section','dg-export-cash');
  cash.append(node(doc,'strong','','Bargeld im Export'));
  for(const entry of data.cashBalances){
   cash.append(node(doc,'div','',displayAmount(entry.amount.toFixed(2),entry.currency)));
  }
  out.append(cash);
 }
 const intro=node(doc,'p','dg-export-note',
  'Dies ist ein gespeicherter DEGIRO-Export, keine Live-Kontoverbindung. Die angezeigten Kurse sind keine ausführbaren Handelskurse.');
 out.append(intro);
 const list=node(doc,'div','dg-export-list');
 for(const rec of data.records.slice(0,250)){
  const card=node(doc,'article','dg-export-card');
  const name=node(doc,'h4','dg-export-product',rec.product||rec.name||'Wertpapier ohne Bezeichnung');
  card.append(name);
  const identity=node(doc,'div','dg-export-identity');
  identity.append(node(doc,'span','dg-export-isin',rec.isin));
  const copy=node(doc,'button','dg-export-copy','ISIN kopieren');
  copy.type='button';
  copy.setAttribute('aria-label','ISIN '+rec.isin+' kopieren');
  copy.addEventListener('click',()=>onCopy(rec.isin));
  identity.append(copy);
  card.append(identity);
  const fields=node(doc,'div','dg-export-fields');
  const values=[['Menge',String(rec.quantity)],['Währung',rec.currency||'Nicht angegeben'],
   ['Schlusskurs',displayAmount(rec.price,rec.currency)],
   ['Wert',displayAmount(rec.value,rec.currency)]];
  if(rec.accountValue && data.accountCurrency){
   values.push(['Wert in '+data.accountCurrency,displayAmount(rec.accountValue,data.accountCurrency)]);
  }
  for(const pair of values){
   const field=node(doc,'div','dg-export-field');
   field.append(node(doc,'span','dg-export-field-label',pair[0]));
   field.append(node(doc,'strong','dg-export-field-value',pair[1]));
   fields.append(field);
  }
  card.append(fields);
  if(/\bfaktor\b|\bfactor\b|constant leverage/i.test(rec.product||rec.name||'')){
   card.append(node(doc,'p','dg-export-factor','Faktorprodukt · kein Gold-Knock-out für Bobs Top-3-Auswahl'));
  }
  list.append(card);
 }
 out.append(list);
 if(data.records.length>250){
  out.append(node(doc,'p','dg-export-note','Es werden die ersten 250 von '+data.records.length+' Wertpapierpositionen angezeigt.'));
 }
}
const api={parseRows,readReport,parseNumber,validISIN,renderResults};
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
function mount(){
 const doc=root.document,host=doc.getElementById('bob-view-degiro');
 if(!host||doc.getElementById('bobDegiroReport'))return;
 const section=node(doc,'section','card');
 section.id='bobDegiroReport';
 section.style.padding='16px';
 section.style.minWidth='0';
 section.style.maxWidth='100%';
 section.style.boxSizing='border-box';
 const style=node(doc,'style','');
 style.textContent=[
 '#bobDegiroReport{overflow-wrap:anywhere}',
 '#bobDegiroReport .dg-export-pick{display:block;width:100%;min-height:44px;padding:10px 14px;margin:10px 0;border-radius:10px;cursor:pointer}',
 '#bobDegiroReport .dg-export-list{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;margin:12px 0}',
 '#bobDegiroReport .dg-export-card{box-sizing:border-box;min-width:0;width:100%;padding:14px;border:1px solid #cdd5da;border-radius:12px;overflow-wrap:anywhere}',
 '#bobDegiroReport .dg-export-product{font-size:16px;line-height:1.4;margin:0 0 10px;font-weight:650;overflow-wrap:anywhere}',
 '#bobDegiroReport .dg-export-identity{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px}',
 '#bobDegiroReport .dg-export-isin{font-size:14px;letter-spacing:.01em;overflow-wrap:anywhere;user-select:text}',
 '#bobDegiroReport .dg-export-copy{padding:7px 10px;min-height:36px;border-radius:8px;font-size:13px;cursor:pointer}',
 '#bobDegiroReport .dg-export-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}',
 '#bobDegiroReport .dg-export-field{display:flex;flex-direction:column;gap:2px;min-width:0}',
 '#bobDegiroReport .dg-export-field-label{font-size:12px;opacity:.74}',
 '#bobDegiroReport .dg-export-field-value{font-size:15px;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}',
 '#bobDegiroReport .dg-export-cash{padding:12px;border:1px solid #cdd5da;border-radius:10px;margin:10px 0}',
 '#bobDegiroReport .dg-export-factor,#bobDegiroReport .dg-export-note{font-size:13px;line-height:1.5;opacity:.85}',
 '#bobDegiroReport .dg-export-factor{margin:12px 0 0}',
 '@media(min-width:880px){#bobDegiroReport .dg-export-list{grid-template-columns:repeat(2,minmax(0,1fr))}}'
 ].join('\n');
 section.append(style);
 section.append(node(doc,'h3','','DEGIRO · Kontodaten lesen (Export)'));
 section.append(node(doc,'p','','CSV aus DEGIRO auswählen. Dein Depotbestand wird danach in Bob auf diesem Gerät gespeichert und unter „Produkte“ angezeigt, bis du ihn löschst oder durch einen neueren Portfolioexport ersetzt. Kein Upload zu Bobs Server.'));
 const select=node(doc,'button','dg-export-pick','CSV-Datei auswählen');
 select.id='dgExportPick';
 select.type='button';
 const input=node(doc,'input','');
 input.id='dgExportFile';
 input.type='file';
 input.accept='.csv,text/csv,text/plain';
 input.style.display='none';
 input.setAttribute('aria-label','DEGIRO-CSV-Datei');
 select.addEventListener('click',()=>input.click());
 section.append(select,input);
 const status=node(doc,'p','','Noch kein Export eingelesen.');
 status.id='dgExportStatus';
 status.setAttribute('role','status');
 status.setAttribute('aria-live','polite');
 section.append(status);
 const out=node(doc,'div','');out.id='dgExportResults';section.append(out);
 const clear=node(doc,'button','','Eingelesene Daten entfernen');
 clear.id='dgExportClear';
 clear.type='button';
 clear.disabled=true;
 section.append(clear);
 const goToAll=node(doc,'button','','Alle DEGIRO-Produkte in Bob ansehen');
 goToAll.type='button';
 goToAll.dataset.view='products';
 section.append(goToAll);
 section.append(node(doc,'p','small','DEGIRO: Portfolio → Export → CSV. Neuer vollständiger Portfolioexport ersetzt die vorherige gespeicherte Depotliste auf diesem Gerät. Handelsfreigabe, Gold-Knock-out-Rangliste und automatische Kontosynchronisation bleiben unverändert. Der CSV-Dateiname wird nach dem Einlesen zurückgesetzt.'));
 host.append(section);
 function reset(){
  try{
   root.BobDegiroPortfolio.clear(root.localStorage);
   root.BobDegiroPortfolio.refresh();
   root.BobDegiroAllProducts?.rebuild?.();
   input.value='';
   out.replaceChildren();
   clear.disabled=true;
   status.textContent='Gespeicherte DEGIRO-Depotprodukte gelöscht. Neue CSV-Datei auswählen.';
  }catch(err){status.textContent='Löschen fehlgeschlagen: '+err.message;}
 }
 clear.addEventListener('click',reset);
 // Restore holdings after reload. Restored CSV prices remain historical.
 try{
  const saved=root.BobDegiroPortfolio.load(root.localStorage);
  if(saved){
   renderResults(doc,out,saved,copyISIN);
   clear.disabled=false;
   status.textContent='✓ Gespeicherter DEGIRO-Depotstand: '+saved.records.length+
    ' Produkte · eingelesen '+new Date(saved.importedAt).toLocaleString('de-CH')+
    ' · keine Live-Kontoverbindung.';
  }
 }catch(_){status.textContent='Lokaler Depotstand nicht erreichbar. CSV-Datei erneut auswählen.';}

 async function copyISIN(isin){
  try{
   if(!root.navigator||!root.navigator.clipboard||!root.navigator.clipboard.writeText)throw Error('Clipboard unavailable');
   await root.navigator.clipboard.writeText(isin);
   status.textContent='ISIN kopiert: '+isin+'. Die bereits eingelesene Portfolioansicht bleibt erhalten.';
  }catch(_){
   status.textContent='ISIN konnte nicht automatisch kopiert werden. Du kannst die ISIN auf der Karte markieren.';
  }
 }
 input.addEventListener('change',async()=>{
  const file=input.files&&input.files[0];
  if(!file)return;
  out.replaceChildren();
  clear.disabled=true;
  status.textContent='CSV-Bericht wird auf diesem Gerät geprüft …';
  try{
   if(file.size>2_000_000)throw Error('Datei größer als 2 MB.');
   const data=readReport(await file.text());
   let stored=false,warning='';
   if(data.kind==='portfolio'){
    try{
     root.BobDegiroPortfolio.save(root.localStorage,data);
     root.BobDegiroPortfolio.refresh();
   root.BobDegiroAllProducts?.rebuild?.();
     stored=true;
    }catch(err){warning=err.message||'Lokale Speicherung nicht verfügbar';}
   }
   renderResults(doc,out,data,copyISIN);
   status.textContent=stored?
    '✓ '+data.records.length+' DEGIRO-Depotprodukte und '+data.cashBalances.length+
    ' Bargeldpositionen dauerhaft in Bob auf diesem Gerät übernommen. Unter „Produkte“ sichtbar. '+
    data.invalidRows.length+' Zeilen ausgelassen · kein Live-Depotsync.':
    data.kind==='transactions'?
     'Transaktionen gelesen, aber Depotbestand nicht ersetzt. Bitte den Portfolio-CSV-Export verwenden.':
     'CSV gelesen, aber NICHT gespeichert ('+warning+'). Alte Depotliste bleibt bestehen.';
   clear.disabled=!stored&&!root.BobDegiroPortfolio.load(root.localStorage);
  }catch(err){
   status.textContent='Import nicht möglich: '+err.message;
  }finally{
   // Allow the same file to be selected again; the visible button makes this clear.
   input.value='';
  }
 });
}
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
