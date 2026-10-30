'use strict';
// Reuse the same strict row grammar and agreement checks as the browser.
const fs=require('fs'),vm=require('vm');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(__dirname+'/degiro_assistant.js','utf8'),context);
const b=context.window.BobDegiro;
function normalizeLayout(text){
 // Restore whitespace at known labels only; never change identity or numbers.
 return String(text).replace(/\bSG(?=Gold)/g,'SG ')
  .replace(/Gold(?=Knock|Turbo|Future)/g,'Gold ')
  .replace(/\bBNP(?=GOLD)/gi,'BNP ')
  .replace(/GOLD(?=Mini)/gi,'GOLD ')
  .replace(/Mini(?=Long|Short)/gi,'Mini ')
  .replace(/(Long|Short)(?=SL)/gi,'$1 ')
  .replace(/Knock-Out(?=Warrant)/g,'Knock-Out ')
  .replace(/Warrant(?=Open|Call|Put)/g,'Warrant ')
  .replace(/Future(?=Faktor)/g,'Future ')
  .replace(/Faktor(?=Long|Short)/g,'Faktor ')
  .replace(/Turbo(?=BEST|Unlimited)/g,'Turbo ')
  .replace(/BEST(?=Open)/g,'BEST ')
  .replace(/Open-End(?=Call|Put)/g,'Open-End ')
  .replace(/Unlimited(?=Mini)/g,'Unlimited ')
  .replace(/Mini(?=Call|Put)/g,'Mini ')
  .replace(/(Call|Put)(?=BAR)/g,'$1 ')
  .replace(/(Long|Short)(?=HB)/g,'$1 ')
  .replace(/((?<![A-Z])B[vV]\s*)(1|10|100|1000)([0-3]\d\/[01]\d\/20\d{2})(?=\s*\|)/g,'$1$2 $3');
}
function parse(images,at){
 const items=new Map();
 for(const [index,passes] of images.entries()){
  const votes=new Map();
  for(const text of passes){
   const seen=new Set();
   for(const block of b.degiroListBlocks(normalizeLayout(text))){
    const row=b.parseDegiroListRow(block);
    if(!row||!b.validIsin(row.isin)||seen.has(row.isin))continue;
    seen.add(row.isin);
    const reads=votes.get(row.isin)||[];reads.push(block);votes.set(row.isin,reads);
   }
  }
  for(const [isin,reads] of votes){
   const row=b.agreedDegiroListRow(reads)||b.agreedExcludedDegiroFactorRow(reads);
   if(!row)continue;
   row.listRow.imageReference='DEGIRO-TOP10-'+(index+1)+'.png';
   const old=items.get(isin);
   const signature=x=>JSON.stringify([x.direction,...['venue','currency','ko','strike','ratio','maturity','excluded'].map(k=>x.listRow[k])]);
   if(old&&signature(old)!==signature(row))throw Error('Conflicting list observations');
   if(!old)items.set(isin,row);
  }
 }
 if(items.size!==10)throw Error('Ten complete distinct rows required');
 const rows=[...items.values()],archive={storedAt:at,files:images.map(()=>({})),items:rows};
 return {items:rows,evidence:{origin:'degiro-screenshot',listUploadedAt:at,references:[],fixedBarriers:{},products:rows.map(x=>({
  isin:x.isin,name:x.name,productDirection:x.direction,price:null,leverage:null,ko:x.listRow.ko||null,
  isinConfirmed:false,quote:null,snapshot:null,currency:x.listRow.currency,
  basisPrice:x.listRow.strike||null,ratio:x.listRow.ratio||null,maturity:x.listRow.maturity||null,
  listVenueEvidence:b.listVenueForSync(x.isin,archive)
 }))}};
}
module.exports={parse,normalizeLayout};
if(require.main===module){try{const x=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(parse(x.images,x.at)));}catch(e){process.stderr.write('List verification failed\n');process.exitCode=1;}}
