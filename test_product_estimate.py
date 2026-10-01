import copy
import unittest
from datetime import timedelta
from unittest.mock import patch

import product_estimate as e
import product_quotes as q
import sg_quotes as sg
from test_sg_quotes import fixture, NOW, AT, ISIN
from test_sg_futures import future_fixture


class ProductEstimateTests(unittest.TestCase):
    def setUp(self):
        self.patches=[patch.object(e,'_anchors',{}),patch.object(sg,'_INPUT_CACHE',{})]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def anchor(self):
        data=fixture()
        result=sg.parse_snapshot(*data,ISIN,NOW)
        self.assertTrue(result['eligible'])
        return result,data

    def inputs(self,data,now,gold=4201.4,fxrate=.884):
        spot,fx=copy.deepcopy(data[3]),copy.deepcopy(data[4])
        spot.update(spot_usd_oz=gold,price_as_of=now.isoformat())
        fx.update(data_updated_at=now.isoformat(),effective_at={'EUR':now.isoformat()},rates={'EUR':fxrate})
        sg._INPUT_CACHE.update(spot=(0,spot),fx=(0,fx))
        return spot,fx

    def test_short_product_formula_and_current_fx(self):
        result,data=self.anchor();now=NOW+timedelta(seconds=80)
        spot,fx=self.inputs(data,now,4201.4,.885)
        stale=q.freshness(result,now);c=stale['calculatedProduct']
        self.assertTrue(c['available']);self.assertFalse(stale['eligible'])
        gold0=result['leverageInputs']['spotUsd'];fx0=result['leverageInputs']['usdEur']
        strike=result['productModel']['strike']
        expected=result['ask']-.1*((4201.4-strike)*.885-(gold0-strike)*fx0)
        self.assertAlmostEqual(c['askEur'],expected,places=4)
        self.assertEqual(c['priceAt'],now.isoformat())
        self.assertFalse(c['eligible']);self.assertEqual(stale['price'],result['price'])
        self.assertEqual(stale['priceKind'],'calculated')
        self.assertAlmostEqual(c['askEur']-c['bidEur'],result['ask']-result['bid'])

    def test_long_model_moves_with_gold_and_observed_quote_has_precedence(self):
        result,data=self.anchor();now=NOW+timedelta(seconds=80)
        model=dict(result['productModel'],direction='LONG',ko=3900,strike=3900)
        anchor=next(iter(e._anchors.values()));anchor=dict(anchor,**model)
        spot,fx=self.inputs(data,now,anchor['underlyingPriceUsd']+10)
        c=e.calculate(model,anchor,spot,fx,now)
        self.assertTrue(c['available']);self.assertAlmostEqual(c['askEur'],anchor['ask']+.884)
        current=q.freshness(result,NOW)
        self.assertEqual(current['priceKind'],'observed-issuer')
        self.assertNotIn('calculatedProduct',current)

    def test_failure_without_anchor_or_with_changed_terms(self):
        result,data=self.anchor();now=NOW+timedelta(seconds=80)
        spot,fx=self.inputs(data,now)
        self.assertFalse(e.calculate(result['productModel'],None,spot,fx,now)['available'])
        anchor=next(iter(e._anchors.values()))
        for k,v in [('underlying','SILVER'),('ratio',.01),('strike',4461),('ko',4461),('direction','LONG'),('classification',1)]:
            out=e.calculate(dict(result['productModel'],**{k:v}),anchor,spot,fx,now)
            self.assertFalse(out['available']);self.assertNotIn('priceEur',out)

    def test_stale_future_inputs_closed_session_ko_and_old_reference_block(self):
        result,data=self.anchor();now=NOW+timedelta(seconds=80)
        spot,fx=self.inputs(data,now)
        anchor=next(iter(e._anchors.values()));model=result['productModel']
        bad=[]
        for at in [(now-timedelta(seconds=61)).isoformat(),(now+timedelta(seconds=1)).isoformat()]:
            bad.append((dict(spot,price_as_of=at),fx))
            bad.append((spot,dict(fx,data_updated_at=at)))
            bad.append((spot,dict(fx,effective_at={'EUR':at})))
        bad.extend([(dict(spot,spot_usd_oz=model['ko']),fx),(spot,dict(fx,market_session='closed'))])
        for s,x in bad:self.assertFalse(e.calculate(model,anchor,s,x,now)['available'])
        old=dict(anchor,referenceAt=(now-timedelta(seconds=1801)).isoformat())
        self.assertFalse(e.calculate(model,old,spot,fx,now)['available'])
        expired=dict(model,tradingEndAt=(now-timedelta(seconds=1)).isoformat())
        self.assertFalse(e.calculate(expired,anchor,spot,fx,now)['available'])

    def test_anchor_requires_tightly_aligned_observations(self):
        data=fixture();data[2]['quote']['datetimeBid']=(NOW-timedelta(seconds=20)).isoformat()
        result=sg.parse_snapshot(*data,ISIN,NOW)
        self.assertTrue(result['eligible']);self.assertFalse(e._anchors)

    def test_source_outage_falls_back_but_identity_error_does_not(self):
        result,data=self.anchor();now=NOW+timedelta(seconds=80)
        self.inputs(data,now)
        with patch.object(sg,'fetch_snapshot',side_effect=OSError('network')),\
             patch.object(sg,'market_input',side_effect=lambda k:sg._INPUT_CACHE[k][1]),\
             patch.object(sg.q,'freshness',wraps=q.freshness) as fresh:
            fallback=sg.get_quote(data[0],data[1],ISIN)
        # get_quote uses real wall clock; recalculate against test time to
        # verify model restoration without accidentally refreshing any input.
        self.assertIn('productModel',fallback)
        fallback=q.freshness(fallback,now)
        self.assertTrue(fallback['calculatedProduct']['available']);self.assertFalse(fallback['found'])
        with patch.object(sg,'fetch_snapshot',side_effect=ValueError('identity mismatch')),\
             patch.object(sg,'market_input',return_value={}):
            blocked=sg.get_quote(data[0],data[1],ISIN)
        self.assertNotIn('productModel',blocked)

    def test_other_verified_sg_products_share_only_the_exact_future_basis(self):
        product,props,snapshot,fx=future_fixture()
        product['Isin']=ISIN;props[0]['Value']=ISIN
        self.assertEqual(q.sg_future_contract(product,ISIN)['ric'],'GCZ26')
        ref=sg.parse_future_research(*future_fixture(),'DE000FG309G0',NOW)
        with patch.dict(sg.PRODUCT_IDS,{},clear=True),patch.object(q,'get_quote',return_value=ref) as shared:
            out=sg.get_quote(product,props,ISIN)
        shared.assert_called_once_with('DE000FG309G0')
        self.assertEqual(out['futureResearch']['underlyingPriceUsd'],ref['futureResearch']['underlyingPriceUsd'])
        for k in ('bid','ask','ratio','indicativeLeverage'):self.assertNotIn(k,out['futureResearch'])
        self.assertFalse(out['eligible']);self.assertFalse(out['found'])
        product['AssetRic']='GCG27'
        self.assertIsNone(q.sg_future_contract(product,ISIN))


if __name__ == '__main__':unittest.main()
