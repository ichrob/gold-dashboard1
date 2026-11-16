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

    def test_old_gap_uses_retained_original_spot_evidence_even_after_seven_days(self):
        # Only the diagnostic journal expires after seven days. The original
        # spot archive is immutable by source time and does not share that TTL.
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(at-20000,)
        data=archive.report(conn,[_account(at)],
                            now_ms=at+archive.RETENTION_MS+10)
        self.assertEqual(data['counts']['outsideRetention'],0)
        self.assertEqual(data['counts']['nearbyOriginal'],1)
        self.assertEqual(data['items'][0]['timeRelation'],'before-or-at-event')
        self.assertEqual(data['items'][0]['deltaSeconds'],20)
        self.assertEqual(conn.execute.call_count,1)
        self.assertFalse(data['realOrders'])

    def test_future_gap_cannot_query_original_or_manufacture_prior_input(self):
        at=1000000
        conn=Mock()
        data=archive.report(conn,[_account(at)],now_ms=at-1000)
        self.assertEqual(data['counts']['futureEvent'],1)
        self.assertEqual(data['counts']['nearbyOriginal'],0)
        self.assertEqual(data['items'][0]['state'],'future-event-unavailable')
        self.assertIsNone(data['items'][0]['nearestSourceAt'])
        conn.execute.assert_not_called()

    def test_old_gap_without_stored_original_is_unknown_not_proof_of_outage(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=None
        data=archive.report(conn,[_account(at)],
                            now_ms=at+archive.RETENTION_MS*4)
        self.assertEqual(data['counts']['notObservedNearEvent'],1)
        self.assertEqual(data['counts']['outsideRetention'],0)
        self.assertEqual(data['items'][0]['state'],
                         'no-original-observed-in-90s-window')
        self.assertIn('does not prove',data['note'])
        self.assertEqual(conn.execute.call_count,1)

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

    def test_eleventh_paper_profile_is_included_in_gap_read_and_report(self):
        at=1000000
        accounts=[{'profile':'control-'+str(i),
                   'recentCases':{'status':'observed','items':[]}}
                  for i in range(10)]
        last=_account(at)
        last['profile']='noema5000nov'
        accounts.append(last)
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(at-10000,)
        check=archive.report(conn,accounts,now_ms=at+100000)
        self.assertEqual(check['totalDistinctClocks'],1)
        self.assertEqual(check['counts']['nearbyOriginal'],1)
        report=bob_diagnostics.simulation_evidence_snapshot(
            {'status':'observed','accounts':accounts,'spotGapArchive':check})
        self.assertEqual(len(report['accountSamples']),11)
        self.assertEqual(report['accountSamples'][-1]['profile'],'noema5000nov')
        self.assertEqual(report['gapCorrelation']['distinctRecordedGapInstants'],1)
        self.assertFalse(report['gapReview']['realOrders'])

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
