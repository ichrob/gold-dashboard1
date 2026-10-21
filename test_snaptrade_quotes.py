import copy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
import snaptrade_quotes as q
import snaptrade_bridge as b
from test_product_quotes import snapshot,ISIN,NOW

SG_ISIN='DE000FG7N6Z2'


class HoldingQuotesTests(unittest.TestCase):
    def test_bnp_factor_observation_without_gold_gate_or_approval(self):
        data=snapshot();data['result']['productName']='Synthetic Faktor Long';data['result']['first']['underlyingISIN']='SYNTHETIC'
        out=q.parse_bnp(data,ISIN,'EUR',NOW)
        self.assertTrue(out['current']);self.assertFalse(out['tradeApproved']);self.assertFalse(out['isDegiroQuote'])
        self.assertEqual(out['bidAt'],'2026-09-30T16:06:00.282000+00:00')
        stale=q.freshness(out,NOW+timedelta(seconds=100))
        self.assertFalse(stale['current'])

    def test_no_implicit_sg_time_no_future_no_crossed_pair(self):
        product=dict(Isin=SG_ISIN,Id=1,Currency='EUR',ExchangeCode='CBDE',Status=129,ProductClassificationId=44100,TodayBarrierHitDate='2026-01-01T12:00:00Z')
        point=dict(Bid=10,Ask=11,Date=NOW.isoformat())
        result=q.parse_sg(product,[point],SG_ISIN,'EUR',NOW)
        self.assertTrue(result['current']);self.assertFalse(result['ended'])
        self.assertEqual(result['kind'],'issuer-chart')
        for change in ({'Date':'2026-09-30T16:06:00'},{'Ask':9},{'Bid':float('nan')}):
            with self.assertRaises(ValueError):q.parse_sg(product,[dict(point,**change)],SG_ISIN,'EUR',NOW)
        future=q.parse_sg(product,[dict(point,Date=(NOW+timedelta(seconds=1)).isoformat())],SG_ISIN,'EUR',NOW)
        self.assertFalse(future['current'])
        self.assertFalse(q.parse_sg(product,[],SG_ISIN,'EUR',NOW)['current'])

    def test_wrong_currency_identity_and_terminal_status(self):
        for mutate in (lambda r:r.update(isin='WRONG'),lambda r:r['currency'].update(isoCode='CHF'),lambda r:r.update(issuerCompanyName='Wrong')):
            data=snapshot();mutate(data['result'])
            with self.assertRaises(ValueError):q.parse_bnp(data,ISIN,'EUR',NOW)
        data=snapshot();data['result']['config']['isCanceled']=True
        self.assertEqual(q.parse_bnp(data,ISIN,'EUR',NOW)['code'],'ENDED')
        data=snapshot();data['result']['ask']=0
        self.assertEqual(q.parse_bnp(data,ISIN,'EUR',NOW)['code'],'ONE_SIDED')

    def test_secondary_row_uses_exact_identity_and_keeps_gold_parser_strict(self):
        html=Path('test_fixtures/comdirect_sg_quote.html').read_text()
        now=datetime.fromisoformat('2026-10-14T05:00:00+00:00')
        # Existing quote fixture is a public product; replace only its type.
        import comdirect_quotes
        original=comdirect_quotes.parse_page(html,SG_ISIN,now)
        at=datetime.fromisoformat(original['bidAt'])
        result=q.parse_comdirect(html,SG_ISIN,'EUR','Société Générale',at)
        self.assertTrue(result['current']);self.assertFalse(result['tradeApproved'])
        with self.assertRaises(ValueError):q.parse_comdirect(html,ISIN,'EUR','Société Générale',at)
        with self.assertRaises(ValueError):q.parse_comdirect(html,SG_ISIN,'EUR','BNP Paribas',at)
        self.assertFalse(q.freshness(result,at+timedelta(seconds=91))['current'])

    def test_all_five_holdings_are_attempted_and_no_chart_promoted(self):
        old=copy.deepcopy(b._STATE)
        try:
            positions=[dict(isin=ISIN,currency='EUR',positionKey=str(i)) for i in range(5)]
            # Same ISIN and currency is fetched once even across multiple lots.
            b._STATE.update(snapshot={'accounts':[{'positions':positions}]})
            calls=[]
            def observe(p):
                calls.append(p['isin']);return dict(isin=p['isin'],currency='EUR',identityVerified=True,kind='issuer-chart',bid='1',ask='2',bidAt=NOW.isoformat(),askAt=NOW.isoformat())
            b.observation_tick(observe)
            self.assertEqual(calls,[ISIN])
            for p in b._STATE['snapshot']['accounts'][0]['positions']:
                self.assertIn('issuerObservation',p)
                self.assertNotIn('issuerQuote',p)
            b.observation_tick(lambda p:dict(isin='WRONG',currency='EUR'))
            self.assertEqual(b._STATE['snapshot']['accounts'][0]['positions'][0]['issuerObservation']['code'],'SOURCE_UNAVAILABLE')
        finally:b._STATE.clear();b._STATE.update(old)

    def test_public_paths_come_only_from_verified_identity(self):
        q._IDENTITIES.clear();calls=[]
        def get(url,*args):
            calls.append(url);return dict(Isin='WRONG',Id=1,Currency='EUR',ExchangeCode='CBDE',Status=1)
        with patch.object(q,'secondary',side_effect=lambda p,r:r):
            result=q.get_observation(dict(isin=SG_ISIN,currency='EUR',name='SG Synthetic'),get)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['code'],'SOURCE_UNAVAILABLE')


if __name__=='__main__':unittest.main()
