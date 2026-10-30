"""Shared consumer failover preserves source clocks and strict evidence gates."""
import copy
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import server
import spot_data
import xaus_spot
import market_cards
import sg_quotes


class SharedFallbackTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.at = (self.now-timedelta(seconds=10)).isoformat()

    def test_all_generic_spot_consumers_share_warm_backup_without_io(self):
        q = dict(price=4100., at=self.at, source='XAUS · XAU/USD Spot',
                 observed=True, instrument='XAU/USD')
        with patch.object(spot_data, 'primary', side_effect=ValueError('offline')), \
             patch.object(xaus_spot, '_quote', q), \
             patch.object(xaus_spot, 'current') as fetch:
            selected = spot_data.current()
            card = market_cards.fetch_spot()
            self.assertTrue(selected['backupActive'])
            self.assertEqual(selected['proxyKind'], 'xaus-spot')
            self.assertEqual(card['source'], q['source'])
            self.assertEqual(card['at'], self.at)
            selected['price'] = 1
            self.assertEqual(spot_data.current()['price'], 4100.)
            fetch.assert_not_called()

    def test_original_wins_and_stale_backup_fails_without_new_clock(self):
        with patch.object(spot_data, 'primary', return_value={'price':4200}) as primary, \
             patch.object(xaus_spot, 'peek') as peek:
            self.assertEqual(spot_data.current()['price'], 4200)
            peek.assert_not_called()
        for seconds in (61, -10):
            with patch.object(spot_data, 'primary', side_effect=ValueError('offline')), \
                 patch.object(xaus_spot, '_quote', dict(price=4100, at=(self.now-timedelta(seconds=seconds)).isoformat())):
                with self.assertRaises(ValueError): spot_data.current()

    def test_backup_read_never_waits_for_inflight_refresh(self):
        with xaus_spot._lock:
            self.assertIsNone(xaus_spot.peek())

    def test_fx_shared_with_models_and_original_time_reaches_legacy_consumers(self):
        data = dict(result='success', base='USD', rates={'EUR':.9,'CHF':.8},
            data_updated_at=self.at, effective_at={'EUR':self.at, 'CHF':self.at},
            sources={'EUR':'live','CHF':'live'}, market_session='open',
            provider='dated backup', backupActive=True)
        before = copy.deepcopy(data)
        with patch.object(sg_quotes, 'market_input', return_value=data) as fetch, \
             patch.object(server, '_fx_cache', {'EUR':None,'CHF':None}), \
             patch.object(server, '_fx_meta', {}):
            self.assertEqual(server.shared_fx_snapshot(), (.9,.8,[]))
            fetch.assert_called_once_with('fx')
            for c in ('EUR','CHF'):
                meta = server._fx_meta[c]
                self.assertEqual(meta['fetchedAt'], self.at)
                self.assertEqual(meta['sourceAt'], self.at)
                self.assertTrue(meta['backupActive'])
            data['data_updated_at'] = (self.now-timedelta(seconds=120)).isoformat()
            _, _, errors = server.shared_fx_snapshot()
            self.assertTrue(errors)
            self.assertEqual(server._fx_meta['EUR']['sourceAt'], self.at)
            self.assertTrue(server._fx_meta['EUR']['error'])
        data['data_updated_at'] = self.at
        self.assertEqual(data, before)

    def test_confirmed_five_minute_bars_recover_hour_without_inventing_ohlc(self):
        step = 300000
        end = int(self.now.timestamp()//3600)*3600000
        rows = [dict(openTime=end-110*3600000+i*step,open=4100,high=4102,
                     low=4098,close=4101,instrument='XAU/USD',source='test',
                     estimated=False,isOpen=False,providerIsOpen=False)
                for i in range(110*12)]
        with patch.object(server, '_technical_history', {'5m':rows}), \
             patch('technical_candles.fetch', return_value=[]), \
             patch.object(server, 'fetch_json') as network:
            out = server.fetch_technical_history('1h', '3mo')
            self.assertEqual(len(out), 110)
            self.assertEqual(out[-1]['openTime'], end-3600000)
            self.assertEqual(out[-1]['high'],4102)
            self.assertFalse(out[-1]['estimated'])
            self.assertEqual(out[-1]['source'], 'test')
            network.assert_not_called()
        self.assertEqual(server.aggregate_bars(rows[:11],60), [])

    def test_all_timeframes_bypass_bundle_ttl_when_recovery_has_newer_evidence(self):
        now = self.now.timestamp()
        for tf, minutes in server.technical_candles.MINUTES.items():
            end = int(now//(minutes*60))*minutes*60000
            row = dict(openTime=end-minutes*60000, instrument='XAU/USD',isOpen=False)
            old = dict(row,openTime=end-2*minutes*60000)
            bundle = {'spots':{'spot_price_as_of':self.at}, 'history':{'bars_by_tf':{tf:[old]}}}
            with self.subTest(tf=tf), patch.object(server,'_live_cache',bundle), \
                 patch.object(server,'_live_cache_at',now-1), \
                 patch.object(server,'_technical_history',{tf:[row]}):
                self.assertFalse(server.live_cache_reusable(now))

    def test_fx_standby_is_ready_without_a_second_backup_network_call(self):
        import fx_data
        from unittest.mock import Mock
        data = dict(result='success', base='USD', rates={'EUR':.9,'CHF':.8},
            data_updated_at=self.at, effective_at={'EUR':self.at, 'CHF':self.at},
            sources={'EUR':'live','CHF':'live'}, market_session='open',
            source='live', provider='dated backup', backupActive=True)
        with patch.object(fx_data, '_standby', None), \
             patch.object(fx_data, '_standby_attempted', float('-inf')), \
             patch.object(fx_data, 'backup', return_value=data) as backup:
            fx_data.warm_backup()
            fx_data.warm_backup()
            self.assertEqual(backup.call_count, 1)
            original = copy.deepcopy(data)
            fetch = Mock(side_effect=OSError('primary offline'))
            result = fx_data.fetch_rates(fetch, now=self.now)
            self.assertTrue(result['backupActive'])
            self.assertEqual(result['data_updated_at'], self.at)
            self.assertEqual(backup.call_count, 1)
            self.assertEqual(data, original)
            with patch.object(fx_data, '_standby', dict(data,
                    data_updated_at=(self.now-timedelta(seconds=91)).isoformat())):
                self.assertIsNone(fx_data.peek_backup(self.now))
