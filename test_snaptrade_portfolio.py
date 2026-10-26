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

    def test_activity_coverage_partial_and_conflicting_ids(self):
        # Historical provider pages may exceed the bounded daily read budget.
        # Different entries under one provider ID never count as proven trades.
        base = {'type':'BUY', 'trade_date':'2026-10-24',
                'currency':{'code':'CHF'}, 'units':1, 'price':9, 'fee':0}
        def get(path, config, params=None):
            if path.endswith('/orders'):
                return []
            offset = params['offset']
            batch = [dict(base, id='test-'+str(offset+i)) for i in range(500)]
            if offset == 0:
                batch[1] = dict(base, id='test-0', units=2)
            return {'data':batch, 'pagination':{'total':12599}}
        with patch.object(b, 'ACTIVITY_OFFSETS', (0, 500)):
            result = b.read_journal(A, CONFIG, get=get)
        activity = result['activities']
        self.assertEqual(activity['code'], 'READ_OK')
        self.assertFalse(activity['complete'])
        self.assertEqual(activity['activityCoverageReason'], 'PAGE_LIMIT')
        self.assertEqual(activity['activitySourceTotal'], 12599)
        self.assertEqual(activity['conflictingActivityIdentifiers'], 1)
        self.assertEqual(len(activity['rows']), 998)
        self.assertEqual(result['orders']['code'], 'READ_OK')
        # Partial history cannot produce realized FIFO profit.
        journal = b.trades.build(result)
        self.assertFalse(journal['historyComplete'])
        self.assertEqual(journal['realized'], [])

    def test_short_inconsistent_activity_page_is_not_complete(self):
        def get(path, config, params=None):
            if path.endswith('/orders'):
                return []
            return {'data':[{'id':'single', 'type':'BUY', 'trade_date':'2026-10-24'}],
                    'pagination':{'total':100}}
        result = b.read_journal(A, CONFIG, get=get)
        self.assertFalse(result['activities']['complete'])
        self.assertEqual(result['activities']['activityCoverageReason'], 'SHORT_PAGE')
        self.assertEqual(result['activities']['activitySourceTotal'], 100)

    def test_personal_activity_rate_budget_caps_burst_and_reports_partial_history(self):
        # Holdings/positions, balances and orders already consume three of
        # SnapTrade Personal's ten allowed account requests per minute.
        calls = []
        def get(path, config, params=None):
            calls.append((path, params))
            if path.endswith('/orders'):
                return []
            return {'data': [
                {'id': 'activity-'+str(params['offset']+i), 'type':'BUY',
                 'trade_date':'2026-10-24','currency':{'code':'CHF'}}
                for i in range(500)], 'pagination': {'total': 12599}}
        got = b.read_journal(A, CONFIG, get=get)
        activities = got['activities']
        self.assertEqual(len(b.ACTIVITY_OFFSETS), 5)
        self.assertEqual(activities['code'], 'READ_OK')
        self.assertEqual(activities['activityPagesReceived'], 5)
        self.assertEqual(activities['activityCoverageReason'], 'PAGE_LIMIT')
        self.assertEqual(activities['activitySourceTotal'], 12599)
        self.assertEqual(len(activities['rows']), 2500)
        self.assertFalse(activities['complete'])
        self.assertEqual(len(calls), 6)  # one order call + five activities
        self.assertFalse(b.trades.build(got)['historyComplete'])

    def test_provider_429_keeps_previous_journal_and_counts_successful_pages(self):
        activity = {'id':'prior','type':'BUY','trade_date':'2026-10-20',
                    'currency':{'code':'CHF'},'units':1}
        old = b.read_journal(A, CONFIG, get=lambda path,c,params=None:
            [] if path.endswith('/orders') else {'data':[activity], 'pagination':{'total':1}})
        self.assertEqual(old['activities']['code'], 'READ_OK')
        def throttled(path, config, params=None):
            if path.endswith('/orders'):
                return []
            if params['offset'] >= 1000:
                raise b.ReadError('RATE_LIMITED', 60)
            return {'data':[
                {'id':'new-'+str(params['offset']+i),'type':'BUY','trade_date':'2026-10-24',
                 'currency':{'code':'CHF'}} for i in range(500)],
                'pagination':{'total':12599}}
        # The existing 24-hour journal cooldown stays intact; a new parser
        # revision permits one bounded recheck, never a retry loop.
        with patch.object(b.trades,'SCHEMA',b.trades.SCHEMA+1):
            got = b.read_journal(A, CONFIG, old, get=throttled)
            self.assertEqual(got['activities']['code'],'UNAVAILABLE')
            self.assertEqual(got['activities']['failureCode'],'RATE_LIMITED')
            self.assertEqual(got['activities']['activityPagesReceived'],2)
            self.assertEqual(got['activities']['rows'],old['activities']['rows'])
            self.assertEqual(got['activities']['checkedAt'],old['activities']['checkedAt'])
            self.assertFalse(b.trades.build(got)['sourceAvailable'])
            calls=[]
            b.read_journal(A, CONFIG, got, get=lambda *args:(calls.append(args),[])[1])
            self.assertEqual(len(calls),1)  # only orders, no immediate activity retry

    def test_filtered_trade_coverage_complete_but_not_fifo(self):
        # Large real account histories include cash sweeps. The provider's
        # BUY,SELL filter should fit the smaller, separate observation budget.
        calls = []
        def get(path, config, params=None):
            calls.append(params)
            self.assertEqual(params['type'], 'BUY,SELL')
            self.assertEqual(params['limit'], 1000)
            offset = params['offset']
            rows = [
                {'id':'trade-'+str(i), 'type':'BUY' if i%2==0 else 'SELL',
                 'trade_date':'2026-10-24' if i<2000 else '2026-06-03',
                 'symbol':{'raw_symbol':'DE000FG309G0','symbol':'ABC','currency':{'code':'CHF'}},
                 'currency':{'code':'CHF'}, 'units':1, 'price':5, 'fee':0}
                for i in range(offset,min(offset+1000,2704))]
            return {'data':rows, 'pagination':{'total':2704}}
        got = b.read_trade_coverage(A,CONFIG,known_isins={'DE000FG309G0'},get=get)
        self.assertEqual(got['code'],'READ_OK')
        self.assertEqual(got['filter'],'BUY,SELL')
        self.assertEqual(got['totalMatching'],2704)
        self.assertEqual(got['observed'],2704)
        self.assertEqual(got['buyCount'],1352)
        self.assertEqual(got['sellCount'],1352)
        self.assertEqual(got['validIsinCount'],2704)
        self.assertEqual(got['currentHoldingsIsinMatches'],2704)
        self.assertEqual(got['missingOrInvalidIsinCount'],0)
        self.assertEqual(got['holdingBreakdown'],[{
            'isin':'DE000FG309G0', 'buys':1352,'sells':1352,
            'firstDay':'2026-06-03','lastDay':'2026-10-24'
        }])
        self.assertFalse(got['holdingBreakdownTruncated'])
        self.assertEqual(got['earliestTradeDay'],'2026-06-03')
        self.assertEqual(got['latestTradeDay'],'2026-10-24')
        self.assertTrue(got['completeFilteredTradeWindow'])
        self.assertFalse(got['accountHistoryComplete'])
        self.assertFalse(got['fifoEligible'])
        self.assertEqual([q['offset'] for q in calls],[0,1000,2000])
        calls.clear()
        self.assertEqual(b.read_trade_coverage(A,CONFIG,got,get=get),got)
        self.assertEqual(calls,[])  # weekly cooldown, no paid extra refresh

    def test_filtered_matches_only_checksum_confirmed_current_holding_isins(self):
        # Unrecognized provider names/symbols must never be matched by
        # apparent resemblance; only checksum-valid stored ISIN identity.
        items=[
            {'id':'a','type':'BUY','trade_date':'2026-10-01',
             'symbol':{'raw_symbol':'DE000FG309G0'}},
            {'id':'b','type':'SELL','trade_date':'2026-10-03',
             'symbol':{'raw_symbol':'DE000FG309G0'}},
            {'id':'c','type':'BUY','trade_date':'2026-10-02',
             'symbol':{'raw_symbol':'DE000FG309G1'}},
            {'id':'d','type':'SELL','trade_date':'2026-10-04',
             'symbol':{'symbol':'FG309G', 'description':'DE000FG309G0'}},
        ]
        result=b.read_trade_coverage(A, CONFIG, known_isins={
            'DE000FG309G0','DE000FG309G1','DE000FG14AV8'}, get=lambda path, cfg, params=None:{
            'data':items,'pagination':{'total':4}})
        self.assertTrue(result['completeFilteredTradeWindow'])
        self.assertEqual(result['observed'],4)
        self.assertEqual(result['validIsinCount'],2)
        self.assertEqual(result['missingOrInvalidIsinCount'],2)
        self.assertEqual(result['currentHoldingsIsinMatches'],2)
        by_isin={x['isin']:x for x in result['holdingBreakdown']}
        self.assertEqual(by_isin['DE000FG309G0']['buys'],1)
        self.assertEqual(by_isin['DE000FG309G0']['sells'],1)
        self.assertEqual(by_isin['DE000FG309G0']['firstDay'],'2026-10-01')
        self.assertEqual(by_isin['DE000FG309G0']['lastDay'],'2026-10-03')
        self.assertEqual(by_isin['DE000FG14AV8']['buys'],0)
        self.assertNotIn('DE000FG309G1',by_isin)
        self.assertFalse(result['fifoEligible'])
        self.assertFalse(result['accountHistoryComplete'])
        # Snapshot has bounded ISIN counts, never the provider's raw IDs.
        self.assertNotIn("'id': 'a'", repr(result))
        self.assertNotIn('trade_date', repr(result))

    def test_filtered_trade_partial_and_provider_errors_fail_closed(self):
        def large(path,config,params=None):
            offset=params['offset']
            return {'data':[{'id':str(offset+i),'type':'BUY','trade_date':'2026-10-20'}
                            for i in range(1000)],'pagination':{'total':4200}}
        partial=b.read_trade_coverage(A,CONFIG,get=large)
        self.assertEqual(partial['code'],'READ_OK')
        self.assertFalse(partial['completeFilteredTradeWindow'])
        self.assertEqual(partial['coverageReason'],'PAGE_LIMIT')
        self.assertEqual(partial['observed'],3000)
        self.assertFalse(partial['fifoEligible'])
        with patch.object(b,'TRADE_COVERAGE_SCHEMA',b.TRADE_COVERAGE_SCHEMA+1):
            def error(path,config,params=None):
                if params['offset']==1000:
                    raise b.ReadError('RATE_LIMITED',3600)
                return {'data':[{'id':str(i),'type':'BUY','trade_date':'2026-10-20'}
                                for i in range(1000)],'pagination':{'total':2704}}
            failed=b.read_trade_coverage(A,CONFIG,partial,get=error)
        self.assertEqual(failed['code'],'UNAVAILABLE')
        self.assertEqual(failed['failureCode'],'RATE_LIMITED')
        self.assertEqual(failed['pagesReceivedInFailedAttempt'],1)
        self.assertEqual(failed['checkedAt'],partial['checkedAt'])
        self.assertEqual(failed['observed'],partial['observed'])
        self.assertFalse(failed['fifoEligible'])
        # If filtering is ignored, the response must not count as BUY/SELL.
        bad=b.read_trade_coverage(A,CONFIG,get=lambda p,c,params=None: {
            'data':[{'id':'not-a-trade','type':'CASH_TRANSACTION'}],
            'pagination':{'total':1}})
        self.assertEqual(bad['code'],'UNAVAILABLE')
        self.assertEqual(bad['failureCode'],'INVALID_RESPONSE')
        self.assertNotIn('rows',bad)

    def test_only_fixed_filtered_trade_request_is_allowed(self):
        reqs=[]
        from unittest.mock import Mock
        ok=Mock()
        ok.read.return_value=b'{"data":[],"pagination":{"total":0}}'
        ok.__enter__=Mock(return_value=ok)
        ok.__exit__=Mock(return_value=False)
        opener=Mock()
        opener.open.return_value=ok
        with patch.object(b,'build_opener',return_value=opener):
            got=b.api_get('/accounts/'+A+'/activities',CONFIG,
                          {'offset':1000,'limit':1000,'type':'BUY,SELL'})
            self.assertIn('data',got)
            for params in (
                {'offset':3000,'limit':1000,'type':'BUY,SELL'},
                {'offset':0,'limit':1000,'type':'SELL'},
                {'offset':0,'limit':500,'type':'BUY,SELL'},
                {'offset':0,'limit':1000,'type':'BUY,SELL','refresh':True},
            ):
                with self.assertRaises(b.ReadError):
                    b.api_get('/accounts/'+A+'/activities',CONFIG,params)
            self.assertEqual(opener.open.call_count,1)

    def test_filtered_scan_never_stacks_on_due_standard_activity_burst(self):
        from time import time as clock
        snap=b.read_snapshot(CONFIG,lambda path, _:fixtures()[path])
        base={'owner':p.identity(CONFIG['clientId']), 'history':[], 'changes':[],
              'csv':{},'journal':{}}
        activity={'code':'READ_OK', 'rows':[], 'attemptedEpoch':clock(),'pagingVersion':b.HISTORY_PAGING_VERSION,
                  'schemaVersion':b.trades.SCHEMA}
        fake={'orders':{'code':'READ_OK','rows':[]},'activities':activity}
        recent=copy.deepcopy(base)
        recent['journal'][p.identity(A)]={'activities':activity}
        with (patch.object(b,'load_ledger',return_value=recent),
              patch.object(b,'read_journal',return_value=fake),
              patch.object(b,'read_trade_coverage',return_value={'code':'READ_OK','observed':0}) as filtered,
              patch.object(b,'save_ledger')):
            b.update_portfolio(copy.deepcopy(snap),CONFIG,b._GENERATION)
            filtered.assert_called_once()
        with (patch.object(b,'load_ledger',return_value=copy.deepcopy(base)),
              patch.object(b,'read_journal',return_value=fake),
              patch.object(b,'read_trade_coverage') as filtered,
              patch.object(b,'save_ledger')):
            # When standard activity history is due, no extra filtered
            # requests are permitted in the same read cycle.
            b.update_portfolio(copy.deepcopy(snap),CONFIG,b._GENERATION)
            filtered.assert_not_called()

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
        limited=b.read_journal(A,CONFIG,get=get,max_bytes=100000)
        self.assertFalse(limited['activities']['complete'])
        self.assertLess(len(json.dumps(b.history_codec.encode_ledger({'journal': {'a': limited}})).encode()),110000)

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
