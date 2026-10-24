import copy
from datetime import datetime, timezone, timedelta
import json
import os
import unittest
from unittest.mock import patch
import snaptrade_bridge as b
import snaptrade_portfolio as p
from test_snaptrade_bridge import fixtures, CONFIG, A


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.state = copy.deepcopy(b._STATE)
        self.ledger = copy.deepcopy(b._LEDGER)
        self.owner = b._LEDGER_OWNER
        self.generation = b._GENERATION
        b._LEDGER.clear(); b._LEDGER_OWNER = None

    def tearDown(self):
        b._STATE.clear(); b._STATE.update(self.state)
        b._LEDGER.clear(); b._LEDGER.update(self.ledger)
        b._LEDGER_OWNER = self.owner; b._GENERATION = self.generation

    def position(self, **kwargs):
        row = {'instrument': {'id':'test-id', 'symbol':'TEST', 'kind':'stock'},
               'units':'3', 'currency':'CHF', 'price':'8', 'cost_basis':'10', **kwargs}
        return b.normalize_positions({'results':[row]})['positions'][0]

    def test_long_short_zero_and_missing_cost_do_not_invent_profit(self):
        long = self.position()
        self.assertEqual(long['marketValue'], '24')
        self.assertEqual(long['unrealizedPnl'], '-6')
        self.assertEqual(long['unrealizedPercent'], '-20.0')
        short = self.position(units='-3')
        self.assertEqual(short['unrealizedPnl'], '6')
        self.assertEqual(short['unrealizedPercent'], '20.0')
        self.assertIsNone(self.position(cost_basis=None)['unrealizedPnl'])
        self.assertIsNone(self.position(cost_basis='0')['unrealizedPercent'])
        self.assertIsNone(self.position(units='NaN')['marketValue'])
        self.assertIsNone(self.position(price='1e999999')['marketValue'])

    def test_unknown_contract_multiplier_blocks_arithmetic_not_price(self):
        for kind in ('option','future','future_option','cfd','bond','other'):
            row=self.position(instrument={'id':'x', 'symbol':'TEST', 'kind':kind})
            self.assertEqual(row['valuationPrice'],'8')
            self.assertIsNone(row['marketValue']); self.assertIsNone(row['unrealizedPnl'])
            self.assertFalse(row['tradeApproved'])

    def test_exact_isin_only_no_description_name_match(self):
        row=self.position(instrument={'id':'x','symbol':'DE000FG309G0','kind':'other'})
        self.assertEqual(row['isin'],'DE000FG309G0')
        self.assertFalse(row['identityVerified']); self.assertFalse(row['tradeApproved'])
        self.assertIsNone(self.position(instrument={'id':'x','kind':'other','symbol':'DE000FG309G1','description':'DE000FG309G0'})['isin'])
        self.assertIsNone(self.position(instrument={'id':'x','kind':'other','symbol':'FG309G','description':'DE000FG309G0'})['isin'])

    def test_account_value_not_summed_across_currencies_or_cash_equivalents(self):
        data=fixtures()
        data['/connections/'+data['/authorizations'][0]['id']+'/accounts']['results'][0]['net_value']={'amount':'100.12','currency':'CHF'}
        row=data['/accounts/'+A+'/positions/all']['results'][0]; row['cash_equivalent']=True
        snap=b.read_snapshot(CONFIG,lambda path,_:data[path])
        a=snap['accounts'][0]
        self.assertEqual(a['netValue'],{'amount':'100.12','currency':'CHF'})
        self.assertTrue(a['positions'][0]['cashEquivalent'])
        self.assertNotIn('profit',a)

    def snapshot(self, units='3', seconds=0):
        return {'observedAt':(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat(),
                'completeConnections':True,'accounts':[{'accountKey':'account','netValue':{'amount':'100','currency':'CHF'},
                 'positionsSourceAt':(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat(),
                 'cash':[], 'positions':[{'positionKey':'position','units':units,'name':'Test'}]}]}

    def test_quantity_changes_are_observations_not_trade_fills(self):
        history=[]; first=self.snapshot()
        self.assertEqual(p.record(history,first),[])
        self.assertEqual(p.record(history,first),[])
        self.assertEqual(len(history),1)
        changes=p.record(history,self.snapshot('2',seconds=1))
        self.assertEqual(changes[0]['before'],'3'); self.assertEqual(changes[0]['after'],'2')
        self.assertNotIn('side',changes[0]); self.assertNotIn('profit',history[-1])
        partial=self.snapshot('0',seconds=2); partial['completeConnections']=False
        self.assertEqual(p.record(history,partial),[])
        self.assertEqual(p.record(history,self.snapshot('0',seconds=3)),[])

    def test_journal_pagination_dedup_daily_cadence_and_partial(self):
        calls=[]
        activity={'id':'id', 'type':'CONTRIBUTION','amount':100,'currency':{'code':'CHF'},'trade_date':'2026-10-20'}
        def get(path,config,params=None):
            calls.append((path,params))
            if path.endswith('/orders'): return [{'brokerage_order_id':'o','status':'CANCELED','filled_quantity':'0','stop_price':'12'}]
            offset=params['offset']
            return {'data':[dict(activity,id=str(offset+i)) for i in range(500)] if offset==0 else [dict(activity,id='last')],
                    'pagination':{'total':501}}
        result=b.read_journal(A,CONFIG,get=get)
        self.assertEqual(len(result['activities']['rows']),501)
        self.assertTrue(result['activities']['complete'])
        self.assertEqual(result['orders']['rows'][0]['status'],'CANCELED')
        self.assertEqual(result['orders']['rows'][0]['stop'],'12')
        self.assertNotIn('tradeApproved',result['orders']['rows'][0])
        calls.clear(); b.read_journal(A,CONFIG,result,get=get)
        self.assertEqual(len(calls),1); self.assertTrue(calls[0][0].endswith('/orders'))
        failure=b.read_journal(A,CONFIG,result,get=lambda *args: (_ for _ in ()).throw(b.ReadError('ACCESS_DENIED')))
        self.assertEqual(failure['orders']['code'],'UNAVAILABLE')
        self.assertEqual(failure['orders']['rows'],result['orders']['rows'])
        self.assertEqual(failure['orders']['failureCode'], 'ACCESS_DENIED')
        self.assertEqual(failure['orders']['checkedAt'], result['orders']['checkedAt'])
        self.assertIsNotNone(failure['orders']['failureAt'])
        partial=b.read_journal(A,CONFIG,get=lambda path,c,params=None: [] if path.endswith('/orders') else {'data':[dict(activity,id=str(i)) for i in range(500)],'pagination':{'total':9999}})
        self.assertFalse(partial['activities']['complete'])

    def test_journal_failure_codes_are_safe_and_clear_on_success(self):
        # Even an unexpected private error must never surface its raw content.
        def secret_failure(*args, **kwargs):
            raise b.ReadError('PRIVATE_PROVIDER_MESSAGE_DO_NOT_ECHO')
        failed = b.read_journal(A, CONFIG, get=secret_failure)
        for category in ('orders', 'activities'):
            self.assertEqual(failed[category]['code'], 'UNAVAILABLE')
            self.assertEqual(failed[category]['failureCode'], 'PROVIDER_UNAVAILABLE')
            self.assertNotIn('PRIVATE_PROVIDER_MESSAGE_DO_NOT_ECHO', json.dumps(failed))

        def good_read(path, config, params=None):
            if path.endswith('/orders'):
                return []
            return {'data': [], 'pagination': {'total': 0}}

        with patch.object(b.trades, 'SCHEMA', b.trades.SCHEMA + 1):
            recovered = b.read_journal(A, CONFIG, failed, get=good_read)
        for category in ('orders', 'activities'):
            self.assertEqual(recovered[category]['code'], 'READ_OK')
            self.assertNotIn('failureCode', recovered[category])
            self.assertNotIn('failureAt', recovered[category])

    def test_conflicting_order_ids_do_not_cancel_the_entire_journal(self):
        # SnapTrade may return different statuses/fill amounts under one
        # brokerage_order_id. Do not choose a final order state by guesswork.
        shared = {'brokerage_order_id':'same-provider-id','status':'PARTIAL',
                  'filled_quantity':'1','execution_price':'10','action':'BUY'}
        changed = dict(shared, status='EXECUTED', filled_quantity='2')
        independent = {'brokerage_order_id':'different-id','status':'EXECUTED',
                       'filled_quantity':'3','execution_price':'12','action':'SELL'}
        def get(path, config, params=None):
            if path.endswith('/orders'):
                return [shared, changed, independent, dict(independent)]
            return {'data': [], 'pagination': {'total': 0}}
        result = b.read_journal(A, CONFIG, get=get)
        orders = result['orders']
        self.assertEqual(orders['code'], 'READ_OK')
        self.assertFalse(orders['complete'])
        self.assertEqual(orders['conflictingOrderIdentifiers'], 1)
        self.assertEqual(len(orders['rows']), 1)
        self.assertEqual(orders['rows'][0]['key'], p.identity('different-id'))
        self.assertEqual(result['activities']['code'], 'READ_OK')

    def test_history_encrypted_reload_delete_and_owner_separation(self):
        db={}
        def store(action,payload=None):
            if action=='state-save':db.update(payload);return {'saved':True}
            if action=='delete':db.clear();return {'deleted':True}
            return dict(db)
        with patch.dict(os.environ,PUSH_SERVICE_TOKEN='test-local-only'),patch.object(b,'storage',side_effect=store):
            b._LEDGER.update(owner=p.identity(CONFIG['clientId']),history=[{'secretPosition':'private-name'}],changes=[],journal={})
            b.save_ledger()
            self.assertNotIn('private-name',db['sealed'])
            b._LEDGER.clear(); b._LEDGER_OWNER=None
            loaded=b.load_ledger(CONFIG)
            self.assertEqual(loaded['history'][0]['secretPosition'],'private-name')
            self.assertEqual(b.load_ledger({**CONFIG,'clientId':'another-client'})['history'],[])
            b.disconnect();self.assertEqual(db,{})
            self.assertEqual(b._LEDGER,{})

    def test_daily_history_passes_old_two_thousand_limit_and_keeps_size_bound(self):
        calls=[]
        def get(path,config,params=None):
            if path.endswith('/orders'):return []
            offset=params['offset'];calls.append(offset)
            return {'data':[{'id':str(i),'type':'CONTRIBUTION','trade_date':'2026-10-01','amount':1,'currency':{'code':'EUR'}} for i in range(offset,min(offset+500,2101))],
                    'pagination':{'total':2101}}
        result=b.read_journal(A,CONFIG,get=get)
        self.assertTrue(result['activities']['complete'])
        self.assertEqual(len(result['activities']['rows']),2101)
        self.assertEqual(calls,[0,500,1000,1500,2000])
        limited=b.read_journal(A,CONFIG,get=get,max_bytes=300000)
        self.assertFalse(limited['activities']['complete'])
        self.assertLess(len(json.dumps(limited).encode()),310000)

    def test_disconnect_during_journal_does_not_resurrect_history(self):
        snap=b.read_snapshot(CONFIG,lambda path,_:fixtures()[path])
        def interrupted(*args):
            b._GENERATION+=1;b._LEDGER.clear();return {}
        with patch.object(b,'load_ledger',return_value={'owner':'x','history':[],'changes':[],'journal':{}}),patch.object(b,'read_journal',side_effect=interrupted),patch.object(b,'save_ledger') as save:
            b.update_portfolio(snap,CONFIG,self.generation)
        save.assert_not_called();self.assertEqual(b._LEDGER,{})

    def test_issuer_quotes_exact_identity_currency_age_and_not_calculated(self):
        row=self.position(instrument={'id':'x','symbol':'DE000FG309G0','kind':'other'})
        b._STATE.update(code='READ_OK',snapshot={'accounts':[{'positions':[row]}]})
        at=datetime.now(timezone.utc).isoformat()
        quote={'isin':row['isin'],'currency':'CHF','productVerified':True,'found':True,'fresh':True,
               'bid':'7','ask':'8','bidAt':at,'askAt':at,'source':'Test issuer'}
        b.quote_tick(lambda _:quote)
        self.assertEqual(b._STATE['snapshot']['accounts'][0]['positions'][0]['issuerQuote']['bid'],'7')
        for mutation in ({'isin':'WRONG'}, {'currency':'EUR'}, {'priceKind':'calculated-turbo'}, {'sourceFailure':True},
                         {'bidAt':(datetime.now(timezone.utc)-timedelta(seconds=91)).isoformat()}, {'ask':'6'}):
            b.quote_tick(lambda _:{**quote,**mutation})
            self.assertIsNone(b._STATE['snapshot']['accounts'][0]['positions'][0]['issuerQuote'])
        self.assertFalse(row['tradeApproved'])

    def test_new_read_paths_reject_unbounded_queries_and_never_allow_refresh(self):
        self.assertTrue(b.permitted('/accounts/'+A+'/orders'))
        self.assertTrue(b.permitted('/accounts/'+A+'/activities'))
        self.assertFalse(b.permitted('/accounts/'+A+'/orders/place'))
        with self.assertRaises(b.ReadError): b.api_get('/accounts/'+A+'/activities',CONFIG,{'limit':100000})
        with self.assertRaises(b.ReadError): b.api_get('/accounts/'+A+'/orders',CONFIG,{'limit':500,'offset':0})


if __name__=='__main__':unittest.main()
