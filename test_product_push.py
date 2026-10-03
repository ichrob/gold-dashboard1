import unittest
from product_push import transition, evaluate
import time

class ProductPushTransitions(unittest.TestCase):
    now=1800000000000
    def checked(self, count=1, **kwargs):
        return {'products':[{'isin':str(i),'name':'Turbo','direction':'LONG','scope':'XAU/USD','reasons':['KO-Puffer ausreichend']} for i in range(count)], 'expiresAt':self.now+30000, **kwargs}
    def test_python_to_shared_js_runtime(self):
        checked=evaluate({'products': [], 'capturedAt': int(time.time()*1000)})
        self.assertEqual(checked['products'],[])

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
