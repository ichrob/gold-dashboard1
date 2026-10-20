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
    def test_listing_survives_issuer_lookup_failure_without_approval(self):
        e=b.validate(self.payload,self.feed,self.now)
        p=dict(isin=self.isin,direction='SHORT',currency='CHF',brokerVenueEvidence=e)
        report=audit.examine(p,{},self.now.timestamp()*1000)
        self.assertEqual(report['brokerVenueEvidence'],e)
        self.assertIn('identity',report['missing'])
        self.assertFalse(report['tradeApproved'])
        self.assertFalse(report['degiroVerified'])

    def test_save_requires_active_list_and_stores_only_venue_evidence(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=(self.feed,)
        result=b.save(conn,dict(self.payload,bid=2,ask=3,eligible=True),self.now)
        self.assertTrue(result['ok'])
        self.assertNotIn('bid',result['evidence']);self.assertNotIn('eligible',result['evidence'])
        self.assertFalse(result['evidence']['executionConfirmed'])

    def detail_product(self):
        isin = 'DE000FG5GUP8'  # Additional checksum-valid product; synthetic display.
        q = dict(isin=isin, source='DEGIRO-Produktdetail', venue='Societe Generale OTC',
            currency='CHF', bid=2, ask=2.01, sourceTime='14/10/2026 20:13',
            brokerDisplayConfirmed=True, orderWindowVerified=False, orderSubmitted=False,
            executionGuaranteed=False, isExecutableQuote=False)
        p = dict(isin=isin, snapshot=dict(isin=isin, degiroDisplayedQuote=q))
        feed = dict(self.feed, products=[p])
        return p, feed

    def test_new_product_automatically_proves_display_without_manual_confirmation(self):
        p, feed = self.detail_product()
        conn=Mock();conn.execute.return_value.fetchall.return_value=[]
        got=b.attach(conn,feed,self.now)['products'][0]
        e=got['brokerVenueEvidence']
        self.assertEqual(e['kind'],'automatic-detail-screenshot')
        self.assertTrue(b.confirmed(e,p['isin'],'CHF',self.now.timestamp()*1000))
        self.assertFalse(e['executionConfirmed'])
        self.assertNotIn('bid',e)
        q=provider();q.update(isin=p['isin'],found=False)
        q['metadata'].update(currency='CHF',issuerExchangeCode='CBSW')
        self.assertIn('venue',audit.examine(p,q,self.now.timestamp()*1000)['missing'])
        report=audit.examine(got,q,self.now.timestamp()*1000)
        self.assertNotIn('venue',report['missing'])
        self.assertIn('quote',report['missing'])
        self.assertFalse(report['tradeApproved'])

    def test_automatic_never_infers_missing_identity_time_currency_or_execution(self):
        for changes in [dict(isin=self.isin),dict(source='issuer'),dict(venue='—'),
                        dict(currency='USD'),dict(bid=True),dict(ask=1),dict(ask=float('nan')),
                        dict(sourceTime=None),dict(sourceTime='13/10/2026 20:13'),
                        dict(sourceTime='14/10/2026 20:16'),dict(sourceTime='14/10/2026 20:15:30'),
                        dict(brokerDisplayConfirmed=False),dict(isExecutableQuote=True)]:
            p,feed=self.detail_product();p['snapshot']['degiroDisplayedQuote'].update(changes)
            self.assertIsNone(b.automatic(p,feed,self.now),changes)
        p,feed=self.detail_product()
        self.assertIsNone(b.automatic(p,feed,self.now.replace(hour=22)))
        p['snapshot']['isin']=self.isin
        self.assertIsNone(b.automatic(p,feed,self.now))
        p,feed=self.detail_product();feed['listOrigin']='legacy'
        self.assertIsNone(b.automatic(p,feed,self.now))

    def test_new_venue_and_currency_remain_bound_to_original_display(self):
        p,feed=self.detail_product()
        p['snapshot']['degiroDisplayedQuote'].update(venue='Tradegate',currency='EUR')
        e=b.automatic(p,feed,self.now)
        self.assertEqual(e['venue'],'Tradegate')
        self.assertTrue(b.confirmed(e,p['isin'],'EUR',self.now.timestamp()*1000))
        self.assertFalse(b.confirmed(e,p['isin'],'CHF',self.now.timestamp()*1000))

if __name__=='__main__':unittest.main()
