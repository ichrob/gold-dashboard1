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

class VenueContinuityTests(BrokerVenueTests):
    def test_identity_only_proof_does_not_require_or_supply_prices(self):
        p,feed=self.detail_product()
        q=p['snapshot'].pop('degiroDisplayedQuote');q.pop('bid');q.pop('ask')
        p['snapshot']['degiroVenueEvidence']=q
        record=b.automatic(p,feed,self.now)
        self.assertTrue(b.confirmed(record,p['isin'],'CHF',self.now.timestamp()*1000))
        self.assertNotIn('bid',record)
        for field,value in [('isin',self.isin),('currency','USD'),('sourceTime',None),('isExecutableQuote',True)]:
            copy_p=copy.deepcopy(p);copy_p['snapshot']['degiroVenueEvidence'][field]=value
            self.assertIsNone(b.automatic(copy_p,feed,self.now))

    def test_old_generation_is_history_only_and_clock_is_unchanged(self):
        e=b.validate(self.payload,self.feed,self.now)
        conn=Mock();conn.execute.return_value.fetchall.return_value=[(self.isin,e)]
        newer=dict(self.feed,listUploadedAt='new',products=[dict(isin=self.isin,currency='CHF')])
        next_day=self.now+timedelta(days=1)
        product=b.attach(conn,newer,next_day)['products'][0]
        state=b.assessment(product,'CHF',next_day.timestamp()*1000)
        self.assertEqual(state['state'],'historical')
        self.assertFalse(state['current']);self.assertFalse(state['executionConfirmed'])
        self.assertEqual(state['historicalEvidence']['observedMinute'],e['observedMinute'])
        self.assertNotIn('brokerVenueEvidence',product)
        self.assertEqual(b.assessment(product,'EUR',next_day.timestamp()*1000)['state'],'missing')
        self.assertEqual(b.assessment(dict(product,isin='DE000FG8NHQ3'),'CHF',next_day.timestamp()*1000)['state'],'missing')

    def test_replacement_archives_expired_snapshot_without_redating(self):
        p,feed=self.detail_product();conn=Mock()
        b.archive_feed(conn,feed,self.now+timedelta(days=1))
        args=conn.execute.call_args[0][1]
        self.assertEqual(args[3],'2026-10-14T20:13')
        self.assertIn('2026-10-14T22:00',args[4])

    def test_new_detail_revalidates_history(self):
        p,feed=self.detail_product();conn=Mock()
        conn.execute.return_value.fetchall.return_value=[]
        product=b.attach(conn,feed,self.now)['products'][0]
        state=b.assessment(product,'CHF',self.now.timestamp()*1000)
        self.assertEqual(state['state'],'current')
        later=self.now.replace(hour=22)
        self.assertEqual(b.assessment(product,'CHF',later.timestamp()*1000)['state'],'historical')

if __name__=='__main__':unittest.main()

import os
import time
@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'PostgreSQL integration')
class VenueDatabaseTests(unittest.TestCase):
    def test_history_survives_connection_and_list_replacement(self):
        import psycopg
        schema='venues_'+str(time.time_ns())
        now=datetime.fromisoformat('2026-10-14T20:15:00+02:00')
        isin='DE000FG14AV8'
        feed=dict(listOrigin='degiro-screenshot',listUploadedAt='old',products=[dict(isin=isin,currency='CHF')])
        record=b.validate(dict(isin=isin,venue=b.VENUE,currency='CHF',observedMinute='2026-10-14T20:13',imageReference='fixture',reviewed=True),feed,now)
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema);conn.execute('SET search_path TO '+schema)
            b.init(conn);b.archive(conn,record,now)
            older=dict(record,observedMinute='2026-10-14T20:10')
            b.archive(conn,older,now)
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('SET search_path TO '+schema)
            new=dict(feed,listUploadedAt='new')
            next_day=now+timedelta(days=1)
            p=b.attach(conn,new,next_day)['products'][0]
            state=b.assessment(p,'CHF',next_day.timestamp()*1000)
            self.assertEqual(state['state'],'historical');self.assertFalse(state['current'])
            self.assertEqual(state['historicalEvidence']['observedMinute'],record['observedMinute'])
            self.assertFalse(state['executionConfirmed'])
            conn.execute('DROP SCHEMA '+schema+' CASCADE')
