'use strict';
const assert=require('node:assert/strict');
const {terminalStatusAfter}=require('./browser_test_status_sequence.cjs');

// The prior predicate accepted this unrelated repeated `staged` heartbeat and
// then waited for a result that the selected invalid export could never emit.
assert.equal(terminalStatusAfter([{write:10,state:'staged'}],9),null);
assert.equal(terminalStatusAfter([
 {write:10,state:'staged'},
 {write:11,state:'reading'}
],9),null);
assert.deepEqual(terminalStatusAfter([
 {write:10,state:'staged'},
 {write:11,state:'reading'},
 {write:12,state:'reading'},
 {write:13,state:'error'}
],9),{write:13,state:'error'});
assert.deepEqual(terminalStatusAfter([
 {write:21,state:'reading'},
 {write:22,state:'staged'},
 {write:23,state:'staged'}
],20),{write:22,state:'staged'});
assert.equal(terminalStatusAfter(null,0),null);

console.log('Synthetic broker status sequence: action-scoped terminal classification passed');
