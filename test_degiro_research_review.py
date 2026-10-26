import unittest
from datetime import datetime, timezone, timedelta
import degiro_research_review as review

ISIN='DE000FG4JXV7'
NOW=datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)

def issuer():
    at=(NOW-timedelta(seconds=25)).isoformat()
    return dict(isin=ISIN,productVerified=True,found=True,eligible=True,fresh=True,
                bid=12.1,ask=12.2,leverage=18.1,
                bidAt=at,askAt=at,leverageAt=at,snapshotAt=at,
                metadata=dict(status=1,type='KNOCK_OUT',underlyingType='SPOT',
                              underlying='XAU/USD',currency='EUR',direction='SHORT'))


class ResearchGuardTests(unittest.TestCase):
    def test_symbol_search_is_read_only_even_on_exact_provider_match(self):
        a=review.summarize_symbol_search([{'symbol':ISIN+'.CBDE','tradeable':True}],ISIN)
        self.assertEqual(a['code'],'EXACT_SYMBOL_CANDIDATE')
        self.assertEqual(a['exactSymbolCandidates'],1)
        for k in ('accountTradabilityVerified','completeGoldCatalog','executableQuoteVerified','tradeApproved'):
            self.assertIs(a[k], False)
        self.assertEqual(review.summarize_symbol_search([],ISIN)['code'],'SEARCH_EMPTY')
        self.assertEqual(review.summarize_symbol_search([{'description':ISIN}],ISIN)['code'],'NO_EXACT_SYMBOL')
        with self.assertRaises(ValueError): review.summarize_symbol_search([{}]*21,ISIN)
        with self.assertRaises(ValueError): review.summarize_symbol_search([{'symbol':'X'*200}],ISIN)

    def test_issuer_quote_needs_original_four_clocks_not_request_time(self):
        good=review.issuer_observation(ISIN,'SHORT',issuer(),NOW)
        self.assertEqual(good['sourceRole'],'issuer-comparison-only')
        self.assertFalse(good['executable'])
        for key in ('bidAt','askAt','leverageAt','snapshotAt'):
            row=issuer();row[key]=None
            self.assertIsNone(review.issuer_observation(ISIN,'SHORT',row,NOW))
            row=issuer();row[key]=(NOW-timedelta(seconds=100)).isoformat()
            self.assertIsNone(review.issuer_observation(ISIN,'SHORT',row,NOW))
            row=issuer();row[key]=(NOW+timedelta(seconds=3)).isoformat()
            self.assertIsNone(review.issuer_observation(ISIN,'SHORT',row,NOW))
        for changes in ({'isin':'DE000PJ9NB98'}, {'bid':-1}, {'ask':0.1},
                        {'fresh':False}, {'metadata':{**issuer()['metadata'],'underlyingType':'FUTURE'}},
                        {'metadata':{**issuer()['metadata'],'type':'FACTOR'}}):
            self.assertIsNone(review.issuer_observation(ISIN,'SHORT',{**issuer(),**changes},NOW))

    def test_research_top3_requires_ko_and_financing_evidence(self):
        incomplete=dict(isin=ISIN,direction='SHORT',issuerVerified=True,issuerQuoteFresh=True,issuerLeverage=15)
        a=review.preview_top3([incomplete])
        self.assertEqual(a['status'],'insufficient-original-evidence')
        self.assertEqual(a['entries'],[])
        valid={**incomplete,'koDistancePercent':5.2,'financingCostPercent':1.8}
        b=review.preview_top3([valid,valid])
        self.assertEqual(len(b['entries']),1)
        self.assertFalse(b['entries'][0]['tradeApproved'])
        self.assertFalse(b['entries'][0]['executableQuote'])
        self.assertTrue(b['liveTop3Unchanged'])
        self.assertEqual(review.preview_top3([{**valid,'financingCostPercent':None}])['entries'],[])

    def test_rank_financial_metrics_require_independent_original_clocks(self):
        at=(NOW-timedelta(seconds=12)).isoformat()
        good=dict(koDistancePercent=4.7, financingCostPercent=1.2,
                  koDistanceAt=at, financingCostAt=at)
        self.assertEqual(review.original_ranking_metrics(good,NOW),
                         {'koDistancePercent':4.7, 'financingCostPercent':1.2})
        for changed in ({'koDistanceAt':None},
                        {'financingCostAt':(NOW-timedelta(hours=2)).isoformat()},
                        {'financingCostPercent':None},
                        {'koDistancePercent':-4},
                        {'financingCostPercent':float('nan')}):
            result=review.original_ranking_metrics({**good,**changed},NOW)
            self.assertIsNone(result['koDistancePercent'])
            self.assertIsNone(result['financingCostPercent'])

    def test_reuse_only_today_current_exact_identity_no_quote_extension(self):
        result=review.proof_reuse_summary([
            dict(isin=ISIN,listingConfirmed=True,current=True,executionConfirmed=False),
            dict(isin='DE000PJ9NB98',listingConfirmed=True,current=False,executionConfirmed=False)
        ],[ISIN,'DE000PJ9NB98'])
        self.assertEqual(result['currentIdentityCount'],1)
        self.assertEqual(result['furtherIdentityProofNeeded'],1)
        self.assertEqual(result['noNewScreenshotRequiredFor'],[ISIN])
        self.assertFalse(result['quoteFreshnessExtended'])
        self.assertFalse(result['tradeApproved'])


if __name__=='__main__':
    unittest.main()
