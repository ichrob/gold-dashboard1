import copy
import unittest
import bob_test_overview as overview


class RiskPaperOverviewTests(unittest.TestCase):
    def report(self, status='observed'):
        return {'areas':{'riskPaper':{
            'status':status,'checkedAt':1000000,'startedAt':900000,
            'accounts':[
                {'status':'observed','delaySeconds':0,'closed':2,
                 'reviewReady':True,'position':{'private':'hidden'}},
                {'status':'observed','delaySeconds':30,'closed':0,
                 'pending':{'private':'hidden'}},
                {'status':'observed','delaySeconds':60,'closed':1,
                 'recent':[{'private':'hidden'}]},
            ]}}}

    def test_all_three_risk_variants_are_inventory_rows_without_success_claim(self):
        report=self.report();before=copy.deepcopy(report)
        result=overview.snapshot(report,1001)
        rows={row['id']:row for row in result['items'] if row['id'].startswith('risk-paper-')}
        self.assertEqual(set(rows),{'risk-paper-0','risk-paper-30','risk-paper-60'})
        self.assertEqual([rows['risk-paper-'+str(d)]['sampledRecords'] for d in (0,30,60)],
                         [2,0,1])
        self.assertTrue(all(row['state']=='checked' for row in rows.values()))
        self.assertTrue(all(row['completed'] is False for row in rows.values()))
        self.assertTrue(all(row['truncated'] is True for row in rows.values()))
        self.assertNotIn('hidden',str(result))
        self.assertEqual(report,before)

    def test_missing_variant_stays_visible_and_unavailable(self):
        report=self.report(status='partial')
        del report['areas']['riskPaper']['accounts'][1]
        rows={row['id']:row for row in overview.snapshot(report,1001)['items']
              if row['id'].startswith('risk-paper-')}
        self.assertEqual(rows['risk-paper-0']['state'],'checked')
        self.assertEqual(rows['risk-paper-30']['state'],'unavailable')
        self.assertIsNone(rows['risk-paper-30']['sampledRecords'])
        self.assertEqual(rows['risk-paper-60']['state'],'checked')

    def test_stale_or_unverified_report_never_looks_running(self):
        for status in ('stale','unavailable'):
            with self.subTest(status=status):
                rows=[row for row in overview.snapshot(self.report(status),1001)['items']
                      if row['id'].startswith('risk-paper-')]
                self.assertEqual(len(rows),3)
                self.assertTrue(all(row['state']=='unavailable' for row in rows))
                self.assertTrue(all(row['sampledRecords'] is None for row in rows))


if __name__=='__main__': unittest.main()
