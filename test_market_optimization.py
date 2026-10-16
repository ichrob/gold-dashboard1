import copy
import unittest
from datetime import datetime, timezone
import decision_audit as audit
import market_optimization as review


class Tests(unittest.TestCase):
    def row(self, direction='LONG', change=.05, **extra):
        at=datetime(2026,10,16,10,tzinfo=timezone.utc).timestamp()*1000
        payload=dict(origin='background',ruleVersion=audit.RULE_VERSION,direction=direction,
            barAt=at-300000,price=100,priceAt=at,reason='Bestätigung fehlt',
            shadowDirection='NEUTRAL',trendContext=dict(available=True,phase='CONTINUATION',
                intact=True,direction=direction),
            earlyImpulse=dict(version='early-impulse-v1',available=True,direction=direction,
                barAt=at-300000,comparisonOnly=True,affectsApproval=False),
            entryQuality=dict(version='entry-quality-v1',available=True,direction='NEUTRAL',
                priceAt=at,atr5m=.02,deviationAtr=2,roomR=1,signalAgeMinutes=20,
                reasons=['Abstand zur EMA20 über 1,5 ATR']),**extra)
        r=audit.normalize(payload,at)[1]
        r['_marketReviewTruths']={h:dict(price=100+change,at=at+h*60000) for h in review.HORIZONS}
        return r,(r['_marketReviewTruths'][15],None,None)

    def test_all_horizons_and_filtered_pair_same_cases(self):
        row=self.row();before=copy.deepcopy(row)
        result=review.report([row],audit.outcome,now=row[0]['recordedAt']+2000000)
        self.assertEqual(row,before)
        self.assertEqual({g['horizon'] for g in result['groups']},{1,5,15,30})
        for g in result['groups']:
            self.assertEqual(g['cases'],1)
            self.assertEqual(g['variants']['timing']['wait'],1)
            self.assertAlmostEqual(g['variants']['baseline']['sumPct'],.01)
        self.assertFalse(result['automaticRuleChange'])

    def test_atr_catches_small_move_and_short_is_symmetric(self):
        for direction,change in [('LONG',.05),('SHORT',-.05)]:
            row=self.row(direction,change);r=row[0]
            r['marketOptimization']['variants']['baseline']='NEUTRAL'
            result=review.report([row],audit.outcome)
            self.assertEqual(result['moveCount'],4)
            for move in result['moves']:
                self.assertTrue(move['atrThreshold']);self.assertFalse(move['fixedThreshold'])
                self.assertAlmostEqual(move['moveAtr'],2.5)
                self.assertEqual(move['direction'],direction)

    def test_missing_atr_not_zero_and_invalid_short_horizon_excluded(self):
        row=self.row();r=row[0]
        r['marketOptimization']['atr5m']=None
        r['_marketReviewTruths'][1]['at']+=30001
        result=review.report([row],audit.outcome,now=r['recordedAt']+2000000)
        self.assertEqual(result['atrMissing'],1)
        self.assertEqual(result['missing'],1)
        self.assertEqual(len(result['groups']),3)

    def test_sample_precedes_outcome_and_old_rows_not_backfilled(self):
        a=self.row();b=copy.deepcopy(a);b[0]['recordedAt']+=300000
        a[0]['_marketReviewTruths']={};a=(a[0],(None,None,None))
        result=review.report([a,b],audit.outcome,now=a[0]['recordedAt']+2000000)
        self.assertEqual(result['sampled'],1);self.assertFalse(result['groups'])
        b[0].pop('marketOptimization')
        self.assertEqual(review.report([b],audit.outcome)['sampled'],0)

    def test_stale_input_or_unknown_variant_excludes_common_cohort(self):
        for field in ('input','variant'):
            row=self.row()
            if field=='input':row[0]['marketOptimization']['inputFresh']=False
            else:row[0]['marketOptimization']['variants']['regime']=None
            self.assertFalse(review.report([row],audit.outcome)['groups'])

    def test_endpoint_reversal_and_validation_separation(self):
        row=self.row();r=row[0]
        r['marketOptimization']['variants']['baseline']='NEUTRAL'
        r['_marketReviewTruths'][30]['price']=99.9
        result=review.report([row],audit.outcome)
        self.assertTrue(all(m['endpointReversal'] for m in result['moves']))
        self.assertEqual(result['groups'][0]['phase'],'collection')

    def test_capture_rejects_future_entry_clock(self):
        row=self.row();r=row[0]
        r['entryQuality']['priceAt']=r['recordedAt']+1
        frozen=review.capture(r)
        self.assertIsNone(frozen['atr5m']);self.assertIsNone(frozen['variants']['timing'])

    def test_database_iso_timestamps_supported(self):
        row=self.row();r=row[0]
        for truth in r['_marketReviewTruths'].values():
            truth['at']=datetime.fromtimestamp(truth['at']/1000,timezone.utc).isoformat()
        self.assertEqual(len(review.report([row],audit.outcome)['groups']),4)


if __name__=='__main__':unittest.main()
