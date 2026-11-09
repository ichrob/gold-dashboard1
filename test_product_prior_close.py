import unittest
from datetime import datetime
from product_prior_close import evaluate

ISIN = 'DE000FG7K283'
PRODUCT = dict(Id=7127448, Isin=ISIN, ExchangeCode='CBDE',
               AssetNMP='XAUUSD', AssetCurrency='USD', Currency='EUR', Status=65)


def at(value):
    return datetime.fromisoformat(value)


class PreviousSessionResearchTests(unittest.TestCase):
    def test_monday_uses_friday_last_observed_not_an_earlier_quote(self):
        now = at('2026-11-09T09:00:30+01:00')
        points = [dict(Date='2026-11-06T21:55:01+01:00', Bid=9, Ask=9.01),
                  dict(Date='2026-11-06T21:59:00+01:00', Bid=10, Ask=10.01),
                  dict(Date='2026-11-09T08:58:20+01:00', Bid=10.5, Ask=10.51),
                  dict(Date='2026-11-09T09:00:00+01:00', Bid=11, Ask=11.01)]
        out = evaluate(PRODUCT, points, ISIN, now=now)
        d = out['dailyChange']
        self.assertAlmostEqual(d['percent'], 10)
        self.assertEqual(d['previousClose'], 10)
        self.assertEqual(d['referenceAt'], '2026-11-06T20:59:00+00:00')
        self.assertEqual(d['at'], '2026-11-09T08:00:00+00:00')
        self.assertEqual(d['basis'], 'bid-vs-last-observed-prior-day')
        self.assertEqual(d['currency'], 'EUR')
        self.assertFalse(d['isExecutableQuote'])
        self.assertIsNone(out['lateReference'])
        # A 30s refresh with only current live point can keep ORIGINAL Friday time.
        subsequent = evaluate(PRODUCT, points[-1:], ISIN, now=now,
                              reference=dict(isin=ISIN, currency='EUR', productId=PRODUCT['Id'],
                                exchangeCode='CBDE', kind='last-observed-late-session-bid',
                                referenceAt=d['referenceAt'], referenceBid=d['previousClose']))
        self.assertEqual(subsequent['dailyChange']['percent'], 10)

    def test_summer_dst_and_chf_market_exact_binding(self):
        now = at('2026-07-06T09:01:00+02:00')
        product = dict(PRODUCT, Currency='CHF', ExchangeCode='CBSW')
        market=('https://www.sg-zertifikate.ch/','CBSW','CHF')
        points=[dict(Date='2026-07-03T21:59:59+02:00',Bid=20),
                dict(Date='2026-07-06T09:00:40+02:00',Bid=19)]
        row=evaluate(product,points,ISIN,now=now,market=market)['dailyChange']
        self.assertEqual(row['currency'],'CHF')
        self.assertAlmostEqual(row['percent'],-5)

    def test_exact_reference_identity_currency_date_and_session_end(self):
        now=at('2026-11-09T09:00:30+01:00')
        points=[dict(Date='2026-11-09T09:00:00+01:00',Bid=11)]
        baseline=dict(isin=ISIN, currency='EUR', productId=PRODUCT['Id'],
                      exchangeCode='CBDE', kind='last-observed-late-session-bid',
                      referenceAt='2026-11-06T21:59:00+01:00', referenceBid=10)
        for key,value in [('isin','DE000OTHER00'),('currency','CHF'),
                          ('productId',999),('exchangeCode','CBSW'),
                          ('kind','unverified'),('referenceAt','2026-11-05T21:59:00+01:00'),
                          ('referenceAt','2026-11-06T12:59:00+01:00'),
                          ('referenceBid',0)]:
            with self.subTest(key=key,value=value):
                changed=dict(baseline,**{key:value})
                self.assertIsNone(evaluate(PRODUCT,points,ISIN,now=now,
                                           reference=changed)['dailyChange'])
        self.assertIsNone(evaluate(PRODUCT,points,ISIN,now=now)['dailyChange'])

    def test_evening_source_bid_is_saved_without_guessing_official_close(self):
        now=at('2026-11-09T21:59:55+01:00')
        points=[dict(Date='2026-11-09T21:54:59+01:00',Bid=9),
                dict(Date='2026-11-09T21:59:30+01:00',Bid=10)]
        out=evaluate(PRODUCT,points,ISIN,now=now)
        self.assertIsNone(out['dailyChange'])
        self.assertEqual(out['lateReference']['referenceBid'],10)
        self.assertEqual(out['lateReference']['referenceAt'],'2026-11-09T20:59:30+00:00')

    def test_no_historical_or_terminal_percent_ever_fabricated(self):
        now=at('2026-11-09T09:00:00+01:00')
        old=[dict(Date='2026-11-06T21:59:00+01:00',Bid=10)]
        self.assertIsNone(evaluate(PRODUCT,old,ISIN,now=now)['dailyChange'])
        pts=old+[dict(Date='2026-11-09T08:59:30+01:00',Bid=11)]
        for terminal in [dict(PRODUCT,Status=2),dict(PRODUCT,TodayBarrierHitDate='2026-11-09')]:
            self.assertIsNone(evaluate(terminal,pts,ISIN,now=now)['dailyChange'])
        with self.assertRaises(ValueError):
            evaluate(dict(PRODUCT,Isin='DE000WRONG00'),pts,ISIN,now=now)
        with self.assertRaises(ValueError):
            evaluate(PRODUCT,list(reversed(pts)),ISIN,now=now)
        with self.assertRaises(ValueError):
            evaluate(PRODUCT,[dict(Date='2026-11-09T09:03:00+01:00',Bid=11)],ISIN,now=now)


if __name__ == '__main__':
    unittest.main()
