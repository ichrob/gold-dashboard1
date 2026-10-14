import unittest
from real_trade_journal import device_plan

class DevicePlanTest(unittest.TestCase):
    def setUp(self):
        self.plan={'tradeId':'real-1','active':True,'dir':'SHORT','stop':4200}
        self.j={'real-1':({'trade':self.plan},{'trade':{**self.plan,'stop':4180}})}
    def test_idle_device_inherits_real_trade_and_tighter_stop(self):
        cfg,on=device_plan({'timeframe':'5m','trade':None},False,self.j)
        self.assertTrue(on);self.assertEqual(cfg['trade']['stop'],4180)
        self.assertEqual(cfg['timeframe'],'5m');self.assertEqual(cfg['journalTradeId'],'real-1')
    def test_other_active_trade_not_overwritten(self):
        self.assertIsNone(device_plan({'trade':{'tradeId':'other'}},True,self.j))
    def test_multiple_active_trades_not_guessed(self):
        self.assertIsNone(device_plan({},False,{**self.j,'other':self.j['real-1']}))
    def test_closed_link_detaches(self):
        cfg,on=device_plan({'trade':self.plan,'journalTradeId':'real-1'},True,{})
        self.assertFalse(on);self.assertIsNone(cfg['trade'])
    def test_closed_unlinked_trade_also_detaches(self):
        cfg,on=device_plan({'trade':self.plan},True,{}, {'real-1'})
        self.assertFalse(on);self.assertIsNone(cfg['trade'])
    def test_closed_trade_does_not_replace_a_new_position(self):
        self.assertIsNone(device_plan({'trade':{'tradeId':'other'}},True,{}, {'real-1'}))
    def test_device_selected_other_trade_untouched(self):
        self.assertIsNone(device_plan({'trade':{'tradeId':'other'},'journalTradeId':'real-1'},True,self.j))
    def test_central_stop_never_loosened(self):
        self.j['real-1'][1]['trade']['stop']=4300
        cfg,_=device_plan({},False,self.j);self.assertEqual(cfg['trade']['stop'],4200)
    def test_no_journal_no_activation(self):
        self.assertIsNone(device_plan({},False,{}))
if __name__=='__main__':unittest.main()
