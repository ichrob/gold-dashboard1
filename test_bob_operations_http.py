import http.client
import json
import threading
import unittest
from unittest.mock import patch
import server

class OperationsHttpTests(unittest.TestCase):
    def test_auth_before_read_and_no_raw_diagnostics_leak(self):
        httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        try:
            for allowed in (False,True):
                with patch.object(server.Handler,'authenticated',return_value=allowed), patch.object(server,'read_diagnostics_for_mcp',return_value={'areas':{},'secret':'DO-NOT-EXPOSE'}) as read:
                    c=http.client.HTTPConnection(*httpd.server_address)
                    c.request('GET','/api/operations-summary');r=c.getresponse();data=r.read()
                    self.assertEqual(r.status,200 if allowed else 401)
                    self.assertEqual(read.call_count,int(allowed))
                    self.assertEqual(r.getheader('Cache-Control'),'no-store')
                    self.assertNotIn(b'DO-NOT-EXPOSE',data)
                    if allowed:self.assertFalse(json.loads(data)['realOrders'])
                    c.close()
        finally:
            httpd.shutdown();httpd.server_close();thread.join()
