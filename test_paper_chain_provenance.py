import copy
import unittest
from datetime import datetime, timezone
import paper_evidence_chain as chain
from test_paper_net_evidence import closed_case, T


class ChainProvenanceTests(unittest.TestCase):
    def test_exit_requires_matching_original_quote_and_clock(self):
        changes = [dict(isin='different-product'), dict(currency='CHF'),
                   dict(source=None), dict(bidAt=None), dict(bidAt=T-90001),
                   dict(bidAt=T+30001), dict(bidAt=True), dict(bidAt=float('nan')),
                   dict(estimated=True)]
        for changeset in changes:
            c = closed_case()
            c['events'][-1]['quote'].update(changeset)
            with self.subTest(changeset=changeset):
                self.assertFalse(chain.review(c)['complete'])

    def test_exit_requires_original_full_unit_accounting(self):
        for key, value in [('units', 1), ('units', True), ('recordedAt', T-1),
                           ('recordedAt', T+30001), ('kind', 'deferred-sale')]:
            c = closed_case(); c['events'][-1][key] = value
            with self.subTest(key=key,value=value):
                self.assertFalse(chain.review(c)['complete'])
        c = closed_case(); c['remainingUnits'] = 1
        self.assertFalse(chain.review(c)['complete'])

    def test_entry_clock_and_malformed_evidence_fail_closed(self):
        for key, value in [('askAt', None), ('askAt', T+1), ('askAt', T-90001),
                           ('source', ''), ('estimated', True)]:
            c = closed_case(); c['entryQuote'][key] = value
            self.assertFalse(chain.review(c)['complete'])
        for key, value in [('events', [None]), ('product', []),
                           ('entryQuote', 'broken'), ('selectionEvidence', [])]:
            c = closed_case(); c[key] = value
            self.assertFalse(chain.review(c)['complete'])

    def test_valid_partial_exits_and_iso_clocks_keep_originals(self):
        c = closed_case()
        event = c['events'][-1]
        event['units'] = 2
        c['events'].append(copy.deepcopy(event))
        for q, key in [(c['entryQuote'], 'askAt'), (event['quote'], 'bidAt')]:
            q['quoteAt'] = datetime.fromtimestamp(q.pop(key)/1000,timezone.utc).isoformat()
        before = copy.deepcopy(c)
        result = chain.review(c)
        self.assertTrue(result['complete'])
        self.assertFalse(result['brokerExecutionVerified'])
        self.assertEqual(c, before)
