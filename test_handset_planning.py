import copy
import json
import os
import unittest
import uuid
from unittest.mock import patch
import handset_planning as p

CONFIG=dict(budgetCHF=1000,riskCHF=100,feesCHF=8,trailAtr=1.5,minRR=2)


class Planning(unittest.TestCase):
    def test_config_rejects_missing_boolean_nonfinite_and_impossible_budgets(self):
        self.assertEqual(p.validate(CONFIG),CONFIG)
        for key in CONFIG:
            for value in (None, True, float('nan'), float('inf'), -1, '100'):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    p.validate(dict(CONFIG,**{key:value}))
        for extra in (dict(riskCHF=1001),dict(feesCHF=100),dict(unknown=1)):
            with self.assertRaises(ValueError):p.validate(dict(CONFIG,**extra))
        self.assertEqual(p.validate(dict(CONFIG,feesCHF=0))['feesCHF'],0)

    def test_tick_reuses_sources_and_records_missing_configuration(self):
        state=dict(config=None,revision=3,result=None)
        report=dict(listUploadedAt='generation',items=[dict(isin='DE000FG14AV8',
            state='incomplete',handsetObservation=dict(observedAt='capture'))])
        class Db:
            def execute(self,sql,args):self.sql=sql;self.args=args
        db=Db()
        from types import SimpleNamespace
        with patch.object(p,'read',return_value=state),patch('degiro_product_audit.read',return_value=report),\
             patch('evaluator_runtime.run',return_value=SimpleNamespace(stdout=json.dumps(dict(calculatedAt=1000,items=[])))) as run:
            p.tick(db,dict(listUploadedAt='generation',products=[]),{},dict(handsetPlans={},handsetPlanRevision=3),dict(spots={}),1000)
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['config'],None)
        self.assertEqual(db.args[1],3)
        self.assertIn('revision=%s',db.sql)

    def test_postgres_settings_survive_reads_and_reject_lost_updates(self):
        url=os.environ.get('BOB_TEST_DATABASE_URL')
        if not url:self.skipTest('test database not configured')
        import psycopg
        with psycopg.connect(url) as conn:
            schema='planning_'+uuid.uuid4().hex
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET LOCAL search_path TO '+schema)
            p.init(conn)
            self.assertIsNone(p.read(conn)['config'])
            saved=p.handle(conn,dict(action='plan-save',expectedRevision=0,config=CONFIG))
            self.assertEqual(saved['revision'],1)
            self.assertEqual(p.read(conn)['config'],CONFIG)
            with self.assertRaises(ValueError):p.handle(conn,dict(action='plan-save',expectedRevision=0,config=CONFIG))
            self.assertEqual(p.read(conn)['config'],CONFIG)
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_new_config_cannot_be_used_with_old_model_parameters(self):
        with patch.object(p,'read',return_value=dict(config=CONFIG,revision=2,result=None)),\
             patch('evaluator_runtime.run') as run:
            p.tick(None,{}, {},dict(handsetPlanRevision=1),{},1000)
        run.assert_not_called()

    def test_shared_analysis_exposes_both_model_plans_without_changing_signal(self):
        import subprocess
        from test_paper_end_to_end import SCRIPT, NOW
        from test_paper_entry_pipeline import EntryPipelineTests
        q,_=EntryPipelineTests().fixture()
        payload=json.dumps(dict(now=NOW,quote=q,price=4072))
        baseline=json.loads(subprocess.run(['node','-e',SCRIPT],input=payload,text=True,
            capture_output=True,check=True,timeout=30).stdout)['market']
        script=SCRIPT.replace("evaluate({bundle,timeframe:",
            "evaluate({bundle,handsetPlanRevision:4,handsetPlanSettings:{trailAtr:1.8,minRR:2.5},timeframe:")
        model=json.loads(subprocess.run(['node','-e',script],input=payload,text=True,
            capture_output=True,check=True,timeout=30).stdout)['market']
        self.assertEqual(model['handsetPlanRevision'],4)
        self.assertEqual(set(model['handsetPlans']),{'LONG','SHORT'})
        self.assertTrue(all(x.get('available') for x in model['handsetPlans'].values()))
        for key in ('direction','ready','plan','entryPlanState','price','suggestedStop'):
            self.assertEqual(baseline.get(key),model.get(key),key)


if __name__=='__main__':unittest.main()
