import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
import future_estimate as f
import background_push as b

class OvernightEvidenceTests(unittest.TestCase):
    def test_night_archive_keeps_original_ticks_every_thirty_seconds(self):
        source = datetime(2026,10,19,4,0,tzinfo=timezone.utc)
        tick = dict(at=source.isoformat(),price=4200,proxyKind='gold-api-spot',underlying='XAU/USD',contract=f.CONTRACT)
        event=Mock();event.wait.side_effect=InterruptedError('end test loop')
        store=Mock(return_value={'ok':True})
        self.assertEqual(b.degiro_poll_seconds(source.timestamp()*1000),300)
        with patch.object(f,'_storage_loaded',True),patch.object(f,'_active_until',1000),patch.object(f.time,'monotonic',return_value=100),patch.object(f.background_push,'gold_weekend_seconds_remaining',return_value=0),patch.object(f,'fetch_spot_tick',return_value=tick),patch.object(f,'record_spot_tick') as record,patch.object(f.bob_market_store,'request',store),patch.object(f.threading,'Event',return_value=event):
            with self.assertRaises(InterruptedError):f._collect()
        record.assert_called_once_with(tick)
        store.assert_called_once_with('write',dict(at=tick['at'],price=4200,symbol='XAU',currency='USD'))
        event.wait.assert_called_once_with(30)

    def test_weekend_never_fetches_original_quotes(self):
        event=Mock();event.wait.side_effect=InterruptedError()
        with patch.object(f.background_push,'gold_weekend_seconds_remaining',return_value=3600),patch.object(f,'fetch_spot_tick') as fetch,patch.object(f.threading,'Event',return_value=event):
            with self.assertRaises(InterruptedError):f._collect()
        fetch.assert_not_called();event.wait.assert_called_once_with(3600)
