"""Forward-only measurement of research hybrid projections."""
import datetime as dt
import unittest
from unittest.mock import patch

import estimate_quality as q
import hybrid_product_price as h
from test_hybrid_product_price import record, BASE

def tick(seconds, gold=4150):
    at=(BASE+dt.timedelta(seconds=seconds)).isoformat()
    return (lambda:dict(price=gold,at=at,source='spot fixture'),
            lambda:dict(result='success',base='USD',source='live',
                        sources=dict(EUR='live'),market_session='open',
                        rates=dict(EUR=.92),data_updated_at=at,
                        effective_at=dict(EUR=at)))

class HybridQualityTests(unittest.TestCase):
    def setUp(self):
        self.patchers=[patch.object(h,'_ANCHORS',{})]+[
            patch.object(q,key,{}) for key in ('_pending','_errors','_seen','_truth_receipts')]
        for p in self.patchers:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patchers)])

    def test_freeze_before_quote_arrives_and_show_measured_error(self):
        original=record()
        first=h.apply(original,BASE,*tick(-5))
        self.assertFalse(first['calculatedProduct']['validation']['ready'])
        self.assertEqual(first['calculatedProduct']['validation']['sampleCount'],0)
        later=BASE+dt.timedelta(seconds=40)
        # Provider still displays its old quote. The older model produces a
        # prediction before the new issuer quote is known, at this real time.
        candidate=h.apply(original,later,*tick(40,gold=4155))
        self.assertTrue(candidate['calculatedProduct']['available'])
        self.assertEqual(candidate['calculatedProduct']['validation']['sampleCount'],0)
        # At +70 the issuer finally publishes a quote originally timed at +40.
        # That timestamp can match only the already recorded +40 prediction.
        updated=record()
        updated['chartEvidence'].update(
            bid=13.81,ask=13.83,pointAt=later.isoformat())
        observed=h.apply(updated,BASE+dt.timedelta(seconds=70),*tick(70,gold=4155))
        validation=observed['calculatedProduct']['validation']
        self.assertEqual(validation['sampleCount'],1)
        self.assertFalse(validation['ready'],'a single calibration error is no guarantee')
        self.assertTrue(validation['meanAbsoluteError']>0)
        self.assertEqual(validation['source'],'prospective-sg-comdirect')
        self.assertFalse(validation['affectsApproval'])
        self.assertFalse(observed['calculatedProduct']['eligible'])
        self.assertFalse(observed['calculatedProduct']['isDegiroQuote'])

    def test_calibration_cannot_validate_itself_and_identity_isolated(self):
        a=record()
        r=h.apply(a,BASE,*tick(-5))
        self.assertEqual(r['calculatedProduct']['validation']['sampleCount'],0)
        # Same source observation must not manufacture new truth/evidence.
        r=h.apply(a,BASE+dt.timedelta(seconds=2),*tick(2))
        self.assertEqual(r['calculatedProduct']['validation']['sampleCount'],0)
        model=r['productModel']
        key=h.validation_key(model,'ask')
        self.assertEqual(q.quality(key,5,BASE+dt.timedelta(seconds=2))['sampleCount'],0)
        self.assertNotEqual(key,h.validation_key(dict(model,isin='DE000FG4JXV7'),'ask'))


if __name__=='__main__':
    unittest.main()
