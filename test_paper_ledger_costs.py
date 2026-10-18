import copy,json,os,unittest,uuid
from unittest.mock import patch
import paper_ledger_costs as costs
import paper_simulation as sim
import paper_portfolios as portfolios
from test_paper_portfolios import market,quote,ISIN

class CashCosts(unittest.TestCase):
    def test_affordability_includes_entry_slippage_and_two_sale_fee_reserve(self):
        self.assertEqual(costs.units(13,10,costs.MODEL),0)
        self.assertEqual(costs.units(13.005,10,costs.MODEL),1)
        self.assertEqual(costs.units(100,10,costs.MODEL),9)
    def test_cost_debits_are_idempotent_and_partial_sales_pay_each_fee(self):
        c=dict(ledgerCostModel=costs.MODEL,quantity=4,allocated=40.,cashReleased=0.,events=[],remainingUnits=4,pendingUnits=0)
        control=dict(cash=60.,realizedProfit=0.)
        costs.apply(control,c);self.assertAlmostEqual(control['cash'],58.98)
        costs.apply(control,c);self.assertAlmostEqual(control['cash'],58.98)
        c['events'].append(dict(units=2,quote={'bid':11.}));c.update(cashReleased=22.,remainingUnits=2)
        control['cash']+=22;control['realizedProfit']+=2
        costs.apply(control,c);self.assertAlmostEqual(control['cash'],79.969)
        c['events'].append(dict(units=2,quote={'bid':12.}));c.update(cashReleased=46.,remainingUnits=0)
        control['cash']+=24;control['realizedProfit']+=4
        costs.apply(control,c)
        self.assertAlmostEqual(control['cash'],102.957)
        self.assertAlmostEqual(c['ledgerModelNetEur'],2.957)
        self.assertAlmostEqual(control['realizedProfit'],2.957)
    def test_missing_quote_does_not_charge_sale_until_actual_paper_settlement(self):
        c=dict(ledgerCostModel=costs.MODEL,quantity=1,allocated=10.,cashReleased=0.,events=[dict(units=1,quote=None)],remainingUnits=0,pendingUnits=1)
        control=dict(cash=90.,realizedProfit=0.)
        costs.apply(control,c);self.assertEqual(c['ledgerFeesEur'],1.)
        self.assertIsNone(c['ledgerModelNetEur'])
        c['events'].append(dict(units=1,quote={'bid':11.}));c.update(pendingUnits=0,cashReleased=11.)
        control['cash']+=11;control['realizedProfit']+=1
        costs.apply(control,c);self.assertEqual(c['ledgerFeesEur'],2.)
        costs.apply(control,c);self.assertEqual(c['ledgerFeesEur'],2.)
    def test_old_case_and_baseline_are_not_rewritten(self):
        control=dict(cash=80.,equity=80.,realizedProfit=-20.)
        costs.apply(control,dict(quantity=3,allocated=30.));self.assertEqual(control['cash'],80.)
        costs.activate(control,costs.START);control['equity']=75.
        costs.activate(control,costs.START+1000);self.assertEqual(control['costsOpeningEquity'],80.)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class CashLedgerIntegration(unittest.TestCase):
    def test_entry_stop_and_replay_use_net_cash_in_durable_account(self):
        import psycopg
        now=costs.START+3600000;schema='net_cost_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema);conn.execute('SET search_path TO '+schema)
            with patch('paper_portfolios.time.time',return_value=now/1000):sim.init(conn)
            ledger=portfolios.Ledger(conn,'balanced');policy=portfolios.POLICIES['balanced']
            m=market();m.update(dataAt=now,analysisBarAt=now)
            selection={'choices':[dict(isin=ISIN)]}
            sim.run_once(ledger,{},m,selection,{ISIN:quote(now)},now,policy)
            c=ledger.execute('SELECT payload FROM bob_paper_cases').fetchone()[0]
            account=ledger.execute('SELECT payload FROM bob_paper_control').fetchone()[0]
            self.assertEqual(c['quantity'],6)
            self.assertAlmostEqual(account['cash'],100-60.6-1-.0303)
            self.assertAlmostEqual(c['ledgerCostsDebited'],1.0303)
            later=now+30000;m.update(dataAt=later,price=3979)
            q=quote(later);q.update(bid=9.9,ask=10.)
            sim.run_once(ledger,{},m,selection,{ISIN:q},later,policy)
            account=ledger.execute('SELECT payload FROM bob_paper_control').fetchone()[0]
            c=ledger.execute('SELECT payload FROM bob_paper_cases').fetchone()[0]
            self.assertAlmostEqual(account['cash'],96.74)
            self.assertAlmostEqual(account['realizedProfit'],-3.26)
            self.assertAlmostEqual(account['costPeriodProfit'],-3.26)
            self.assertAlmostEqual(c['reflection']['costModel']['modelNetEur'],-3.26)
            sim.run_once(ledger,{},m,selection,{ISIN:q},later,policy)
            self.assertAlmostEqual(ledger.execute('SELECT payload FROM bob_paper_control').fetchone()[0]['cash'],96.74)
            conn.execute('DROP SCHEMA '+schema+' CASCADE')
