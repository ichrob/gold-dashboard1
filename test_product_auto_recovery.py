"""Source reconciliation must repair data diagnostics without approving orders."""
import copy
import unittest
from unittest.mock import patch
import degiro_product_audit as audit
from test_degiro_product_audit import NOW, ISIN, iso, provider, feed
from term_series import observed_condition


class AutoRecoveryTests(unittest.TestCase):
    def pair(self):
        return dict(isin=ISIN, bid=6, ask=6.02, currency='EUR',
            bidAt=iso(NOW-1000), askAt=iso(NOW-1000), quoteAt=iso(NOW-1000),
            source='comdirect · SG LiveTrading', venue='LT Societe Generale',
            priceKind='market-observation', isExecutableQuote=False, degiroExecutable=False)

    def source(self):
        q = provider()
        q.update(found=False, eligible=False, marketOpen=None, secondaryQuote=self.pair())
        q['metadata']['issuerExchangeCode'] = 'CBDE'
        return q

    def test_backup_repairs_data_pair_without_changing_execution_flags(self):
        q = self.source(); before = copy.deepcopy(q)
        q['bidAt'] = q['askAt'] = None
        item = audit.examine(feed()['products'][0], q, NOW)
        for code in ('quote', 'quote-time', 'market-status'):
            self.assertNotIn(code, item['missing'])
        self.assertEqual(item['dataQuoteKind'], 'market-observation')
        self.assertEqual(item['quoteSourceAt'], self.pair()['bidAt'])
        self.assertFalse(item['tradeApproved']); self.assertFalse(item['degiroVerified'])
        self.assertFalse(q['found']); self.assertFalse(q['eligible'])
        self.assertEqual(q['secondaryQuote'], before['secondaryQuote'])

    def test_bad_or_old_backup_stays_missing(self):
        for change in (dict(isin='DE000FC1CHB7'), dict(currency='CHF'), dict(venue='other'),
                       dict(priceKind='issuer-chart'), dict(isExecutableQuote=True),
                       dict(bidAt=iso(NOW-90001)), dict(askAt=iso(NOW+1)),
                       dict(delayed=True), dict(ask=1), dict(source='unknown')):
            q=self.source(); q['secondaryQuote'].update(change)
            self.assertIn('quote', audit.examine(feed()['products'][0], q, NOW)['missing'], change)

    def test_conflicting_identity_stays_unconfirmed(self):
        for change in (dict(productDirection='LONG'), dict(currency='CHF'),
                       dict(snapshot={'isin':'DE000FC1CHB7'}), dict(snapshot={'direction':'LONG'})):
            product=dict(feed()['products'][0], isinConfirmed=False, **change)
            self.assertIn('list-identity', audit.examine(product, provider(), NOW)['missing'])

    def test_verified_secondary_terms_and_original_series_clock(self):
        q=provider(); q['metadata'].pop('ratio'); q['metadata'].pop('strike')
        q['metadata']['termsFixed']=False
        source='https://www.comdirect.de/inf/zertifikate/'+ISIN
        q['conditions']={key:observed_condition(value,source,ISIN,iso(NOW-1000))
                         for key,value in [('ko',4200),('strike',4250)]}
        q['conditions']['ratio']=dict(value=.1,source=source,reviewedAt=iso(NOW),conditionVerified=True)
        item=audit.examine(feed()['products'][0],q,NOW)
        for code in ('ko-time','strike','ratio'):
            self.assertNotIn(code,item['missing'])
        # A fresh fetch/checkedAt cannot renew the original 8-hour series.
        q['checkedAt']=iso(NOW+audit.BARRIER_MAX_MS)
        self.assertIn('ko-time',audit.examine(feed()['products'][0],q,NOW+audit.BARRIER_MAX_MS)['missing'])
        for change in (dict(conflict=True),dict(revoked=True),dict(dateText='01.01.2020')):
            bad=copy.deepcopy(q);bad['conditions']['ko'].update(change)
            self.assertIn('ko-time',audit.examine(feed()['products'][0],bad,NOW)['missing'])

    def test_mismatched_series_does_not_repair_barrier(self):
        q=provider();q['metadata']['termsFixed']=False
        q['conditions']={'ko':observed_condition(4200,'issuer','DE000FC1CHB7',iso(NOW))}
        self.assertIn('ko-time',audit.examine(feed()['products'][0],q,NOW)['missing'])

    def test_recovery_clears_only_repaired_incidents_and_records_it(self):
        product_feed=feed();product_feed['products'][0]['isinConfirmed']=False
        old=None
        for _ in range(3):old=audit.build(product_feed,{},NOW,old)
        self.assertTrue(old['items'][0]['needsKiHelp'])
        q=self.source();q.pop('leverageAt')
        current=audit.build(product_feed,{ISIN:q},NOW,old)
        item=current['items'][0]
        self.assertIn('list-identity',item['recoveredFields'])
        self.assertIn('quote',item['recoveredFields'])
        self.assertEqual(audit.public_help_codes(current),['product-leverage-clock-missing'])
        self.assertFalse(item['tradeApproved'])


if __name__ == '__main__':
    unittest.main()
