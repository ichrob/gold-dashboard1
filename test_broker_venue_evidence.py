import copy
import unittest
from datetime import datetime,timedelta
from unittest.mock import Mock
import broker_venue_evidence as b
import degiro_product_audit as audit
from test_degiro_product_audit import provider

class BrokerVenueTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.fromisoformat('2026-10-14T20:15:00+02:00')
        self.isin='DE000FG14AV8'
        self.feed=dict(listOrigin='degiro-screenshot',listUploadedAt='generation',products=[dict(isin=self.isin)])
        self.payload=dict(isin=self.isin,venue=b.VENUE,currency='CHF',observedMinute='2026-10-14T20:13',imageReference='owner image',reviewed=True)
    def test_screenshot_removes_only_venue_gap(self):
        e=b.validate(self.payload,self.feed,self.now)
        q=provider();q.update(isin=self.isin,currency='EUR',found=False)
        q['metadata'].update(currency='CHF',issuerExchangeCode='CBSW')
        p=dict(isin=self.isin,direction='SHORT',brokerVenueEvidence=e)
        r=audit.examine(p,q,self.now.timestamp()*1000)
        self.assertNotIn('venue',r['missing'])
        self.assertIn('quote',r['missing'])
        self.assertFalse(r['degiroVerified']);self.assertFalse(r['tradeApproved'])
        self.assertEqual(r['brokerVenueEvidence']['timePrecision'],'minute')
        p.pop('brokerVenueEvidence')
        self.assertIn('venue',audit.examine(p,q,self.now.timestamp()*1000)['missing'])
    def test_wrong_identity_currency_expired_future_and_missing_review(self):
        e=b.validate(self.payload,self.feed,self.now)
        for changes in [dict(isin='DE000FG8NHQ3'),dict(currency='EUR'),dict(venue='other'),dict(executionConfirmed=True)]:
            self.assertFalse(b.confirmed(dict(e,**changes),self.isin,'CHF',self.now.timestamp()*1000))
        self.assertFalse(b.confirmed(e,self.isin,'CHF',self.now.replace(hour=22).timestamp()*1000))
        for changes in [dict(reviewed=False),dict(isin='other'),dict(observedMinute='2026-10-15T20:13'),dict(observedMinute='2026-10-14T21:00'),dict(observedMinute='2026-10-14T20:13:00'),dict(imageReference='')]:
            with self.assertRaises(ValueError):b.validate(dict(self.payload,**changes),self.feed,self.now)
    def test_list_replacement_revokes_proof_and_client_cannot_inject(self):
        e=b.validate(self.payload,self.feed,self.now)
        conn=Mock();conn.execute.return_value.fetchall.return_value=[(self.isin,e)]
        attached=b.attach(conn,self.feed)
        self.assertEqual(attached['products'][0]['brokerVenueEvidence'],e)
        self.assertNotIn('brokerVenueEvidence',self.feed['products'][0])
        attached['listUploadedAt']='replacement'
        self.assertNotIn('brokerVenueEvidence',b.attach(conn,attached)['products'][0])
    def test_save_requires_active_list_and_stores_only_venue_evidence(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=(self.feed,)
        result=b.save(conn,dict(self.payload,bid=2,ask=3,eligible=True),self.now)
        self.assertTrue(result['ok'])
        self.assertNotIn('bid',result['evidence']);self.assertNotIn('eligible',result['evidence'])
        self.assertFalse(result['evidence']['executionConfirmed'])

if __name__=='__main__':unittest.main()
