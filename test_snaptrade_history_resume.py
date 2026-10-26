import copy
import unittest
from unittest.mock import patch
import snaptrade_bridge as b
from test_snaptrade_bridge import CONFIG,A

class HistoryResumeTests(unittest.TestCase):
    def provider(self,total=12599,changed=False,duplicate=False):
        def get(path,config,params=None):
            if path.endswith('/orders'):return []
            self.calls.append(params['offset'])
            start=params['offset']
            data=[dict(id=str(i if not duplicate else i%500),type='CONTRIBUTION',trade_date='2026-10-24',currency={'code':'CHF'},amount=1) for i in range(start,min(total,start+500))]
            if changed and start==0:data[0]['amount']=2
            return dict(data=data,pagination={'total':total})
        return get

    def test_complete_history_resumes_with_five_page_budget_and_restart_safe_cursor(self):
        self.calls=[];state=None
        for cycle in range(8):
            self.calls=[]
            with patch.object(b.time,'time',return_value=2000000000+cycle*601):
                state=b.read_journal(A,CONFIG,copy.deepcopy(state),get=self.provider())
            self.assertLessEqual(len(self.calls),5)
            a=state['activities']
            if a['complete']:break
            self.assertFalse(b.trades.build(state)['historyComplete'])
            self.assertEqual(a['activityCoverageReason'],'PAGE_LIMIT')
        self.assertTrue(a['complete'])
        self.assertEqual(len(a['rows']),12599)
        self.assertEqual(a['nextOffset'],12599)
        self.assertEqual(a['activitySourceTotal'],12599)

    def test_changed_head_or_total_restarts_without_combining_snapshots(self):
        self.calls=[]
        with patch.object(b.time,'time',return_value=2000000000):
            old=b.read_journal(A,CONFIG,get=self.provider())
        for provider in (self.provider(changed=True),self.provider(total=12600)):
            self.calls=[]
            with patch.object(b.time,'time',return_value=2000000601):
                new=b.read_journal(A,CONFIG,old,get=provider)
            self.assertEqual(self.calls,[0,500,1000,1500,2000])
            self.assertEqual(len(new['activities']['rows']),2500)

    def test_duplicate_pages_never_claim_full_history(self):
        self.calls=[]
        state=b.read_journal(A,CONFIG,get=self.provider(total=1000,duplicate=True))
        self.assertFalse(state['activities']['complete'])
        self.assertEqual(state['activities']['activityCoverageReason'],'IDENTITY_COUNT_MISMATCH')

    def test_duplicate_pages_without_total_still_cannot_claim_complete(self):
        self.calls=[]
        provider=self.provider(total=1001,duplicate=True)
        def get(path,config,params=None):
            result=provider(path,config,params)
            if isinstance(result,dict):result['pagination']={}
            return result
        state=b.read_journal(A,CONFIG,get=get)
        self.assertFalse(state['activities']['complete'])
        self.assertEqual(state['activities']['activityCoverageReason'],'IDENTITY_COUNT_MISMATCH')

    def test_retry_cadence_and_size_limit_preserve_bounds(self):
        self.calls=[]
        with patch.object(b.time,'time',return_value=2000000000):
            old=b.read_journal(A,CONFIG,get=self.provider())
        self.assertFalse(b.activity_due(old['activities'],2000000599))
        self.assertTrue(b.activity_due(old['activities'],2000000600))
        failed={**old['activities'],'code':'UNAVAILABLE','failureCode':'RATE_LIMITED'}
        self.assertFalse(b.activity_due(failed,2000000601))
        self.calls=[]
        limited=b.read_journal(A,CONFIG,get=self.provider(),max_bytes=10)
        self.assertFalse(limited['activities']['complete'])
        self.assertEqual(limited['activities']['activityCoverageReason'],'SIZE_LIMIT')

if __name__=='__main__':unittest.main()
