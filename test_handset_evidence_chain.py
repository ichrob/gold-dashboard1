import copy
import unittest
from datetime import timedelta
from test_android_observations import run, NOW, ISIN
from android_observations import prepare
from handset_evidence_chain import project


def sample(offset=0):
    payload=run()
    at=NOW+timedelta(seconds=offset)
    payload['batchId']=('b' if offset else 'a')*32
    payload['listUploadedAt']=at.isoformat()
    payload['results'][0]['draft']=payload['results'][0]['draft'].replace(
        '2026-10-28T10:59:00Z',at.isoformat())+'\nAnzeigezeit (Anzeige ungeprüft): '+at.strftime('%d/%m/%Y %H:%M')+'\nHandelsplatz (Anzeige ungeprüft): SG OTC'
    return prepare(payload,{'products':[{'isin':ISIN}]},at)

class ChainTests(unittest.TestCase):
    def test_one_original_cannot_produce_a_trade_and_duplicate_revision_is_not_an_exit(self):
        first=sample();second=copy.deepcopy(first);second['revision']+=1
        p=project([second,first])['products'][0]
        self.assertEqual(p['observationCount'],1)
        self.assertIsNone(p['illustrativeReplay'])
        self.assertEqual(p['repairPlan']['reason'],'device-attempt-budget-exhausted')

    def test_same_native_currency_ask_to_bid_replay_keeps_originals_and_excludes_net_performance(self):
        a,b=sample(),sample(3600)
        original=copy.deepcopy([a,b])
        result=project([b,a]);p=result['products'][0];r=p['illustrativeReplay']
        self.assertAlmostEqual(r['grossPerUnit'],-.01)
        self.assertEqual(r['entrySide'],'ask');self.assertEqual(r['exitSide'],'bid')
        self.assertIsNone(r['netResult']);self.assertFalse(r['performanceEligible'])
        self.assertFalse(result['netProductReturnsVerified'])
        self.assertEqual([a,b],original)
        self.assertEqual(len(p['originals']),2)

    def test_incompatible_venue_currency_clock_or_stale_observation_cannot_pair(self):
        a,b=sample(),sample(3600)
        for field,value in [('Währung','CHF'),('Handelsplatz','OTHER'),('Anzeigezeit','')]:
            x=copy.deepcopy(b);x['results'][0]['observation']['fields'][field]=value
            self.assertIsNone(project([x,a])['products'][0]['illustrativeReplay'])
        for key,value in [('staleAtReceipt',True),('observedAt','bad')]:
            x=copy.deepcopy(b);x['results'][0]['observation'][key]=value
            self.assertIsNone(project([x,a])['products'][0]['illustrativeReplay'])
        for offset in (60,18001):
            self.assertIsNone(project([sample(offset),a])['products'][0]['illustrativeReplay'])

    def test_missing_quotes_routes_to_status_check_instead_of_blind_retry(self):
        a=sample();a['results'][0].update(observation=None,code='NO_QUOTES')
        plan=project([a])['products'][0]['repairPlan']
        self.assertEqual(plan['requestedFields'],[])
        self.assertEqual(plan['reason'],'check-product-status-before-reread')
        self.assertFalse(plan['automaticExecution'])

    def test_cost_model_is_same_as_existing_ledger_for_one_unit_without_account_write(self):
        from paper_ledger_costs import MODEL
        p=project([sample(3600),sample()])['products'][0]['illustrativeReplay']
        cost=p['costModelReplay']
        self.assertEqual(cost['assumptions'],MODEL)
        self.assertEqual(cost['quantity'],1)
        self.assertAlmostEqual(cost['modelNetEur'],-.01-2-(13.07+13.06)*.0005)
        self.assertFalse(cost['ledgerUpdated'])
        self.assertFalse(cost['brokerNetVerified'])
        a,b=sample(),sample(3600)
        for row in (a,b):row['results'][0]['observation']['fields']['Währung']='CHF'
        cost=project([b,a])['products'][0]['illustrativeReplay']['costModelReplay']
        self.assertIsNone(cost['modelNetEur'])
        self.assertEqual(cost['status'],'missing-dated-fx')

    def test_new_capture_with_old_or_reversed_display_clock_is_not_a_price_step(self):
        a,b=sample(),sample(3600)
        for display in ('28/10/2026 11:00','28/10/2026 10:59','28/10/2026 11:02'):
            x=copy.deepcopy(b);x['results'][0]['observation']['fields']['Anzeigezeit']=display
            self.assertIsNone(project([x,a])['products'][0]['illustrativeReplay'])

    def test_daily_chf_reference_is_accepted_only_as_ex_post_model(self):
        from handset_evidence_chain import cost_replay, clock
        a = dict(currency='CHF', ask=54.31, bid=54.30,
                 at=clock('2026-11-06T07:36:43Z'), displayTime='06/11/2026 08:36')
        b = dict(currency='CHF', ask=55.95, bid=55.94,
                 at=clock('2026-11-06T08:30:12Z'), displayTime='06/11/2026 09:30')
        original = copy.deepcopy((a,b))
        cost = cost_replay(a,b)
        self.assertAlmostEqual(cost['grossEur'], 1.63/.9143, places=5)
        self.assertAlmostEqual(cost['modelNetEur'], 1.63/.9143-2-(54.31+55.94)/.9143*.0005, places=5)
        self.assertTrue(cost['fxConversion']['acceptedForModel'])
        self.assertTrue(cost['fxConversion']['exPost'])
        self.assertFalse(cost['fxConversion']['intradayVerified'])
        self.assertFalse(cost['brokerNetVerified'])
        self.assertFalse(cost['ledgerUpdated'])
        self.assertEqual((a,b),original)
        for update in (dict(displayTime='07/11/2026 09:30'),
                       dict(at=clock('2026-11-07T08:30:12Z')),
                       dict(displayTime='invalid')):
            self.assertEqual(cost_replay(a,dict(b,**update))['status'],'missing-dated-fx')

    def test_status_integrates_chain_without_mutations(self):
        from android_observations import status
        class Db:
            def execute(self,sql):
                self.sql=sql;return self
            def fetchall(self):return [(sample(),),(sample(3600),)]
        db=Db();out=status(db)
        self.assertTrue(db.sql.startswith('SELECT'))
        self.assertIsNotNone(out['evidenceChain']['products'][0]['illustrativeReplay'])
        self.assertEqual(len(out['runs']),2)

if __name__=='__main__':unittest.main()
