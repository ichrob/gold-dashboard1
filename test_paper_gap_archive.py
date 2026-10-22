"""Read-only archive correlation: observed clock proximity, never a simulated fill."""
import json
import unittest
from decimal import Decimal
from unittest.mock import Mock
import paper_gap_archive as archive
import bob_diagnostics


class _Tx:
    def __enter__(self):return self
    def __exit__(self,*args):return False


def _account(at, extra=None):
    return {'profile':'conservative','recentCases':{'status':'observed','items':[
        {'status':'inconclusive','events':[
            {'kind':'data-gap','recordedAt':at,'reason':'not used'},
            {'kind':'deferred-sale','recordedAt':at+1000}]}]}}


class PaperArchiveEvidenceTests(unittest.TestCase):
    def test_one_exact_clock_across_profiles_is_one_query(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(at+30000,)
        accounts=[_account(at),{**_account(at),'profile':'balanced'}]
        data=archive.report(conn,accounts,now_ms=at+100000)
        self.assertEqual(data['sampledDistinctClocks'],1)
        self.assertEqual(data['counts']['nearbyOriginal'],1)
        self.assertEqual(data['items'][0]['timeRelation'],'after-event')
        self.assertEqual(data['items'][0]['deltaSeconds'],30)
        self.assertFalse(data['realOrders'])
        self.assertEqual(conn.execute.call_count,1)
        sql=conn.execute.call_args.args[0].upper()
        self.assertTrue(sql.strip().startswith('SELECT'))
        self.assertNotIn('INSERT',sql)
        self.assertNotIn('UPDATE ',sql)
        self.assertNotIn('DELETE ',sql)
        self.assertNotIn('not used',json.dumps(data))

    def test_postgres_decimal_epoch_is_recognized(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(Decimal('998000.000'),)
        result=archive.report(conn,[_account(at)],now_ms=at+100000)
        self.assertEqual(result['counts']['nearbyOriginal'],1)
        self.assertEqual(result['items'][0]['timeRelation'],'before-or-at-event')
        self.assertEqual(result['items'][0]['deltaSeconds'],2)

    def test_no_nearby_original_is_only_absent_from_this_archive(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=None
        data=archive.report(conn,[_account(at)],now_ms=at+100000)
        self.assertEqual(data['counts']['notObservedNearEvent'],1)
        self.assertEqual(data['items'][0]['state'],'no-original-observed-in-90s-window')
        self.assertIn('other market feeds',data['note'])

    def test_old_record_outside_retention_never_queried(self):
        conn=Mock()
        data=archive.report(conn,[_account(1000000)],now_ms=1000000+archive.RETENTION_MS+10)
        self.assertEqual(data['counts']['outsideRetention'],1)
        conn.execute.assert_not_called()

    def test_db_query_failure_explicitly_unknown(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.side_effect=RuntimeError('NO TABLE or transient lock')
        data=archive.report(conn,[_account(at)],now_ms=at+100000)
        self.assertEqual(data['status'],'partial')
        self.assertEqual(data['counts']['queryUnavailable'],1)
        self.assertNotIn('NO TABLE',json.dumps(data))

    def test_only_bounded_latest_clocks(self):
        account={'profile':'balanced','recentCases':{'status':'observed','items':[
            {'status':'inconclusive','events':[{'kind':'data-gap','recordedAt':at}
                for at in range(1,60)]}]}}
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=None
        data=archive.report(conn,[account],now_ms=100000)
        self.assertLessEqual(data['sampledDistinctClocks'],archive.MAX_EVENTS)
        self.assertEqual(conn.execute.call_count,data['sampledDistinctClocks'])
        self.assertTrue(data['totalDistinctClocks']<=40)

    def test_projection_inside_simulation_report_preserves_only_allowlist(self):
        sample={'status':'observed','accounts':[_account(1000000)],
            'spotGapArchive':{'status':'observed','readOnly':True,
                'source':'Gold-API-original-spot-archive','secret':'no',
                'counts':{'nearbyOriginal':1,'secret':'no'},
                'items':[{'eventAt':1000000,'state':'nearby-original-observed',
                    'nearestSourceAt':1000001,'timeRelation':'after-event',
                    'secret':'no'}]}}
        d=bob_diagnostics.simulation_evidence_snapshot(sample)
        self.assertEqual(d['spotGapArchive']['counts']['nearbyOriginal'],1)
        self.assertNotIn('secret',json.dumps(d))
        self.assertNotIn('no"',json.dumps(d))


if __name__=='__main__':
    unittest.main()
