import copy
import unittest
import bob_test_overview as overview


class RiskPaperOverviewTests(unittest.TestCase):
    def report(self, status='observed'):
        return {'areas':{'riskPaper':{
            'status':status,'checkedAt':1000,'startedAt':900,
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

    def test_retired_risk_variants_keep_their_stored_counts_without_running_claim(self):
        report=self.report(status='retired')
        report['areas']['riskPaper']['retiredAt']=1000
        rows={row['id']:row for row in overview.snapshot(report,200000)['items']
              if row['id'].startswith('risk-paper-')}
        self.assertTrue(all(row['state']=='retired' for row in rows.values()))
        self.assertEqual([rows['risk-paper-'+str(d)]['sampledRecords'] for d in (0,30,60)],
                         [2,0,1])
        self.assertTrue(all(row['completed'] is False for row in rows.values()))

    def test_new_full_journal_studies_are_in_test_overview(self):
        source=self.report()
        source['areas']['simulationAndPush']={
            'paper':{'sessionMode':'trading'},
            'shadowStudies':{'status':'observed',
                             'studies':[{'study':'regime-routing','startedAt':800,
                                         'checkedAt':1000,'eventCount':4,'eventsRecorded':9,
                                         'casesPriced':2},
                                        {'study':'wait-vs-enter','startedAt':800,
                                         'checkedAt':1000,'eventsRecorded':9,
                                         'casesPriced':0},
                                        {'study':'product-e2e','startedAt':800,
                                         'checkedAt':1000,'eventsRecorded':9,
                                         'casesPriced':1}]}}
        before=copy.deepcopy(source)
        rows={r['id']:r for r in overview.snapshot(source,1001)['items']
              if r['id'].startswith('shadow-')}
        self.assertEqual(set(rows),{'shadow-regime-routing','shadow-wait-vs-enter',
                                    'shadow-product-e2e'})
        self.assertEqual(rows['shadow-regime-routing']['state'],'checked')
        self.assertEqual(rows['shadow-product-e2e']['comparableCases'],1)
        self.assertEqual(rows['shadow-regime-routing']['sampledRecords'],9)
        self.assertTrue(all(not r['completed'] and not r['truncated']
                            for r in rows.values()))
        self.assertEqual(source,before)
        for study in source['areas']['simulationAndPush']['shadowStudies']['studies']:
            study['status']='retired'
        rows={r['id']:r for r in overview.snapshot(source,200000)['items']
              if r['id'].startswith('shadow-')}
        self.assertTrue(all(r['state']=='retired' for r in rows.values()))
        self.assertEqual(rows['shadow-regime-routing']['sampledRecords'],9)
        self.assertEqual(rows['shadow-product-e2e']['comparableCases'],1)
        self.assertTrue(all(r['completed'] is False for r in rows.values()))

        source['areas']['simulationAndPush']['shadowStudies']['studies'][0]['status']='running'
        source['areas']['simulationAndPush']['shadowStudies']['studies'][1]['status']='running'
        source['areas']['simulationAndPush']['shadowStudies']['studies'][2]['status']='running'
        source['areas']['simulationAndPush']['paper']['sessionMode']='night'
        rows={r['id']:r for r in overview.snapshot(source,200000)['items']
              if r['id'].startswith('shadow-')}
        self.assertTrue(all(r['state']=='night-paused' for r in rows.values()))

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
