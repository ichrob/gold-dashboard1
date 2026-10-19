"""Continuity is valuation only; original evidence and release gates stay intact."""
import copy
import datetime as dt
import unittest
from unittest.mock import patch
import price_continuity as pc
from test_hybrid_product_price import TestHybridProjection, inputs, BASE, at


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.r = TestHybridProjection().bnp()
        self.r.update(eligible=False, bidAt=at(200), askAt=at(200),
                      quoteFailureCode='STALE_OR_INVALID_SOURCE_TIME')
        self.s, self.fx = inputs()
        self.p = patch.object(pc, '_PENDING', {})
        self.p.start(); self.addCleanup(self.p.stop)

    def run_model(self, r=None, spot=None, fx=None):
        return pc.apply(r or self.r, BASE, spot or self.s, fx or self.fx)

    def test_no_anchor_model_price_and_leverage_without_fake_spread(self):
        before=copy.deepcopy(self.r)
        out=self.run_model(); c=out['priceContinuity']
        self.assertEqual(c['state'],'calculated')
        self.assertEqual(c['kind'],'intrinsic')
        self.assertAlmostEqual(c['price'],13.8)
        self.assertAlmostEqual(c['leverage'],4150/150)
        self.assertNotIn('bid',c);self.assertNotIn('ask',c)
        self.assertFalse(c['eligible']);self.assertFalse(c['degiroExecutable'])
        self.assertEqual(self.r,before)
        for k,v in before.items():self.assertEqual(out[k],v)

    def test_returns_to_fresh_original_and_compares_matching_clock(self):
        self.run_model()
        recovered=dict(self.r,bidAt=at(4),askAt=at(4),bid=13.8,ask=13.82)
        c=self.run_model(recovered)['priceContinuity']
        self.assertEqual(c['state'],'original')
        self.assertAlmostEqual(c['comparison']['differenceEur'],.01)
        recovered.update(bidAt=at(50),askAt=at(50))
        self.assertNotIn('comparison',self.run_model(recovered)['priceContinuity'])

    def test_rejects_stale_or_skewed_inputs_changed_model_and_ko(self):
        for spot,fx in ((inputs(spot_age=61)[0],self.fx),
                        (self.s,inputs(fx_age=61)[1]),
                        (inputs(spot_age=40)[0],self.fx),
                        (inputs(gold=3999)[0],self.fx)):
            self.assertEqual(self.run_model(spot=spot,fx=fx)['priceContinuity']['state'],'unavailable')
        for changes in ({'currency':'CHF'},{'underlyingType':'FUTURE'},
                        {'status':2},{'tradingHalted':True},{'ko':4100}):
            r=copy.deepcopy(self.r);r['metadata'].update(changes)
            self.assertEqual(self.run_model(r)['priceContinuity']['state'],'unavailable')

    def test_freshest_same_currency_identity_only(self):
        r=copy.deepcopy(self.r)
        r['analysisQuote']=dict(r, bidAt=at(10),askAt=at(10),source='comdirect')
        r['secondaryQuote']=dict(r, bidAt=at(5),askAt=at(5),source='other')
        self.assertEqual(self.run_model(r)['priceContinuity']['source'],'other')
        r['secondaryQuote']['isin']='wrong'
        self.assertEqual(self.run_model(r)['priceContinuity']['source'],'comdirect')
        r['analysisQuote']['currency']='CHF'
        self.assertEqual(self.run_model(r)['priceContinuity']['state'],'calculated')

    def test_promotion_keeps_verified_issuer_model(self):
        r=copy.deepcopy(self.r)
        r['issuerModelSource']={k:r[k] for k in ('isin','source','sourceUrl')}
        r.update(source='comdirect · BNP LiveTrading',
                 sourceUrl='https://www.comdirect.de/inf/zertifikate/'+r['isin'])
        self.assertEqual(self.run_model(r)['priceContinuity']['state'],'calculated')
        r['issuerModelSource']['isin']='wrong'
        self.assertEqual(self.run_model(r)['priceContinuity']['state'],'unavailable')

    def test_cached_output_does_not_extend_input_lifetime(self):
        out=self.run_model()
        self.assertEqual(self.run_model(out,inputs(spot_age=90)[0])['priceContinuity']['state'],'unavailable')

if __name__=='__main__':unittest.main()
