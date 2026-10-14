import unittest
from datetime import datetime, timezone
from trade_workflow import eligible_purchase, receipt_clock
from real_trade_journal import sale_matches

class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,14,14,tzinfo=timezone.utc)
        self.buy={'status':'pending-review','side':'BUY','isin':'DE000FG309G0','quantity':2,'priceEur':10,'executedLocal':'14.10.2026 13:00:00'}
    def test_current_receipt_preserves_source_time(self):
        self.assertTrue(eligible_purchase(self.buy,[self.buy],self.now))
        self.assertIsNone(receipt_clock(self.buy).tzinfo)
    def test_historic_future_and_invalid_receipts_do_not_activate(self):
        for patch in ({'executedLocal':'13.10.2026 13:00:00'},{'executedLocal':'14.10.2026 17:00:00'},{'quantity':True},{'priceEur':float('nan')},{'status':'incomplete'},{'side':'SELL'}):
            r={**self.buy,**patch};self.assertFalse(eligible_purchase(r,[r],self.now))
    def test_sale_or_multiple_buys_prevent_reopening(self):
        for side in ('BUY','SELL'):
            other={**self.buy,'side':side,'executedLocal':'14.10.2026 14:00:00'}
            self.assertFalse(eligible_purchase(self.buy,[self.buy,other],self.now))
    def test_source_local_buy_can_match_later_full_sale(self):
        snap={'product':{'isin':self.buy['isin'],'quantity':2},'purchase':{'at':None,'executedLocal':'13.10.2026 10:00:00'}}
        sale={**self.buy,'side':'SELL','executedLocal':'13.10.2026 11:00:00','orderIdDigest':'a'*64}
        self.assertTrue(sale_matches(snap,sale))
        self.assertFalse(sale_matches(snap,{**sale,'quantity':1}))
        self.assertFalse(sale_matches(snap,{**sale,'executedLocal':'13.10.2026 09:00:00'}))
if __name__=='__main__':unittest.main()
