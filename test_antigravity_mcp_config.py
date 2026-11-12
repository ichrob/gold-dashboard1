"""Offline security checks for disabled Antigravity-to-Bob MCP template."""
import json
from pathlib import Path
import unittest


class AntigravityBobMcpTemplateTests(unittest.TestCase):
    def test_disabled_until_explicit_owner_oauth_consent(self):
        file=Path("docs/antigravity-bob-readonly-mcp.disabled.json")
        payload=json.loads(file.read_text(encoding="utf-8"))
        self.assertEqual(list(payload),["mcpServers"])
        self.assertEqual(list(payload["mcpServers"]),["bob-private-readonly"])
        item=payload["mcpServers"]["bob-private-readonly"]
        self.assertEqual(set(item),{"serverUrl","enabledTools","disabled","timeoutSeconds"})
        self.assertEqual(item["serverUrl"],"https://bob-private-scanner.onrender.com/mcp")
        self.assertIs(item["disabled"],True)
        self.assertLessEqual(item["timeoutSeconds"],30)
        self.assertEqual(set(item["enabledTools"]),{
            "bob_product_audit","bob_product_gaps","bob_diagnostics",
            "bob_signal_history","bob_push_history"
        })
        self.assertNotIn("httpUrl",item)
        self.assertNotIn("headers",item)
        self.assertNotIn("oauth",item)

    def test_no_private_creds_or_mutation_tools(self):
        data=Path("docs/antigravity-bob-readonly-mcp.disabled.json").read_text()
        for secret in ("apiKey","access_token","clientSecret",
                       "Authorization","Bearer ","password","ghp_",
                       "bob_termux_execute","bob_phone_command","place_order",
                       "bob_push_test"):
            self.assertNotIn(secret,data)
        doc=Path("BOB_ANTIGRAVITY_TERMUX.md").read_text()
        self.assertIn("disabled: true",doc)
        self.assertIn("18.06.2026",doc)
        self.assertIn("Antigravity",doc)


if __name__=="__main__":
    unittest.main()
