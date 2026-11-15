"""Intraday 30–300-minute decision gates: forward-only, no broker orders."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
import intraday_timing_study as study
import paper_portfolios
import paper_simulation


class IntradayFasterModes(unittest.TestCase):
    def test_neutral_hour_is_explicit_study_only(self):
        signal={'available':True,'direction':'LONG','ema':'LONG','macd':'LONG'}
        neutral={'available':True,'direction':'NEUTRAL'}
        opposed={'available':True,'direction':'SHORT'}
        self.assertFalse(study.gate(signal,neutral,study.VARIANTS['base5'])[0])
        self.assertTrue(study.gate(signal,neutral,study.VARIANTS['fast3neutral'])[0])
        self.assertTrue(study.gate(signal,neutral,study.VARIANTS['follow5neutral'])[0])
        self.assertFalse(study.gate(signal,opposed,study.VARIANTS['fast3neutral'])[0])
        self.assertFalse(study.gate(signal,{'available':False},study.VARIANTS['fast3neutral'])[0])

    def test_score_thresholds_compare_without_replacing_main_score(self):
        long={'direction':'LONG'}
        short={'direction':'SHORT'}
        self.assertEqual(study.score_gate(long,{'score':68},study.VARIANTS['score65']),(True,None))
        self.assertEqual(study.score_gate(long,{'score':68},study.VARIANTS['score70'])[1],'collective-score-too-weak')
        self.assertEqual(study.score_gate(short,{'score':32},study.VARIANTS['score65']),(True,None))
        self.assertEqual(study.score_gate(short,{'score':32},study.VARIANTS['score70'])[1],'collective-score-too-weak')
        self.assertFalse(study.score_gate(long,{'score':None},study.VARIANTS['score65'])[0])
        self.assertTrue(study.score_gate(long,{'score':0},study.VARIANTS['base5'])[0])

    def test_frozen_target_room_compare_15_to_20_r(self):
        base=study.VARIANTS['base5']
        strict=study.VARIANTS['rr20']
        self.assertTrue(study.target_room(4035,4000,20,'LONG',base))
        self.assertFalse(study.target_room(4035,4000,20,'LONG',strict))
        self.assertTrue(study.target_room(3965,4000,20,'SHORT',base))
        self.assertFalse(study.target_room(3965,4000,20,'SHORT',strict))
        self.assertFalse(study.target_room(4050,4000,0,'LONG',base))

    def test_new_november_maximum_is_300_min_legacy_stays_240(self):
        for name in ('trend800nov','normal1000nov'):
            self.assertEqual(paper_portfolios.POLICIES[name]['max_holding_minutes'],300)
        self.assertNotIn('max_holding_minutes',paper_portfolios.POLICIES['trend800'])
        now=int(datetime(2026,11,10,10,0,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        market={'plan':{'direction':'LONG','entry':4000.,'stop':3990.,'target':4020.,'unit':'USD/oz'},
                'price':4000.,'dataAt':now,'analysisBarAt':now,'direction':'LONG'}
        product={'isin':'TEST','indicative':True}
        legacy=paper_simulation.new_case(market,product,None,now)
        current=paper_simulation.new_case(market,product,None,now,max_holding_minutes=300)
        self.assertEqual(legacy['endsAt'],now+240*60000)
        self.assertEqual(current['endsAt'],now+300*60000)
        late=int(datetime(2026,11,10,20,0,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        capped=paper_simulation.new_case(market,product,None,late,max_holding_minutes=300)
        cutoff=int(datetime(2026,11,10,21,45,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        self.assertEqual(capped['endsAt'],cutoff)
        with self.assertRaises(ValueError):
            paper_simulation.new_case(market,product,None,now,max_holding_minutes=360)

    def test_protective_stop_is_forward_only_symmetric_and_never_loosened(self):
        for side in ('LONG','SHORT'):
            sign = 1 if side=='LONG' else -1
            p = {'direction':side,'entryPrice':4000.,'risk':10.,
                 'atr':5.,'stop':4000.-sign*10.}
            base = study.VARIANTS['base5']
            be = study.VARIANTS['breakeven5']
            atr = study.VARIANTS['trailatr5']
            self.assertIsNone(study.prospective_protective_stop(
                p,4000.+sign*9.,be))
            self.assertIsNone(study.prospective_protective_stop(
                p,4000.+sign*20.,base))
            self.assertEqual(study.prospective_protective_stop(
                p,4000.+sign*10.,be),4000.)
            self.assertEqual(study.prospective_protective_stop(
                p,4000.+sign*16.,atr),4000.+sign*11.)
            locked={**p,'stop':4000.+sign*12.}
            self.assertIsNone(study.prospective_protective_stop(
                locked,4000.+sign*15.,atr))
            self.assertIsNone(study.prospective_protective_stop(
                {**p,'atr':None},4000.+sign*16.,atr))
            self.assertIsNone(study.prospective_protective_stop(
                p,float('nan'),be))


if __name__=='__main__':
    unittest.main()
