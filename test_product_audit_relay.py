"""Exercise the actual server reader without starting server background jobs."""
import ast
import io
import json
import pathlib
import unittest
from urllib.request import Request

class RelayTests(unittest.TestCase):
    def reader(self, payload):
        tree=ast.parse(pathlib.Path('server.py').read_text())
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in
                   ('read_private_product_audit_for_mcp','read_private_report_for_mcp')]
        seen=[]
        def opening(request, timeout):
            seen.append((request,timeout))
            return io.BytesIO(payload)
        scope=dict(PUSH_SERVICE_URL='https://private.example',PUSH_SERVICE_TOKEN='test-only',Request=Request,urlopen=opening,json=json)
        exec(compile(ast.Module(body=functions,type_ignores=[]),'server.py','exec'),scope)
        return scope['read_private_product_audit_for_mcp'],seen
    def test_large_report_preserves_evidence_and_status(self):
        report={'status':'stale','items':[{'sourceObservations':'x'*100000,'tradeApproved':False}]}
        reader,seen=self.reader(json.dumps(report).encode())
        self.assertEqual(reader(),report)
        self.assertEqual(seen[0][0].get_header('X-bob-push-token'),'test-only')
        self.assertEqual(seen[0][1],8)
    def test_bounded_and_invalid_reports_rejected(self):
        for raw in [b'x'*(2*1024*1024+1),b'[]',b'not-json']:
            reader,_=self.reader(raw)
            with self.assertRaises(ValueError):reader()
    def test_browser_route_uses_same_reader(self):
        source=pathlib.Path('server.py').read_text()
        route=source.split('if path == "/api/degiro/audit":',1)[1].split('if path == "/api/mtf":',1)[0]
        self.assertIn('result = read_private_product_audit_for_mcp()',route)
        self.assertIn('status = 503',route)
    def test_comparison_status_is_allowlisted_without_new_public_access(self):
        source=pathlib.Path('server.py').read_text()
        self.assertIn('"/comparison-status"',source)
        self.assertIn("read_private_report_for_mcp('/comparison-status')",source)
if __name__=='__main__':unittest.main()
