import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import android_observations as a

NOW=datetime(2026,10,28,11,tzinfo=timezone.utc)
ISIN='DE000FD0S0G4'
DRAFT='\n'.join(['BOB APP-LESEENTWURF – NICHT VERIFIZIERT',f'ISIN: {ISIN}','Quelle: DEGIRO-App','Erfasst: 2026-10-28T10:59:00Z','Währung (Anzeige ungeprüft): EUR','Geld (Anzeige ungeprüft): 13,06','Brief (Anzeige ungeprüft): 13,07','Hinweis (Anzeige ungeprüft): Keine Aussage zur Handelbarkeit','Kein automatischer Handelsnachweis, keine Freigabe, keine Order.'])
def run():
    return dict(batchId='a'*32,revision=5,listUploadedAt=NOW.isoformat(),isins=[ISIN],results=[dict(isin=ISIN,attempts=2,draft=DRAFT,code='COMPLETE')],events=[dict(isin=ISIN,attempt=2,code='PARTIAL',at=NOW.isoformat())])

class MemoryDb:
    def __init__(self): self.rows={};self.sql=[];self.result=None
    def execute(self,sql,params=()):
        self.sql.append(sql)
        if 'SELECT payload FROM bob_android_read_runs WHERE' in sql:self.result=(self.rows[params[0]],) if params[0] in self.rows else None
        elif 'SELECT payload FROM bob_paper_products' in sql:self.result=({'products':[{'isin':ISIN}]},)
        elif 'INSERT INTO bob_android_read_runs' in sql:self.rows.setdefault(params[0],json.loads(params[1]))
        else: raise AssertionError(sql)
        return self
    def fetchone(self):return self.result

class AndroidObservations(unittest.TestCase):
    def test_app_version_is_optional_bounded_and_survives_private_status(self):
        self.assertIsNone(a.prepare(run(),{},NOW)['appVersionCode'])
        payload=run();payload['appVersionCode']=10210
        saved=a.prepare(payload,{},NOW)
        class StatusDb:
            def execute(self,*args):return self
            def fetchall(self):return [(saved,)]
        self.assertEqual(a.status(StatusDb())['runs'][0]['appVersionCode'],10210)
        for bad in [True,0,-1,2100000001,'10210',{}]:
            payload['appVersionCode']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):a.prepare(payload,{},NOW)
    def test_partial_is_recomputed_and_cannot_be_promoted(self):
        r=a.prepare(run(),{'products':[{'isin':ISIN}]},NOW)
        self.assertEqual(r['results'][0]['code'],'PARTIAL')
        obs=r['results'][0]['observation']
        self.assertIn('Hebel',obs['missingFields'])
        self.assertFalse(obs['verified']);self.assertFalse(obs['tradeApproved']);self.assertFalse(obs['executable']);self.assertIsNone(obs['sourceTime'])
        self.assertTrue(r['results'][0]['matchedCurrentList'])
        self.assertFalse(a.prepare(run(),{},NOW)['results'][0]['matchedCurrentList'])
    def test_bad_product_time_unknown_field_and_crossed_quotes_rejected(self):
        for draft in [DRAFT.replace(ISIN,'DE000FG77MY4'),DRAFT+'\nPassword: secret',DRAFT.replace('13,06','14,06'),DRAFT.replace('10:59:00Z','10:59:00'),DRAFT.replace('2026-10-28T10','2026-10-29T10')]:
            with self.subTest(draft=draft),self.assertRaises(ValueError):a.parse_draft(draft,ISIN,NOW)
    def test_late_delivery_preserves_historical_evidence_without_freshness(self):
        old=DRAFT.replace('2026-10-28T10','2026-10-20T10')
        observation=a.parse_draft(old,ISIN,NOW)
        self.assertTrue(observation['staleAtReceipt'])
        self.assertFalse(observation['executable'])
        self.assertIsNone(observation['sourceTime'])
    def test_duplicate_ids_results_and_bad_events_rejected(self):
        for key,value in [('isins',[ISIN,ISIN]),('results',run()['results']*2),('events',[{'code':'unknown'}]),('revision',True)]:
            r=run();r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.prepare(r,{},NOW)
    def test_idempotence_and_resume_versions_keep_both_results(self):
        db=MemoryDb();original=a.prepare
        with patch.object(a,'prepare',side_effect=lambda p,f:original(p,f,NOW)):
            payload={'action':'save','run':run()}
            first=a.handle(db,payload);self.assertTrue(first['saved']);self.assertEqual(first['revision'],5)
            self.assertTrue(a.handle(db,payload)['duplicate']);self.assertEqual(len(db.rows),1)
            changed=copy.deepcopy(payload);changed['run']['results'][0]['attempts']=1
            with self.assertRaises(ValueError):a.handle(db,changed)
            changed['run']['revision']=6
            a.handle(db,changed);self.assertEqual(len(db.rows),2)
        self.assertFalse(any('UPDATE bob_paper' in s or 'INSERT INTO bob_paper' in s for s in db.sql))
    def test_invalid_shape_does_not_crash(self):
        for value in [[],{'action':'save','run':[]},{'action':'save','run':{'batchId':[]}}]:
            with self.assertRaises(ValueError):a.handle(MemoryDb(),value)

if __name__=='__main__':unittest.main()

class AndroidObservationDatabase(unittest.TestCase):
    def test_postgres_roundtrip_and_read_only_diagnosis(self):
        import os
        url=os.environ.get('BOB_TEST_DATABASE_URL')
        if not url:self.skipTest('CI PostgreSQL not configured')
        import psycopg
        import uuid
        with psycopg.connect(url) as conn:
            try:
                schema='android_reader_'+uuid.uuid4().hex
                conn.execute('CREATE SCHEMA '+schema)
                conn.execute('SET LOCAL search_path TO '+schema)
                a.init(conn)
                conn.execute('CREATE TABLE bob_paper_products(id INT PRIMARY KEY,payload JSONB)')
                conn.execute('INSERT INTO bob_paper_products VALUES(1,%s::jsonb)',(json.dumps({'products':[{'isin':ISIN}]}),))
                original=a.prepare
                with patch.object(a,'prepare',side_effect=lambda p,f:original(p,f,NOW)):
                    a.handle(conn,{'action':'save','run':run()})
                    self.assertTrue(a.handle(conn,{'action':'save','run':run()})['duplicate'])
                self.assertEqual(len(a.handle(conn,{'action':'read'})['runs']),1)
                status=a.status(conn)
                self.assertEqual(status['runs'][0]['results'][0]['code'],'PARTIAL')
                self.assertNotIn('13,06',json.dumps(status))
                self.assertEqual(conn.execute('SELECT payload FROM bob_paper_products').fetchone()[0],{'products':[{'isin':ISIN}]})
            finally:conn.rollback()
