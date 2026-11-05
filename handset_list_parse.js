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
function appImage(value){
 if(!value||!Array.isArray(value.before)||value.before.length<1||value.before.length>10
    ||JSON.stringify(value.before)!==JSON.stringify(value.after))return null;
 const seen=new Set();
 for(const text of value.before){
  if(typeof text!=='string'||text.length>800)return null;
  const ids=text.match(/\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b/g)||[];
  const row=b.parseDegiroListRow(text);
  // Accessibility text is not OCR: never apply character correction.
  if(ids.length!==1||!b.validIsin(ids[0])||!row||row.isin!==ids[0]||row.identityCorrection
     ||seen.has(ids[0])||!(row.listRow.complete||b.agreedExcludedDegiroFactorRow([text,text])))return null;
  seen.add(ids[0]);
 }
 return [value.before.join('\n'),value.after.join('\n')];
}
// Two differently scaled on-device OCR passes of ONE approved screenshot.
// This is a faster recognition route, not a second independent source.
// The server repeats exact identity, product grammar and two-pass agreement.
function canonicalLocalOcrIdentity(raw){
 const value=String(raw).toUpperCase();
 if(value.length!==12)return null;
 if(b.validIsin(value)&&value.startsWith('DE000'))return value;
 if(!/^DE[0OQ]{3}[A-Z0-9]{7}$/.test(value))return b.validIsin(value)?value:null;
 const candidate='DE000'+value.slice(-7).replace(/O/g,'0').replace(/I/g,'1');
 return b.validIsin(candidate)?candidate:null;
}
function localOcrImage(value) {
 if(!value || !Array.isArray(value.expectedIsins) ||
    !Array.isArray(value.passes) || value.passes.length!==2 ||
    value.expectedIsins.length<1 || value.expectedIsins.length>10 ||
    new Set(value.expectedIsins).size!==value.expectedIsins.length ||
    value.expectedIsins.some(id=>typeof id!=='string'||!b.validIsin(id)))
   return null;
 for(const pass of value.passes) {
  if(!Array.isArray(pass) || pass.length!==value.expectedIsins.length)return null;
  for(let i=0;i<pass.length;i++){
   const text=pass[i],id=value.expectedIsins[i];
   if(typeof text!=='string'||text.length<1||text.length>800||
      /passwort|password|kontostand|portfolio|order bestätigen|stückzahl kaufen/i.test(text))
     return null;
   const actual=text.match(/\b(?:[A-Z]{2}[A-Z0-9]{9}[0-9]|DE[0OQ]{3}[A-Z0-9]{7})\b/gi)||[];
   if(actual.length!==1||canonicalLocalOcrIdentity(actual[0])!==id)return null;
   const row=b.parseDegiroListRow(text);
   if(!row||row.isin!==id ||
      !(row.listRow.complete||b.agreedExcludedDegiroFactorRow([text,text])))return null;
  }
 }
 return value.passes.map(pass=>pass.join('\n'));
}
// Checkpoints contain only product grammar accepted from actual optical
// passes. Never store a raw screen transcript or turn one read into two.
function agreedImageRows(passes) {
 const votes=new Map();
 for(const text of passes){const seen=new Set();for(const block of b.degiroListBlocks(normalizeLayout(text))){
  const row=b.parseDegiroListRow(block);if(!row||!b.validIsin(row.isin)||seen.has(row.isin))continue;
  seen.add(row.isin);const reads=votes.get(row.isin)||[];reads.push(block);votes.set(row.isin,reads);
 }}
 return [...votes.values()].map(reads=>b.agreedDegiroListRow(reads)||b.agreedExcludedDegiroFactorRow(reads)).filter(Boolean);
}
function nativeImage(passes) {
 if(!Array.isArray(passes)||passes.length<2||passes.length>3||
    passes.some(t=>typeof t!=='string'||t.length>30000))return null;
 const clean=passes.map(text=>b.degiroListBlocks(normalizeLayout(text)).map(block=>{
  const start=block.search(/\b(?:SG|BNP)\s+Gold\b/i);
  const footer=/\b(?:Societe Generale|Société Générale|BNP(?: Paribas)?)\s+OTC\s+(?:EUR|CHF)\b/i.exec(block);
  if(start<0||!footer)return null;
  const value=block.slice(start,footer.index+footer[0].length);
  if(value.length>800||/passwort|password|kontostand|portfolio|order bestätigen|stückzahl kaufen/i.test(value))return null;
  const ids=value.match(/\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b/g)||[];
  const row=b.parseDegiroListRow(value);
  return ids.length===1&&b.validIsin(ids[0])&&row&&row.isin===ids[0]&&
   !row.identityCorrection&&(row.listRow.complete||b.agreedExcludedDegiroFactorRow([value,value]))?value:null;
 }).filter(Boolean).join('\n'));
 if(clean.some(text=>b.degiroListBlocks(text).length>10))return null;
 // Privacy filtering must not change ANY accepted row, optional value,
 // disagreement or exclusion. Otherwise keep the original optical work path.
 const original=agreedImageRows(passes),filtered=agreedImageRows(clean);
 return original.length>0&&JSON.stringify(original)===JSON.stringify(filtered)?clean:null;
}
function parse(images,at,appSources=[],localSources=[]){
 const items=new Map();
 for(const [index,passes] of images.entries()){
  for(const row of agreedImageRows(passes)){
   const isin=row.isin;
   if(appSources[index]) {
    row.listRow.source='DEGIRO-App-Text';
    row.listRow.crossChecked=false;
    row.listRow.textCaptureMatched=true;
    row.listRow.extractionMethod='accessibility-before-after';
   }
   else if(localSources[index]) {
    row.listRow.source='DEGIRO-Listenbild';
    row.listRow.extractionMethod='on-device-mlkit-two-scale';
    row.listRow.textCaptureMatched=false;
    // CrossChecked remains the actual two-pass parser decision; no issuer,
    // market-time, account or trade authorization is invented.
   }
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
module.exports={canonicalLocalOcrIdentity,parse,normalizeLayout,appImage,localOcrImage,nativeImage};
if(require.main===module){try{const x=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(x.mode==='prepare-app'?x.images.map(i=>appImage(i.appText)||localOcrImage(i.localOcr)):x.mode==='prepare-native'?nativeImage(x.passes):parse(x.images,x.at,x.appSources,x.localSources)));}catch(e){process.stderr.write('List verification failed\n');process.exitCode=1;}}
