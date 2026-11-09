"""No-secret Gemini MCP configuration and boundary checks (offline)."""
import json
from pathlib import Path
import unittest

import bob_oauth_store as store


class GeminiMcpConfigTests(unittest.TestCase):
    def test_config_has_one_read_only_server_and_exact_callback(self):
        config = json.loads(Path("docs/gemini-readonly-mcp-settings.json").read_text())
        self.assertEqual(list(config), ["mcpServers"])
        self.assertEqual(list(config["mcpServers"]), ["bob-readonly"])
        server = config["mcpServers"]["bob-readonly"]
        self.assertEqual(server["httpUrl"], store.RESOURCE)
        self.assertIs(server["trust"], False)
        self.assertEqual(server["oauth"]["redirectUri"], store.GEMINI_REDIRECT)
        self.assertEqual(set(server["oauth"]["scopes"]), store.GEMINI_READ_SCOPES)
        self.assertEqual(set(server["includeTools"]), {
            "bob_product_audit", "bob_product_gaps", "bob_diagnostics",
            "bob_signal_history", "bob_push_history",
        })
        self.assertEqual(set(server), {"httpUrl", "trust", "oauth", "includeTools"})
        self.assertEqual(set(server["oauth"]), {"enabled", "redirectUri", "scopes"})
        self.assertIs(server["oauth"]["enabled"], True)
        raw = Path("docs/gemini-readonly-mcp-settings.json").read_text().lower()
        for secret in ('clientsecret', 'apikey', 'password', 'authorization', 'termux',
                       'phone:control', 'push:test', 'order', 'bearer '):
            self.assertNotIn(secret, raw)

    def test_gemini_callback_is_never_chatgpt_callback(self):
        self.assertNotEqual(store.GEMINI_REDIRECT, store.REDIRECT)
        self.assertEqual(store.GEMINI_REDIRECT, "http://localhost:8765/oauth/callback")
        self.assertTrue(set(store.GEMINI_READ_SCOPES).isdisjoint(
            {store.PHONE_SCOPE, store.TERMUX_SCOPE, store.PUSH_TEST_SCOPE}))


if __name__ == "__main__":
    unittest.main()
