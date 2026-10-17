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

class CurrentQuoteTests(unittest.TestCase):
    def test_current_gold_not_fibonacci_target(self):
        c=m.context([dict(at=4,text='XAU/USD 15 Minuten. Gold notiert aktuell bei 4.200,50 Dollar. Fibonacci 61,8 Prozent bei 4100 Dollar.')],4)
        self.assertEqual(c['currentGoldQuote']['price'],4200.5)
        self.assertEqual(c['currentGoldQuote']['tolerance'],.005)
    def test_only_actual_quote_and_one_price(self):
        for text in ['Fibonacci 61,8 Prozent bei 4200 Dollar.', 'Wenn Gold steht bei 4200 Dollar, kaufen wir.', 'Gold is currently trading at 4200 USD. Gold is trading at 4300 USD.']:
            self.assertNotIn('currentGoldQuote',m.context([dict(at=0,text=text)],0))
    def test_english_quote_and_date_without_time(self):
        c=m.context([dict(at=0,text='2026-10-16. Gold is currently trading at 4,200.25 USD.')],0)
        self.assertEqual(c['currentGoldQuote']['price'],4200.25)
        self.assertEqual(c['analysisDay'],'2026-10-16')
        self.assertIsNone(c['analysisAt'])
