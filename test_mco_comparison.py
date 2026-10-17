import unittest
import mco_comparison as m
import youtube_research as y

class ContextTests(unittest.TestCase):
    def test_explicit_context_attached_to_level(self):
        rows=[dict(at=0,text='Stand: 17.10.2026 13:30 MESZ. XAU/USD im 15 Minuten Chart. Fibonacci 61,8 Prozent bei 4200 Dollar.')]
        c=y.extract_fibonacci_levels(rows)[0]['comparisonContext']
        self.assertEqual(c['analysisAt'],1792236600000)
        self.assertEqual(c['timeframe'],'15m');self.assertEqual(c['instrument'],'XAU/USD')
    def test_missing_timezone_and_mixed_instruments(self):
        c=m.context([dict(at=0,text='Stand: 17.10.2026 13:30. XAU/USD und Futures im 15 Minuten Chart.')],0)
        self.assertIsNone(c['analysisAt']);self.assertIsNone(c['instrument'])
    def test_conflicting_time_and_timeframe(self):
        c=m.context([dict(at=0,text='Stand: 2026-10-17 10:00 UTC. Stand: 2026-10-17 11:00 UTC. 15 Minuten und 1h XAUUSD.')],0)
        self.assertIsNone(c['analysisAt']);self.assertIsNone(c['timeframe'])
    def test_no_upload_or_subtitle_time_inference(self):
        c=m.context([dict(at=42,text='Heute Gold 61,8 Prozent bei 4200 Dollar.')],42)
        self.assertIsNone(c['analysisAt']);self.assertIsNone(c['instrument']);self.assertIsNone(c['timeframe'])
        self.assertIsNone(m.context([dict(at=0,text='Stand: 2026-10-17 10:00 UTC.')],200)['analysisAt'])
