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
