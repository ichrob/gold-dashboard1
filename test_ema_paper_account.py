"""Independent EMA paper account, start capital, routing and fail-closed evidence."""
import copy
import json
import unittest
from unittest.mock import MagicMock, patch
import paper_portfolios as p
from test_paper_portfolios import market


class EmaAccountTests(unittest.TestCase):
    def trial(self):
        m=market()
        plan={**m['plan'],'source':'ema25-paper-v1','experimental':True}
        m.update(plan=None,entryTimingGate={'allowed':False},relaxedPaper={
            'version':'ema25-paper-v1','paperOnly':True,'plan':plan,
            'gate':{'allowed':True,'paperOnly':True,'maxDeviationAtr':2.5}})
        return m

    def test_seed_once_from_initialization_and_separate_capital(self):
        saved={}
        conn=MagicMock()
        def record(sql,args=()):
            if sql.startswith('INSERT INTO bob_paper_ema3000nov_control'):
                self.assertIn('ON CONFLICT DO NOTHING',sql)
                saved.update(json.loads(args[0]))
        conn.execute.side_effect=record
        with patch('paper_portfolios.time.time',return_value=1794427000):p.init(conn)
        self.assertEqual(saved['startAt'],1794427000000)
        for k in ('initialCapital','cash','equity'):self.assertEqual(saved[k],3000)
        self.assertTrue(saved['enabled'])
        self.assertEqual(saved['totalProfit'],0)
        self.assertEqual(p.POLICIES['ema3000nov']['max_holding_minutes'],300)
        self.assertEqual(p.POLICIES['ema3000nov']['daily_loss_fraction'],.03)

    def test_trial_only_replaces_new_account_input_and_keeps_product_selection(self):
        m=self.trial();before=copy.deepcopy(m);conn=MagicMock();selected={'choices':[]}
        with patch('paper_simulation.run_once') as run:
            p.run_all(conn,{},m,selected,{},1794427000000,{},active={})
        for call in run.call_args_list:
            profile=call.args[0].profile
            if profile=='ema3000nov':
                self.assertIsNotNone(call.args[2]['plan'])
                self.assertTrue(call.args[2]['entryTimingGate']['allowed'])
                self.assertIs(call.args[3],selected)
            elif profile=='normal1000nov':
                self.assertIsNone(call.args[2]['plan'])
                self.assertFalse(call.args[2]['entryTimingGate']['allowed'])
        self.assertEqual(m,before)

    def test_missing_blocked_or_mismatched_trial_never_inherits_main_plan(self):
        self.assertIsNone(p.relaxed_paper_market(market())['plan'])
        for edit in ('blocked','direction','price','marker'):
            m=self.trial()
            if edit=='blocked':m['relaxedPaper']['gate']['allowed']=False
            if edit=='direction':m['relaxedPaper']['plan']['direction']='SHORT'
            if edit=='price':m['relaxedPaper']['plan']['entry']+=1
            if edit=='marker':m['relaxedPaper']['paperOnly']=False
            self.assertIsNone(p.relaxed_paper_market(m)['plan'],edit)

    def test_active_trade_uses_original_monitoring(self):
        m=self.trial();monitor={'plan':{'kind':'active-monitor'}}
        with patch('background_push.analyze',return_value=monitor), patch('paper_simulation.run_once') as run:
            p.run_all(MagicMock(),{},m,{}, {},1794427000000,{},active={
                'ema3000nov':{'status':'open','engine':{'trade':{'active':True}}}})
        call=next(c for c in run.call_args_list if c.args[0].profile=='ema3000nov')
        self.assertIs(call.args[2],monitor)

    def test_diagram_includes_new_account(self):
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=({'initialCapital':3000},)
        conn.execute.return_value.fetchall.return_value=[]
        report=p.diagram_report(conn)
        row=next(a for a in report['accounts'] if a['profile']=='ema3000nov')
        self.assertEqual(row['control']['initialCapital'],3000)
