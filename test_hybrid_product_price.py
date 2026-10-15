"""Hybrid chart/comdirect anchored theoretical prices, no trade clearance."""
import copy
import datetime as dt
import unittest
from unittest.mock import patch

import hybrid_product_price as h

ISIN='DE000FC1CHB7'
BASE=dt.datetime(2026,10,15,17,5,tzinfo=dt.timezone.utc)


def at(seconds):
    return (BASE-dt.timedelta(seconds=seconds)).isoformat()


def record():
    m={'status':1,'issuerExchangeCode':'CBDE','currency':'EUR',
       'underlyingType':'SPOT','underlying':'XAU/USD',
       'simpleNonQuantoTurbo':True,'classificationId':45,'direction':'LONG',
       'ko':4000.,'strike':4000.,'ratio':0.1}
    return dict(isin=ISIN,productVerified=True,found=False,eligible=False,
                importActive=True,sourceFailure=False,metadata=m,
                conditions={'maturity':dict(value='Open End')},
                chartEvidence=dict(bid=13.3,ask=13.32,currency='EUR',
                                   pointAt=at(6)))


def inputs(gold=4150,spot_age=5,fx_age=6):
    spot=lambda:{'price':gold,'at':at(spot_age),'source':'Gold Spot Test'}
    fx=lambda:dict(result='success',base='USD',source='live',
                   sources={'EUR':'live'},market_session='open',
                   rates={'EUR':0.92},data_updated_at=at(fx_age),
                   effective_at={'EUR':at(fx_age)})
    return spot,fx


class TestHybridProjection(unittest.TestCase):
    def setUp(self):
        self.p=patch.object(h,'_ANCHORS',{})
        self.p.start();self.addCleanup(self.p.stop)

    def test_sg_chart_anchor_then_forward_with_same_original_clock(self):
        r=record();s,fx=inputs()
        v=h.apply(r,BASE,s,fx)
        self.assertEqual(v['hybridModelState'],'research-only')
        c=v['calculatedProduct']
        self.assertEqual(c['kind'],'calculated-turbo')
        self.assertEqual(c['anchorKind'],'research-hybrid')
        self.assertFalse(c['eligible']);self.assertFalse(c['isDegiroQuote'])
        self.assertFalse(c['validation']['ready'])
        self.assertEqual(c['referenceSource'],'SG · Live-Chart')
        self.assertEqual(c['referenceAt'],at(6))
        self.assertEqual(c['priceAt'],at(6))  # older FX original input clock
        self.assertAlmostEqual(c['askEur'],13.32)
        self.assertAlmostEqual(c['bidEur'],13.3)
        self.assertEqual(r['chartEvidence']['ask'],13.32)
        self.assertFalse(r.get('calculatedProduct',{}).get('available',False))
        later=BASE+dt.timedelta(seconds=40)
        def later_spot():return {'price':4160,'at':later.isoformat(),'source':'Gold Spot Test'}
        def later_fx():return dict(fx(),data_updated_at=later.isoformat(),
              effective_at={'EUR':later.isoformat()})
        projected=h.apply(r,later,later_spot,later_fx)
        value=projected['calculatedProduct']
        self.assertAlmostEqual(value['askEur'],14.24)
        self.assertEqual(value['referenceAt'],at(6))
        self.assertLess(value['referenceAgeSeconds'],60)

    def test_comdirect_anchor_without_sg_chart(self):
        r=record();r.pop('chartEvidence')
        r['analysisQuote']=dict(isin=ISIN,currency='EUR',
            bid=10,ask=10.03,bidAt=at(6),askAt=at(6),
            priceKind='market-observation',source='comdirect · SG LiveTrading',
            isExecutableQuote=False,degiroExecutable=False)
        s,fx=inputs();v=h.apply(r,BASE,s,fx)
        self.assertEqual(v['calculatedProduct']['referenceSource'],
                         'comdirect · SG LiveTrading')
        self.assertEqual(v['calculatedProduct']['askEur'],10.03)

    def test_non_matching_or_unsafe_inputs_fail_closed(self):
        r=record();s,fx=inputs()
        for field,p in (
            ('root',dict(isin='DE000FG4JXV7')),
            ('root',dict(productVerified=False)),
            ('root',dict(sourceFailure=True)),
            ('root',dict(sourceDisabled=True)),
            ('root',dict(quoteFailureCode='SG_SOURCE_UNAVAILABLE')),
            ('root',dict(importActive=False)),
            ('root',dict(eligible=True)),
            ('meta',dict(status=2)),
            ('meta',dict(tradingHalted=True)),
            ('meta',dict(currency='CHF')),
            ('meta',dict(underlyingType='FUTURE')),
            ('meta',dict(underlying='GCZ26')),
            ('meta',dict(simpleNonQuantoTurbo=False)),
            ('meta',dict(classificationId=44100)),
            ('meta',dict(direction='OTHER')),
            ('meta',dict(strike=0)),
            ('quote',dict(currency='CHF')),
            ('quote',dict(bid=13.5,ask=13.3)),
            ('quote',dict(pointAt='2026-10-15T13:00:00+00:00')),
            ('quote',dict(pointAt=(BASE+dt.timedelta(seconds=2)).isoformat())),
            ('quote',dict(pointAt=at(100))),
            ('quote',dict(pointAt='2026-10-15T17:04:54')),
        ):
            with self.subTest(field=field,change=p):
                x=copy.deepcopy(r)
                target=x if field=='root' else x['metadata'] if field=='meta' else x['chartEvidence']
                target.update(p)
                self.assertNotIn('calculatedProduct',h.apply(x,BASE,s,fx))
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,*inputs(spot_age=90)))
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,*inputs(fx_age=61)))

    def test_quote_clock_skew_blocks_reanchor_but_retains_old_anchor(self):
        r=record()
        s,fx=inputs();h.apply(r,BASE,s,fx)
        moved=BASE+dt.timedelta(seconds=100)
        # Original SG point 6s before the first run: now 106s ago.
        s2=lambda:{'price':4156,'at':moved.isoformat()}
        f2=lambda:dict(fx(),data_updated_at=moved.isoformat(),
                 effective_at={'EUR':moved.isoformat()})
        v=h.apply(r,moved,s2,f2)
        self.assertAlmostEqual(v['calculatedProduct']['askEur'],13.872)
        self.assertEqual(v['calculatedProduct']['referenceAt'],at(6))
        # No new anchor after 30 minutes.
        late=BASE+dt.timedelta(seconds=1900)
        s3=lambda:{'price':4160,'at':late.isoformat()}
        f3=lambda:dict(fx(),data_updated_at=late.isoformat(),
                 effective_at={'EUR':late.isoformat()})
        self.assertNotIn('calculatedProduct',h.apply(r,late,s3,f3))

    def test_quote_does_not_derive_bid_from_single_list_price(self):
        r=record();r.pop('chartEvidence')
        r['price']=10.0 # DEGIRO list row, not bid/ask
        s,fx=inputs()
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,s,fx))
        self.assertNotIn('productModel',h.apply(r,BASE,s,fx))

    def test_missing_fx_or_gold_never_generates_model(self):
        r=record();s,fx=inputs()
        for bad in [
           lambda:dict(fx(),source='delayed'),
           lambda:dict(fx(),market_session='closed'),
           lambda:dict(fx(),rates={'EUR':-1}),
           lambda:dict(fx(),sources={'EUR':'delayed'}),
           lambda:dict(fx(),effective_at={'EUR':at(140)}),
        ]:
            self.assertNotIn('calculatedProduct',h.apply(r,BASE,s,bad))
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,*inputs(gold=3990)))
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,*inputs(gold=0)))

    def test_original_quote_or_existing_issuer_calculation_wins(self):
        r=record();s,fx=inputs()
        q=copy.deepcopy(r);q['eligible']=True
        self.assertIs(h.apply(q,BASE,s,fx),q)
        q=copy.deepcopy(r);q['calculatedProduct']=dict(available=True,
           kind='calculated-turbo',referenceAt=at(7))
        self.assertIs(h.apply(q,BASE,s,fx),q)


if __name__=='__main__':
    unittest.main()
