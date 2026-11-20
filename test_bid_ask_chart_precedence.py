"""Do not replace a valid original issuer bid/ask with a newer chart point.

Paper, display and gearing may use originals; none of these tests grants an
executable DEGIRO quote or mutates stored timestamped evidence.
"""
import copy
import unittest
from datetime import datetime, timedelta, timezone

import leverage_backup

NOW = datetime(2026, 11, 20, 20, 10, tzinfo=timezone.utc)
ISIN = 'DE000FB0A490'


def at(seconds):
    return (NOW-timedelta(seconds=seconds)).isoformat()


def issuer_original():
    return {
        'isin': ISIN, 'found': True, 'eligible': True, 'marketOpen': True,
        'productVerified': True, 'sourceDisabled': False,
        'source': 'SG · Emittent', 'currency': 'EUR',
        'metadata': {'status': 1, 'issuerExchangeCode': 'CBDE'},
        'bid': 50.1, 'ask': 50.2,
        'quoteAt': at(20), 'bidAt': at(20), 'askAt': at(20),
        'chartEvidence': {
            'currency': 'EUR', 'bid': 50.11, 'ask': 50.21,
            'pointAt': at(5)
        }
    }


def comdirect_original():
    pair = {
        'isin': ISIN, 'bid': 50.1, 'ask': 50.2,
        'currency': 'EUR', 'source': 'comdirect · SG LiveTrading',
        'venue': 'LT Societe Generale',
        'isExecutableQuote': False, 'degiroExecutable': False,
        'priceKind': 'market-observation', 'delayed': False,
        'quoteAt': at(20), 'bidAt': at(20), 'askAt': at(20),
    }
    root = issuer_original()
    root.update(found=False, eligible=False, analysisQuote=pair)
    return root


class BidAskBeforeChartTests(unittest.TestCase):
    def test_fresh_validated_issuer_pair_wins_even_if_chart_is_newer(self):
        original = issuer_original()
        before = copy.deepcopy(original)
        self.assertTrue(leverage_backup.current_observed_bid_ask(
            original, original, NOW))
        selected = leverage_backup.select_analysis_quote(original, NOW)
        self.assertIs(selected, original)
        self.assertEqual(selected['ask'], 50.2)
        self.assertEqual(original, before)

    def test_original_comdirect_pair_wins_if_issuer_chart_is_newer(self):
        original = comdirect_original()
        before = copy.deepcopy(original)
        chosen = leverage_backup.select_analysis_quote(original, NOW)
        self.assertEqual(chosen, original['analysisQuote'])
        self.assertEqual(chosen['priceKind'], 'market-observation')
        self.assertEqual(chosen['quoteAt'], at(20))
        self.assertFalse(chosen['isExecutableQuote'])
        self.assertEqual(original, before)

    def test_invalid_or_old_bid_ask_never_blocks_valid_chart(self):
        for change in (
            lambda x: x.update(eligible=False),
            lambda x: x.update(marketOpen=False),
            lambda x: x.update(found=False),
            lambda x: x.update(sourceDisabled=True),
            lambda x: x['metadata'].update(status=2),
            lambda x: x.update(bidAt=at(95), askAt=at(95), quoteAt=at(95)),
            lambda x: x.update(bid=51.0, ask=50.2),
        ):
            with self.subTest(change=change):
                original = issuer_original()
                change(original)
                selected = leverage_backup.select_analysis_quote(original, NOW)
                self.assertEqual(selected['priceKind'], 'issuer-chart')
                self.assertEqual(selected['ask'], 50.21)

    def test_unverified_backup_cannot_override_chart(self):
        original = comdirect_original()
        for invalid in (
            lambda p: p.update(venue='Swiss DOTS'),
            lambda p: p.update(isExecutableQuote=True),
            lambda p: p.update(degiroExecutable=True),
            lambda p: p.update(askAt=at(30)),
            lambda p: p.update(bidAt=at(95), askAt=at(95), quoteAt=at(95)),
        ):
            with self.subTest(invalid=invalid):
                sample = copy.deepcopy(original)
                invalid(sample['analysisQuote'])
                selected = leverage_backup.select_analysis_quote(sample, NOW)
                self.assertEqual(selected['priceKind'], 'issuer-chart')


if __name__ == '__main__':
    unittest.main()
