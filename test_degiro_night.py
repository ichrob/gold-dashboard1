"""Regression checks for the user-confirmed DEGIRO time window.

Source-market and risk alerts remain separate: this schedule does not assert
that gold trading itself stops at 22:00 Zurich.
"""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
import background_push as b
import paper_simulation as p


class DegiroNightTests(unittest.TestCase):
    tz=ZoneInfo('Europe/Zurich')

    def at(self,day,hour,minute=0,month=10):
        return int(datetime(2026,month,day,hour,minute,tzinfo=self.tz).timestamp()*1000)

    def test_trade_and_coldstart_boundaries(self):
        self.assertEqual(b.degiro_session(self.at(12,7,29)), 'night')
        self.assertEqual(b.degiro_poll_seconds(self.at(12,7,29)),60)
        self.assertEqual(b.degiro_session(self.at(12,7,30)), 'preparation')
        self.assertEqual(b.degiro_poll_seconds(self.at(12,7,30)),30)
        self.assertFalse(b.degiro_entry_allowed(self.at(12,7,59)))
        self.assertTrue(b.degiro_entry_allowed(self.at(12,8)))
        self.assertTrue(b.degiro_entry_allowed(self.at(12,21,59)))
        self.assertFalse(b.degiro_entry_allowed(self.at(12,22)))
        self.assertEqual(b.degiro_poll_seconds(self.at(12,22)),300)
        self.assertEqual(b.degiro_poll_seconds(self.at(12,22),True),30)
        self.assertEqual(b.degiro_session(self.at(9,23)), 'weekend')
        self.assertEqual(b.degiro_session(self.at(26,7,30)), 'preparation')

    def test_paper_worker_does_not_run_in_night_or_preparation(self):
        with patch.object(b,'degiro_session',return_value='night'):
            with patch.object(p,'_thread',None),patch.object(p,'_bundle_ready') as event:
                p.enqueue({'spots':{'xaus':4200}},lambda:None)
                event.set.assert_not_called()
        with patch.object(b,'degiro_session',return_value='preparation'):
            with patch.object(p,'_thread',None),patch.object(p,'_bundle_ready') as event:
                p.enqueue({'spots':{'xaus':4200}},lambda:None)
                event.set.assert_not_called()


if __name__=='__main__':unittest.main()
