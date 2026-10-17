import copy
import json
import unittest
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
import degiro_product_audit as audit
import paper_simulation as sim
import swissquote_quotes as swiss
from test_degiro_product_audit import provider, NOW


class SourceRefreshTests(unittest.TestCase):
    def test_calculated_price_refreshes_while_all_issuer_slots_are_busy(self):
        from test_hybrid_product_price import record, inputs, BASE, ISIN
        import hybrid_product_price as hybrid
        from datetime import timedelta
        spot,fx=inputs()
        later=BASE+timedelta(seconds=40)
        with patch.object(hybrid,'_ANCHORS',{}):
            raw=hybrid.apply(record(),BASE,spot,fx)
            with patch.object(sim,'_pool',Mock()), \
                 patch.object(sim,'_pending',{str(i):Future() for i in range(4)}), \
                 patch.object(sim,'_quotes',{ISIN:raw}),patch.object(sim,'_requested',{}), \
                 patch('comdirect_fields.apply',side_effect=lambda q,i:q), \
                 patch('comdirect_quotes.apply',side_effect=lambda q,i:q), \
                 patch.object(swiss,'apply',side_effect=lambda q,i:q), \
                 patch('leverage_backup.apply',side_effect=lambda q:q), \
                 patch('spot_data.current',return_value={'price':4160,'at':later.isoformat()}), \
                 patch('sg_quotes.market_input',return_value=dict(fx(),data_updated_at=later.isoformat(),
                       effective_at={'EUR':later.isoformat()})), \
                 patch.object(hybrid,'datetime',wraps=datetime) as clock:
                clock.now.return_value=later
                clock.fromisoformat=datetime.fromisoformat
                result=sim.quote_cache([{'isin':ISIN}],[],later.timestamp()*1000)[ISIN]
        self.assertAlmostEqual(result['calculatedProduct']['askEur'],14.24)
        self.assertFalse(result['calculatedProduct']['isDegiroQuote'])
        self.assertFalse(result['eligible'])
        self.assertAlmostEqual(raw['calculatedProduct']['askEur'],13.32)

    def test_fields_are_harvested_before_issuer_slot_becomes_available(self):
        from test_comdirect_fields import HTML, ISIN as isin, NOW as fixture_now
        raw={'isin':isin,'sourceDisabled':False}
        import comdirect_fields
        # Use parser-owned observations; no identity or source clock invented.
        html=HTML
        fields=comdirect_fields.parse_page(html,isin,fixture_now)
        with patch.object(sim,'_pool',Mock()), patch.object(sim,'_pending',{str(i):Future() for i in range(4)}), \
             patch.object(sim,'_quotes',{isin:raw}), patch.object(sim,'_requested',{}), \
             patch('comdirect_quotes.get_observation',return_value={'state':'observed','fields':fields}), \
             patch('leverage_backup.apply',side_effect=lambda r:r):
            rows=sim.quote_cache([{'isin':isin}],[],NOW)
        self.assertIn('conditions',rows[isin])
        self.assertNotIn('conditions',raw)
        self.assertNotIn('eligible',rows[isin])
        self.assertEqual(rows[isin]['conditions']['ko'],fields['observations']['ko'])

    def test_third_source_reaches_audit_while_issuer_slots_are_busy(self):
        isin='DE000FG14AV8'
        now=datetime.fromisoformat('2026-10-14T18:54:02+02:00')
        raw=provider(); raw.update(isin=isin,found=False,eligible=False,direction='LONG',currency='CHF')
        raw['metadata'].update(currency='CHF',issuerExchangeCode='CBSW',direction='LONG')
        evidence=swiss.parse_payload(json.loads(Path('test_fixtures/swissquote_long.json').read_text()),isin,now)
        pending={str(i):Future() for i in range(4)}
        with patch.object(sim,'_pool',Mock()), patch.object(sim,'_pending',pending), \
             patch.object(sim,'_quotes',{isin:raw}),patch.object(sim,'_requested',{}), \
             patch('comdirect_quotes.apply',side_effect=lambda r,i:r), \
             patch.object(swiss,'get_observation',return_value=evidence), \
             patch.object(swiss,'datetime') as clock:
            clock.now.return_value=now;clock.min=datetime.min;clock.fromisoformat=datetime.fromisoformat
            rows=sim.quote_cache([dict(isin=isin)],[],now.timestamp()*1000)
        self.assertEqual(rows[isin]['thirdQuote']['askAt'],'2026-10-14T18:54:01+02:00')
        self.assertNotIn('thirdQuote',raw)
        result=audit.examine(dict(isin=isin,direction='LONG'),rows[isin],now.timestamp()*1000)
        for key in ('quote','quote-time','underlying','currency'):
            self.assertNotIn(key,result['missing'])
        self.assertIn('venue',result['missing'])
        self.assertFalse(result['tradeApproved'])

    def test_each_backup_refresh_recalculates_before_private_audit(self):
        from test_leverage_backup import Tests, N, T
        import leverage_backup
        fixture=Tests();fixture.setUp()
        isin='DE000FG7K275'
        raw=copy.deepcopy(fixture.r)
        raw.update(isin=isin,eligible=True,bid=3.99,bidAt='2026-10-07T09:50:00Z',askAt='2026-10-07T09:50:00Z')
        raw['leverageCalculation']={'available':False,'reason':'old missing inputs'}
        def backup(q,i):
            out=copy.deepcopy(q)
            out['analysisQuote']=dict(isin=i,bid=4.99,ask=5,askAt=T,bidAt=T,currency='EUR',priceKind='market-observation')
            return out
        pending={str(i):Future() for i in range(4)}
        with patch.object(sim,'_pool',Mock()),patch.object(sim,'_pending',pending), \
             patch.object(sim,'_quotes',{isin:raw}),patch.object(sim,'_requested',{}), \
             patch('comdirect_quotes.apply',side_effect=backup),patch.object(swiss,'apply',side_effect=lambda q,i:q), \
             patch('spot_data.current',return_value=fixture.g),patch('sg_quotes.market_input',return_value=fixture.fx), \
             patch('leverage_backup.datetime') as clock:
            clock.now.return_value=N;clock.min=datetime.min
            rows=sim.quote_cache([dict(isin=isin)],[],N.timestamp()*1000)
        self.assertTrue(rows[isin]['leverageCalculation']['fresh'])
        self.assertEqual(rows[isin]['leverageCalculation']['value'],8)
        self.assertIsNotNone(leverage_backup.current_evidence(rows[isin],N))
        self.assertFalse(raw['leverageCalculation']['available'])

    def test_currency_identity_does_not_change_with_analysis_conversion(self):
        for isin,direction in swiss.PRODUCTS.items():
            q=provider();q.update(isin=isin,direction=direction,currency='EUR')
            q['metadata'].update(currency='CHF',issuerExchangeCode='CBSW',direction=direction)
            product=dict(isin=isin,direction=direction,currency='CHF')
            out=audit.examine(product,q,NOW)
            for key in ('list-identity','underlying','currency'):
                self.assertNotIn(key,out['missing'])
            self.assertIn('venue',out['missing'])
            product['currency']='EUR'
            self.assertIn('currency',audit.examine(product,q,NOW)['missing'])

    def test_unconfirmed_currency_and_wrong_underlying_still_fail(self):
        q=provider();q['metadata']['currency']='USD'
        self.assertIn('currency',audit.examine(dict(isin=q['isin'],direction='SHORT'),q,NOW)['missing'])
        q['metadata']['underlying']='Silver'
        self.assertIn('underlying',audit.examine(dict(isin=q['isin'],direction='SHORT'),q,NOW)['missing'])

if __name__=='__main__':unittest.main()
