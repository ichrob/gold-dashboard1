"""Regression for the DEGIRO/SnapTrade status separation; no broker requests."""
import unittest
from html.parser import HTMLParser
from degiro_sandbox_panel import PANEL


class _TagOrder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.closed_details = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('details', 'section'):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ('details', 'section'):
            assert self.stack and self.stack[-1] == tag, (tag, self.stack)
            self.stack.pop()
            if tag == 'details':
                self.closed_details += 1


class DegiroSnapTradeStatusPanelTests(unittest.TestCase):
    def test_separate_connected_snaptrade_from_unofficial_sdk(self):
        self.assertLess(PANEL.index('id="dgSnaptradeSyncStatus"'),
                        PANEL.index('id="dgOptionalSdk"'))
        self.assertIn('SnapTrade-Depotlesung aktuell bestätigt', PANEL)
        self.assertIn("data.code==='READ_OK'", PANEL)
        self.assertIn('data.fresh===true', PANEL)
        self.assertIn('nicht als aktuell bestätigt', PANEL)
        self.assertIn('keine orderfreigabe', PANEL.lower())

    def test_status_never_wakes_broker_or_leaks_snapshot_fields(self):
        self.assertIn("fetch('/api/snaptrade/status',{credentials:'same-origin',cache:'no-store'})", PANEL)
        self.assertEqual(PANEL.count("fetch('/api/snaptrade/status'"), 1)
        self.assertNotIn("fetch('/api/snaptrade/check'", PANEL)
        self.assertNotIn("fetch('/api/snaptrade/configure'", PANEL)
        self.assertNotIn('sourceStatus.innerHTML', PANEL)
        self.assertNotIn('sourceDetail.innerHTML', PANEL)
        self.assertIn('if(!document.hidden)refreshSnaptradeSource()', PANEL)

    def test_optional_sdk_is_collapsed_and_html_is_balanced(self):
        parser = _TagOrder()
        parser.feed(PANEL)
        self.assertEqual(parser.stack, [])
        self.assertGreaterEqual(parser.closed_details, 2)
        self.assertIn('Separater inoffizieller DEGIRO-SDK-Test', PANEL)


if __name__ == '__main__':
    unittest.main()
