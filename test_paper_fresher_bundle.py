"""Paper-only, zero-network fresh queued input preference tests."""
import unittest
from datetime import datetime, timezone, timedelta
import paper_simulation as paper


def bundle(now, age_seconds, *, spot=True, history=True, naive=False):
    t=datetime.fromtimestamp(now/1000,timezone.utc)-timedelta(seconds=age_seconds)
    stamp=t.replace(tzinfo=None).isoformat() if naive else t.isoformat()
    return {
        'spots':{'spot_price_as_of':stamp,
            'xaus_is_spot':spot,'is_genuine_xauusd_spot':spot},
        'history':{'bars_by_tf':{'15m':[{'openTime':now-300000}]}} if history else {},
        'trace':'new' if age_seconds==5 else 'old'
    }


class FreshPaperBundleTests(unittest.TestCase):
    NOW=1792690000000

    def test_newer_complete_original_replaces_old_and_keeps_entire_snapshot(self):
        old=bundle(self.NOW,55)
        new=bundle(self.NOW,5)
        self.assertIs(paper.newer_queued_paper_bundle(old,new,self.NOW),new)
        self.assertEqual(paper.newer_queued_paper_bundle(old,new,self.NOW)['trace'],'new')

    def test_never_accept_future_or_stale_source(self):
        old=bundle(self.NOW,55)
        self.assertIs(paper.newer_queued_paper_bundle(old,bundle(self.NOW,-1),self.NOW),old)
        self.assertIs(paper.newer_queued_paper_bundle(old,bundle(self.NOW,61),self.NOW),old)
        self.assertIs(paper.newer_queued_paper_bundle(old,bundle(self.NOW,60),self.NOW),old)
        self.assertIs(paper.newer_queued_paper_bundle(old,bundle(self.NOW,55),self.NOW),old)

    def test_never_accept_unverified_or_incomplete_newer_input(self):
        old=bundle(self.NOW,40)
        self.assertIs(paper.newer_queued_paper_bundle(old,bundle(self.NOW,5,spot=False),self.NOW),old)
        self.assertIs(paper.newer_queued_paper_bundle(old,bundle(self.NOW,5,history=False),self.NOW),old)
        self.assertIs(paper.newer_queued_paper_bundle(old,bundle(self.NOW,5,naive=True),self.NOW),old)
        self.assertIs(paper.newer_queued_paper_bundle(old,None,self.NOW),old)
        self.assertIs(paper.newer_queued_paper_bundle(old,{'spots':{}},self.NOW),old)

    def test_newer_spot_must_carry_observed_closed_15m_bars(self):
        old=bundle(self.NOW,45)
        for frames in (
                {},
                {'15m': []},
                {'15m': [{'openTime':self.NOW-300000,'isOpen':True}]},
                {'15m': [{'openTime':self.NOW-300000,'providerIsOpen':True}]},
                {'15m': [{'openTime':self.NOW-300000,'estimated':True}]},
                {'15m': [{'openTime':'not-a-clock'}]},
                {'15m': [None]}):
            candidate=bundle(self.NOW,5)
            candidate['history']['bars_by_tf']=frames
            self.assertIs(paper.newer_queued_paper_bundle(old,candidate,self.NOW),old)
            self.assertIsNone(paper.late_risk_retry_bundle(old,candidate,self.NOW))

    def test_spot_refresh_never_rolls_back_existing_15m_bar(self):
        old=bundle(self.NOW,45)
        newer=bundle(self.NOW,5)
        newer['history']['bars_by_tf']['15m'][0]['openTime']=self.NOW-1200000
        self.assertIs(paper.newer_queued_paper_bundle(old,newer,self.NOW),old)
        self.assertIsNone(paper.late_risk_retry_bundle(old,newer,self.NOW))
        # A genuinely newer matching closed bar remains usable.
        newer['history']['bars_by_tf']['15m'][0]['openTime']=self.NOW-100000
        self.assertIs(paper.newer_queued_paper_bundle(old,newer,self.NOW),newer)
        self.assertIs(paper.late_risk_retry_bundle(old,newer,self.NOW),newer)

    def test_missing_old_input_can_only_be_replaced_with_verified_source(self):
        original={'spots':{'spot_price_as_of':'invalid'},'history':{}}
        verified=bundle(self.NOW,5)
        self.assertIs(paper.newer_queued_paper_bundle(original,verified,self.NOW),verified)
        self.assertIs(paper.newer_queued_paper_bundle(original,bundle(self.NOW,5,spot=False),self.NOW),original)

    def test_late_risk_retry_requires_a_strictly_newer_complete_snapshot(self):
        old=bundle(self.NOW,55)
        new=bundle(self.NOW,5)
        self.assertIs(paper.late_risk_retry_bundle(old,new,self.NOW),new)
        self.assertIsNone(paper.late_risk_retry_bundle(old,old,self.NOW))
        self.assertIsNone(paper.late_risk_retry_bundle(old,bundle(self.NOW,5,spot=False),self.NOW))
        self.assertIsNone(paper.late_risk_retry_bundle(old,bundle(self.NOW,61),self.NOW))

    def test_invalid_time_and_non_numeric_age_do_not_grant_freshness(self):
        old=bundle(self.NOW,50)
        new=bundle(self.NOW,5)
        for value in (None, float('nan'), True, 'now'):
            self.assertIs(paper.newer_queued_paper_bundle(old,new,value),old)


if __name__=='__main__':
    unittest.main()
