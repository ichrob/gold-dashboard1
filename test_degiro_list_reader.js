'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const c={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),c);const b=c.window.BobDegiro;
function id(n){const base='DE000ZZ'+String(n).padStart(4,'0');for(let d=0;d<10;d++)if(b.validIsin(base+d))return base+d;throw Error('id');}
const a=id(1),z=id(2);
const row=(isin=a,amount='4012.25',currency='EUR')=>`SG Gold Turbo BEST Open-End Call BAR ${amount} BP\n${amount} Bv 10 | ${isin}\nSociete Generale OTC ${currency} (K) (V)`;
const parsed=b.parseDegiroListRow(row());assert(parsed.listRow.complete);assert.equal(parsed.direction,'LONG');assert.equal(parsed.listRow.ko,4012.25);assert.equal(parsed.listRow.ratio,.1);assert.equal(parsed.leverage,'');assert.equal(parsed.price,'');assert.equal(parsed.listRow.sourceTime,null);
const tomorrow=b.parseDegiroListRow(row(a,'4018,37','CHF'));assert.equal(tomorrow.listRow.ko,4018.37);assert.equal(tomorrow.listRow.currency,'CHF');
assert.equal(b.agreedDegiroListRow([row(),row(a,'4013.00')]),null,'conflicting numbers cannot be confirmed');
assert.equal(b.agreedDegiroListRow([row(),row(z)]),null,'different valid IDs cannot vote together');
assert.equal(b.agreedDegiroListRow([row()]),null,'one pass is not enough');
assert(b.agreedDegiroListRow([row(),row(),row(a,'4013.00')]).listRow.crossChecked);
assert.equal(b.agreedDegiroListRow([row(),row(),row(a,'4013.00'),row(a,'4013.00')]),null);
const mini=`BNP GOLD Mini Long SL 3700.25 STR 3650.75 R\n10 | ${a}\nBNP OTC EUR K V`;
const m=b.parseDegiroListRow(mini);assert.equal(m.listRow.ko,3700.25);assert.equal(m.listRow.strike,3650.75);assert.equal(m.listRow.ratio,.1);
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
 console.log('DEGIRO list grammar, independent votes, changed daily values, boundaries, duplicates, evidence and expiry passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
