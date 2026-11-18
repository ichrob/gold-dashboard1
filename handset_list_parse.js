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
// ML Kit can read the SG ratio label 'Bv' as 'By'. Correct only that
// standalone label in a complete SG Gold title, never its numeric value,
// identity or footer. Raw optical passes remain stored and returned unchanged.
// Accessibility and native OCR routes do not use this correction.
function normalizeLocalOcrLabels(text) {
 if(!/^SG\s+Gold\b/i.test(text))return text;
 const id=/\bDE[0OQ]{3}[A-Z0-9]{7}\b/i.exec(text);
 if(!id)return text;
 const title=text.slice(0,id.index);
 if(!/\bBAR\s+[0-9]+(?:[.,][0-9]+)?\b/i.test(title) ||
    !/\bBP\s+[0-9]+(?:[.,][0-9]+)?\b/i.test(title))return text;
 return title.replace(/\bBy(?=\s+[0-9]+(?:[.,][0-9]+)?(?:\s|[|]|$))/gi,'Bv')+text.slice(id.index);
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
   const row=b.parseDegiroListRow(normalizeLocalOcrLabels(text));
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
// Combine only independently agreed rows of the SAME original screenshot.
// A phone ML Kit viewport may legally omit incomplete edge rows, while
// server OCR can read those edges. Each output row still has two real OCR
// passes and the exact ISIN/contract-terms proof; nothing is inferred.
// Ordering must be unambiguous in the two independently read row sequences.
function complementEligible(phonePasses) {
 if(!Array.isArray(phonePasses)||phonePasses.length!==2||
    phonePasses.some(s=>typeof s!=='string'||s.length>30000))return false;
 const claims=new Map(),seenInBoth=new Set();
 for(let pass=0;pass<2;pass++) {
  const reading=phonePasses[pass].split('\n').map(normalizeLocalOcrLabels).join('\n');
  const once=new Set();
  for(const block of b.degiroListBlocks(normalizeLayout(reading))) {
   const row=b.parseDegiroListRow(block);
   if(!row||!b.validIsin(row.isin))continue;
   if(once.has(row.isin))return false;
   once.add(row.isin);
   const signature=JSON.stringify([row.direction,...['venue','currency','ko','strike','ratio','maturity','excluded'].map(k=>row.listRow[k])]);
   if(claims.has(row.isin)) {
    if(claims.get(row.isin)!==signature)return false;
    seenInBoth.add(row.isin);
   } else claims.set(row.isin,signature);
  }
 }
 return seenInBoth.size>0;
}
function complementImage(phonePasses,nativePasses) {
 if(!complementEligible(phonePasses))return null;
 function witnessed(passes,local) {
  if(!Array.isArray(passes) || passes.length<2 || passes.length>3 ||
     passes.some(v=>typeof v!=='string'||v.length>30000))return null;
  const readings=passes.map(value=>local
   ? value.split('\n').map(normalizeLocalOcrLabels).join('\n'):value);
  const agreed=agreedImageRows(readings);
  const result=new Map();
  const sig=row=>JSON.stringify([row.direction,...['venue','currency','ko','strike','ratio','maturity','excluded'].map(k=>row.listRow[k])]);
  for(const row of agreed) {
   const verified=[];
   for(const reading of readings) {
    const matching=b.degiroListBlocks(normalizeLayout(reading)).filter(block=>{
     const parsed=b.parseDegiroListRow(block);
     return parsed&&parsed.isin===row.isin&&sig(parsed)===sig(row);
    });
    if(matching.length>1)return null;
    if(matching.length===1)verified.push(matching[0]);
   }
   if(verified.length>=2)result.set(row.isin,{signature:sig(row),blocks:verified.slice(0,2)});
  }
  return result;
 }
 const phone=witnessed(phonePasses,true),native=witnessed(nativePasses,false);
 if(!phone||!native||phone.size<1||native.size<1)return null;
 const union=new Map(phone);
 for(const [id,row] of native) {
  if(union.has(id)&&union.get(id).signature!==row.signature)return null;
  if(!union.has(id))union.set(id,row);
 }
 if(union.size<2||union.size>10||union.size<=phone.size)return null;
 const followers=new Map([...union.keys()].map(id=>[id,new Set()]));
 const indegree=new Map([...union.keys()].map(id=>[id,0]));
 for(const source of [phone,native]) {
  const ids=[...source.keys()];
  for(let i=1;i<ids.length;i++) {
   const from=ids[i-1],to=ids[i];
   if(from===to||followers.get(from).has(to))continue;
   followers.get(from).add(to);indegree.set(to,indegree.get(to)+1);
  }
 }
 const ordered=[];
 while(ordered.length<union.size) {
  const ready=[...indegree].filter(([id,d])=>d===0 && !ordered.includes(id));
  // Two possible orderings do not prove the visual row order.
  if(ready.length!==1)return null;
  const id=ready[0][0];ordered.push(id);
  for(const next of followers.get(id))indegree.set(next,indegree.get(next)-1);
  indegree.set(id,-1);
 }
 const result=[0,1].map(pass=>ordered.map(id=>union.get(id).blocks[pass]).join('\n'));
 const agreed=agreedImageRows(result);
 if(agreed.length!==union.size || agreed.some(row=>!union.has(row.isin)))return null;
 return result;
}
function parse(images,at,appSources=[],localSources=[]){
 const items=new Map();
 for(const [index,passes] of images.entries()){
  const parsedPasses=localSources[index]?passes.map(pass=>pass.split('\n').map(normalizeLocalOcrLabels).join('\n')):passes;
  for(const row of agreedImageRows(parsedPasses)){
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
// Pure read-only failure classification. Exposes NO product identity, texts,
// prices, account information or images. Never relaxes ten-row verification.
function diagnose(images,appSources=[],localSources=[]){
 if(!Array.isArray(images)||images.length<1||images.length>4)return null;
 const unique=new Map();
 let imagesWithRows=0,conflictingRows=0,duplicateRows=0;
 const signature=x=>JSON.stringify([x.direction,...['venue','currency','ko','strike','ratio','maturity','excluded'].map(k=>x.listRow[k])]);
 for(let index=0;index<images.length;index++){
  const passes=images[index];
  if(!Array.isArray(passes)||passes.length<2||passes.length>3||
    passes.some(p=>typeof p!=='string'||p.length>30000))continue;
  const candidate=localSources[index]?passes.map(p=>p.split('\n').map(normalizeLocalOcrLabels).join('\n')):passes;
  let rows=[];
  try{rows=agreedImageRows(candidate)}catch(_){continue}
  if(rows.length)imagesWithRows++;
  for(const row of rows){
   const previous=unique.get(row.isin);
   if(previous===undefined)unique.set(row.isin,signature(row));
   else if(previous!==signature(row))conflictingRows++;
   else duplicateRows++;
  }
 }
 const uniqueRows=Math.min(10,unique.size);
 return {version:1,uniqueRows,expectedRows:10,
  imagesTotal:images.length,imagesWithRows,
  conflictingRows:Math.min(10,conflictingRows),
  duplicateRows:Math.min(10,duplicateRows),
  reason:conflictingRows?'conflict':unique.size!==10?'incomplete':'other'};
}
module.exports={normalizeLocalOcrLabels,canonicalLocalOcrIdentity,parse,diagnose,normalizeLayout,appImage,localOcrImage,nativeImage,complementImage,complementEligible};
if(require.main===module){try{const x=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(x.mode==='prepare-app'?x.images.map(i=>appImage(i.appText)||localOcrImage(i.localOcr)):x.mode==='prepare-native'?nativeImage(x.passes):x.mode==='complement'?complementImage(x.phone,x.native):x.mode==='complement-eligible'?complementEligible(x.phone):x.mode==='diagnose'?diagnose(x.images,x.appSources,x.localSources):parse(x.images,x.at,x.appSources,x.localSources)));}catch(e){process.stderr.write('List verification failed\n');process.exitCode=1;}}
