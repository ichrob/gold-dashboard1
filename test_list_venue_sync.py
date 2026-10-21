import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import broker_venue_evidence as b
import paper_simulation as sim

class ListVenueSyncTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(b.ZONE).replace(hour=12,minute=0,second=0,microsecond=0)
        self.upload=self.now.replace(hour=8).isoformat()
        self.isin='DE000FG14AV8'
        self.e=dict(version=1,isin=self.isin,venue='Societe Generale OTC',currency='CHF',
                    source='DEGIRO-Listenbild',complete=True,crossChecked=True,
                    isExecutableQuote=False,reference='synthetic-list.jpg',listUploadedAt=self.upload)
        self.p=dict(isin=self.isin,currency='CHF',listVenueEvidence=self.e)
        self.feed=dict(listOrigin='degiro-screenshot',listUploadedAt=self.upload,products=[self.p])
    def test_list_proof_survives_sync_and_reaches_report_without_quote(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=None
        with patch.object(sim.time,'time',return_value=self.now.timestamp()):
            sim.sync(conn,dict(origin='degiro-screenshot',listUploadedAt=self.upload,products=[self.p]))
        writes=[c.args for c in conn.execute.call_args_list if 'INSERT INTO bob_paper_products' in c.args[0]]
        saved=json.loads(writes[0][1][0])
        self.assertEqual(saved['products'][0]['listVenueEvidence'],self.e)
        conn.execute.return_value.fetchall.return_value=[]
        attached=b.attach(conn,saved,self.now)['products'][0]
        state=b.assessment(attached,'CHF',self.now.timestamp()*1000)
        self.assertTrue(state['current']);self.assertFalse(state['executionConfirmed'])
        self.assertEqual(state['evidence']['kind'],'automatic-list-screenshot')
        self.assertIsNone(state['evidence']['sourceTime'])
        self.assertNotIn('bid',state['evidence'])
    def test_conflicts_unchecked_and_foreign_generations_cannot_prove_venue(self):
        for changes in [dict(isin='DE000FG8NHQ3'),dict(currency='EUR'),dict(venue='Swiss DOTS'),
                        dict(crossChecked=False),dict(complete=False),dict(reference=''),
                        dict(listUploadedAt='different'),dict(isExecutableQuote=True)]:
            p=copy.deepcopy(self.p);p['listVenueEvidence'].update(changes)
            self.assertIsNone(b.automatic_list(p,self.feed,self.now),changes)
        self.assertIsNone(b.automatic_list(self.p,self.feed,self.now.replace(hour=22)))
        self.assertIsNone(b.automatic_list(self.p,self.feed,self.now+timedelta(days=1)))
    def test_archive_keeps_original_list_clock(self):
        conn=Mock();b.archive_feed(conn,self.feed,self.now+timedelta(days=1))
        row=conn.execute.call_args.args[1]
        self.assertEqual(row[3],self.now.replace(hour=8).strftime('%Y-%m-%dT%H:%M'))
