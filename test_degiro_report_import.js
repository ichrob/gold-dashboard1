/* Offline only: never uses a broker account or network. */
'use strict';
const assert=require('node:assert/strict');
const {parseRows,readReport,parseNumber,validISIN}=require('./degiro_report_import');
assert.equal(validISIN('DE000PJ9NB98'),true);
assert.equal(validISIN('DE000PJ9NB99'),false);
assert.equal(parseNumber('1.234,5'),1234.5);
assert.equal(parseNumber('1,234.5'),1234.5);
assert.equal(parseNumber('-2'),-2);
assert.equal(parseNumber('=EXEC(1)'),null);
const report='\uFEFFISIN;Produkt;Anzahl;Währung\r\nDE000PJ9NB98;"Gold; Turbo";2,0;EUR\r\nDE000PJ9NB99;Fake;3;EUR\r\n';
const parsed=readReport(report);
assert.equal(parsed.kind,'portfolio');
assert.equal(readReport('DEGIRO report exported on a date\n'+report).records.length,1);
assert.equal(parsed.records.length,1);
assert.equal(parsed.invalidRows[0],3);
assert.equal(parsed.records[0].product,'Gold; Turbo');
assert.equal(parsed.records[0].quantity,2);
assert.equal(parsed.realtime,false);
assert.equal(parsed.brokerVerified,false);
assert.equal(parsed.ordersEnabled,false);
const transactions=readReport('Datum,ISIN,Quantity,Type\n19-10-2026,DE000PJ9NB98,3,Buy');
assert.equal(transactions.kind,'transactions');
assert.equal(transactions.records[0].side,'Buy');
assert.equal(transactions.records[0].date,'19-10-2026');
const swissLayout=[
 'Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF',
 'CASH & CASH FUND & F, , , ,CHF,100.25,100.25',
 'Gold Future Faktor,DE000PJ9NB98,1,12.34,EUR,12.34,11.50'
].join('\n');
const swiss=readReport(swissLayout);
assert.equal(swiss.kind,'portfolio');
assert.equal(swiss.records.length,1);
assert.equal(swiss.cashBalances.length,1);
assert.equal(swiss.cashBalances[0].currency,'CHF');
assert.equal(swiss.cashBalances[0].amount,100.25);
assert.equal(swiss.records[0].isin,'DE000PJ9NB98');
assert.equal(swiss.records[0].quantity,1);
assert.equal(swiss.records[0].price,'12.34');
assert.equal(swiss.records[0].value,'12.34');
assert.equal(swiss.records[0].currency,'EUR');
assert.equal(swiss.records[0].accountValue,'11.50');
assert.equal(swiss.accountCurrency,'CHF');
assert.equal(swiss.invalidRows.length,0);
assert.equal(swiss.brokerVerified,false);
assert.equal(swiss.ordersEnabled,false);

assert.throws(()=>readReport('Date;Comment\n1;foo'),/ISIN/);
assert.throws(()=>readReport('ISIN;Anzahl\nDE000PJ9NB99;1'),/Keine gültigen/);
assert.throws(()=>parseRows('ISIN;Anzahl\n"broken'),/Anführungszeichen/);
assert.throws(()=>parseRows('x;'.repeat(1_100_000)),/2 MB/);
console.log('DEGIRO export local-only parser tests passed');
