import json
import unittest
from unittest.mock import Mock, patch
import real_trade_journal as j


class SaleClosureTests(unittest.TestCase):
    def setUp(self):
        self.trade={'tradeId':'real-1','active':True,'product':{'isin':'DE000FG7K275','quantity':2},
                    'purchase':{'at':'2026-10-01T10:00:00+02:00'}}
        self.sale={'status':'pending-review','side':'SELL','isin':'DE000FG7K275','quantity':2,
                   'priceEur':12.5,'executedLocal':'02.10.2026 11:00:00','orderIdDigest':'a'*64}

    def test_full_sale_matches_without_inventing_execution_timezone(self):
        self.assertTrue(j.sale_matches(self.trade,self.sale))
        self.assertNotIn('executedAt',self.sale)

    def test_partial_wrong_isin_buy_old_future_and_unparsed_never_close(self):
        for mutation in ({'quantity':1},{'isin':'other'},{'side':'BUY'},
                         {'executedLocal':'01.10.2026 09:00:00'},
                         {'executedLocal':'02.10.2099 11:00:00'},
                         {'status':'incomplete'},{'orderIdDigest':None},
                         {'priceEur':False}):
            with self.subTest(mutation=mutation):
                self.assertFalse(j.sale_matches(self.trade,{**self.sale,**mutation}))

    def connection(self,rows,prior=None):
        conn=Mock()
        conn.execute.return_value.fetchall.side_effect=[rows,[('mail-1',{'result':self.sale})]]
        conn.execute.return_value.fetchone.return_value=prior
        return conn

    def test_close_records_sale_preserves_purchase_and_stops_devices(self):
        conn=self.connection([('real-1',self.trade)])
        with patch.object(j,'sync_devices') as sync,patch.object(j,'event') as event:
            self.assertEqual(j.reconcile_sales(conn),1)
            sync.assert_called_once_with(conn)
            self.assertEqual(event.call_count,2)
            self.assertEqual([c.args[2] for c in event.call_args_list],['sale-email-monitoring-closed','trade-evaluated'])
        update=next(c for c in conn.execute.call_args_list if 'UPDATE bob_real_trades' in c.args[0])
        saved=json.loads(update.args[1][0])
        self.assertFalse(saved['active']);self.assertEqual(saved['purchase'],self.trade['purchase'])
        self.assertEqual(saved['exitReceipt']['priceEur'],12.5)
        self.assertNotIn('actualExecution',saved)  # Costs/FX are not guessed.

    def test_ambiguous_positions_or_consumed_sale_never_close(self):
        for rows,prior in (([('one',self.trade),('two',self.trade)],None),
                           ([('one',self.trade)],('closed-already',))):
            with patch.object(j,'sync_devices') as sync,patch.object(j,'event') as event:
                self.assertEqual(j.reconcile_sales(self.connection(rows,prior)),0)
                sync.assert_not_called();event.assert_not_called()

    def test_exact_buy_sell_mail_pair_gives_native_chf_result(self):
        snap={'product':{'isin':'DE000FG7K275','quantity':2,'entry':13.25,'currency':'EUR'}}
        buy={'status':'pending-review','side':'BUY','isin':'DE000FG7K275',
             'quantity':2,'priceEur':13.25,'totalChf':25.10,'costsChf':0.52,
             'orderIdDigest':'b'*64,'executedLocal':'16.10.2026 09:40:40'}
        sell={'status':'pending-review','side':'SELL','isin':'DE000FG7K275',
              'quantity':2,'priceEur':11.47,'totalChf':20.76,'costsChf':0.51,
              'orderIdDigest':'a'*64,'executedLocal':'16.10.2026 14:58:05'}
        result=j.matched_email_chf_settlement(snap,sell,[buy,sell])
        self.assertEqual(result['netCHF'],-4.34)
        self.assertEqual(result['purchaseFeesCHF'],0.52)
        self.assertEqual(result['saleFeesCHF'],0.51)
        self.assertIsNone(j.matched_email_chf_settlement(snap,sell,[buy,buy,sell]))
        self.assertIsNone(j.matched_email_chf_settlement(snap,{**sell,'totalChf':None},[buy,sell]))
        self.assertIsNone(j.matched_email_chf_settlement(snap,sell,[{**buy,'quantity':3},sell]))
        self.assertIsNone(j.matched_email_chf_settlement(snap,sell,[{**buy,'priceEur':14.00},sell]))

    def test_no_open_trade_is_idempotent(self):
        conn=Mock();conn.execute.return_value.fetchall.return_value=[]
        self.assertEqual(j.reconcile_sales(conn),0)
        self.assertEqual(conn.execute.call_count,1)


if __name__=='__main__':unittest.main()
