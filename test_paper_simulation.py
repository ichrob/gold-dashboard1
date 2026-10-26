import copy
import unittest
from unittest.mock import Mock
import paper_simulation as sim

NOW=1791442800000  # 2026-10-08 09:00 Zurich
ISIN='DE000PJ9NCK0'

def market(direction='LONG'):
    long=direction=='LONG'
    return dict(plan=dict(kind='candidate',direction=direction,entry=100.,stop=90. if long else 110.,target=120. if long else 80.,unit='USD/oz'),
                price=100.,priceFresh=True,ready=True,dataAt=NOW,analysisBarAt=NOW,ruleVersion='intraday-responsive-v6',
                direction=direction,mtf=direction,score=80 if long else 20,macd=2 if long else -2,signal=1 if long else -1,atr=10.)

def quote(now=NOW,bid=10.,ask=10.1):
    return dict(isin=ISIN,found=True,marketOpen=True,bid=bid,ask=ask,currency='EUR',source='issuer test',bidAt=now,askAt=now)

def case(direction='LONG'):
    return sim.new_case(market(direction),dict(isin=ISIN,scope='XAU/USD'),quote(),NOW,cash=101.)

def tick(price,seconds=30,direction='LONG',**values):
    return {**market(direction),'price':price,'dataAt':NOW+seconds*1000,**values}

class SimulationTests(unittest.TestCase):
    def test_slow_quote_refresh_cannot_starve_end_of_list(self):
        from concurrent.futures import Future
        from unittest.mock import patch
        submitted=[]
        def submit(fetch, isin):
            future=Future();submitted.append((isin,future));return future
        pool=Mock();pool.submit.side_effect=submit
        products=[dict(isin='product-'+str(i)) for i in range(12)]
        active=products[-1]['isin']
        with patch.object(sim,'_pool',pool), patch.object(sim,'_pending',{}), \
             patch.object(sim,'_quotes',{}), patch.object(sim,'_requested',{}):
            sim.quote_cache(products,[active],NOW)
            self.assertEqual(submitted[0][0],active)
            self.assertEqual(len(submitted),4)
            # A refresh with all slots busy neither blocks nor duplicates requests.
            sim.quote_cache(products,[active],NOW+30000)
            self.assertEqual(len(submitted),4)
            for cycle in (1,2):
                for isin,future in submitted:
                    if not future.done():future.set_result(dict(isin=isin,bidAt=NOW))
                sim.quote_cache(products,[active],NOW+cycle*60000)
            self.assertEqual(len(submitted),12)
            self.assertEqual(len({i for i,_ in submitted}),12)
            self.assertEqual(sim._quotes[active]['bidAt'],NOW,'Never refresh source clocks')

    def test_quote_rejection_diagnostics_preserve_gates(self):
        cases=[(None,'Kursantwort'),({**quote(),'isin':'wrong'},'ISIN'),
               ({**quote(),'currency':'CHF'},'EUR'),
               ({**quote(),'marketOpen':False},'Handelbarkeit'),
               ({**quote(),'found':False,'quoteFailureCode':'PRODUCT_TIMEOUT'},'PRODUCT_TIMEOUT'),
               ({**quote(),'priceKind':'issuer-chart'},'Chart'),
               ({**quote(),'isExecutableQuote':False},'Recherchekurs'),
               ({**quote(),'bid':None},'Geld- oder Briefkurs'),
               ({**quote(),'ask':1},'Widersprüchlicher'),
               (quote(NOW-90001),'90 Sekunden'),(quote(NOW+1),'Zukunft'),
               ({**quote(),'bidAt':None},'Quellzeit')]
        for value,expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected,sim.quote_block_reason(value,NOW,ISIN))
                self.assertIsNone(sim.fresh_quote(value,NOW,ISIN))
        self.assertIsNone(sim.quote_block_reason(quote(),NOW,ISIN))
        self.assertIsNotNone(sim.fresh_quote(quote(NOW-90000),NOW,ISIN))

    def test_new_screenshot_generation_replaces_previous_background_universe(self):
        import json
        class Memory:
            def __init__(self):self.current=None;self.invalidations=0
            def execute(self,sql,args=()):
                if 'SELECT payload FROM bob_paper_products' in sql:
                    self.last=(copy.deepcopy(self.current),) if self.current is not None else None
                elif 'INSERT INTO bob_paper_products' in sql:
                    self.current=json.loads(args[0]);self.last=None
                elif 'UPDATE subscriptions SET selection_evidence=NULL' in sql:
                    self.invalidations+=1;self.last=None
                else: self.last=None
                return self
            def fetchone(self):return self.last
        conn=Memory()
        old=dict(listUploadedAt='2026-10-10T08:00:00.000Z',origin='degiro-screenshot',
                 products=[{'isin':'DE000FG4JXV7','productDirection':'SHORT','price':12}])
        newer=dict(listUploadedAt='2026-10-12T06:00:00.000Z',origin='degiro-screenshot',
                   products=[{'isin':'DE000FC1CHB7','productDirection':'LONG','price':18}])
        # Request timestamps are immutable list versions; mocked time is later than both.
        self.assertFalse(sim.sync(conn,old).get('preserved',False))
        self.assertFalse(sim.sync(conn,newer).get('preserved',False))
        self.assertEqual([p['isin'] for p in conn.current['products']],['DE000FC1CHB7'])
        self.assertEqual(conn.current['listUploadedAt'],newer['listUploadedAt'])
        self.assertEqual(conn.invalidations,2,'Each new list invalidates old product-Push evidence')
        self.assertTrue(sim.sync(conn,old)['preserved'])
        self.assertTrue(sim.sync(conn,{'products':old['products']})['preserved'])
        self.assertTrue(sim.sync(conn,{**newer,'products':old['products']})['preserved'])
        self.assertEqual([p['isin'] for p in conn.current['products']],['DE000FC1CHB7'])
        newer_quote={**newer,'products':[{'isin':'DE000FC1CHB7','productDirection':'LONG','price':19}]}
        self.assertFalse(sim.sync(conn,newer_quote).get('preserved',False))
        self.assertEqual(conn.invalidations,2,'Same-generation quote updates retain the push-list revision')
        self.assertEqual(conn.current['products'][0]['price'],19,
                         'The same active list may receive newer independently verified quotes')
        # Legacy snapshots contained all twelve UI slots, including empty rows.
        conn.current['products'].extend([{'isin':'','name':''},{'isin':None}])
        self.assertFalse(sim.sync(conn,newer_quote).get('preserved',False))
        self.assertEqual(len(conn.current['products']),1)
        padded={**newer_quote,'products':newer_quote['products']+[{'isin':'','name':''}]}
        self.assertFalse(sim.sync(conn,padded).get('preserved',False))
        self.assertEqual(len(conn.current['products']),1)

    def test_invalid_screenshot_timestamp_rejected(self):
        conn=Mock()
        for when in ('not-a-date','2026-10-12T09:00:00',
                     '2099-01-01T00:00:00Z'):
            with self.assertRaises(ValueError):
                sim.sync(conn,dict(products=[{'isin':ISIN}],origin='degiro-screenshot',
                                   listUploadedAt=when))

    def test_weekend_enqueuing_does_not_start_quote_worker(self):
        from unittest.mock import patch
        with patch.object(sim.background_push,'gold_weekend_seconds_remaining',return_value=3600), \
             patch.object(sim.background_push,'degiro_session',return_value='weekend'):
            with patch.object(sim,'_bundle_ready') as event:
                sim.enqueue({'spots':{'xaus':4000}}, lambda:None)
                event.set.assert_not_called()

    def test_weekend_paper_report_explicitly_closed_without_database_mutation(self):
        from unittest.mock import patch
        conn=Mock()
        conn.execute.return_value.fetchone.side_effect=[
            ({'startAt':sim.START,'enabled':True,'status':'running'},),None,None]
        conn.execute.return_value.fetchall.side_effect=[[],[],[]]
        # Fix the simulated market session: selected archive day is Saturday,
        # while CI may execute this test on a live weekday in Zurich.
        with patch.object(sim.background_push,'gold_weekend_seconds_remaining',return_value=3600), \
             patch.object(sim.background_push,'degiro_session',return_value='weekend'):
            out=sim.report(conn,'2026-10-10')
        self.assertTrue(out['marketClosed'])
        self.assertEqual(out['control']['status'],'market-closed')
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in conn.execute.call_args_list))

    def test_100_euro_whole_units_cash_and_loss(self):
        c=sim.new_case(market(),dict(isin=ISIN),quote(),NOW)
        self.assertEqual(c['quantity'],9);self.assertAlmostEqual(c['allocated'],90.9)
        control=dict(initialCapital=100.,cash=100-c['allocated'],dayOpeningEquity=100.)
        sim.capital_snapshot(control,c,quote(),NOW)
        self.assertAlmostEqual(control['cash'],9.1);self.assertAlmostEqual(control['equity'],99.1)
        self.assertAlmostEqual(control['dayProfit'],-.9)
        done=sim.advance_case(c,tick(88),quote(NOW+30000,9.,9.1),NOW+30000)
        control['cash']+=done['cashReleased'];sim.capital_snapshot(control,done,None,NOW+30000)
        self.assertAlmostEqual(control['equity'],90.1);self.assertAlmostEqual(control['dayProfit'],-9.9)

    def test_odd_quantity_partial_uses_whole_units(self):
        c=sim.new_case(market(),dict(isin=ISIN),quote(),NOW)
        done=sim.advance_case(c,tick(120,suggestedStop=110,suggestedTarget=140,analysisBarAt=NOW+300000),quote(NOW+30000,12,12.1),NOW+30000)
        self.assertEqual(done['remainingUnits'],5);self.assertEqual(done['bookedUnits'],4)
        self.assertAlmostEqual(done['cashReleased'],48);self.assertAlmostEqual(done['remaining'],5/9)

    def test_one_unit_closes_at_first_target_without_fraction(self):
        c=sim.new_case(market(),dict(isin=ISIN),quote(ask=75.,bid=74.),NOW)
        done=sim.advance_case(c,tick(120,suggestedTarget=140),quote(NOW+30000,80.,81.),NOW+30000)
        self.assertEqual(done['status'],'closed');self.assertEqual(done['bookedUnits'],1)

    def test_insufficient_capital_never_creates_credit(self):
        with self.assertRaises(ValueError):sim.new_case(market(),dict(isin=ISIN),quote(ask=101.,bid=100.),NOW)

    def test_missing_sale_waits_and_later_price_is_labeled(self):
        c=sim.advance_case(case(),tick(88),None,NOW+30000)
        self.assertEqual(c['cashReleased'],0);self.assertEqual(c['pendingUnits'],10)
        ctl=dict(initialCapital=101.,cash=0.,dayOpeningEquity=101.)
        sim.capital_snapshot(ctl,c,None,NOW+30000);self.assertIsNone(ctl['equity'])
        c=sim.advance_case(c,tick(87,60),quote(NOW+60000,9.,9.1),NOW+60000)
        self.assertEqual(c['pendingUnits'],0);self.assertEqual(c['cashReleased'],90)
        self.assertEqual(c['events'][-1]['kind'],'deferred-sale')
        self.assertEqual(c['events'][-1]['at'],NOW+60000);self.assertTrue(c['productReturnKnown'])

    def test_day_gain_uses_carried_capital_not_daily_100_reset(self):
        ctl=dict(initialCapital=100.,cash=117.1,dayOpeningEquity=117.1)
        sim.capital_snapshot(ctl,None,None,NOW);self.assertEqual(ctl['dayProfit'],0)
        self.assertAlmostEqual(ctl['totalProfit'],17.1)
        c=sim.new_case(market(),dict(isin=ISIN),quote(),NOW,cash=ctl['cash'])
        self.assertEqual(c['quantity'],11)

    def test_ledger_transactions_debit_and_settle_exactly_once(self):
        import json
        class DB:
            def __init__(self):
                self.control=dict(startAt=sim.START,enabled=True)
                self.case=None;self.days={};self.row=None
            def execute(self,sql,args=()):
                self.row=None
                if sql.startswith('SELECT payload FROM bob_paper_control'):
                    self.row=(copy.deepcopy(self.control),)
                elif sql.startswith('SELECT id,payload FROM bob_paper_cases'):
                    if self.case and self.case.get('dbOpen',True):self.row=(self.case['id'],copy.deepcopy(self.case))
                elif sql.startswith('SELECT payload FROM bob_paper_days'):
                    if args[0] in self.days:self.row=(copy.deepcopy(self.days[args[0]]),)
                elif 'INSERT INTO bob_paper_cases' in sql:
                    self.case=json.loads(args[3]);self.row=(args[0],)
                elif sql.startswith('UPDATE bob_paper_cases'):
                    self.case=json.loads(args[0]);self.case['dbOpen']=args[1] is None
                elif 'INSERT INTO bob_paper_days' in sql:
                    self.days[args[0]]=json.loads(args[1])
                elif sql.startswith('UPDATE bob_paper_control'):
                    self.control=json.loads(args[0])
                return self
            def fetchone(self):return self.row
        db=DB();m={**market(),'session':{'entryAllowed':True}};choice={'choices':[{'isin':ISIN}]}
        sim.run_once(db,{},m,choice,{ISIN:quote()},NOW)
        self.assertAlmostEqual(db.control['cash'],9.1)
        self.assertAlmostEqual(db.control['equity'],99.1)
        sim.run_once(db,{},tick(88),choice,{},NOW+30000)
        self.assertIsNone(db.control['equity']);self.assertEqual(db.case['pendingUnits'],9)
        sim.run_once(db,{},tick(87,60),choice,{ISIN:quote(NOW+60000,9.,9.1)},NOW+60000)
        self.assertAlmostEqual(db.control['cash'],90.1)
        self.assertAlmostEqual(db.control['realizedProfit'],-9.9)
        sim.run_once(db,{},m,choice,{ISIN:quote(NOW+60000,9.,9.1)},NOW+60000)
        self.assertAlmostEqual(db.control['cash'],90.1)
        self.assertEqual(db.days['2026-10-08']['cases'],1)
        self.assertEqual(db.days['2026-10-08']['productKnown'],1)

    def test_long_stop_before_any_trail(self):
        c=case();done=sim.advance_case(c,tick(88,suggestedStop=105),quote(NOW+30000,9,9.1),NOW+30000)
        self.assertEqual(done['exitReason'],'stop');self.assertAlmostEqual(done['goldR'],-1.2)
        self.assertEqual(c['status'],'open');self.assertEqual(done['engine']['trade']['stop'],90)

    def test_short_stop_and_target(self):
        stopped=sim.advance_case(case('SHORT'),tick(111,direction='SHORT'),None,NOW+30000)
        target=sim.advance_case(case('SHORT'),tick(79,direction='SHORT'),None,NOW+30000)
        self.assertEqual(stopped['exitReason'],'stop');self.assertEqual(target['exitReason'],'target-exit')
        self.assertAlmostEqual(target['goldR'],2.1)

    def test_never_loosen_stop(self):
        c=sim.advance_case(case(),tick(110,suggestedStop=106),None,NOW+30000)
        self.assertEqual(c['engine']['trade']['stop'],106)
        c=sim.advance_case(c,tick(112,60,suggestedStop=92),None,NOW+60000)
        self.assertGreaterEqual(c['engine']['trade']['stop'],106)

    def test_partial_gain_then_extended_target_and_stop(self):
        c=sim.advance_case(case(),tick(120,suggestedStop=110,suggestedTarget=140,analysisBarAt=NOW+300000),quote(NOW+30000,12,12.1),NOW+30000)
        self.assertEqual(c['status'],'open');self.assertEqual(c['remaining'],.5);self.assertEqual(c['engine']['trade']['target'],140)
        self.assertEqual(c['goldR'],1.)
        c=sim.advance_case(c,tick(109,60),quote(NOW+60000,11,11.1),NOW+60000)
        self.assertEqual(c['exitReason'],'stop');self.assertAlmostEqual(c['goldR'],1.45)
        self.assertAlmostEqual(c['productGrossPct'],((12/10.1-1)+(11/10.1-1))*50)
        self.assertFalse(c['netReturnKnown'])

    def test_gap_never_claims_target_or_profit(self):
        c=sim.advance_case(case(),tick(125,120),quote(NOW+120000,12,12.1),NOW+120000)
        self.assertEqual(c['status'],'inconclusive');self.assertIsNone(c['productGrossPct'])
        self.assertEqual(c['goldR'],0)

    def test_missing_gold_closes_unknown(self):
        c=sim.advance_case(case(),dict(priceFresh=False),None,NOW+91000)
        self.assertEqual(c['status'],'inconclusive')

    def test_old_future_duplicate_clock_does_not_advance(self):
        for at in (NOW,NOW-30000):
            c=sim.advance_case(case(),{**tick(120),'dataAt':at},None,NOW+30000)
            self.assertEqual(c['remaining'],1.)
        self.assertIsNone(sim.fresh_quote(quote(NOW+30000),NOW,ISIN))

    def test_unknown_stale_chart_prices_stay_unknown(self):
        for q in (None,quote(NOW-91000),{**quote(),'priceKind':'issuer-chart'},{**quote(),'currency':'CHF'}):
            c=sim.new_case(market(),dict(isin=ISIN),q,NOW)
            self.assertFalse(c['productReturnKnown'])
        c=sim.advance_case(case(),tick(120),None,NOW+30000)
        self.assertIsNone(c['productGrossPct']);self.assertEqual(c['status'],'closed')

    def test_reversal_closes_before_trailing(self):
        c=sim.advance_case(case(),tick(106,direction='SHORT',suggestedStop=107),None,NOW+30000)
        self.assertEqual(c['exitReason'],'reversal-exit');self.assertEqual(c['engine']['trade']['stop'],90)

    def test_demo_is_closed_labeled_and_not_product_profit(self):
        c=sim.technical_demo(4100,dict(isin=ISIN,name='Gold Long'))
        self.assertTrue(c['demonstration']);self.assertEqual(c['status'],'closed')
        kinds=[e['kind'] for e in c['events']]
        self.assertIn('partial-profit',kinds);self.assertIn('stop-raised',kinds);self.assertIn('target-extended',kinds)
        self.assertIsNone(c['productGrossPct'])

    def test_empty_slots_never_erase_saved_universe(self):
        conn=Mock();r=sim.sync(conn,{'products':[{}, {'price':10}]})
        self.assertTrue(r['preserved']);conn.execute.assert_not_called()

    def test_read_report_does_not_advance_or_write(self):
        conn=Mock();conn.execute.return_value.fetchone.side_effect=[dict_payload:=({'startAt':sim.START},),None,None]
        conn.execute.return_value.fetchall.side_effect=[[],[],[]]
        r=sim.report(conn,'2026-10-08');self.assertEqual(r['cases'],[])
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in conn.execute.call_args_list))

    def test_scheduled_start_not_backfilled(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=({'startAt':sim.START,'enabled':True},)
        sim.run_once(conn,{},market(),{'choices':[{'isin':ISIN}]},{},sim.START-1)
        sql=[call.args[0] for call in conn.execute.call_args_list]
        self.assertFalse(any('INSERT INTO bob_paper_cases' in q for q in sql))

if __name__=='__main__':unittest.main()
