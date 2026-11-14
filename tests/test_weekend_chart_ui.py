"""Regression checks for the existing Bob.html weekend chart path.

These checks deliberately avoid trading logic and external data providers.
"""
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "Bob.html"


class WeekendChartUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HTML.read_text(encoding="utf-8")

    def test_weekend_archive_restores_historical_timeframes(self):
        self.assertIn("restoreServerWeekendArchive()", self.source)
        self.assertIn("if(Object.keys(history).length)chartHistory=history", self.source)
        self.assertIn("['1m','5m','15m','30m','1h','4h']", self.source)

    def test_weekend_chart_explicitly_historical(self):
        self.assertIn("Markt geschlossen · Letzter bestätigter Verlauf bis ", self.source)
        self.assertIn("Historische Kurse, nicht live", self.source)

    def test_chart_excludes_marked_synthetic_and_open_candles(self):
        self.assertIn("!b.isOpen&&!b.providerIsOpen&&!b.synthetic&&!b.estimated", self.source)

    def test_click_keeps_source_time_and_close(self):
        self.assertIn("addEventListener('click',selectChartPoint)", self.source)
        self.assertIn("Schlusskurs: '+priceLabel(Number(chosen.close))", self.source)
        self.assertIn("timeZone:'Europe/Zurich'", self.source)

    def test_history_survives_failed_live_fetch(self):
        self.assertIn("if(!Object.keys(chartHistory).length)chartHistory={};C=[];draw();", self.source)


if __name__ == "__main__":
    unittest.main()
