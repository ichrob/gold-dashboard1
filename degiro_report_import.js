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
  const h=rows[i];const isin=getIndex(h,['ISIN','ISIN-Code','ISIN Code']);
  const qty=getIndex(h,['Anzahl','Stückzahl','Stuckzahl','Quantity','Stücke','Stucke','Anzahl Stück','Number','Aantal']);
  if(isin>=0&&qty>=0){start=i;indexes={isin,qty};break;}
 }
 if(start<0)throw Error('Kein unterstützter DEGIRO-Bericht: Spalten ISIN und Anzahl/Quantity fehlen.');
 const h=rows[start], ix={
  ...indexes,
  name:getIndex(h,['Produkt','Product','Produktname','Product Name','Name','Beschreibung','Description']),
  currency:getIndex(h,['Währung','Wahrung','Currency','Valuta']),
  price:getIndex(h,['Kurs','Preis','Price','Schlusskurs','Closing price']),
  value:getIndex(h,['Wert','Market value','Marktwert','Value','Gesamtwert','Total value']),
  side:getIndex(h,['Kauf/Verkauf','Buy/Sell','Buy / Sell','Transaktion','Type','Art']),
  date:getIndex(h,['Datum','Date','Handelsdatum','Trade date'])
 };
 const kind=(ix.side>=0||ix.date>=0)?'transactions':'portfolio';
 const records=[],invalid=[];
 for(let i=start+1;i<rows.length;i++){
  const row=rows[i],isin=(row[ix.isin]||'').trim().toUpperCase();
  if(!isin)continue;
  if(!validISIN(isin)){invalid.push(i+1);continue;}
  const rawQty=(row[ix.qty]||'').trim();
  const qty=parseNumber(rawQty);
  if(qty===null){invalid.push(i+1);continue;}
  records.push({isin,quantity:qty,product:cell(row,ix.name),currency:cell(row,ix.currency),price:cell(row,ix.price),value:cell(row,ix.value),side:cell(row,ix.side),date:cell(row,ix.date)});
 }
 if(!records.length)throw Error('Keine gültigen ISIN- und Mengenzeilen im Export gefunden.');
 return {kind,records,invalidRows:invalid,source:'DEGIRO export (user-provided)',realtime:false,brokerVerified:false,ordersEnabled:false};
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
const api={parseRows,readReport,parseNumber,validISIN};
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
function mount(){
 const host=root.document.getElementById('bob-view-degiro');if(!host)return;
 const section=root.document.createElement('section');section.className='card';section.style.padding='16px';
 section.innerHTML='<h3>DEGIRO · Kontodaten lesen (Export)</h3><p>Offiziellen DEGIRO-Portfolio- oder Transaktionsbericht als CSV öffnen. Bob liest ihn nur auf diesem Gerät, ohne Server-Upload, Anmeldung oder Orderzugriff.</p><label for="dgExportFile">CSV-Datei aus DEGIRO auswählen</label><input id="dgExportFile" type="file" accept=".csv,text/csv,text/plain" style="display:block;width:100%;margin:12px 0"><p id="dgExportStatus" role="status">Noch keine Datei eingelesen.</p><div id="dgExportResults"></div><button id="dgExportClear" type="button">Eingelesene Daten entfernen</button><p class="small">DEGIRO: Portfolio → Export oder Inbox → Transaktionen → Export → CSV. Berichte sind historische Momentaufnahmen, keine Livekurse. Kein automatisches Kontosynchronisieren und keine Handelsfreigabe. Die Datei verlässt dieses Gerät nicht.</p>';
 host.append(section);
 const input=section.querySelector('#dgExportFile'),status=section.querySelector('#dgExportStatus'),out=section.querySelector('#dgExportResults');
 function clear(){input.value='';out.replaceChildren();status.textContent='Keine Daten gespeichert. Neue Datei auswählen.';}
 section.querySelector('#dgExportClear').addEventListener('click',clear);
 input.addEventListener('change',async()=>{
  out.replaceChildren();
  const file=input.files&&input.files[0];
  if(!file)return;
  try{
   if(file.size>2_000_000)throw Error('Datei größer als 2 MB.');
   const data=readReport(await file.text());
   status.textContent=(data.kind==='portfolio'?'Portfolio':'Transaktionen')+': '+data.records.length+' Zeilen gelesen; '+data.invalidRows.length+' Zeilen mit ungültigen ISIN-/Mengenangaben ausgelassen. Kein Live-Depotsync.';
   const table=root.document.createElement('table');table.style.width='100%';
   const header=root.document.createElement('tr');
   for(const name of ['ISIN','Produkt','Menge','Währung']){const th=root.document.createElement('th');th.textContent=name;header.append(th);}
   table.append(header);
   for(const rec of data.records.slice(0,1000)){
    const tr=root.document.createElement('tr');
    for(const value of [rec.isin,rec.product,rec.quantity,rec.currency]){const td=root.document.createElement('td');td.textContent=String(value);tr.append(td);}
    table.append(tr);
   }
   out.append(table);
   if(data.records.length>1000){const p=root.document.createElement('p');p.textContent='Nur die ersten 1.000 Zeilen dargestellt.';out.append(p);}
  }catch(err){status.textContent='Import nicht möglich: '+err.message;}
  finally{input.value='';}
 });
}
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
