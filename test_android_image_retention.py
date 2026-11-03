"""Retention regressions for temporary, value-less Android screenshots."""
import inspect
import os
import unittest
import uuid
from datetime import datetime, timezone, timedelta

import android_image_retention as retention
import android_list


class ImageRetentionUnitTests(unittest.TestCase):
    def test_no_broad_api_delete_or_live_backup_deletion(self):
        self.assertNotIn('DELETE FROM bob_android_list_images',
                         inspect.getsource(android_list.handle))
        sql=inspect.getsource(retention.sweep_once)
        self.assertIn("i.parsed_items IS NULL",sql)
        self.assertIn("replacement.token_hash=i.token_hash",sql)
        self.assertIn("replacement.created_at>i.created_at",sql)
        self.assertIn("'synced'",sql)
        self.assertIn("AT TIME ZONE 'Europe/Zurich'",sql)
        self.assertIn("FOR UPDATE OF i SKIP LOCKED",sql)
        self.assertIn("'48 hours'",sql)
        self.assertIn("LIMIT %s",sql)
        # Check only the executable SQL, not the explanatory docstring.
        db_sql=sql.split('rows=conn.execute(',1)[1].split(').fetchall()',1)[0]
        self.assertNotIn("VACUUM",db_sql.upper())

    def test_absent_image_table_has_no_mutation(self):
        class Query:
            def __init__(self,value): self.value=value
            def fetchone(self): return (self.value,)
        class DB:
            def __init__(self): self.queries=[];self.commits=0
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def execute(self,sql,args=()):
                self.queries.append((sql,args))
                if sql=="SELECT to_regclass('bob_android_list_images')":
                    return Query(None)
                raise AssertionError('Unexpected database query')
            def commit(self): self.commits+=1
        db=DB()
        result=retention.sweep_once(lambda:db)
        self.assertEqual(result['removed'],0)
        self.assertIsNone(result['physicalBytesFreed'])
        self.assertEqual(db.commits,0)
        self.assertEqual(len(db.queries),1)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'Postgres integration needs isolated CI database')
class ImageRetentionPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.psycopg=psycopg
        self.dsn=os.environ['BOB_TEST_DATABASE_URL']
        self.schema='png_retention_'+uuid.uuid4().hex
        with psycopg.connect(self.dsn,autocommit=True) as db:
            db.execute('CREATE SCHEMA '+self.schema)
        with self.connect() as conn:
            conn.execute("""CREATE TABLE bob_android_list_images(
                batch_id text PRIMARY KEY,
                token_hash text NOT NULL,
                created_at timestamptz NOT NULL,
                payload jsonb NOT NULL,
                import_receipt jsonb,
                parsed_items jsonb,
                processing_at timestamptz)""")
            conn.commit()
        self.now=datetime.now(timezone.utc)

    def connect(self):
        conn=self.psycopg.connect(self.dsn)
        conn.execute('SET search_path TO '+self.schema)
        return conn

    def tearDown(self):
        with self.psycopg.connect(self.dsn,autocommit=True) as conn:
            conn.execute('DROP SCHEMA '+self.schema+' CASCADE')

    def add(self,owner,hours,stage,*,parsed=False,pointer=False,processed_hours=None):
        from psycopg.types.json import Jsonb
        bid=uuid.uuid4().hex
        date=self.now-timedelta(hours=hours)
        img=({'at':date.isoformat(),'_bobPrivateImageRefV1':'a'*64}
             if pointer else {'at':date.isoformat(),'png':'safe-test-only-encoded'})
        receipt=dict(stage=stage,count=10 if parsed else 0)
        with self.connect() as conn:
            conn.execute("""INSERT INTO bob_android_list_images
                (batch_id,token_hash,created_at,payload,import_receipt,parsed_items,processing_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",(
                bid,owner,date,Jsonb({'images':[img]}),Jsonb(receipt),
                Jsonb([{'isin':str(i)} for i in range(10)]) if parsed else None,
                self.now-timedelta(hours=processed_hours) if processed_hours is not None else None))
            conn.commit()
        return bid

    def remaining(self):
        with self.connect() as conn:
            return {r[0] for r in conn.execute(
                'SELECT batch_id FROM bob_android_list_images').fetchall()}

    def test_only_expired_failed_replaced_same_device_same_day(self):
        from zoneinfo import ZoneInfo
        # Use local Swiss calendar day just as production must.
        day=(self.now-timedelta(hours=50)).astimezone(ZoneInfo('Europe/Zurich')).date()
        earlier=self.now-timedelta(hours=50)
        if earlier.hour>20:
            self.skipTest('Unstable calendar boundary for age fixture')
        old=self.add('devA',50,'waiting-memory')
        newer=self.add('devA',49,'synced',parsed=True)
        self.assertEqual((self.now-timedelta(hours=49)).astimezone(
            ZoneInfo('Europe/Zurich')).date(),day)
        foreign=self.add('devB',50,'read-failed')
        different_day=self.add('devC',70,'read-failed')
        different_day_success=self.add('devC',25,'synced',parsed=True)
        active=self.add('devD',3,'read-failed')
        active_success=self.add('devD',2,'synced',parsed=True)
        preserved=self.add('devE',50,'synced',parsed=True)
        pointer=self.add('devF',50,'read-failed',pointer=True)
        pointer_success=self.add('devF',49,'synced',parsed=True)
        result=retention.sweep_once(self.connect)
        self.assertEqual(result['status'],'expired-obsolete-only')
        self.assertEqual(result['removed'],1)
        self.assertGreater(result['logicalPayloadBytes'],0)
        self.assertIsNone(result['physicalBytesFreed'])
        remain=self.remaining()
        self.assertNotIn(old,remain)
        for bid in [newer,foreign,different_day,different_day_success,
                    active,active_success,preserved,pointer,pointer_success]:
            self.assertIn(bid,remain)

    def test_expiry_is_bounded_to_eight_per_run(self):
        # Build a same-day original and a verified, later one (different dates
        # in UTC may still be same in Switzerland).
        import zoneinfo
        date=(self.now-timedelta(hours=50)).astimezone(
            zoneinfo.ZoneInfo('Europe/Zurich')).date()
        if (self.now-timedelta(hours=49)).astimezone(
                zoneinfo.ZoneInfo('Europe/Zurich')).date()!=date:
            self.skipTest('Fixture spans Swiss midnight')
        old=[self.add('devA',50,'read-failed') for _ in range(10)]
        new=self.add('devA',49,'synced',parsed=True)
        first=retention.sweep_once(self.connect)
        second=retention.sweep_once(self.connect)
        self.assertEqual((first['removed'],second['removed']),(8,2))
        remain=self.remaining()
        self.assertEqual(remain,{new})
        self.assertTrue(all(bid not in remain for bid in old))


if __name__=='__main__':
    unittest.main()
