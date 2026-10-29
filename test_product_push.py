import unittest
from product_push import transition, evaluate
import time

class ProductPushTransitions(unittest.TestCase):
    now=1800000000000
    def checked(self, count=1, **kwargs):
        return {'products':[{'isin':str(i),'name':'Turbo','direction':'LONG','scope':'XAU/USD','reasons':['KO-Puffer ausreichend']} for i in range(count)], 'expiresAt':self.now+30000, **kwargs}
    def test_expiry_is_not_a_missing_product_evidence_claim(self):
        state,_=transition(None,self.checked(),self.now)
        expired={'products': [], 'expiresAt': self.now+31000, 'expiryOnly': True,
                 'reasons': ['Zeitfenster der letzten Markt- und Produktprüfung abgelaufen']}
        state,message=transition(state,expired,self.now+31000)
        self.assertEqual(state['products'], [])
        self.assertFalse(state['notified'])
        self.assertIn('wird erneuert', message['title'])
        self.assertIn('im Hintergrund', message['body'])
        self.assertNotIn('Screenshot', message['body'])
        self.assertIsNone(transition(state,expired,self.now+32000)[1])

    def test_real_product_gap_still_requests_evidence(self):
        state,_=transition(None,self.checked(),self.now)
        _,message=transition(state,self.checked(0,reasons=['KO-Nachweis fehlt']),self.now+1000)
        self.assertIn('Klärung erforderlich', message['title'])
        self.assertIn('Screenshot', message['body'])

    def test_python_to_shared_js_runtime(self):
        checked=evaluate({'products': [], 'capturedAt': int(time.time()*1000)})
        self.assertEqual(checked['products'],[])

    def test_only_internal_quote_map_reaches_verifier(self):
        import json
        from unittest.mock import patch
        from types import SimpleNamespace
        payload={'products': [], 'rankingPolicy': {'untrusted': True}, 'quotes': {'untrusted': {'approved': True}}}
        with patch('product_push.evaluator_runtime.run', return_value=SimpleNamespace(stdout='{}')) as run:
            evaluate(payload)
            self.assertEqual(json.loads(run.call_args.kwargs['input'])['quotes'], {})
            self.assertIsNone(json.loads(run.call_args.kwargs['input'])['rankingPolicy'])
            evaluate(payload, ranking_policy={'id':'trusted'})
            self.assertEqual(json.loads(run.call_args.kwargs['input'])['rankingPolicy'], {'id':'trusted'})
            evaluate(payload, quotes={'verified-source': {'isin': 'example'}})
            self.assertIn('verified-source', json.loads(run.call_args.kwargs['input'])['quotes'])
        self.assertIn('untrusted', payload['quotes'])

    def test_invalid_or_stale_selection_is_a_client_error_and_fails_closed(self):
        import subprocess
        from unittest.mock import patch
        for reason in ('Prüfanfrage veraltet','Produktliste ungültig'):
            failure=subprocess.CalledProcessError(1,'node',stderr=reason)
            with patch('product_push.evaluator_runtime.run', side_effect=failure):
                with self.assertRaisesRegex(ValueError,reason):
                    evaluate({'products': [], 'capturedAt': int(time.time()*1000)})
        failure=subprocess.CalledProcessError(1,'node',stderr='Unexpected internal failure')
        with patch('product_push.evaluator_runtime.run', side_effect=failure):
            with self.assertRaisesRegex(RuntimeError,'nicht unabhängig geprüft'):
                evaluate({'products': [], 'capturedAt': int(time.time()*1000)})

    def test_zero_one_two_three(self):
        for count in range(4):
            state, message=transition(None,self.checked(count),self.now)
            self.assertEqual(bool(message),bool(count))
            self.assertEqual(len(state['products']),count)
            if message:
                self.assertEqual(message['data']['kind'],'product-approved')
                self.assertIn('Prüfung',message['body'])
                self.assertIn('KO-Puffer',message['body'])
    def test_repeated_quotes_and_ranking_order_do_not_spam(self):
        state,_=transition(None,self.checked(2),self.now)
        update=self.checked(2);update['products'].reverse();update['products'][0]['price']=10.2
        state,message=transition(state,update,self.now+10000)
        self.assertIsNone(message);self.assertTrue(state['notified'])
    def test_change_includes_removed_product(self):
        state,_=transition(None,self.checked(2),self.now)
        state,message=transition(state,self.checked(1),self.now+1000)
        self.assertIn('Nicht mehr freigegeben: 1',message['body'])
    def test_withdrawal_only_once_and_no_initial_abstention_push(self):
        state,_=transition(None,self.checked(1),self.now)
        state,message=transition(state,self.checked(0,reasons=['Marktsignal neutral']),self.now+1000)
        self.assertEqual(message['data']['kind'],'product-withdrawn')
        self.assertIn('Marktsignal neutral',message['body'])
        self.assertIsNone(transition(state,self.checked(0),self.now+2000)[1])
        self.assertIsNone(transition(None,self.checked(0),self.now)[1])
    def test_expiry_withdraws_and_cooldown_prevents_flapping(self):
        state,_=transition(None,self.checked(),self.now)
        state,message=transition(state,self.checked(),self.now+31000)
        self.assertEqual(message['data']['kind'],'product-withdrawn')
        renewed=self.checked(expiresAt=self.now+90000)
        state,message=transition(state,renewed,self.now+40000)
        self.assertIsNone(message);self.assertFalse(state['notified'])
        self.assertIsNotNone(transition(state,self.checked(expiresAt=self.now+400000),self.now+300001)[1])

if __name__=='__main__':unittest.main()

