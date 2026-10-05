import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
import future_reference as f

NOW=datetime(2026,10,5,20,tzinfo=timezone.utc)
class ReferenceTests(unittest.TestCase):
    def quote(self, **extra):
        return dict(dict(price=4166.15,at=NOW.isoformat(),kind='cfd',declaredContract='GCZ26',realtimeCfd=True),**extra)
    def select(self, quote, contract='GCZ26'):
        with patch.object(f.investing_card,'fetch',return_value=quote):
            return f.select({'contract':contract},{'available':True,'priceUsd':4100,'kind':'estimate'},NOW)
    def test_cfd_preferred_without_inventing_exchange_or_validation(self):
        r=self.select(self.quote())
        self.assertEqual(r['priceUsd'],4166.15)
        self.assertEqual(r['kind'],'cfd-reference')
        self.assertFalse(r['isExchangeRealtime'])
        self.assertFalse(r['validation']['ready'])
        self.assertNotIn('referenceAt',r)
    def test_stale_future_time_wrong_contract_closed_fallback(self):
        for delta in [-61,1]:
            self.assertEqual(self.select(self.quote(at=(NOW+timedelta(seconds=delta)).isoformat()))['kind'],'estimate')
        for change in [dict(declaredContract='GCG27'),dict(realtimeCfd=False),dict(kind='spot')]:
            self.assertEqual(self.select(self.quote(**change))['kind'],'estimate')
        self.assertEqual(self.select(self.quote(),'GCG27')['kind'],'estimate')
    def test_failure_keeps_fallback_provenance(self):
        with patch.object(f.investing_card,'fetch',side_effect=OSError()):
            r=f.select({'contract':'GCZ26'},{'available':False,'reason':'keine Schätzung'},NOW)
        self.assertFalse(r['available']);self.assertEqual(r['reason'],'keine Schätzung')
if __name__=='__main__': unittest.main()
