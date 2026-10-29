"""Read-only Bob MCP request, privacy and unavailable-audit tests."""
import unittest
import bob_mcp


class BobMcpTests(unittest.TestCase):
    def test_large_diagnostics_keep_broker_status_and_mark_omissions(self):
        import json
        report = {'status':'observed', 'readOnly':True, 'areas':{
            'history':{'items':['x'*300000]},
            'degiroSync':{'status':'stale','lastSuccessAt':'2026-10-20T06:00:00Z'}}}
        _, response = bob_mcp.handle({'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'bob_diagnostics'}}, lambda: self.fail('product access'), lambda: report)
        self.assertFalse(response['result']['isError'])
        payload=response['result']['content'][0]['text']
        self.assertLessEqual(len(payload.encode()), bob_mcp._MAX_RESULT_BYTES)
        result=json.loads(payload)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['omittedAreas'],['history'])
        self.assertEqual(result['areas']['degiroSync'],report['areas']['degiroSync'])
        self.assertNotIn('truncated',report)

    def test_broker_metadata_excludes_holdings_and_does_not_fake_freshness(self):
        from bob_diagnostics import broker_sync_snapshot
        result=broker_sync_snapshot({'code':'AUTH_REQUIRED','running':False,'fresh':False,
            'snapshot':{'observedAt':'2026-10-20T06:00:00Z','holdings':[{'secret':'private'}]},
            'password':'secret'})
        self.assertEqual(result['status'],'stale')
        self.assertEqual(result['lastSuccessAt'],'2026-10-20T06:00:00Z')
        self.assertNotIn('snapshot',result)
        self.assertNotIn('password',result)
        self.assertEqual(broker_sync_snapshot({})['status'],'unavailable')

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
                                 {"bob_product_audit","bob_product_gaps","bob_diagnostics","bob_signal_history","bob_push_history"})
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

    def test_push_history_is_read_only_and_rejects_unsafe_queries(self):
        import json
        window = {"start":"2026-10-23T18:00:00+02:00",
                  "end":"2026-10-23T23:00:00+02:00"}
        calls = []
        def history_reader(args):
            calls.append(args)
            return {"readOnly":True, "status":"observed", "records":[
                {"classification":"synthetic-test", "handsetReceipt":"not-verified"}]}
        req = {"jsonrpc":"2.0", "id":42, "method":"tools/call",
               "params":{"name":"bob_push_history", "arguments":window}}
        _, result = bob_mcp.handle(req, lambda: self.fail("product reader"),
                                   lambda: {"readOnly":True},
                                   push_history_reader=history_reader)
        self.assertFalse(result["result"]["isError"])
        parsed = json.loads(result["result"]["content"][0]["text"])
        self.assertEqual(parsed["records"][0]["classification"],"synthetic-test")
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]["start"],"2026-10-23T16:00:00+00:00")
        req["params"]["arguments"]={"untrustedPath":"../../secret"}
        _, result = bob_mcp.handle(req, lambda: self.fail("product reader"),
                                   lambda: {"readOnly":True},
                                   push_history_reader=history_reader)
        self.assertEqual(result["error"]["code"],-32602)
        self.assertEqual(len(calls),1)

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
                          "terminated":None,"excluded":None,"readOnly":None,
                          "degiroConnected":None,"items":[]})


    def test_concurrent_diagnostics_serialize_complete_snapshot_reader(self):
        import threading
        import time
        active = 0
        highest = 0
        guard = threading.Lock()
        start = threading.Barrier(3)
        results = []

        def reader():
            nonlocal active, highest
            with guard:
                active += 1
                highest = max(highest, active)
            time.sleep(0.05)
            with guard:
                active -= 1
            return {"status":"observed","readOnly":True,"areas":{}}

        def call():
            start.wait()
            results.append(bob_mcp.handle(
                {"jsonrpc":"2.0","id":1,"method":"tools/call",
                 "params":{"name":"bob_diagnostics",
                           "arguments":{"focus":"overview"}}},
                lambda: self.fail("product access"), reader))

        threads = [threading.Thread(target=call) for _ in range(2)]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(highest, 1)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(status == 200 for status, _ in results))


if __name__ == "__main__":
    unittest.main()
