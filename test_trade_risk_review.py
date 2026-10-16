"""Risk, confirmed screenshot matching, fee P&L and 30-second watcher tests."""
import json
import unittest
from unittest.mock import patch

import trade_risk_review as risk
import real_trade_journal as journal
import manual_paper_watch as watch


ISIN='DE000FC1CHB7'
BASE={
  'tradeId':'real-screenshot-1','active':True,'dir':'LONG',
  'product':{'isin':ISIN,'entry':13.25,'quantity':2,'currency':'EUR'},
  'purchase':{'at':'2026-10-16T09:40:40+02:00','totalCHF':25.50,'feesCHF':0.46},
}
SALE={
  'side':'SELL','isin':ISIN,'quantity':2,'transactionId':'547600895',
  'imageSha256':'a'*64,'executedLocal':'16.10.2026 14:58:05',
  'price':11.47,'saleValueCHF':21.27,'feesCHF':0.51,
  'saleNetCHF':20.76,'eurPerCHF':1.0783,
  'exitReason':'stop-loss-user-confirmed'
}


class DummyResult:
    def __init__(self,value):self.value=value
    def fetchone(self):return self.value


class Conn:
    def __init__(self,active=True):
        self.active=active
        self.snapshot=dict(BASE)
        self.operations=[]
    def execute(self,sql,args=()):
        self.operations.append((sql,args))
        if 'SELECT active,snapshot FROM bob_real_trades' in sql:
            return DummyResult((self.active,self.snapshot))
        if 'SELECT id FROM bob_real_trades' in sql:
            return DummyResult(None)
        return DummyResult(None)


class TradeRiskTests(unittest.TestCase):
    def test_product_stop_fees_chf_break_even(self):
        review=risk.preview(dict(entry=13.25,quantity=2,stop=11.50,target=15,
            chfPerUnit=1/1.0783,buyFeeCHF=.50,sellFeeCHF=.51,maxRiskPct=5))
        self.assertAlmostEqual(review['riskPct'],13.21,places=2)
        self.assertLess(review['riskStopCHF'],-4)
        self.assertGreater(review['breakEvenProduct'],13.25)
        self.assertTrue(any('Risikogrenze' in m for m in review['warnings']))
        self.assertFalse(review['executable'])
    def test_structure_atr_and_fail_closed(self):
        r=risk.preview(dict(entry=13,quantity=2,atr=.5,structureStop=12.0))
        self.assertEqual(r['suggestedStop'],12.0)
        self.assertIsNone(r['breakEvenProduct'])
        for bad in [dict(entry=13,quantity=2,stop=13.1),
                    dict(entry=13,quantity=2,target=12.9),
                    dict(entry=float('nan'),quantity=2),
                    dict(entry=13,quantity=0),
                    dict(entry=13,quantity=1.2)]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                risk.preview(bad)
    def test_evaluation_never_mistakes_model_for_execution(self):
        closed={**BASE,'active':False,
            'exitReceipt':{'saleNetCHF':20.76,'source':'Screenshot vom Nutzer bestätigt'}}
        result=risk.evaluation(closed,[10,14,13.5])
        self.assertEqual(result['realizedNetCHF'],-4.74)
        self.assertEqual(result['modelObservations'],3)
        self.assertEqual(result['modelMfePct'],5.66)
        self.assertEqual(result['verdict'],'Verlust')
        self.assertTrue(result['modelOnly'])


class ConfirmSaleTests(unittest.TestCase):
    def submit(self,sale=None,user=True,conn=None):
        conn=conn or Conn()
        with patch.object(journal,'event'),patch.object(journal,'sync_devices') as sync:
            result=journal.confirmed_screenshot_sale(conn,dict(tradeId=BASE['tradeId'],
                   userConfirmed=user,sale=SALE if sale is None else sale))
        return result,conn,sync
    def test_confirm_close_archive_and_stop_monitoring(self):
        result,c,sync=self.submit()
        self.assertTrue(result['closed'])
        self.assertEqual(result['evaluation']['realizedNetCHF'],-4.74)
        updates=[(sql,args) for sql,args in c.operations if 'UPDATE bob_real_trades SET active=FALSE' in sql]
        self.assertEqual(len(updates),1)
        saved=json.loads(updates[0][1][0])
        self.assertFalse(saved['active'])
        self.assertEqual(saved['exitReceipt']['transactionId'],'547600895')
        self.assertEqual(saved['monitoringStatus'],'closed')
        sync.assert_called_once()
    def test_no_unconfirmed_sale_no_mismatched_receipt(self):
        errors=[({**SALE,'isin':'DE000AA00000'},True),
                ({**SALE,'quantity':3},True),({**SALE,'side':'BUY'},True),
                ({**SALE,'saleNetCHF':21.50},True),
                ({**SALE,'eurPerCHF':1.0},True),
                ({**SALE,'imageSha256':''},True),
                (SALE,False)]
        for sale,user in errors:
            with self.subTest(sale=sale,user=user),self.assertRaises(ValueError):
                self.submit(sale,user)
        with self.assertRaises(ValueError):
            self.submit(conn=Conn(active=False))
    def test_polling_interval_minimum_thirty_seconds(self):
        self.assertEqual(watch.WATCH_POLL_INTERVAL_MS,30000)


if __name__=='__main__':unittest.main()
