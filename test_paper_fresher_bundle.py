"""Paper-only, zero-network fresh queued input preference tests."""
import unittest
import io
from datetime import datetime, timezone, timedelta
from contextlib import redirect_stdout
from unittest.mock import patch
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

    def test_rejected_newer_candidate_reports_bounded_reason_and_clocks(self):
        old=bundle(self.NOW,45)
        missing=bundle(self.NOW,5,history=False)
        evidence=paper.rejected_newer_paper_bundle_evidence(
            old,missing,self.NOW)
        self.assertEqual(evidence,{
            'reasonCode':'observed-closed-15m-missing',
            'currentSourceAt':self.NOW-45000,
            'candidateSourceAt':self.NOW-5000,
            'currentClosed15mAt':self.NOW-300000,
            'candidateClosed15mAt':None})

        rollback=bundle(self.NOW,5)
        rollback['history']['bars_by_tf']['15m'][0]['openTime']=self.NOW-1200000
        self.assertEqual(
            paper.rejected_newer_paper_bundle_evidence(old,rollback,self.NOW)['reasonCode'],
            'observed-closed-15m-rollback')
        self.assertIsNone(paper.rejected_newer_paper_bundle_evidence(
            old,bundle(self.NOW,5),self.NOW))

    def test_enqueue_prints_real_rejection_reason_without_bundle_payload(self):
        old=bundle(self.NOW,45)
        rejected=bundle(self.NOW,5,history=False)
        class Running:
            @staticmethod
            def is_alive():
                return True
        saved=(paper._latest,paper._study_latest,paper._thread)
        try:
            paper._latest=None
            paper._study_latest=old
            paper._thread=Running()
            output=io.StringIO()
            with patch.object(paper.background_push,'degiro_session',return_value='trading'), \
                    patch.object(paper.time,'time',return_value=self.NOW/1000), \
                    redirect_stdout(output):
                paper.enqueue(rejected,None)
            line=output.getvalue()
            self.assertIn('BOB_STUDY_CANDIDATE_REJECTED',line)
            self.assertIn('BOB_STUDY_CANDIDATE_ENQUEUE outcome=rejected',line)
            self.assertIn('candidate_trace=',line)
            self.assertIn('selected_source_at_ms=',line)
            self.assertIn('reason=observed-closed-15m-missing',line)
            self.assertNotIn("'spots'",line)
            self.assertNotIn("'history'",line)
            self.assertIs(paper._study_latest,old)
        finally:
            paper._latest,paper._study_latest,paper._thread=saved
            paper._bundle_ready.clear()

    def test_enqueue_and_final_selection_share_redacted_bundle_trace(self):
        old=bundle(self.NOW,45)
        newer=bundle(self.NOW,5)
        for item in (old,newer):
            item['spots']['xaus']=4000.0
        class Running:
            @staticmethod
            def is_alive():
                return True
        saved=(paper._latest,paper._study_latest,paper._thread)
        try:
            paper._latest=paper._study_latest=old
            paper._thread=Running()
            output=io.StringIO()
            with patch.object(paper.background_push,'degiro_session',return_value='trading'), \
                    patch.object(paper.time,'time',return_value=self.NOW/1000), \
                    redirect_stdout(output):
                paper.enqueue(newer,None)
                market=dict(ready=True,priceFresh=False,
                            dataAt=self.NOW-45000,analysisBarAt=self.NOW-300000)
                selected,_=paper.refresh_original_study_input(
                    old,market,{},paper.latest_paper_bundle,
                    lambda candidate,settings,priority: dict(
                        ready=True,priceFresh=True,
                        dataAt=paper.stamp(candidate['spots']['spot_price_as_of']),
                        analysisBarAt=self.NOW-300000),
                    lambda:self.NOW,evidence_phase='quality-final')
            lines=output.getvalue()
            trace=paper.study_bundle_handoff_evidence(newer)['trace']
            self.assertIs(selected,newer)
            self.assertIn('BOB_STUDY_CANDIDATE_ENQUEUE outcome=selected',lines)
            self.assertIn(
                'BOB_STUDY_FINAL_SELECTION phase=quality-final '
                'retry_required=1 outcome=reused',lines)
            self.assertGreaterEqual(lines.count('selected_trace='+trace),2)
            self.assertNotIn('4000.0',lines)
            self.assertNotIn("'spots'",lines)
        finally:
            paper._latest,paper._study_latest,paper._thread=saved
            paper._bundle_ready.clear()

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

    def test_quote_only_wakeup_cannot_repeat_original_quality_generation(self):
        # A new collector enqueue advances the local generation exactly once.
        self.assertTrue(paper.quality_generation_pending(7,8))
        # Completed quote futures can wake the same worker again, but must not
        # turn its unchanged local bundle into another original study cycle.
        self.assertFalse(paper.quality_generation_pending(8,8))
        self.assertFalse(paper.quality_generation_pending(9,8))

    def test_only_strictly_selected_candidate_advances_quality_generation(self):
        current={}
        selected={}
        self.assertEqual(paper.next_quality_generation(current,selected,7),8)
        self.assertEqual(paper.next_quality_generation(current,current,7),7)


class OriginalStudyCandleRetryTests(unittest.TestCase):
    """Original source-time recheck only, without estimates or market-gate bypass."""

    NOW = 1792690000000

    def originals(self):
        from test_paper_shadow_studies import observed
        old, market = observed(self.NOW-20000)
        newer, _ = observed(self.NOW-5000)
        bar=(self.NOW//300000-1)*300000
        market.update(analysisBarAt=bar,entryTiming='five-minute-confirmation',
                      ready=True,priceFresh=True)
        newer['history']['bars_by_tf']['5m']=[
            dict(openTime=bar, instrument='XAU/USD',isOpen=False)]
        return old,newer,market

    def test_fresh_spot_with_missing_5m_rechecks_one_new_original_bundle(self):
        import copy
        old,new,base=self.originals()
        original=copy.deepcopy((old,new))
        calls=[]
        def analyze(bundle,settings,priority):
            calls.append(bundle)
            return dict(base,dataAt=paper.stamp(bundle['spots']['spot_price_as_of']),
                        price=bundle['spots']['xaus'])
        self.assertTrue(paper.study_closed_bar_retry_needed(
            old,analyze(old,{},2),self.NOW))
        calls.clear()
        selected,market=paper.analyze_latest_bundle(
            old,{},lambda:new,analyze,lambda:self.NOW)
        self.assertIs(selected,new)
        self.assertEqual(calls,[old,new])
        self.assertEqual(market['dataAt'],paper.stamp(new['spots']['spot_price_as_of']))
        self.assertFalse(paper.study_closed_bar_retry_needed(selected,market,self.NOW))
        self.assertEqual((old,new),original)

    def test_final_study_handoff_rechecks_snapshot_aged_during_work(self):
        # Initial analysis is fresh. Fifty seconds of bounded paper work later,
        # that exact input is stale while a newer complete ORIGINAL is queued.
        start=self.NOW
        late=start+50000
        old=bundle(start,20)
        new=bundle(late,5)
        closed_bar=start-1800000
        for candidate in (old,new):
            candidate['spots']['xaus']=1.0
            candidate['history']['bars_by_tf']['15m'][0]['openTime']=closed_bar
        calls=[]
        def analyze(candidate,settings,priority):
            calls.append(candidate)
            return dict(ready=True,priceFresh=True,price=1.0,
                        dataAt=paper.stamp(candidate['spots']['spot_price_as_of']),
                        analysisBarAt=closed_bar,direction=None)

        market=analyze(old,{},2)
        self.assertFalse(paper.study_closed_bar_retry_needed(old,market,start))
        calls.clear()
        selected,refreshed=paper.refresh_original_study_input(
            old,market,{},lambda:new,analyze,lambda:late)

        self.assertIs(selected,new)
        self.assertEqual(calls,[new])
        self.assertEqual(
            refreshed['dataAt'],
            paper.stamp(new['spots']['spot_price_as_of']))
        self.assertEqual(old['trace'],'old')
        self.assertEqual(new['trace'],'new')

    def test_final_study_handoff_logs_retained_selection_without_retry(self):
        old=bundle(self.NOW,20)
        queued=bundle(self.NOW,5)
        closed_bar=self.NOW-900000
        for candidate in (old,queued):
            candidate['spots']['xaus']=1.0
            candidate['history']['bars_by_tf']['15m'][0]['openTime']=closed_bar
        market=dict(ready=True,priceFresh=True,price=1.0,
                    dataAt=paper.stamp(old['spots']['spot_price_as_of']),
                    analysisBarAt=closed_bar,direction=None)
        calls=[]
        output=io.StringIO()
        with redirect_stdout(output):
            selected,unchanged=paper.refresh_original_study_input(
                old,market,{},lambda:queued,
                lambda candidate,settings,priority:calls.append(candidate),
                lambda:self.NOW)

        evidence=output.getvalue()
        self.assertIs(selected,old)
        self.assertIs(unchanged,market)
        self.assertEqual(calls,[])
        self.assertIn(
            'BOB_STUDY_FINAL_SELECTION phase=analysis retry_required=0 '
            'outcome=retained',evidence)
        self.assertIn(
            'candidate_trace='+paper.study_bundle_handoff_evidence(queued)['trace'],
            evidence)
        self.assertIn(
            'selected_trace='+paper.study_bundle_handoff_evidence(old)['trace'],
            evidence)
        self.assertNotIn("'spots'",evidence)
        self.assertNotIn("'history'",evidence)

    def test_final_study_handoff_retains_freshest_original_across_later_arrivals(self):
        # Background requests are ordered by collection time. A later request
        # may still carry an older provider clock and must not hide the fresher
        # complete ORIGINAL already queued for the final quality handoff.
        fresh=bundle(self.NOW,5)
        later_but_older=bundle(self.NOW,55)
        class Running:
            @staticmethod
            def is_alive():
                return True

        saved=(paper._latest,paper._study_latest,paper._thread)
        try:
            paper._latest=paper._study_latest=None
            paper._thread=Running()
            with patch.object(paper.background_push,'degiro_session',return_value='trading'), \
                    patch.object(paper.time,'time',return_value=self.NOW/1000):
                paper.enqueue(fresh,None)
                paper.enqueue(later_but_older,None)

            self.assertIs(paper._latest,later_but_older)
            self.assertIs(paper.latest_paper_bundle(),fresh)
        finally:
            paper._latest,paper._study_latest,paper._thread=saved
            paper._bundle_ready.clear()

    def test_no_new_original_or_no_missing_bar_means_no_extra_analysis(self):
        old,new,base=self.originals()
        calls=[]
        def analyze(b,s,priority):
            calls.append(b)
            return dict(base,dataAt=paper.stamp(b['spots']['spot_price_as_of']),
                        price=b['spots']['xaus'])
        # No newer timestamp: another call would not fix the original gap.
        same=old
        selected,_=paper.analyze_latest_bundle(
            old,{},lambda:same,analyze,lambda:self.NOW)
        self.assertIs(selected,old)
        self.assertEqual(len(calls),1)
        calls.clear()
        # A matching original 5m candle means source input is already complete.
        old['history']['bars_by_tf']['5m']=new['history']['bars_by_tf']['5m']
        selected,_=paper.analyze_latest_bundle(
            old,{},lambda:new,analyze,lambda:self.NOW)
        self.assertIs(selected,old)
        self.assertEqual(len(calls),1)

    def test_future_or_unverified_queued_spot_never_bypasses_candle_checks(self):
        old,new,base=self.originals()
        calls=[]
        def analyze(b,s,priority):
            calls.append(b)
            return dict(base,dataAt=paper.stamp(b['spots']['spot_price_as_of']),
                        price=b['spots']['xaus'])
        new['spots']['is_genuine_xauusd_spot']=False
        selected,_=paper.analyze_latest_bundle(
            old,{},lambda:new,analyze,lambda:self.NOW)
        self.assertIs(selected,old)
        self.assertEqual(len(calls),1)
        self.assertFalse(paper.study_closed_bar_retry_needed(
            old,dict(base,priceFresh=False),self.NOW))
        self.assertFalse(paper.study_closed_bar_retry_needed(
            old,dict(base,dataAt=self.NOW+100000),self.NOW))

if __name__=='__main__':
    unittest.main()
