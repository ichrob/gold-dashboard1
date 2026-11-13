import unittest
from unittest.mock import patch
import market_ui_health as m
import bob_diagnostics

class UiHealthTests(unittest.TestCase):
    def setUp(self):
        p=patch.object(m,'_tabs',{});p.start();self.addCleanup(p.stop)
    def test_failure_recovery_expiry_and_independent_tabs(self):
        m.record({'tab':'a'*16,'code':'spot-mismatch'},100)
        m.record({'tab':'b'*16,'code':'ok'},110)
        self.assertEqual(m.snapshot(120)['codes'],['spot-mismatch'])
        m.record({'tab':'a'*16,'code':'ok'},130)
        self.assertEqual(m.snapshot(140)['codes'],[])
        self.assertEqual(m.snapshot(140)['lastRecoveryAt'],130)
        self.assertEqual(m.snapshot(400)['state'],'not-observed')
        self.assertEqual(m.snapshot(400)['healthyReports'],0)
    def test_bounded_and_no_private_fields(self):
        for i in range(40):m.record({'tab':f'{i:016x}','code':'data-unavailable','price':999,'account':'private'},100+i)
        self.assertEqual(m.snapshot(140)['activeReports'],32)
        self.assertNotIn('private',str(m.snapshot(140)))
        self.assertEqual(m.snapshot(140)['healthyReports'],0)
        with self.assertRaises(ValueError):m.record({'tab':'private','code':'ok'})
        with self.assertRaises(ValueError):m.record({'tab':'a'*16,'code':'trade-approved'})
    def test_triage_sees_fault(self):
        result=bob_diagnostics.triage_snapshot({'runtime':{'marketUi':{'codes':['spot-mismatch'],'lastObservedAt':100}},'background':{'status':'ok'}})
        self.assertTrue(any(x['code']=='MARKET_UI_RENDER_FAILURE' for x in result['items']))

class UiEndpointTests(unittest.TestCase):
    def test_unauthenticated_report_does_not_change_health(self):
        import io,json,server
        from unittest.mock import Mock
        h=object.__new__(server.Handler);h.path='/api/diag'
        body=json.dumps({'event':'market-ui:observation','details':{'tab':'a'*16,'code':'ok'}}).encode()
        h.headers={'Content-Length':str(len(body))};h.rfile=io.BytesIO(body)
        h.wfile=io.BytesIO();h.authenticated=Mock(return_value=False)
        with patch.object(server.bob_auth,'send') as send,patch.object(m,'record') as record:
            h.do_POST()
        send.assert_called_once_with(h,401);record.assert_not_called()
