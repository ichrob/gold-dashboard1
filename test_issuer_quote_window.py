import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import issuer_quote_window as q

Z=ZoneInfo("Europe/Zurich")
class SGSessionTests(unittest.TestCase):
    def test_weekday_boundaries_and_dst(self):
        for at,paused in ((datetime(2026,11,2,7,59,tzinfo=Z),True),
                          (datetime(2026,11,2,8,0,tzinfo=Z),False),
                          (datetime(2026,11,2,21,59,tzinfo=Z),False),
                          (datetime(2026,11,2,22,0,tzinfo=Z),True),
                          (datetime(2026,11,1,12,0,tzinfo=Z),True),
                          (datetime(2026,7,6,8,0,tzinfo=Z),False)):
            with self.subTest(at=at):
                a=q.advisory(at.astimezone(timezone.utc))
                self.assertEqual(a['scheduledPause'],paused)
                self.assertFalse(a['marketOpenConfirmed'])
                self.assertFalse(a['quoteFresh'])
                self.assertFalse(a['holidayVerified'])
        self.assertTrue(q.advisory(datetime(2026,11,2,23,tzinfo=Z))['nextRoutineCheckAt'].startswith('2026-11-03T08:00'))
        self.assertTrue(q.advisory(datetime(2026,11,6,23,tzinfo=Z))['nextRoutineCheckAt'].startswith('2026-11-09T08:00'))
        with self.assertRaises(ValueError):
            q.advisory(datetime(2026,11,2,23))

    def test_only_known_sg_gold_quote_fields_are_deferred(self):
        now=datetime(2026,11,2,23,tzinfo=Z)
        requested=['Geld','Brief','Anzeigezeit','Hebel','KO-Schwelle','Basispreis','Bv','Währung']
        item={'isin':'DE000SX7PE82','name':'SG Gold Turbo BEST Open-End Call'}
        self.assertEqual(q.filter_handset_fields(requested,now,item,{}),
                         ['KO-Schwelle','Basispreis','Bv','Währung'])
        self.assertEqual(q.filter_handset_fields(requested,now,{'name':'BNP GOLD Mini Long'},{}),requested)
        self.assertEqual(q.filter_handset_fields(requested,now,{},{}),requested)
        self.assertEqual(q.filter_handset_fields(requested,datetime(2026,11,2,19,tzinfo=Z),item,{}),requested)
        # No new source timestamps, money values, market approvals, or mutable source snapshots.
        self.assertEqual(requested,['Geld','Brief','Anzeigezeit','Hebel','KO-Schwelle','Basispreis','Bv','Währung'])
        self.assertIn('societegenerale.ch',q.advisory(now)['sourceUrl'])

if __name__=='__main__':unittest.main()
