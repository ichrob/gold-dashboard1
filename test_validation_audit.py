import base64
import json
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
import validation_audit as audit
import bob_validation_store as store
import test_auth as baseline

NOW = datetime(2026, 10, 2, 16, tzinfo=timezone.utc)


class AuditTests(unittest.TestCase):
    def test_pairing_reasons_preserve_frozen_values_and_receipts(self):
        def prediction(offset, received, truth=None):
            return dict(quoteAt=(NOW+timedelta(seconds=offset)).isoformat(),price=4200,
                        receivedAt=(NOW+timedelta(seconds=received)).isoformat(),truthAt=truth)
        truth = dict(quoteAt=NOW.isoformat(),price=4199,
                     receivedAt=(NOW+timedelta(minutes=10)).isoformat())
        rows=[prediction(0,1,truth['quoteAt']),prediction(6,1),
              prediction(0,601),prediction(5,1)]
        original=[dict(r) for r in rows]
        result=audit.classify(rows,[truth])
        self.assertEqual([r['pairingState'] for r in result],['paired',
                         'no_truth_within_5_seconds','truth_received_before_prediction',
                         'candidate_not_paired_check_one_use_rule'])
        self.assertEqual(rows,original)
        self.assertTrue(all(r['price']==4200 for r in result))

    def test_export_is_read_only_bounded_and_marks_missing_provenance(self):
        class Query:
            def __init__(self, rows): self.rows=rows
            def fetchone(self): return self.rows[0]
            def fetchall(self): return self.rows
        class Conn:
            def execute(self,sql,args=None):
                self_check.assertTrue(sql.startswith('SELECT'))
                if sql=='SELECT now()':return Query([(NOW,)])
                self_check.assertEqual(args,(audit.LIMIT+1,))
                if 'bob_future_predictions' in sql:
                    return Query([('301–900s',NOW,4200,NOW-timedelta(minutes=10),NOW,None)]*(audit.LIMIT+1))
                return Query([])
        self_check=self
        result=audit.read_archive(Conn())
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['predictions']),audit.LIMIT)
        self.assertFalse(result['isLiveApproval'])
        self.assertEqual(len(result['limitations']),3)


class ExportAuthTests(baseline.AuthenticationTests):
    def test_export_requires_auth_before_archive_access(self):
        with patch.object(store,'request') as read:
            status,_,_,_=self.request('GET','/api/collection-export')
            self.assertEqual(status,401)
            read.assert_not_called()

    def test_authenticated_export_and_old_store_failure(self):
        basic='Basic '+base64.b64encode(b'test-user:test-only-password').decode()
        for saved,status in (({'audit':{'predictions':[]}},200),({'pairs':[]},503)):
            with patch.object(store,'request',return_value=saved) as read:
                code,h,body,_=self.request('GET','/api/collection-export',headers={'Authorization':basic})
                self.assertEqual(code,status)
                self.assertEqual(h['Cache-Control'],'no-store')
                read.assert_called_once_with('read',{'includeAudit':True})
                if status==200:
                    self.assertIn('attachment',h['Content-Disposition'])
                    self.assertEqual(json.loads(body),saved)


if __name__=='__main__':unittest.main()
