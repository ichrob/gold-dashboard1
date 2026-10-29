'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const c={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),c);const b=c.window.BobDegiro;
function id(n){const base='DE000ZZ'+String(n).padStart(4,'0');for(let d=0;d<10;d++)if(b.validIsin(base+d))return base+d;throw Error('id');}
const a=id(1),z=id(2);
const today=Date.parse('2026-10-23T11:00:00Z'),yesterday={storedAt:'2026-10-22T10:00:00Z',files:[{name:'old.png',blob:'old-blob'}]};
const sameDay={storedAt:'2026-10-23T10:00:00Z',files:[{name:'first.png',blob:'first-blob'}]};
assert.equal(b.listAppendSourceFiles('append',[],sameDay,today).length,1);
assert.equal(b.listAppendSourceFiles('append',[],yesterday,today),null,'do not merge prior-day list');
assert.equal(b.listAppendSourceFiles('replace',[],sameDay,today).length,0,'replacement starts fresh');
assert.equal(b.listAppendSourceFiles('append',[{name:'pending.png'}],yesterday,today)[0].name,'pending.png','pending batch takes priority');
assert.equal(b.listAppendSourceFiles('append',[],null,today),null,'append requires existing images');

const row=(isin=a,amount='4012.25',currency='EUR')=>`SG Gold Turbo BEST Open-End Call BAR ${amount} BP\n${amount} Bv 10 | ${isin}\nSociete Generale OTC ${currency} (K) (V)`;
const parsed=b.parseDegiroListRow(row());assert(parsed.listRow.complete);assert.equal(parsed.direction,'LONG');assert.equal(parsed.listRow.ko,4012.25);assert.equal(parsed.listRow.ratio,.1);assert.equal(parsed.leverage,'');assert.equal(parsed.price,'');assert.equal(parsed.listRow.sourceTime,null);
const tomorrow=b.parseDegiroListRow(row(a,'4018,37','CHF'));assert.equal(tomorrow.listRow.ko,4018.37);assert.equal(tomorrow.listRow.currency,'CHF');
assert.equal(b.agreedDegiroListRow([row(),row(a,'4013.00')]),null,'conflicting numbers cannot be confirmed');
assert.equal(b.agreedDegiroListRow([row(),row(z)]),null,'different valid IDs cannot vote together');
assert.equal(b.agreedDegiroListRow([row()]),null,'one pass is not enough');
assert(b.agreedDegiroListRow([row(),row(),row(a,'4013.00')]).listRow.crossChecked);
assert.equal(b.agreedDegiroListRow([row(),row(),row(a,'4013.00'),row(a,'4013.00')]),null);
// Fragmented mobile OCR: no single reading has all columns, but every
// required field has two matching observations from the same image.
const noVenue=row().replace('Societe Generale OTC EUR','Societe Generale OTC');
const noStrike=row().replace('BP','XX');
const noRatio=row().replace('Bv 10','Bv O');
assert(!b.parseDegiroListRow(noVenue).listRow.complete);
assert(!b.parseDegiroListRow(noStrike).listRow.complete);
assert(!b.parseDegiroListRow(noRatio).listRow.complete);
const rescued=b.agreedDegiroListRow([noVenue,noStrike,noRatio]);
assert(rescued?.listRow.complete,'two observations per field can safely complete one row');
assert.equal(rescued.listRow.ko,4012.25);
assert.equal(rescued.listRow.strike,4012.25);
assert.equal(rescued.listRow.venue,'Societe Generale OTC');
assert.equal(rescued.listRow.ratio,.1);
assert.equal(b.agreedDegiroListRow([noVenue,noStrike]),null,'one observed strike is insufficient');
assert.equal(b.agreedDegiroListRow([noVenue+' FAKTOR',noStrike+' FAKTOR',noRatio+' FAKTOR']),null,'factor products stay excluded');
assert.equal(b.agreedDegiroListRow([noVenue,noStrike,row(z).replace('Bv 10','Bv O')]),null,'never mix different identifiers');
assert.equal(b.agreedDegiroListRow([
  noVenue,noStrike,noRatio,
  row(a,'4013.00').replace('Societe Generale OTC EUR','Societe Generale OTC'),
  row(a,'4013.00').replace('BP','XX'),
  row(a,'4013.00').replace('Bv 10','Bv O')
]),null,'two independently confirmed different KO values must not be merged');

const mini=`BNP GOLD Mini Long SL 3700.25 STR 3650.75 R\n10 | ${a}\nBNP OTC EUR K V`;
const m=b.parseDegiroListRow(mini);assert.equal(m.listRow.ko,3700.25);assert.equal(m.listRow.strike,3650.75);assert.equal(m.listRow.ratio,.1);

// Text manually transcribed from the two October 23 DEGIRO screenshots. These
// are parser tests only, NOT a claim that browser OCR read the original pixels.
const secondImageRows=[
 'SG Gold Knock-Out Warrant Open End Put BAR 4521.97 BP 4521.97 Bv 10 | DE000FG34XV8\nSociete Generale OTC CHF K V',
 'BNP GOLD Mini Long SL 3684.6673 STR 3612.4189 R 10 | DE000PJ8APE4\nBNP OTC EUR K V',
 'SG Gold Turbo Classic Call BAR 3980 BP 3980 Bv 10 20/11/2026 | DE000FG4TJL6\nSociete Generale OTC EUR K V',
 'SG Gold Knock-Out Warrant Put BAR 4400 BP 4400 Bv 10 19/03/2027 | DE000FG8NHQ3\nSociete Generale OTC CHF K V',
 'SG Gold Turbo BEST Open-End Put BAR 4225.31 BP 4225.31 Bv 10 | DE000FG7Q280\nSociete Generale OTC EUR K V'
];
assert.equal(secondImageRows.length,5);
for(const txt of secondImageRows){
 const p=b.parseDegiroListRow(txt);
 assert(p?.listRow.complete, 'second DEGIRO screenshot row must parse: '+txt);
 assert(b.validIsin(p.isin));
}
// Reproduce the OCR defect from the actual second row (one targeted
// 2x crop, PSM 6): "DEOOOPU8APE4" is not a valid ISIN, while the pixels
// show DE000PJ8APE4. Scope J/U repair to exactly that verified screenshot.
const observedMiniOcr='BNP GOLD Mini Long SL 3684.6673 STR 3612.4189 R\\n10 | DEOOOPU8APE4\\nBNP OTC EUR CK )(v)'.replaceAll('\\n','\n');
const correctedMini=b.parseDegiroListRow(observedMiniOcr);
assert.equal(correctedMini?.isin,'DE000PJ8APE4');
assert.equal(correctedMini?.originalIsin,'DEOOOPU8APE4');
assert(correctedMini?.identityCorrection?.includes('J/U'));
assert(correctedMini?.listRow.complete);
assert.equal(correctedMini?.listRow.ko,3684.6673);
assert.equal(correctedMini?.listRow.strike,3612.4189);
assert.equal(correctedMini?.listRow.ratio,0.1);
assert.equal(b.agreedDegiroListRow([observedMiniOcr,observedMiniOcr]).isin,'DE000PJ8APE4');
// 26 October original shows the same reviewed ISIN with CHANGED SL/STR.
// Neither last Friday's static values nor a stale issuer quote may overwrite it.
const currentMiniOcr=observedMiniOcr.replace('3684.6673','3687.0930').replace('3612.4189','3614.7971');
const currentMini=b.parseDegiroListRow(currentMiniOcr);
assert.equal(currentMini?.isin,'DE000PJ8APE4','Monday values must retain the known reviewed J/U identity');
assert.equal(currentMini?.listRow?.ko,3687.0930);
assert.equal(currentMini?.listRow?.strike,3614.7971);
assert.equal(currentMini?.listRow?.complete,true);
assert.equal(currentMini?.listRow?.isExecutableQuote,false);
assert.equal(currentMini?.listRow?.sourceTime,null);
assert.equal(b.agreedDegiroListRow([currentMiniOcr,currentMiniOcr])?.isin,'DE000PJ8APE4');
assert.equal(b.agreedDegiroListRow([observedMiniOcr,currentMiniOcr]),null,'never blend dated KO/STR values across observations');
assert.equal(b.agreedDegiroListRow([currentMiniOcr,currentMiniOcr.replace('3687.0930','3687.0931')]),null,'one mismatching original term must fail');
for(const conflicting of [
 observedMiniOcr.replace('BNP OTC EUR','BNP OTC CHF'),
 observedMiniOcr.replace('Mini Long','Mini Short'),
 observedMiniOcr.replace(/R\s+10/,'R 20'),
 observedMiniOcr.replace('BNP GOLD','SG GOLD'),
 observedMiniOcr.replace('3684.6673','0.0000'),
 observedMiniOcr.replace('3612.4189','4000.0000'),
 observedMiniOcr.replace('3612.4189','3612.418')
])assert.notEqual(b.parseDegiroListRow(conflicting)?.isin,'DE000PJ8APE4','Never correct a known alias without coherent current broker row');
assert.equal(b.agreedDegiroListRow([observedMiniOcr,observedMiniOcr.replace('DEOOOPU8APE4','DE000FG8NHQ3')]),null,'different valid product identifiers cannot be combined');
// Screenshot 1000075082.jpg, row two: full-row OCR can damage the
// title/SL/STR while separately cropped title and OTC footer stay readable.
// Two independent OCR passes of BOTH regions must agree before admission.
const isolatedMiniHead='BNP GOLD Mini Long SL 3684.6673 STR 3612.4189 R\n10 | DEOOOPU8APE4';
const isolatedMiniFooter='BNP OTC EUR (K) (V)';
const compositeMini=b.segmentedDegiroListReadings([isolatedMiniHead,isolatedMiniHead],
 [isolatedMiniFooter,isolatedMiniFooter]);
assert.equal(compositeMini.length,2);
const joinedMini=b.agreedDegiroListRow(compositeMini);
assert.equal(joinedMini?.isin,'DE000PJ8APE4');
assert.equal(joinedMini?.direction,'LONG');
assert.equal(joinedMini?.listRow?.venue,'BNP OTC');
assert.equal(joinedMini?.listRow?.ko,3684.6673);
assert.equal(joinedMini?.listRow?.strike,3612.4189);
assert.equal(b.segmentedDegiroListReadings([isolatedMiniHead],[isolatedMiniFooter,isolatedMiniFooter]).length,0);
assert.equal(b.segmentedDegiroListReadings([isolatedMiniHead,isolatedMiniHead],[isolatedMiniFooter]).length,0);
assert.equal(b.segmentedDegiroListReadings([isolatedMiniHead,isolatedMiniHead],[isolatedMiniFooter,'BNP OTC CHF K V']).length,0,'mismatched currency rejected before consensus');
assert.equal(b.agreedDegiroListRow(b.segmentedDegiroListReadings(
 [isolatedMiniHead,isolatedMiniHead],[isolatedMiniFooter,'BNP OTC CHF K V'])),null);
assert.equal(b.agreedDegiroListRow(b.segmentedDegiroListReadings(
 [isolatedMiniHead,isolatedMiniHead.replace('3684.6673','3684.6674')],
 [isolatedMiniFooter,isolatedMiniFooter])),null);
assert.equal(b.agreedDegiroListRow(b.segmentedDegiroListReadings(
 [isolatedMiniHead,isolatedMiniHead.replace('DEOOOPU8APE4','DE000FG8NHQ3')],
 [isolatedMiniFooter,isolatedMiniFooter])),null);
assert.equal(b.segmentedDegiroListReadings(
 [isolatedMiniHead,isolatedMiniHead],['some quote without venue',isolatedMiniFooter]).length,0);
assert.equal(b.segmentedDegiroListReadings(
 [isolatedMiniHead,isolatedMiniHead],[isolatedMiniFooter,isolatedMiniFooter+'\nISIN DE000FG8NHQ3']).length,0);

const bottomOverlap='SG Gold Knock-Out Warrant Open End Put BAR 4521.97 BP 4521.97 Bv 10 | DE000FG34XV8';
assert.equal(b.clippedDegiroListReference([bottomOverlap,bottomOverlap]).isin,'DE000FG34XV8');
assert.equal(b.parseDegiroListRow(row().replace('Call','Put')).direction,'SHORT');
assert(!b.parseDegiroListRow(row().replace('Call','Call Put')).listRow.complete);
assert(!b.parseDegiroListRow(row().replace('Societe Generale OTC','BNP OTC')).listRow.complete);
assert(!b.parseDegiroListRow(row().replace('Bv 10','Bv O')).listRow.complete);
assert.equal(b.parseDegiroListRow(row()+' '+z),null);
assert.equal(b.degiroListBlocks('Societe Generale OTC CHF\n'+row()+'\nSG Gold Turbo Put BAR 4400').length,2);
const now=Date.parse('2026-10-21T08:00:00Z');
const item=b.agreedDegiroListRow([row(),row()]);item.listRow.imageReference='synthetic-list.png';
const archive={storedAt:'2026-10-21T07:00:00Z',files:[{name:'synthetic-list.png'}],items:[item]};
assert(b.observedDegiroListRow(a,archive,now).currentDay);
assert.equal(b.observedDegiroListRow(z,archive,now),null);
assert.equal(b.observedDegiroListRow(a,archive,Date.parse('2026-10-22T08:00:00Z')).currentDay,false);
const html=b.renderDegiroListEvidence({isin:a},now,archive);assert(html.includes('DEGIRO-Listennachweis'));assert(html.includes('Societe Generale OTC'));assert(html.includes('kein ausführbarer Brokerkurs'));
(async()=>{
 const seen=[];const recognize=async(file,...args)=>{seen.push(args);return {data:{listItems:[file.row],text:''}}};
 const items=await b.readListBatch([{name:'one.png',row:item},{name:'two.png',row:item}],recognize);
 assert.equal(items.length,1);assert.equal(items[0].listRow.imageReference,'one.png');assert.equal(seen[0][3],true);
 await assert.rejects(()=>b.readListBatch([{row:item},{row:b.agreedDegiroListRow([row(a,'4019.00'),row(a,'4019.00')])}],recognize),/Widersprüchliche/);
 // Text fallback also respects file boundaries and does not attach a clipped
 // product on image one to the first full identifier on image two.
 const rawFiles=[row()+'\nSG Gold Turbo BEST Open-End Put BAR 4500',row(z)];
 const fallback=await b.readListBatch(rawFiles,async text=>({data:{text}}));assert.equal(fallback.length,2);assert.equal(fallback[1].direction,'LONG');
 await assert.rejects(()=>b.readListBatch([{name:'cut.png'}],async()=>({data:{listItems:[item],partialRows:['BNP GOLD Mini Short SL 9999']}})),/Abgeschnittene/);
 // Actual mobile overlap: screenshot one ends after a legible ISIN but
 // before the OTC/currency footer; screenshot two contains the complete row.
 const clippedText=row().split('Societe Generale OTC')[0];
 const continuation=b.clippedDegiroListReference([clippedText,clippedText]);
 assert.equal(continuation.isin,a);
 assert.equal(continuation.issuer,'SG');
 assert.equal(continuation.direction,'LONG');
 assert.equal(b.clippedDegiroListReference([row(),row()]),null,'complete rows must never become continuations');
 assert.equal(b.clippedDegiroListReference([clippedText,clippedText.replace(a,z)]),null,'conflicting partial ISIN readings must not resolve');
 const structured=async file=>({data:{listItems:[file.row].filter(Boolean),partialRows:file.continuation?[file.continuation]:[]}});
 const other=b.agreedDegiroListRow([row(z),row(z)]);
 const merged=await b.readListBatch([{name:'first.png',row:other,continuation},{name:'next.png',row:item}],structured);
 assert.equal(merged.length,2);
 assert.equal(merged.filter(x=>x.isin===a).length,1,'overlap must not duplicate a product');
 await assert.rejects(()=>b.readListBatch([{name:'first.png',row:other,continuation},{name:'next.png',row:other}],structured),/Abgeschnittene/,'missing continuation must retain the previous list');
 await assert.rejects(()=>b.readListBatch([{name:'first.png',row:other,continuation:{...continuation,direction:'SHORT'}},{name:'next.png',row:item}],structured),/Abgeschnittene/,'direction conflicts must not be accepted');
 // Automatic Top-10 series, including persisted/retried image files: never
 // accept a shorter set or silently trim a longer catalog selection.
 const ten=Array.from({length:11},(_,i)=>{
  const prefix='DE000AA'+String(i).padStart(4,'0');
  const isin=Array.from({length:10},(_,d)=>prefix+d).find(b.validIsin);
  return b.agreedDegiroListRow([row(isin),row(isin)]);
 });
 const topFiles=[{name:'DEGIRO-TOP10-first.png',rows:ten.slice(0,4)},
  {name:'DEGIRO-TOP10-second.png',rows:ten.slice(3,8)},
  {name:'DEGIRO-TOP10-third.png',rows:ten.slice(7,10)}];
 const readTop=async f=>({data:{listItems:f.rows}});
 assert.equal((await b.readListBatch(topFiles,readTop)).length,10);
 await assert.rejects(()=>b.readListBatch(topFiles.slice(0,2),readTop),/genau zehn/);
 await assert.rejects(()=>b.readListBatch([{name:'DEGIRO-TOP10-catalog.png',rows:ten}],readTop),/genau zehn/);
 console.log('DEGIRO list grammar, independent votes, changed daily values, boundaries, duplicates, evidence and expiry passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
