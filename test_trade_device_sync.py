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
class CloseTradePushTests(unittest.TestCase):
    def test_closed_trade_disables_its_push_without_disabling_market_or_future_opt_in(self):
        import real_trade_journal as journal
        class Cursor:
            def __init__(self,rows=()): self.rows=rows
            def fetchall(self):return self.rows
        class FakeConn:
            def __init__(self):self.operations=[]
            def execute(self,sql,args=()):
                self.operations.append((sql,args))
                if 'SELECT id,settings,state FROM bob_real_trades' in sql:
                    return Cursor([])
                if 'SELECT id FROM bob_real_trades WHERE active=FALSE' in sql:
                    return Cursor([('closed-123',)])
                if 'SELECT id,active_trade,background_config,trade_enabled FROM subscriptions' in sql:
                    return Cursor([])
                return Cursor([])
        c=FakeConn()
        journal.sync_devices(c)
        operations=[(sql,args) for sql,args in c.operations if sql.lstrip().startswith('UPDATE subscriptions')]
        self.assertEqual(len(operations),1)
        sql,params=operations[0]
        self.assertIn('active_trade=FALSE',sql)
        self.assertIn('trade_monitor=NULL',sql)
        self.assertIn("jsonb_set(background_config - 'journalTradeId'",sql)
        self.assertIn("background_state=COALESCE",sql)
        self.assertIn("background_config->'trade'->>'tradeId'=ANY",sql)
        self.assertNotIn('trade_enabled=',sql)
        self.assertNotIn('general_enabled=',sql)
        self.assertEqual(params,(['closed-123'],)*4)

    def test_browser_close_is_idempotent_and_does_not_affect_other_trade(self):
        old={'tradeId':'closed-123','active':True}
        cfg,on=device_plan({'trade':old,'journalTradeId':'closed-123'},True,{}, {'closed-123'})
        self.assertFalse(on)
        self.assertIsNone(cfg['trade'])
        self.assertNotIn('journalTradeId',cfg)
        self.assertIsNone(device_plan({'trade':{'tradeId':'new-456'},
             'journalTradeId':'closed-123'},True,{}, {'closed-123'}))

if __name__=='__main__':unittest.main()
