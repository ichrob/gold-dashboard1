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
    return dict(isin=ISIN,sourceUrl='https://www.sg-zertifikate.de/product-details/'+ISIN.lower(),
                productVerified=True,found=False,eligible=False,
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

    def bnp(self):
        r=record();r.pop('chartEvidence')
        r.update(source='BNP Paribas · Emittent OTC',
                 sourceUrl='https://derivate.bnpparibas.com/product-details/'+ISIN+'/',
                 found=True, currency='EUR', bid=13.3, ask=13.32,
                 bidAt=at(6),askAt=at(6),eligible=True)
        r['metadata'].update(simpleTurbo=True)
        for k in ('ko','strike'):
            r['conditions'][k]=dict(value=r['metadata'][k],conditionVerified=True,dateText='15.10.2026')
        obs={k:dict(value=r['metadata'][k]) for k in ('ratio','direction','currency','underlying')}
        obs.update(quanto=dict(value=False),issuer=dict(value='BNP Paribas'))
        r['comdirectFieldsBackup']=dict(isin=ISIN,state='active',conflicts=[],inactive=False,
            source='https://www.comdirect.de/inf/zertifikate/'+ISIN,checkedAt=at(2),observations=obs)
        return r

    def test_sg_original_prepares_anchor_without_replacing_quote(self):
        r=record();r.update(found=True,eligible=True)
        before=copy.deepcopy(r);spot,fx=inputs()
        direct=h.apply(r,BASE,spot,fx)
        self.assertEqual(direct,before)
        self.assertEqual(len(h._ANCHORS),1)
        later=BASE+dt.timedelta(seconds=120)
        stale=copy.deepcopy(r);stale.update(eligible=False,fresh=False)
        stale.pop('chartEvidence')
        live_spot=lambda:dict(price=4160,at=later.isoformat())
        live_fx=lambda:dict(fx(),data_updated_at=later.isoformat(),effective_at={'EUR':later.isoformat()})
        model=h.apply(stale,later,live_spot,live_fx)
        self.assertTrue(model['calculatedProduct']['available'])
        self.assertEqual(model['calculatedProduct']['referenceAt'],at(6))
        self.assertFalse(model['eligible'])
        self.assertEqual(r,before)
        # Expired anchors and changed contract identity cannot become a model.
        expired=BASE+dt.timedelta(seconds=1900)
        self.assertNotIn('calculatedProduct',h.apply(stale,expired,
            lambda:dict(price=4160,at=expired.isoformat()),
            lambda:dict(fx(),data_updated_at=expired.isoformat(),effective_at={'EUR':expired.isoformat()})))
        changed=copy.deepcopy(stale);changed['metadata']['strike']+=1
        self.assertNotIn('calculatedProduct',h.apply(changed,later,live_spot,live_fx))

    def test_bnp_original_warms_anchor_then_stale_uses_model_and_recovers(self):
        r=self.bnp();s,fx=inputs()
        direct=h.apply(r,BASE,s,fx)
        self.assertNotIn('calculatedProduct',direct)
        later=BASE+dt.timedelta(seconds=120)
        stale=copy.deepcopy(r);stale.update(eligible=False,fresh=False,
            quoteFailureCode='STALE_OR_INVALID_SOURCE_TIME')
        ls=lambda:dict(price=4160,at=later.isoformat())
        lf=lambda:dict(fx(),data_updated_at=later.isoformat(),effective_at={'EUR':later.isoformat()})
        value=h.apply(stale,later,ls,lf)
        self.assertAlmostEqual(value['calculatedProduct']['askEur'],14.24)
        self.assertEqual(value['calculatedProduct']['referenceAt'],at(6))
        self.assertEqual(value['quoteFailureCode'],'STALE_OR_INVALID_SOURCE_TIME')
        self.assertEqual(value['bidAt'],r['bidAt'])
        self.assertFalse(value['eligible'])
        recovered=dict(r,bidAt=later.isoformat(),askAt=later.isoformat())
        self.assertNotIn('calculatedProduct',h.apply(recovered,later,ls,lf))

    def test_bnp_rejects_unproved_currency_model_expired_terms_and_wrong_identity(self):
        r=self.bnp()
        for mutate in (lambda x:x['comdirectFieldsBackup']['observations'].pop('quanto'),
                       lambda x:x['comdirectFieldsBackup']['observations']['quanto'].update(value=True),
                       lambda x:x['conditions']['ko'].update(dateText='14.10.2026'),
                       lambda x:x['comdirectFieldsBackup'].update(isin='wrong'),
                       lambda x:x.update(quoteFailureCode='INVALID_RESPONSE'),
                       lambda x:x['metadata'].update(status=2)):
            bad=copy.deepcopy(r);mutate(bad)
            self.assertIsNone(h.model_for(bad,BASE))

    def test_bnp_stale_without_aligned_original_reports_no_estimate(self):
        r=self.bnp()
        # A product quote from two minutes earlier cannot be anchored against
        # today's current spot/FX, even when product terms are valid.
        r.update(eligible=False,fresh=False,quoteFailureCode='STALE_OR_INVALID_SOURCE_TIME',
                 bidAt=at(130),askAt=at(130))
        s,fx=inputs()
        out=h.apply(r,BASE,s,fx)
        self.assertEqual(out['hybridModelState'],'awaiting-original-reference')
        self.assertIn('BNP-Originalkurs',out['hybridEstimateReason'])
        self.assertNotIn('calculatedProduct',out)
        self.assertFalse(out['eligible'])
        self.assertEqual(out['bidAt'],at(130))
        self.assertFalse(h._ANCHORS)

    def test_bnp_projection_near_ko_cannot_show_negative_price(self):
        r=self.bnp();s,fx=inputs()
        h.apply(r,BASE,s,fx)  # First authenticated, dated BNP anchor.
        later=BASE+dt.timedelta(seconds=120)
        stale=copy.deepcopy(r)
        stale.update(eligible=False,fresh=False,quoteFailureCode='STALE_OR_INVALID_SOURCE_TIME')
        near_ko=lambda:dict(price=4000.1,at=later.isoformat())
        live_fx=lambda:dict(fx(),data_updated_at=later.isoformat(),
                            effective_at={'EUR':later.isoformat()})
        out=h.apply(stale,later,near_ko,live_fx)
        self.assertEqual(out['hybridModelState'],'unavailable')
        self.assertIn('nicht plausibel positiv',out['hybridEstimateReason'])
        self.assertNotIn('calculatedProduct',out)
        self.assertFalse(out['eligible'])
        self.assertEqual(out['ask'],r['ask'])  # Original quote not overwritten.

    def test_bnp_old_anchor_is_not_an_evergreen_original(self):
        r=self.bnp();s,fx=inputs()
        h.apply(r,BASE,s,fx)
        later=BASE+dt.timedelta(seconds=1801)
        stale=copy.deepcopy(r)
        stale.update(eligible=False,fresh=False,quoteFailureCode='STALE_OR_INVALID_SOURCE_TIME')
        moved=lambda:dict(price=4160,at=later.isoformat())
        live_fx=lambda:dict(fx(),data_updated_at=later.isoformat(),
                            effective_at={'EUR':later.isoformat()})
        out=h.apply(stale,later,moved,live_fx)
        self.assertEqual(out['hybridModelState'],'unavailable')
        self.assertIn('30 Minuten',out['hybridEstimateReason'])
        self.assertNotIn('calculatedProduct',out)
        self.assertFalse(out['eligible'])

    def test_bnp_short_moves_opposite_gold_without_trade_clearance(self):
        r=self.bnp()
        r['metadata'].update(direction='SHORT',ko=4400.,strike=4400.)
        r['comdirectFieldsBackup']['observations']['direction']['value']='SHORT'
        for k in ('ko','strike'):
            r['conditions'][k]['value']=4400.
        r['eligible']=True
        spot,fx=inputs()
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,spot,fx))
        later=BASE+dt.timedelta(seconds=125)
        stale=copy.deepcopy(r)
        stale.update(eligible=False,fresh=False,quoteFailureCode='STALE_OR_INVALID_SOURCE_TIME')
        risen=lambda:dict(price=4160,at=later.isoformat())
        live_fx=lambda:dict(fx(),data_updated_at=later.isoformat(),
                            effective_at={'EUR':later.isoformat()})
        out=h.apply(stale,later,risen,live_fx)
        model=out['calculatedProduct']
        self.assertTrue(model['available'])
        self.assertAlmostEqual(model['askEur'],12.4)
        self.assertEqual(model['direction'],'SHORT')
        self.assertFalse(model['isDegiroQuote'])
        self.assertFalse(model['eligible'])
        self.assertFalse(out['eligible'])
        self.assertEqual(out['ask'],r['ask'])

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
        # Reuse the returned cached payload, as the background refresh does.
        projected=h.apply(v,later,later_spot,later_fx)
        value=projected['calculatedProduct']
        self.assertAlmostEqual(value['askEur'],14.24)
        self.assertEqual(value['referenceAt'],at(6))
        self.assertLess(value['referenceAgeSeconds'],60)
        self.assertAlmostEqual(v['calculatedProduct']['askEur'],13.32)

    def test_cached_projection_disappears_when_inputs_or_terms_fail(self):
        s,fx=inputs()
        cached=h.apply(record(),BASE,s,fx)
        self.assertTrue(cached['calculatedProduct']['available'])
        for change,spot in (({},inputs(spot_age=90)[0]),
                            ({'sourceDisabled':True},s),
                            ({'metadata':dict(record()['metadata'],ko=4200)},s)):
            with self.subTest(change=change):
                result=h.apply(dict(cached,**change),BASE,spot,fx)
                self.assertNotIn('calculatedProduct',result)
                self.assertNotIn('hybridModelState',result)
        self.assertTrue(cached['calculatedProduct']['available'])

    def test_comdirect_anchor_without_sg_chart(self):
        r=record();r.pop('chartEvidence')
        r['analysisQuote']=dict(isin=ISIN,currency='EUR',
            bid=10,ask=10.03,bidAt=at(6),askAt=at(6),
            priceKind='market-observation',source='comdirect · SG LiveTrading',
            venue='LT Societe Generale',
            sourceUrl='https://www.comdirect.de/inf/zertifikate/'+ISIN,
            isExecutableQuote=False,degiroExecutable=False)
        s,fx=inputs();v=h.apply(r,BASE,s,fx)
        self.assertEqual(v['calculatedProduct']['referenceSource'],
                         'comdirect · SG LiveTrading')
        self.assertEqual(v['calculatedProduct']['askEur'],10.03)

    def test_non_matching_or_unsafe_inputs_fail_closed(self):
        r=record();s,fx=inputs()
        for field,p in (
            ('root',dict(isin='DE000FG4JXV7')),
            ('root',dict(sourceUrl='https://www.sg-zertifikate.de/product-details/de000fg4jxv7')),
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
            # Each row tests admission without an earlier valid anchor.
            with self.subTest(field=field,change=p), patch.object(h,'_ANCHORS',{}):
                x=copy.deepcopy(r)
                target=x if field=='root' else x['metadata'] if field=='meta' else x['chartEvidence']
                target.update(p)
                self.assertNotIn('calculatedProduct',h.apply(x,BASE,s,fx))
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,*inputs(spot_age=90)))
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,*inputs(fx_age=61)))

    def test_clock_gap_more_than_30_seconds_rejected_for_new_anchor(self):
        r=record()
        # The SG price was observed 45 seconds ago, while the current Gold
        # price is 5 seconds old; anchoring them together would distort price
        # projections during a fast XAUUSD move.
        r['chartEvidence']['pointAt']=at(46)
        s,fx=inputs(spot_age=5,fx_age=6)
        self.assertNotIn('calculatedProduct',h.apply(r,BASE,s,fx))
        self.assertFalse(h._ANCHORS)
        # Sources can be 29 s apart and still be analysed with original clocks.
        r['chartEvidence']['pointAt']=at(33)
        v=h.apply(r,BASE,s,fx)
        self.assertEqual(v['hybridModelState'],'research-only')
        c=v['calculatedProduct']
        self.assertEqual(c['referenceClockGapSeconds'],28)
        self.assertFalse(c['eligible'])
        self.assertFalse(c['isDegiroQuote'])
        self.assertIn('bis 30 s',c['note'])

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

    def test_comdirect_wrong_venue_or_mismatched_url_rejected(self):
        r=record();r.pop('chartEvidence')
        r['analysisQuote']=dict(isin=ISIN,currency='EUR',
            bid=10,ask=10.03,bidAt=at(6),askAt=at(6),
            priceKind='market-observation',source='comdirect · SG LiveTrading',
            venue='LT Societe Generale',
            sourceUrl='https://www.comdirect.de/inf/zertifikate/'+ISIN,
            isExecutableQuote=False,degiroExecutable=False)
        s,fx=inputs()
        for key,bad in [('venue','LT BNP Paribas'),
                        ('source','comdirect · BNP LiveTrading'),
                        ('sourceUrl','https://www.comdirect.de/inf/zertifikate/DE000FG4JXV7'),
                        ('degiroExecutable',True),
                        ('isExecutableQuote',True)]:
            p=copy.deepcopy(r);p['analysisQuote'][key]=bad
            with self.subTest(key=key):
                self.assertNotIn('calculatedProduct',h.apply(p,BASE,s,fx))

    def test_conflicting_prices_with_same_clock_are_not_reanchored(self):
        p=record();s,fx=inputs()
        self.assertIn('calculatedProduct',h.apply(p,BASE,s,fx))
        p['chartEvidence']['bid']=14.2
        p['chartEvidence']['ask']=14.22
        self.assertNotIn('calculatedProduct',h.apply(p,BASE,s,fx))
        # Changed original quote can be accepted only with a *new* timestamp.
        p['chartEvidence']['pointAt']=at(3)
        self.assertEqual(h.apply(p,BASE,s,fx)['calculatedProduct']['referenceAt'],at(3))

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
