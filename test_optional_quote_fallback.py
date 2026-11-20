"""Optional external source failures must not revoke a verified issuer quote."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import product_quotes
import paper_simulation


ISIN = 'DE000FB0A490'
NOW = 1795200000000


def primary(eligible=True):
    return dict(isin=ISIN, found=True, eligible=eligible, fresh=eligible,
                marketOpen=True, productVerified=True, source='issuer original',
                sourceUrl='https://issuer.example/source',
                currency='EUR', priceKind='market-observation',
                metadata=dict(status=1, currency='EUR', issuerExchangeCode='CBDE'),
                bid=9.99, ask=10.0, bidAt=NOW, askAt=NOW)


def optional_failure(stage, isin, operation, original, events):
    assert isin == ISIN
    if stage == 'comdirect-terms':
        events.append(dict(stage=stage, state='failed', retryAfterSeconds=30))
    if stage == 'comdirect-quote':
        events.append(dict(stage=stage, state='waiting', retryAfterSeconds=30))
    return copy.deepcopy(original)


class OptionalSourceDoesNotDowngradePrimary(unittest.TestCase):
    def test_primary_quote_stays_eligible_when_secondary_fetch_failed(self):
        for approved in (True, False):
            with self.subTest(approved=approved), ExitStack() as stack:
                stack.enter_context(patch('product_repair_learning.source_order', return_value=[]))
                stack.enter_context(patch('product_source_recovery.enrich', side_effect=optional_failure))
                stack.enter_context(patch.object(product_quotes, '_get_quote_primary',
                                                 return_value=primary(approved)))
                stack.enter_context(patch.object(product_quotes, '_restore_exact_sg_metadata',
                                                 side_effect=lambda r, isin: r))
                stack.enter_context(patch('leverage_backup.apply', side_effect=lambda r: r))
                stack.enter_context(patch('leverage_backup.select_analysis_quote',
                                          side_effect=lambda r: r))
                stack.enter_context(patch('secondary_validity.apply', side_effect=lambda r, isin: r))
                stack.enter_context(patch('hybrid_product_price.apply', side_effect=lambda r: r))
                stack.enter_context(patch('price_continuity.apply', side_effect=lambda r: r))
                quote = product_quotes._get_quote_bounded(ISIN)
                self.assertIs(quote['eligible'], approved)
                self.assertEqual({e['state'] for e in quote['sourceRecovery']},
                                 {'waiting', 'failed'})
                self.assertEqual(quote['isin'], ISIN)
                self.assertEqual(quote['bidAt'], NOW)

    def test_paper_and_push_refresh_do_not_demote_original(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(paper_simulation, '_pool', object()))
            stack.enter_context(patch.object(paper_simulation, '_pending', {}))
            stack.enter_context(patch.object(paper_simulation, '_quotes', {}))
            stack.enter_context(patch.object(paper_simulation, '_requested', {}))
            stack.enter_context(patch.object(paper_simulation, '_observed_snapshot', {}))
            stack.enter_context(patch('product_repair_learning.request_order', return_value=[]))
            stack.enter_context(patch('quote_updates.updates.track'))
            stack.enter_context(patch('product_source_recovery.enrich',
                                      side_effect=optional_failure))
            stack.enter_context(patch('leverage_backup.apply', side_effect=lambda r: r))
            stack.enter_context(patch('comdirect_fields.apply', side_effect=lambda r: r))
            stack.enter_context(patch('hybrid_product_price.apply', side_effect=lambda r: r))
            quote = primary()
            result = paper_simulation.quote_cache(
                [{'isin': ISIN, 'quote': quote}], [], NOW)
            observed = paper_simulation.observed_quotes([{'isin': ISIN}])
            self.assertTrue(result[ISIN]['eligible'])
            self.assertTrue(observed[ISIN]['eligible'])
            self.assertEqual(quote, primary())
            self.assertEqual({e['state'] for e in result[ISIN]['sourceRecovery']},
                             {'waiting', 'failed'})


if __name__ == '__main__':
    unittest.main()
