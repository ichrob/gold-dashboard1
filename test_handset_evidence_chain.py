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
        self.assertIn('Hebel',p['repairPlan']['requestedFields'])

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
