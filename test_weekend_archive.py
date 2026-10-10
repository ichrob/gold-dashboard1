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

class WeekendObservationBackfillTests(unittest.TestCase):
    def test_sparse_spot_observations_are_labeled_and_no_empty_buckets_added(self):
        now=datetime.now(timezone.utc)
        step=900
        base=(int(now.timestamp())//step-4)*step
        rows=[(datetime.fromtimestamp(base+10,timezone.utc),4100.),
              (datetime.fromtimestamp(base+20,timezone.utc),4102.),
              (datetime.fromtimestamp(base+step*2+10,timezone.utc),4101.)]
        history=w.observation_bars(rows,['15m'],now=now.timestamp())
        candles=history['15m']
        self.assertEqual(len(candles),2)
        self.assertEqual(candles[0]['high'],4102.)
        self.assertTrue(candles[0]['observedOnly'])
        self.assertEqual(candles[0]['samples'],2)
        self.assertEqual(candles[1]['openTime']-candles[0]['openTime'],2*step*1000)

    def test_synthetic_cfd_cannot_be_mistaken_for_spot(self):
        now=datetime.now(timezone.utc)
        step=60000
        end=(int(now.timestamp()*1000)//step)*step
        bar=dict(open=4000.,high=4001.,low=3999.,close=4000.,isOpen=False,
                 instrument='GOLD-CFD',source='Investing.com')
        bars=[dict(bar,openTime=end-2*step),dict(bar,openTime=end-step)]
        q=dict(at=datetime.fromtimestamp(end/1000,timezone.utc).isoformat(),bars=bars)
        self.assertIsNotNone(w.valid('cfd-chart:1m',q))
        self.assertIsNone(w.valid('chart:1m',q))
        self.assertIsNone(w.valid('cfd-chart:1m',dict(q,bars=[dict(bars[0],instrument='XAU/USD'),bars[1]])))


class WeekendRestartHistoryTests(unittest.TestCase):
    def test_merge_retains_pre_restart_candles_without_filling_missing_intervals(self):
        now=datetime.now(timezone.utc)
        minute=60000
        end=int(now.timestamp()*1000)//minute*minute
        def bar(offset,price):
            return dict(openTime=end-offset*minute,open=price,high=price+1,
                low=price-1,close=price,isOpen=False,instrument='GOLD-CFD',
                source='Investing.com · gespeicherte Stichproben',samples=2)
        earlier=[bar(7,4000),bar(5,4002)]
        later=[bar(2,4005),bar(1,4008)]
        merged=w.merge_chart_history({'bars':earlier},{'bars':later,'at':now.isoformat()})
        self.assertEqual([b['openTime'] for b in merged['bars']],
            [b['openTime'] for b in earlier+later])
        self.assertIsNotNone(w.valid('cfd-chart:1m',
            dict(merged,at=datetime.fromtimestamp(end/1000,timezone.utc).isoformat())))
        self.assertEqual(len(merged['bars']),4)

    @unittest.skipUnless(__import__('os').environ.get('BOB_TEST_DATABASE_URL'),'Postgres integration')
    def test_db_preserves_chart_across_separate_connections(self):
        import os,psycopg
        minute=60000
        end=int(datetime.now(timezone.utc).timestamp()*1000)//minute*minute
        def bars(offsets):
            return [dict(openTime=end-offset*minute,open=4000.,high=4001.,
                low=3999.,close=4000.,isOpen=False,instrument='GOLD-CFD',
                source='Investing.com · saved samples',samples=2) for offset in offsets]
        a={'at':datetime.fromtimestamp((end-4*minute)/1000,timezone.utc).isoformat(),'bars':bars([6,5])}
        b={'at':datetime.fromtimestamp(end/1000,timezone.utc).isoformat(),'bars':bars([2,1])}
        # a's last candle closes at end-4 minutes; b's closes at end.
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            w.init(conn)
            w.handle(conn,'write',{'items':{'cfd-chart:1m':a}})
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            w.handle(conn,'write',{'items':{'cfd-chart:1m':b}})
            self.assertEqual(len(w.handle(conn,'read',{})['cfdHistory']['1m']),4)
            conn.execute("DELETE FROM bob_weekend_archive WHERE data_key='cfd-chart:1m'")
