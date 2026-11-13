import copy
import unittest
from unittest.mock import patch

import android_observations as observations
from handset_import_assessment import assess
from test_android_observations import MemoryDb, run, NOW, ISIN


class ImportAssessment(unittest.TestCase):
    def prepared(self):
        return observations.prepare(run(), {'products': [{'isin': ISIN}]}, NOW)

    def test_native_chf_cost_and_no_fabricated_plan(self):
        r=self.prepared()
        r['results'][0]['observation']['fields'].update(Währung='CHF', Geld='43,07', Brief='43,09')
        before=copy.deepcopy(r)
        x=assess(r)['items'][0]
        self.assertEqual(x['unitPurchaseCHF'], 43.09)
        self.assertEqual(x['spread'], .02)
        for field in ('quantity', 'modelStop', 'totalCHF', 'lossCHF', 'riskUsagePct', 'sourceTime'):
            self.assertIsNone(x[field])
        self.assertFalse(x['rankingPenalty'])
        self.assertFalse(x['tradeApproved'])
        self.assertEqual(r, before)

    def test_missing_leverage_does_not_block_valid_pair_or_penalize(self):
        x=assess(self.prepared())['items'][0]
        self.assertEqual(x['ask'], 13.07)
        self.assertIsNone(x['displayedLeverage'])
        self.assertIsNone(x['unitPurchaseCHF'])
        self.assertIn('DATED_EUR_CHF_REFERENCE_MISSING', x['reasons'])
        self.assertNotIn('LEVERAGE_MISSING', x['reasons'])

    def test_each_requested_isin_gets_pending_or_failed_result(self):
        r=self.prepared()
        r['isins'].append('DE000FG0SGZ2')
        r['results'][0].update(code='READ_TIMEOUT', observation=None)
        x=assess(r)['items']
        self.assertEqual(len(x), 2)
        self.assertIn('READ_NOT_AVAILABLE', x[0]['reasons'])
        self.assertIn('READ_PENDING', x[1]['reasons'])

    def test_invalid_pair_and_restricted_display_stay_explicit(self):
        for bad in ('0', '-1', 'NaN', 'Infinity', 'bad', True):
            r=self.prepared()
            r['results'][0]['observation']['fields']['Brief']=bad
            x=assess(r)['items'][0]
            self.assertIsNone(x['ask'])
            self.assertIn('DISPLAY_PAIR_INVALID_OR_MISSING', x['reasons'])
        r=self.prepared()
        r['results'][0]['observation']['fields']['Hinweis']='Kurse verzögert'
        self.assertIn('DISPLAY_RESTRICTED_OR_UNCONFIRMED', assess(r)['items'][0]['reasons'])

    def test_save_is_atomic_with_run_and_retry_retains_same_assessment(self):
        db=MemoryDb()
        with patch.object(observations, 'prepare', return_value=self.prepared()):
            reply=observations.handle(db, dict(action='save', run=run()))
        stored=copy.deepcopy(db.rows)
        self.assertTrue(reply['saved'])
        self.assertIn('importAssessment', next(iter(db.rows.values())))
        self.assertTrue(observations.handle(db, dict(action='save', run=run()))['duplicate'])
        self.assertEqual(db.rows, stored)

    def test_old_runs_are_projected_read_only_and_marked_unpersisted(self):
        r=self.prepared()
        class Db:
            def execute(self, sql):
                self.sql=sql
                return self
            def fetchall(self):
                return [(r,)]
        db=Db()
        x=observations.status(db)['runs'][0]
        self.assertFalse(x['importAssessmentPersisted'])
        self.assertEqual(x['importAssessment']['items'][0]['ask'], 13.07)
        self.assertNotIn('importAssessment', r)
        self.assertTrue(db.sql.startswith('SELECT'))


if __name__ == '__main__':
    unittest.main()
