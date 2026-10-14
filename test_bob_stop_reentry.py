import copy
import json
import unittest
from unittest.mock import Mock
import paper_simulation as sim
import paper_portfolios as profiles
from test_trend_follow import NOW, ISIN, market, quote, case


class MemoryLedger:
    def __init__(self,opened=None):
        self.control=dict(startAt=NOW-1,enabled=True,initialCapital=800.,cash=800.,equity=800.)
        self.active=opened
        if opened:self.control['cash']-=opened['allocated']
        self.days={};self.completed=[]

    def execute(self,sql,args=()):
        row=None
        if 'SELECT payload FROM bob_paper_control' in sql:row=(copy.deepcopy(self.control),)
        elif 'SELECT id,payload FROM bob_paper_cases' in sql:
            if self.active:row=(self.active['id'],copy.deepcopy(self.active))
        elif 'SELECT payload FROM bob_paper_days' in sql:
            if args[0] in self.days:row=(copy.deepcopy(self.days[args[0]]),)
        elif 'UPDATE bob_paper_cases SET' in sql:
            saved=json.loads(args[0])
            if args[1] is not None:self.completed.append(saved);self.active=None
            else:self.active=saved
        elif 'INSERT INTO bob_paper_cases' in sql:
            self.active=json.loads(args[3]);row=(self.active['id'],)
        elif 'INSERT INTO bob_paper_days' in sql:self.days[args[0]]=json.loads(args[1])
        elif 'UPDATE bob_paper_control SET' in sql:self.control=json.loads(args[0])
        cursor=Mock();cursor.fetchone.return_value=row;return cursor


class BobStopReentryTests(unittest.TestCase):
    def tick(self,ledger,m,q):
        selected=dict(choices=[dict(isin=ISIN,direction=m['direction'],scope='XAU/USD')])
        sim.run_once(ledger,{},m,selected,{ISIN:q},m['dataAt'],profiles.POLICIES['trend800'])

    def test_800_migrates_to_bob_stop_then_stops_and_reenters_on_new_signal_bar(self):
        ledger=MemoryLedger(case())
        tick=market(price=4005.,at=NOW+30000)
        tick['suggestedStop']=3995.
        self.tick(ledger,tick,quote(NOW+30000,10.2))
        self.assertFalse(ledger.active['trendFollow'])
        self.assertEqual(ledger.active['engine']['trade']['stop'],3995.)
        self.assertEqual(ledger.active['exitPolicy'],'bob-stop-reentry-v1')
        self.assertTrue(any(e['kind']=='stop-policy-changed' for e in ledger.active['events']))
        # A worse later suggestion must never loosen the adopted Bob stop.
        tick=market(price=4004.,at=NOW+60000);tick['suggestedStop']=3990.
        self.tick(ledger,tick,quote(NOW+60000,10.1))
        self.assertEqual(ledger.active['engine']['trade']['stop'],3995.)
        self.tick(ledger,market(price=3994.,at=NOW+90000),quote(NOW+90000,9.8))
        self.assertIsNone(ledger.active)
        self.assertEqual(ledger.completed[0]['exitReason'],'stop')
        self.assertEqual(ledger.completed[0]['remainingUnits'],0)
        self.tick(ledger,market(price=4000.,at=NOW+120000),quote(NOW+120000))
        self.assertIsNone(ledger.active)
        self.assertIn('neue bestätigte',ledger.control['reason'])
        # A newly confirmed setup receives its own entry, initial Bob stop and ID.
        self.tick(ledger,market(price=4000.,at=NOW+630000,bar=NOW+300000),quote(NOW+630000))
        self.assertIsNotNone(ledger.active)
        self.assertEqual(ledger.active['engine']['trade']['stop'],3980.)
        self.assertNotEqual(ledger.active['id'],ledger.completed[0]['id'])
        self.assertGreater(ledger.active['quantity'],0)

    def test_missing_exit_bid_keeps_capital_pending_and_blocks_reentry(self):
        ledger=MemoryLedger(case(False))
        self.tick(ledger,market(price=3970.,at=NOW+30000),None)
        self.assertIsNotNone(ledger.active)
        self.assertEqual(ledger.active['status'],'closed')
        self.assertGreater(ledger.active['pendingUnits'],0)
        before=ledger.control['cash']
        self.tick(ledger,market(at=NOW+60000,bar=NOW+300000),None)
        self.assertEqual(ledger.control['cash'],before)
        self.assertEqual(len(ledger.completed),0)


if __name__=='__main__':unittest.main()
