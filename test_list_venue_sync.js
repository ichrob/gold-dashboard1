const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobDegiro,isin='DE000FG14AV8';
const text='SG Gold Knock-Out Warrant Open End Call BAR 4066.45 BP 4066.45 Bv 10 | '+isin+'\nSociete Generale OTC CHF K V';
const row=b.agreedDegiroListRow([text,text]);assert(row?.listRow.crossChecked);
row.listRow.imageReference='fixture.jpg';
const archive={storedAt:'2026-10-21T06:39:49.626Z',files:[{name:'fixture.jpg'}],items:[row]};
const proof=b.listVenueForSync(isin,archive);
assert.equal(proof.venue,'Societe Generale OTC');assert.equal(proof.currency,'CHF');
assert.equal(proof.reference,'fixture.jpg');assert.equal(proof.listUploadedAt,archive.storedAt);
assert.equal(proof.isExecutableQuote,false);assert(!('bid' in proof));

// Periodic refresh must retain proof and native currency even when the analysis
// product uses EUR conversion, while leaving its quote and prices unchanged.
const quote={isin,currency:'EUR',bid:5.9,ask:6};
const analysis={isin,currency:'EUR',price:6,quote,leverage:60};
const synced=b.paperProductsForSync([analysis],archive)[0];
assert.equal(synced.listVenueEvidence.reference,'fixture.jpg');
assert.equal(synced.currency,'CHF');
assert.strictEqual(synced.quote,quote);
assert.equal(synced.price,6);
assert.equal(analysis.currency,'EUR','Do not mutate analysis products');
assert.equal(b.paperProductsForSync([{isin:'DE000FG8NHQ3',currency:'EUR'}],archive)[0].listVenueEvidence,null);
assert(fs.readFileSync('degiro_assistant.js','utf8').includes('sync({...buildPaperListEvidence(),products:paperProductsForSync(ps),references})'));
row.listRow.crossChecked=false;assert.equal(b.listVenueForSync(isin,archive),null);
assert.equal(b.listVenueForSync('DE000FG8NHQ3',archive),null);
assert(fs.readFileSync('degiro_assistant.js','utf8').includes('listVenueEvidence:listVenueForSync(isin)'));
console.log('List row OCR to sync evidence: identity, footer, currency, original generation and crosscheck passed');
