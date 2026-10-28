import json
import time
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock,patch
import push_server as p

class RiskDeliveryTests(unittest.TestCase):
    def run_delivery(self, fail_second=False):
        db=MagicMock();conn=db.return_value.__enter__.return_value
        now=int(time.time()*1000)
        cfg={'riskEnabled':True,'timeframe':'15m','trade':None}
        conn.execute.return_value.fetchall.return_value=[(1,{},True,False,False,cfg,{},None,None)]
        def event(kind,risk):
            return {'title':'fixture','body':'fixture','tag':'fixture','data':{'kind':'general','eventKind':kind,'riskOnly':risk,'dataAt':now,'expiresAt':now+(60000 if risk else 180000)}}
        events=[event('signal-change',False),event('risk-warning',True)]
        with ExitStack() as stack:
            for obj,name in [(p.rule_learning,'tick'),(p.ranking_learning,'tick'),(p,'record_market_observation')]:stack.enter_context(patch.object(obj,name))
            stack.enter_context(patch.object(p.rule_learning,'policy',return_value={}))
            stack.enter_context(patch.object(p,'db',db))
            stack.enter_context(patch.object(p.background_push,'analyze',return_value={'ready':True,'priceFresh':True,'dataAt':now}))
            stack.enter_context(patch.object(p.background_push,'advance',return_value=({'risk':{'enabled':True,'checkedAt':now}},events)))
            stack.enter_context(patch.object(p,'vapid',return_value='fixture'))
            send=stack.enter_context(patch.object(p,'webpush',side_effect=[None,p.WebPushException('fixture')] if fail_second else None))
            count=p.run_background({})
        writes=[c for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE subscriptions SET background_state=')]
        self.assertEqual(send.call_count,2)
        messages=[json.loads(c.kwargs['data']) for c in send.call_args_list]
        self.assertFalse(messages[0]['data'].get('riskOnly'))
        self.assertTrue(messages[1]['data']['riskOnly'])
        self.assertLessEqual(send.call_args_list[1].kwargs['ttl'],60)
        return count,writes
    def test_success_persists_only_after_both_notifications(self):
        count,writes=self.run_delivery();self.assertEqual(count,2);self.assertEqual(len(writes),1)
        self.assertTrue(json.loads(writes[0].args[1][0])['risk']['enabled'])
    def test_partial_failure_keeps_previous_checkpoint(self):
        count,writes=self.run_delivery(True);self.assertEqual(count,1);self.assertFalse(writes)
if __name__=='__main__':unittest.main()
