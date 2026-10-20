import copy
import unittest
from datetime import datetime,timezone
from unittest.mock import Mock
import list_corrections as c
import paper_simulation

class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.feed={'listOrigin':'degiro-screenshot','listUploadedAt':'2026-10-20T06:13:00Z','products':[{'isin':'US0378331005','direction':'LONG','currency':'EUR','quote':{'bid':1}}]}
        self.payload={'reviewed':True,'version':c.version(self.feed),'products':[{'isin':'US5949181045','direction':'SHORT','currency':'CHF','venue':'Societe Generale OTC'}],'observedMinute':'2026-10-20T08:12','imageReference':'test original'}
        self.now=datetime(2026,10,20,7,tzinfo=timezone.utc)
    def test_identity_replacement_keeps_provenance_not_quotes(self):
        before=copy.deepcopy(self.feed)
        out,venues=c.prepare(self.feed,self.payload,self.now)
        self.assertEqual(self.feed,before)
        self.assertEqual(out['listUploadedAt'],before['listUploadedAt'])
        self.assertNotIn('quote',out['products'][0])
        self.assertFalse(out['products'][0]['isinConfirmed'])
        self.assertFalse(venues[0]['executionConfirmed'])
        self.assertEqual(out['listCorrection']['previousProducts'],before['products'])
    def test_bnp_reviewed_row_is_recorded_and_legacy_correction_recovers(self):
        import broker_venue_evidence as b
        self.payload['products'][0].update(venue='BNP OTC',currency='EUR')
        out,venues=c.prepare(self.feed,self.payload,self.now)
        self.assertEqual(len(venues),1)
        self.assertEqual(venues[0]['venue'],'BNP OTC')
        self.assertEqual(out['listCorrection']['imageReference'],'test original')
        conn=Mock();conn.execute.return_value.fetchall.return_value=[]
        # Existing reviewed corrections predate the imageReference field. The
        # correction record remains a traceable original review reference.
        out['listCorrection'].pop('imageReference')
        got=b.attach(conn,out,self.now)['products'][0]
        proof=got['brokerVenueEvidence']
        self.assertTrue(b.confirmed(proof,got['isin'],'EUR',self.now.timestamp()*1000))
        self.assertEqual(proof['observedMinute'],self.payload['observedMinute'])
        self.assertEqual(proof['reviewedAt'],out['listCorrection']['at'])
        self.assertFalse(proof['executionConfirmed'])
        self.assertNotIn('bid',proof)
        self.assertNotIn('brokerVenueEvidence',b.attach(conn,out,self.now.replace(day=21))['products'][0])
        out.pop('listCorrection')
        self.assertNotIn('brokerVenueEvidence',b.attach(conn,out,self.now)['products'][0])

    def test_empty_reference_slots_are_ignored(self):
        self.feed['references']=[None, None]
        self.feed['fixedBarriers']=None
        self.payload['version']=c.version(self.feed)
        out,_=c.prepare(self.feed,self.payload,self.now)
        self.assertEqual(out['references'],[])
        self.assertEqual(out['fixedBarriers'],{})
    def test_concurrent_change_rejected(self):
        self.feed['products'].append({'isin':'US5949181045'})
        with self.assertRaises(ValueError):c.prepare(self.feed,self.payload,self.now)
    def test_duplicates_rejected(self):
        self.payload['products']*=2
        with self.assertRaises(ValueError):c.prepare(self.feed,self.payload,self.now)
    def test_unreviewed_rejected(self):
        self.payload['reviewed']=False
        with self.assertRaises(ValueError):c.prepare(self.feed,self.payload,self.now)
    def test_expired_evidence_rejected(self):
        self.payload['observedMinute']='2026-10-19T08:12'
        with self.assertRaises(ValueError):c.prepare(self.feed,self.payload,self.now)
    def test_stale_tab_cannot_undo_correction(self):
        out,_=c.prepare(self.feed,self.payload,self.now)
        conn=Mock();conn.execute.return_value.fetchone.return_value=(out,)
        result=paper_simulation.sync(conn,{'products':self.feed['products'],'listUploadedAt':self.feed['listUploadedAt'],'origin':'degiro-screenshot'})
        self.assertTrue(result['preserved'])
        self.assertEqual(conn.execute.call_count,1)

if __name__=='__main__':unittest.main()
