import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import weekend_archive as w

class WeekendArchiveTests(unittest.TestCase):
    def test_cards_eligibility(self):
        now=datetime.now(timezone.utc)
        at=now.isoformat()
        self.assertIsNotNone(w.valid('spot',dict(price=4100.,at=at,symbol='XAU/USD')))
        self.assertIsNone(w.valid('spot',dict(price=4100.,at=at,symbol='GC=F')))
        self.assertIsNone(w.valid('spot',dict(price=4100.,at=(now-timedelta(days=8)).isoformat(),symbol='XAU/USD')))
    def test_chart_identity_and_candle_close(self):
        now=datetime.now(timezone.utc)
        step=900000
        end=(int(now.timestamp()*1000)//step)*step
        bars=[dict(openTime=end-step*2,open=4100.,high=4103.,low=4098.,close=4101.,isOpen=False,instrument='XAU/USD'),
              dict(openTime=end-step,open=4101.,high=4104.,low=4099.,close=4102.,isOpen=False,instrument='XAU/USD')]
        data=dict(at=datetime.fromtimestamp(end/1000,timezone.utc).isoformat(),bars=bars)
        self.assertIsNotNone(w.valid('chart:15m',data))
        self.assertIsNone(w.valid('chart:15m',dict(data,bars=[dict(bars[0],isOpen=True),bars[1]])))
    def test_preserve_timestamps(self):
        at=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        bundle={'spots':dict(xaus=4100.,spot_price_as_of=at,primary='Gold API'),'history':{'bars_by_tf':{}}}
        data=w.collect_items(bundle,{'cfd':dict(price=4102.,at=at,kind='cfd')})
        self.assertEqual(data['spot']['at'],at)
        self.assertEqual(data['cfd']['at'],at)
        self.assertFalse(any(k.startswith('chart:') for k in data))
    @unittest.skipUnless(__import__('os').environ.get('BOB_TEST_DATABASE_URL'),'Postgres integration')
    def test_persists_last_values_across_connections(self):
        import os,psycopg
        at=(datetime.now(timezone.utc)-timedelta(minutes=2))
        current=dict(price=4100.,at=at.isoformat(),symbol='XAU/USD')
        old=dict(price=3000.,at=(at-timedelta(minutes=5)).isoformat(),symbol='XAU/USD')
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            w.init(conn);w.handle(conn,'write',{'items':{'spot':current}})
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            w.handle(conn,'write',{'items':{'spot':old}})
            card=w.handle(conn,'read',{})['cards']['spot']
            self.assertEqual(card['price'],4100.)
            self.assertFalse(card['realtimeCfd'])
            self.assertEqual(card['at'],at.isoformat())
            conn.execute("DELETE FROM bob_weekend_archive WHERE data_key='spot'")
if __name__=='__main__':unittest.main()
