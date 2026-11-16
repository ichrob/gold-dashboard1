import copy
import unittest
from unittest.mock import patch

import android_observations as observations
from handset_import_assessment import assess
from test_android_observations import MemoryDb, run, NOW, ISIN


class ImportAssessment(unittest.TestCase):
    def test_saved_budget_is_not_misreported_as_missing_or_used_as_historical_input(self):
        from contextlib import nullcontext
        r=self.prepared()
        r['importAssessment']=dict(version=2, items=[dict(reasons=['CHF_CAPITAL_MISSING'])])
        original=copy.deepcopy(r)
        planning=dict(config=dict(budgetCHF=100, riskCHF=30), revision=3,
                      resultFresh=False, realOrders=False)
        class Db:
            def execute(self, sql):
                assert sql.startswith('SELECT')
                return self
            def fetchall(self):return [(r,)]
            def transaction(self):return nullcontext()
        with patch('handset_planning.read', return_value=planning):
            result=observations.status(Db())
        assessment=result['runs'][0]['importAssessment']
        item=assessment['items'][0]
        self.assertEqual(result['planning']['config']['budgetCHF'],100)
        self.assertEqual(result['planning']['config']['riskCHF'],30)
        self.assertFalse(assessment['planningSettingsChecked'])
        self.assertNotIn('CHF_CAPITAL_MISSING',item['reasons'])
        self.assertNotIn('CHF_RISK_BUDGET_MISSING',item['reasons'])
        self.assertIn('CHF_CAPITAL_NOT_IN_IMPORT',item['reasons'])
        self.assertIn('SOURCE_CLOCK_UNCONFIRMED',item['reasons'])
        self.assertIsNone(item['quantity'])
        self.assertIsNone(item['sourceTime'])
        self.assertFalse(item['tradeApproved'])
        self.assertFalse(result['runs'][0]['importAssessmentPersisted'])
        self.assertEqual(r,original)

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

    def test_one_sided_and_crossed_display_values_remain_visible_without_a_valid_pair(self):
        for missing,remaining,expected in [('Brief','displayedBid',13.06),
                                           ('Geld','displayedAsk',13.07)]:
            r=self.prepared()
            r['results'][0]['observation']['fields'].pop(missing)
            original=copy.deepcopy(r)
            x=assess(r)['items'][0]
            self.assertEqual(x[remaining],expected)
            self.assertIsNone(x['displayedAsk' if missing=='Brief' else 'displayedBid'])
            self.assertFalse(x['displayPairValid'])
            for key in ('bid','ask','spread','unitPurchaseCHF','quantity','sourceTime'):
                self.assertIsNone(x[key])
            self.assertIn('DISPLAY_PAIR_INVALID_OR_MISSING',x['reasons'])
            self.assertFalse(x['tradeApproved'])
            self.assertEqual(r,original)
        r=self.prepared()
        r['results'][0]['observation']['fields'].update(Geld='14',Brief='13')
        x=assess(r)['items'][0]
        self.assertEqual((x['displayedBid'],x['displayedAsk']),(14,13))
        self.assertFalse(x['displayPairValid'])
        self.assertIsNone(x['spread'])

    def test_legacy_assessment_is_reprojected_without_rewriting_originals_or_clocks(self):
        r=self.prepared()
        r['results'][0]['observation']['fields'].pop('Brief')
        r['importAssessment']=dict(version=1,items=[dict(bid=None,ask=None)])
        original=copy.deepcopy(r)
        class Db:
            def execute(self,sql):
                self.sql=sql
                return self
            def fetchall(self):return [(r,)]
        db=Db()
        out=observations.status(db)['runs'][0]
        self.assertEqual(out['importAssessment']['version'],3)
        self.assertFalse(out['importAssessmentPersisted'])
        item=out['importAssessment']['items'][0]
        self.assertEqual(item['displayedBid'],13.06)
        self.assertIsNone(item['displayedAsk'])
        self.assertEqual(item['observedAt'],r['results'][0]['observation']['observedAt'])
        self.assertEqual(out['importAssessment']['assessedAt'],r['receivedAt'])
        self.assertEqual(r,original)
        self.assertTrue(db.sql.startswith('SELECT'))

    def test_missing_leverage_does_not_block_valid_pair_or_penalize(self):
        x=assess(self.prepared())['items'][0]
        self.assertEqual(x['ask'], 13.07)
        self.assertIsNone(x['displayedLeverage'])
        self.assertIsNone(x['unitPurchaseCHF'])
        self.assertIn('DATED_EUR_CHF_REFERENCE_NOT_IN_IMPORT', x['reasons'])
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
