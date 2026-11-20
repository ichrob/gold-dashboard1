"""Guardrails for free-only Cloudflare Worker deploy manifests.

These are source-of-truth templates for an independently authorized future
deployment, not a deployment trigger. Tests must never require API tokens.
"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
PATHS = [
    ROOT / "ops/cloudflare-watchdog/wrangler.jsonc",
    ROOT / "ops/oracle_a1_retry/wrangler.jsonc",
    ROOT / "ops/cloudflare-ai-review/wrangler.jsonc",
]


class TestCloudflareConfig(unittest.TestCase):
    def test_free_only_and_privacy_defaults(self):
        for path in PATHS:
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                obs = data["observability"]
                self.assertTrue(data["upload_source_maps"])
                self.assertTrue(obs["enabled"])
                self.assertTrue(obs["redact_query_string"])
                self.assertTrue(obs["logs"]["enabled"])
                self.assertTrue(obs["logs"]["invocation_logs"])
                self.assertTrue(obs["issues"]["enabled"])
                self.assertFalse(obs["traces"]["enabled"])
                self.assertLessEqual(obs["logs"]["head_sampling_rate"], 1)
                for forbidden in ("logpush", "paid", "routes", "tail_consumers",
                                  "browser", "r2_buckets"):
                    self.assertNotIn(forbidden, data)
                self.assertTrue((path.parent / data["main"]).resolve().is_file())

    def test_clock_existing_10_minute_schedule_is_unchanged(self):
        cfg = json.loads(PATHS[0].read_text(encoding="utf-8"))
        self.assertEqual(cfg["triggers"]["crons"], ["4,14,24,34,44,54 * * * *"])
        self.assertEqual(cfg["vars"]["ENABLED"], "false")

    def test_oracle_remains_fail_closed_and_no_public_endpoint(self):
        cfg = json.loads(PATHS[1].read_text(encoding="utf-8"))
        self.assertFalse(cfg["workers_dev"])
        self.assertFalse(cfg["preview_urls"])
        self.assertEqual(cfg["triggers"]["crons"], ["*/30 * * * *"])
        for name in ("ENABLED", "ALLOW_APPLY", "PLAN_VERIFIED_ALWAYS_FREE"):
            self.assertEqual(cfg["vars"][name], "false")
        self.assertFalse(any("PRIVATE_KEY" in str(x) or "TOKEN" in str(x)
                             for x in cfg.get("vars", {}).keys()))

    def test_ai_keeps_existing_binding_and_no_new_cron(self):
        cfg = json.loads(PATHS[2].read_text(encoding="utf-8"))
        self.assertEqual(cfg["ai"]["binding"], "AI")
        self.assertTrue(cfg["workers_dev"])
        self.assertNotIn("triggers", cfg)
        self.assertFalse(cfg["observability"]["traces"]["enabled"])


if __name__ == "__main__":
    unittest.main()
