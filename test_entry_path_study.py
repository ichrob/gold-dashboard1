import unittest
from unittest.mock import Mock
from entry_path_study import evaluate,read,PROTOCOL,MAX_SAMPLES_PER_TRIAL

class PathTests(unittest.TestCase):
    def setUp(self):
        self.at=1800000000000
        self.base=self.row(0,4000)
    def row(self,minutes,price,**kw):
        return dict(dict(at=self.at+minutes*60000,priceAt=self.at+minutes*60000,price=price,valid=True,ready=True,direction='LONG',cohort='v1'),**kw)
    def test_fixed_filter_and_horizons_costs(self):
        rows=[self.row(-15,3980),self.row(-5,3990)]+[self.row(m,4010) for m in PROTOCOL['horizons']]
        r=evaluate(self.base,rows,self.at+3700000)
        self.assertFalse(r['candidateKeep']);self.assertEqual(len(r['horizons']),4)
        self.assertEqual(r['comparison'][0]['candidate'],0)
        self.assertAlmostEqual(r['comparison'][0]['baseline'],.21)
        self.assertGreater(r['earlierComparison'][0]['earlier'],r['earlierComparison'][0]['baseline'])
    def test_future_wrong_version_and_stale_do_not_fill_gaps(self):
        for bad in [self.row(60,4010,at=self.at+4000000),self.row(60,4010,cohort='other'),self.row(62,4010)]:
            r=evaluate(self.base,[bad],self.at+3900000)
            self.assertEqual(r['horizons'][-1]['status'],'missing')
            self.assertFalse(r['comparison'])
    def test_short_direction_extrema_and_gaps(self):
        base=dict(self.base,direction='SHORT')
        rows=[self.row(-15,4020),self.row(10,4040),self.row(60,3960)]
        r=evaluate(base,rows,self.at+3800000)
        self.assertFalse(r['candidateKeep']);self.assertAlmostEqual(r['observedAdversePct'],-1)
        self.assertAlmostEqual(r['observedFavorablePct'],1)
        self.assertLess(r['coveragePct'],5)
        self.assertEqual(r['horizons'][0]['status'],'missing')
    def test_neutral_early_false_alarm_and_no_hindsight_direction(self):
        base=dict(self.base,ready=False,direction='NEUTRAL')
        r=evaluate(base,[self.row(-5,4010),self.row(60,3990)],self.at+3800000)
        self.assertFalse(r['comparison']);self.assertIsNone(r['horizons'][-1]['directionalPct'])
        self.assertLess(r['earlierComparison'][0]['earlier'],0)
        self.assertEqual(r['earlierComparison'][0]['baseline'],0)
    def test_missing_prior_is_unknown_not_keep(self):
        r=evaluate(self.base,[self.row(60,4100)],self.at+3800000)
        self.assertIsNone(r['candidateKeep']);self.assertFalse(r['comparison'])
    def test_full_sample_coverage_and_duplicate_clock(self):
        rows=[self.row(i/2,4000) for i in range(1,121)]
        r=evaluate(self.base,rows+rows,self.at+3600000)
        self.assertEqual(r['coveragePct'],100)

    def test_read_uses_bounded_per_trial_primary_key_ranges(self):
        conn=Mock()
        conn.execute.side_effect=[
            Mock(fetchone=lambda:(PROTOCOL,)),
            Mock(fetchall=lambda:[]),
            Mock(fetchall=lambda:[]),
        ]
        self.assertEqual(read(conn,'campaign',self.at)['items'],[])
        sql,params=conn.execute.call_args_list[2].args
        self.assertIn('CROSS JOIN LATERAL',sql)
        self.assertIn('WITH trials AS MATERIALIZED',sql)
        self.assertEqual(params,('campaign','campaign',MAX_SAMPLES_PER_TRIAL+1))

    def test_over_cap_trial_is_unknown_not_partial_comparison(self):
        base=self.base
        rows=[(self.at, self.row(i/2,4000))
              for i in range(MAX_SAMPLES_PER_TRIAL+1)]
        conn=Mock()
        conn.execute.side_effect=[
            Mock(fetchone=lambda:(PROTOCOL,)),
            Mock(fetchall=lambda:[(self.at,'development',base)]),
            Mock(fetchall=lambda:rows),
        ]
        item=read(conn,'campaign',self.at+4_000_000)['items'][0]
        self.assertEqual(item['sampleCoverageStatus'],'over-cap')
        self.assertEqual(item['label'],'Stichprobenlimit überschritten; Ergebnis unbekannt')
        self.assertFalse(item['comparison'])
        self.assertTrue(all(h['status']=='unavailable' for h in item['horizons']))
