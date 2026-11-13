import unittest
from pathlib import Path


class DegiroBridgeBrowserHarnessTests(unittest.TestCase):
    def test_synthetic_export_activates_broker_before_trusted_click(self):
        source = Path(__file__).with_name("browser_degiro_browser_bridge.cjs").read_text(
            encoding="utf-8"
        )
        export = source.split("async function exportCSV", 1)[1].split(
            "// A normal export", 1
        )[0]

        foreground = export.index("await broker.bringToFront();")
        click = export.index("await broker.locator('#export').click();")
        terminal_wait = export.index("await broker.waitForFunction", click)

        self.assertLess(foreground, click)
        self.assertLess(click, terminal_wait)
        self.assertIn("synthetic broker state", export[terminal_wait:])
        self.assertIn("writes:window.gmStatusWrites", export[terminal_wait:])
        self.assertIn("armed:GM_getValue('bob-export-arm-v1',0)>Date.now()", export[terminal_wait:])


if __name__ == "__main__":
    unittest.main()
