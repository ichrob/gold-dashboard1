import os
import time
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import bob_market_store as store
import future_estimate as future
import future_analysis as analysis
from urllib.error import HTTPError

class MarketStoreTests(unittest.TestCase):
 def point(self,at,price=4100):return dict(symbol='XAU',currency='USD',at=at.isoformat(),price=price)
 def test_restart_restore_keeps_source_time_and_stale_quotes_blocked(self):
  now=datetime.now(timezone.utc);old=now-timedelta(minutes=20)
  with patch.object(future,'_spot_ticks',[]):
   future.restore_spot_observations([self.point(old)],now)
   self.assertEqual(future._spot_ticks[0]['at'],old.isoformat())
   self.assertFalse(future.calculate(dict(contract='GCZ26',underlyingAt=old.isoformat(),underlyingPriceUsd=4190),future._spot_ticks,now,'gold-api-spot')['available'])
   future.restore_spot_observations([self.point(old)],now)
   self.assertEqual(len(future._spot_ticks),1)
   with self.assertRaises(ValueError):future.restore_spot_observations([self.point(old,4101)],now)
   self.assertEqual(future._spot_ticks[0]['price'],4100)
 def test_invalid_history_cannot_be_imported(self):
  now=datetime.now(timezone.utc)
  for p in (self.point(now+timedelta(seconds=1)),self.point(now-timedelta(hours=2)),dict(self.point(now),symbol='GCZ26'),dict(self.point(now),price=True),dict(self.point(now),at='2026-10-01T12:00:00')):
   with patch.object(future,'_spot_ticks',[]):
    with self.assertRaises((ValueError,TypeError)):future.restore_spot_observations([p],now)
    self.assertFalse(future._spot_ticks)
 def test_rate_limit_backoff_and_retry_after(self):
  e=HTTPError('https://example.test',429,'limited',{},None)
  self.assertGreaterEqual(analysis.retry_delay(e,1),300)
  e.headers={'Retry-After':'1200'}
  self.assertEqual(analysis.retry_delay(e,1),1200)
  e.headers={'Retry-After':'bad'}
  self.assertGreaterEqual(analysis.retry_delay(e,1),300)
  self.assertEqual(analysis.retry_delay(OSError(),20),1800)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class PostgresMarketTests(unittest.TestCase):
 def test_frozen_future_prediction_survives_connections_and_matches_only_later_truth_once(self):
  import psycopg
  import bob_validation_store as v
  dsn=os.environ['BOB_TEST_DATABASE_URL'];now=datetime.now(timezone.utc)
  at=now-timedelta(seconds=1);ref=at-timedelta(seconds=120)
  p=dict(key=v.KEY,type='prediction',at=at.isoformat(),referenceAt=ref.isoformat(),value=4200)
  t=dict(key=v.KEY,type='truth',at=at.isoformat(),value=4198)
  with psycopg.connect(dsn) as conn:
   v.init(conn);v.handle(conn,'write',{'events':[p]})
  with psycopg.connect(dsn) as conn:
   v.handle(conn,'write',{'events':[dict(p,value=4300),t]})
  with psycopg.connect(dsn) as conn:
   rows=v.handle(conn,'read',{})['pairs'];pair=next(x for x in rows if x['truthAt']==at.isoformat())
   self.assertEqual(pair['prediction'],4200);self.assertEqual(pair['truth'],4198)
   again=v.handle(conn,'write',{'events':[t]})['pairs']
   self.assertEqual(sum(x['truthAt']==at.isoformat() for x in again),1)
  with psycopg.connect(dsn) as conn:
   with self.assertRaises(ValueError):v.handle(conn,'write',{'events':[dict(t,value=4197)]})
   conn.rollback()
  # A prediction submitted after truth was already archived cannot validate.
  late=now-timedelta(seconds=20)
  truth=dict(t,at=late.isoformat())
  pred=dict(p,at=late.isoformat(),referenceAt=(late-timedelta(seconds=120)).isoformat())
  with psycopg.connect(dsn) as conn:
   v.handle(conn,'write',{'events':[truth]})
  with psycopg.connect(dsn) as conn:
   v.handle(conn,'write',{'events':[pred]})
   self.assertFalse(any(x['truthAt']==late.isoformat() for x in v.handle(conn,'read',{})['pairs']))
   conn.execute('DELETE FROM bob_future_predictions WHERE quote_at IN (%s,%s)',(at,late))
   conn.execute('DELETE FROM bob_future_truths WHERE quote_at IN (%s,%s)',(at,late))

 def test_two_connections_preserve_timestamp_and_reject_rewrites(self):
  import psycopg
  dsn=os.environ['BOB_TEST_DATABASE_URL'];now=datetime.now(timezone.utc)
  p=dict(symbol='XAU',currency='USD',at=now.isoformat(),price=4160.25)
  with psycopg.connect(dsn) as conn:
   store.init(conn);self.assertTrue(store.handle(conn,'write',p)['ok'])
  with psycopg.connect(dsn) as conn:
   saved=store.handle(conn,'read',{})['observations']
   self.assertIn(p,saved)
   self.assertTrue(store.handle(conn,'write',p)['ok'])
  with psycopg.connect(dsn) as conn:
   with self.assertRaises(ValueError):store.handle(conn,'write',dict(p,price=4161.25))
   conn.rollback()
  with psycopg.connect(dsn) as conn:
   self.assertIn(p,store.handle(conn,'read',{})['observations'])
   conn.execute('DELETE FROM bob_spot_observations WHERE stream=%s AND quote_at=%s',(store.STREAM,now))

if __name__=='__main__':unittest.main()
