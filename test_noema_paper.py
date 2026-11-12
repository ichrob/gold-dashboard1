import contextlib
import json
import unittest
from unittest.mock import patch
import paper_portfolios as p

class NoEmaTests(unittest.TestCase):
    def test_seed_and_isolation(self):
        seeds={}
        class Conn:
            def execute(self, sql, args=()):
                if sql.startswith('INSERT INTO bob_paper_noema5000nov_control'):
                    seeds.update(json.loads(args[0]))
        with patch('paper_portfolios.time.time', return_value=1794430000):
            p.init(Conn())
        self.assertEqual(seeds['startAt'],1794430000000)
        self.assertEqual(seeds['cash'],5000)
        self.assertTrue(seeds['enabled'])
        self.assertNotEqual(p.names('noema5000nov'),p.names('normal1000nov'))
        for key in ('score_long','score_short','exposure_fraction','daily_loss_fraction','max_holding_minutes'):
            self.assertEqual(p.POLICIES['noema5000nov'][key],p.POLICIES['normal1000nov'][key])

    def test_variant_routes_only_to_new_account_and_missing_variant_blocks(self):
        class Conn:
            def transaction(self): return contextlib.nullcontext()
        market={'plan':None,'entryTimingGate':{'allowed':False},
                'paperNoEmaEntry':{'plan':{'test':'independent'},'entryTimingGate':{'allowed':True}}}
        seen={}
        def run(conn,bundle,m,*args,profile_policy=None): seen[conn.profile]=m
        with patch('paper_simulation.run_once',side_effect=run):
            p.run_all(Conn(),{},market,{'choices':[]},{},1794430000000,{},active={})
        self.assertIsNone(seen['normal1000nov']['plan'])
        self.assertEqual(seen['noema5000nov']['plan'],{'test':'independent'})
        self.assertIsNone(market['plan'])
        with patch('paper_simulation.run_once',side_effect=run):
            p.run_all(Conn(),{}, {'plan':{'must':'not reuse'}},{},{},1794430000000,{},active={})
        self.assertIsNone(seen['noema5000nov']['plan'])
