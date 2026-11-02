"""Regression: periodic paired diagnostics must not bypass the archive retry gate."""
from pathlib import Path
import unittest

ANDROID = Path(__file__).parent / "android_companion" / "app" / "src" / "main" / "java" / "ch" / "bob" / "degirocompanion"


class PhoneJobRetryRouteTests(unittest.TestCase):
    def test_job_uses_bounded_automatic_delivery_and_always_finishes(self):
        job = (ANDROID / "PhoneDiagnosticJob.kt").read_text(encoding="utf-8")
        self.assertIn("ProductDetailDelivery.autoStart(applicationContext) { jobFinished(params,retry) }",job)
        self.assertNotIn("ProductDetailDelivery.start(applicationContext)",job)

    def test_throttled_path_releases_callback_and_manual_path_remains_direct(self):
        source = (ANDROID / "ProductDetailDelivery.kt").read_text(encoding="utf-8")
        start = source.split("fun autoStart(",1)[1].split("\n    fun start(",1)[0]
        self.assertIn("completed:(()->Unit)? = null",start)
        self.assertIn("DetailAutoRetryPolicy.allowed(",start)
        self.assertIn("completed?.invoke()",start)
        self.assertIn("start(c,completed)",start)
        manual = (ANDROID / "ProductReadActivity.kt").read_text(encoding="utf-8")
        self.assertIn("ProductDetailDelivery.start(this) { refresh() }",manual)


if __name__ == "__main__":
    unittest.main()
