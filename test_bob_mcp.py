"""Read-only Bob MCP request, privacy and unavailable-audit tests."""
import unittest
import bob_mcp


class BobMcpTests(unittest.TestCase):
    def test_only_read_tools_and_no_implicit_execution(self):
        calls = []
        def reader():
            calls.append(True)
            return {"status":"ok", "items":[]}
        for method in ("initialize", "ping", "tools/list"):
            status, response = bob_mcp.handle(
                {"jsonrpc":"2.0", "id":1, "method":method}, reader)
            self.assertEqual(status,200)
            self.assertEqual(calls, [])
            if method == "tools/list":
                tools = response["result"]["tools"]
                self.assertEqual({x["name"] for x in tools},
                                 {"bob_product_audit","bob_product_gaps"})
                self.assertTrue(all(x["annotations"]["readOnlyHint"] for x in tools))
                self.assertTrue(all(not x["annotations"]["destructiveHint"] for x in tools))
        status, response = bob_mcp.handle(
            {"jsonrpc":"2.0","method":"notifications/initialized"},reader)
        self.assertEqual((status,response),(202,None))
        self.assertEqual(calls,[])

    def test_full_report_and_missing_fields_preserve_source_status(self):
        report={"status":"stale","listUploadedAt":"2026-10-15T08:00:00Z",
                "total":1, "incomplete":None, "lastCheckedAt":"old-clock",
                "items":[{"isin":"DE000FG4JXV7","direction":"SHORT","state":"incomplete",
                          "missing":["quote-time","leverage-time"],
                          "source":"SG","quoteSourceAt":None,"tradeApproved":False,
                          "sourceObservations":[{"source":"SG","bid":3.0}]}]}
        for name in ("bob_product_audit","bob_product_gaps"):
            _, response = bob_mcp.handle(
                {"jsonrpc":"2.0","id":7,"method":"tools/call",
                 "params":{"name":name,"arguments":{}}},lambda:report)
            self.assertFalse(response["result"]["isError"])
            import json
            result=json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(result["status"],"stale")
            self.assertEqual(result["items"][0]["isin"],"DE000FG4JXV7")
            self.assertEqual(result["items"][0]["missing"],["quote-time","leverage-time"])
            self.assertIs(result["items"][0]["tradeApproved"],False)
            if name == "bob_product_gaps":
                self.assertNotIn("sourceObservations",result["items"][0])

    def test_arbitrary_methods_and_args_cannot_read(self):
        def forbidden():
            self.fail("database access from disallowed request")
        for request in (
            {"jsonrpc":"2.0","id":1,"method":"resources/read"},
            {"jsonrpc":"2.0","id":1,"method":"tools/call",
             "params":{"name":"place_order","arguments":{}}},
            {"jsonrpc":"2.0","id":1,"method":"tools/call",
             "params":{"name":"bob_product_audit","arguments":{"execute":True}}},
            {"jsonrpc":"2.0","id":1,"method":"tools/call",
             "params":{"name":"bob_product_audit","arguments":None}},
            {"jsonrpc":"2.0","id":1,"method":"tools/call","params":None},
        ):
            status, response = bob_mcp.handle(request,forbidden)
            self.assertEqual(status,200)
            self.assertIn("error",response)

    def test_invalid_request_and_absent_list_do_not_create_fake_recovery(self):
        status, response = bob_mcp.handle([],lambda:self.fail("no database"))
        self.assertEqual(status,400)
        self.assertIn("error",response)
        self.assertEqual(bob_mcp.gaps({"status":"checking-new-list","incomplete":None}),
                         {"status":"checking-new-list","total":None,
                          "incomplete":None,"lastCheckedAt":None,
                          "listUploadedAt":None,"needsHelp":None,
                          "terminated":None,"readOnly":None,
                          "degiroConnected":None,"items":[]})


if __name__ == "__main__":
    unittest.main()
