"""Synthetic chronology, retry and protocol-migration regressions."""
import copy
import unittest

import research_learning as learning
import strategy_lab as lab
from test_research_learning import candles,report


class ResearchEvidenceFixTests(unittest.TestCase):
    def test_same_day_retry_is_not_new_evidence(self):
        first_rows=candles(900);later=candles(930)
        first=learning.enrich(report(first_rows),first_rows,day='2026-10-27')
        fresh=learning.enrich(report(later),later,first,day='2026-10-28')
        self.assertTrue(fresh['learningCycle']['newIndependentEvidence'])
        before=copy.deepcopy(fresh)
        retry=learning.enrich(report(later),later,fresh,day='2026-10-28')
        self.assertFalse(retry['learningCycle']['newIndependentEvidence'])
        self.assertEqual(retry['learningCycle']['prospective'],fresh['learningCycle']['prospective'])
        self.assertEqual(fresh,before)
        next_day=learning.enrich(report(later),later,retry,day='2026-10-29')
        self.assertFalse(next_day['learningCycle']['newIndependentEvidence'])

    def test_genuinely_later_same_day_window_is_new_without_extra_session(self):
        rows=candles(900)
        first=learning.enrich(report(rows),rows,day='2026-10-27')
        a=learning.enrich(report(candles(930)),candles(930),first,day='2026-10-28')
        b=learning.enrich(report(candles(960)),candles(960),a,day='2026-10-28')
        self.assertTrue(b['learningCycle']['newIndependentEvidence'])
        self.assertEqual(b['learningCycle']['prospective']['sessions'],a['learningCycle']['prospective']['sessions'])
        self.assertGreater(b['learningCycle']['prospective']['lastEvaluatedBarAt'],a['learningCycle']['prospective']['lastEvaluatedBarAt'])

    def test_blocked_protocol_cannot_reuse_same_day_observation_flag(self):
        rows=candles(900)
        first=learning.enrich(report(rows),rows,day='2026-10-27')
        later=candles(930)
        prior=learning.enrich(report(later),later,first,day='2026-10-28')
        prior['learningCycle']['proposal']['protocol']['engineVersion']='different-engine'
        blocked=learning.enrich(report(candles(960)),candles(960),prior,day='2026-10-28')
        self.assertEqual(blocked['learningCycle']['status'],'blocked')
        self.assertFalse(blocked['learningCycle']['newIndependentEvidence'])

    def test_old_research_protocol_is_archived_not_pooled_with_new(self):
        rows=candles(900)
        old=learning.enrich(report(rows),rows,day='2026-10-27')
        old['learningCycle']['version']='bob-rolling-shadow-v2'
        old['learningCycle']['prospective']['trades']=123
        before=copy.deepcopy(old)
        new=learning.enrich(report(rows),rows,old,day='2026-10-28')['learningCycle']
        self.assertEqual(new['previousProtocolArchive']['version'],'bob-rolling-shadow-v2')
        self.assertEqual(new['previousProtocolArchive']['prospective']['trades'],123)
        self.assertEqual(new['prospective']['trades'],0)
        self.assertEqual(new['version'],learning.VERSION);self.assertEqual(old,before)
        self.assertFalse(new['newIndependentEvidence'])
        for field in ('liveRuleChanged','automaticOrder','productNetValidated'):
            self.assertFalse(new[field])

    def test_latest_twelve_complete_windows_include_latest_possible_fold(self):
        rows=candles(1700);result=lab.run(rows)
        starts=list(range(lab.TRAIN_END,len(rows)-2*lab.HORIZON-lab.VALIDATION-lab.TEST+1,lab.TEST))
        expected=starts[-12:]
        self.assertEqual(len(result['folds']),12)
        self.assertEqual([f['trainEndMs'] for f in result['folds']],[rows[i-1]['openTime'] for i in expected])
        last_end=expected[-1]+2*lab.HORIZON+lab.VALIDATION+lab.TEST-1
        self.assertEqual(result['folds'][-1]['testEndMs'],rows[last_end]['openTime'])
        self.assertLess(len(rows)-last_end-1,lab.TEST)
        selection=result['foldSelection']
        self.assertEqual(selection['omittedEarlier'],len(starts)-12)
        self.assertEqual(selection['latestTestEndMs'],rows[last_end]['openTime'])
        self.assertFalse(result['evidence']['productNetValidated'])

    def test_short_histories_keep_all_complete_windows_and_future_cannot_rewrite_fold(self):
        rows=candles(700);result=lab.run(rows)
        self.assertEqual(result['foldSelection']['omittedEarlier'],0)
        self.assertLess(result['foldSelection']['selected'],12)
        rows=candles(1700);before=lab.run(rows)
        extended=lab.run(candles(1772))
        common={f['testStartMs']:f for f in before['folds']}
        overlap=[f for f in extended['folds'] if f['testStartMs'] in common]
        self.assertTrue(overlap)
        for fold in overlap:self.assertEqual(fold,common[fold['testStartMs']])
        self.assertGreater(extended['folds'][-1]['testEndMs'],before['folds'][-1]['testEndMs'])


if __name__=='__main__':unittest.main()
