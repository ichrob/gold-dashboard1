const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('real_trade_journal.js','utf8');
const body=src.slice(src.indexOf(' function reviewLines('),src.indexOf(' function renderEvaluation('));
const context={};vm.createContext(context);vm.runInContext(body,context);
assert(context.reviewLines({realizedNetCHF:-2}).join(' ').includes('-2.00 CHF'));
assert(context.reviewLines({realizedNetCHF:null}).join(' ').includes('unvollständig'));
assert(context.reviewLines({realizedNetProduct:0,currency:'EUR'}).join(' ').includes('0.00 EUR'));
assert(!context.reviewLines({}).join(' ').includes('NaN'));
console.log('Trade review: net loss, zero net and missing evidence passed');
