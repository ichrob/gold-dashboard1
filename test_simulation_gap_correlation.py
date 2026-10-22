"""Regression tests for shared paper clock diagnosis without fake executions."""
import json
import unittest
import bob_diagnostics as diag


class RecordedPaperGapTests(unittest.TestCase):
    def test_shared_clock_not_six_independent_outages(self):
        def case(at,reason):
            return {'status':'inconclusive','events':[
                {'kind':'data-gap','recordedAt':at,'reason':reason},
                {'kind':'deferred-sale','recordedAt':at+1000,'reason':'virtual'}]}
        no_market='Aktuelle Goldkursabdeckung fehlt; kein belegter Ausstieg'
        long_gap='Goldkurslücke über 90 Sekunden; Reihenfolge unbekannt'
        result=diag.simulation_evidence_snapshot({
            'status':'observed','accounts':[
                {'profile':'conservative','status':'running',
                 'recentCases':{'status':'observed','items':[case(1000,no_market),case(2000,no_market)]}},
                {'profile':'balanced','status':'running',
                 'recentCases':{'status':'observed','items':[case(1000,no_market)]}},
                {'profile':'trend800','status':'running',
                 'recentCases':{'status':'observed','items':[case(3000,long_gap)]}}]})
        gap=result['gapCorrelation']
        self.assertEqual(gap['sampledInconclusiveCases'],4)
        self.assertEqual(gap['gapEventReasonCounts']['missing-current-market'],3)
        self.assertEqual(gap['gapEventReasonCounts']['bar-gap-over-90s'],1)
        self.assertEqual(gap['distinctRecordedGapInstants'],3)
        self.assertEqual(gap['repeatedGapInstants'],1)
        self.assertEqual([x['affectedVirtualCases'] for x in gap['recentRecordedGapInstants']],[2,1,1])
        self.assertEqual([x['recordedAt'] for x in gap['recentRecordedGapInstants']],[1000,2000,3000])
        self.assertNotIn('Goldkurslücke',json.dumps(result,ensure_ascii=False))
        self.assertFalse(result['realOrders'])
        self.assertFalse(result['accountSamples'][0]['netProductReturnsVerified'])

    def test_unknown_reasons_and_bad_times_never_invent_evidence(self):
        r=diag.simulation_evidence_snapshot({
            'status':'observed','accounts':[{'profile':'early100',
                'recentCases':{'status':'observed','items':[
                   {'status':'inconclusive','events':[
                        {'kind':'data-gap','recordedAt':float('nan'),'reason':'UNTRUSTED TOKEN'},
                        {'kind':'data-gap','recordedAt':None,'reason':'other'}]},
                   {'status':'closed','events':[
                        {'kind':'data-gap','recordedAt':12345,'reason':'irrelevant'}]}]}}]})
        g=r['gapCorrelation']
        self.assertEqual(g['distinctRecordedGapInstants'],0)
        self.assertEqual(g['gapEventsWithoutRecordedAt'],2)
        self.assertEqual(g['gapEventReasonCounts']['unclassified'],2)
        self.assertEqual(g['sampledInconclusiveCases'],1)
        self.assertNotIn('UNTRUSTED TOKEN',json.dumps(r))

    def test_no_history_is_not_success(self):
        r=diag.simulation_evidence_snapshot({'status':'observed','accounts':[
            {'profile':'conservative','recentCases':{'status':'unavailable'}}]})
        self.assertEqual(r['accountSamples'][0]['sampleStatus'],'unavailable')
        self.assertEqual(r['gapCorrelation']['sampledInconclusiveCases'],0)
        self.assertEqual(r['gapCorrelation']['distinctRecordedGapInstants'],0)
        self.assertEqual(diag.simulation_evidence_snapshot(None)['status'],'unavailable')


if __name__=='__main__':
    unittest.main()
