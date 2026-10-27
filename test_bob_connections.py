import unittest
from bob_connections import snapshot

class ConnectionTests(unittest.TestCase):
    def test_read_ok_is_not_fresh_and_unknown_is_not_failure(self):
        r={'observedAt':1000,'areas':{'runtime':{'snaptradePersonal':{'code':'READ_OK','fresh':False,'checkedAt':990}}}}
        rows={x['id']:x for x in snapshot(r,1000)['items']}
        self.assertEqual(rows['snaptrade']['state'],'stale-or-partial')
        self.assertFalse(rows['snaptrade']['dataFresh'])
        self.assertEqual(rows['android']['state'],'unknown')
        self.assertIsNone(rows['android']['lastSuccessAt'])

    def test_missing_future_and_old_clocks_never_current(self):
        for clock in (None, True, 1001, 1):
            r={'observedAt':clock,'areas':{}}
            self.assertNotEqual(snapshot(r,1000)['items'][0]['state'],'current')

    def test_no_private_credentials_or_account_values(self):
        r={'observedAt':1000,'areas':{'runtime':{'snaptradePersonal':{'code':'READ_OK','fresh':True,'checkedAt':999,'token':'SECRET','balance':123456}}}}
        out=str(snapshot(r,1000))
        self.assertNotIn('SECRET',out)
        self.assertNotIn('123456',out)

    def test_browser_receipt_never_claims_handset_display(self):
        r={'areas':{'pushDeliveries':{'records':[{'browserShowReceipt':'confirmed','browserShowAt':999}]}}}
        row=next(x for x in snapshot(r,1000)['items'] if x['id']=='push')
        self.assertFalse(row['dataFresh'])
        self.assertIn('kein Nachweis',row['note'])
