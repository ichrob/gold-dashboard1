import json
import unittest
from unittest.mock import Mock, patch
import bob_diagnostics as diagnostics
import bob_mcp
from test_bob_oauth import StateTests, HttpTests
import bob_oauth_store as store
import server


class ScopeTests(StateTests):
    def test_old_grant_never_gains_diagnostics_on_refresh(self):
        tokens = self.exchange(self.authorize())
        for grant in self.state['grants'].values():
            grant.pop('scope', None)  # Existing pre-upgrade storage.
        self.assertEqual(self.call('check',token=tokens['access_token'])['scope'], store.SCOPE)
        self.assertIn('error', self.refresh(tokens['refresh_token'], scope=store.DIAGNOSTICS_SCOPE))
        renewed = self.refresh(tokens['refresh_token'])
        self.assertEqual(renewed['scope'], store.SCOPE)

    def test_new_scope_survives_exchange_refresh_and_check(self):
        scope = store.SCOPE + ' ' + store.DIAGNOSTICS_SCOPE
        req = self.begin(scope=scope)['request']
        self.assertEqual(self.call('pending',request=req)['scope'], scope)
        code = self.call('approve',request=req,until=self.now+10000)['code']
        tokens = self.exchange(code)
        self.assertEqual(tokens['scope'], scope)
        renewed = self.refresh(tokens['refresh_token'])
        self.assertEqual(self.call('check',token=renewed['access_token'])['scope'], scope)


class DiagnosticsHttpTests(HttpTests):
    def test_scope_enforced_by_http_dispatcher(self):
        for scope, allowed in [(store.SCOPE, False), (store.DIAGNOSTICS_SCOPE, True)]:
            self.begin()
            req = self.state['pending'][store.digest(self.nonce)]
            req['scope'] = scope
            cookies = self.cookie+'; '+self.session
            status, _, body = self.request('GET','/oauth/resume',headers={'Cookie':cookies})
            self.assertEqual(status,200)
            self.assertEqual(b'Diagnoseberichte' in body, allowed)
            result = store.transition(self.state,'approve',{'request':self.nonce,'until':__import__('time').time()+10000})
            tokens = store.transition(self.state,'token',dict(grant_type='authorization_code',client_id=self.cid,
                redirect_uri=store.REDIRECT,code=result['code'],code_verifier=self.verifier,resource=store.RESOURCE))
            headers = {'Authorization':'Bearer '+tokens['access_token'],'Content-Type':'application/json'}
            payload = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'bob_diagnostics'}}
            with patch.object(server,'read_diagnostics_for_mcp',return_value={'readOnly':True}) as reader:
                result = json.loads(self.request('POST','/mcp',json.dumps(payload),headers)[2])
                self.assertEqual(reader.call_count, int(allowed))
                self.assertEqual('error' in result, not allowed)
            if allowed:
                payload['params']['name'] = 'bob_product_audit'
                with patch.object(server,'read_private_product_audit_for_mcp') as reader:
                    result = json.loads(self.request('POST','/mcp',json.dumps(payload),headers)[2])
                    self.assertIn('error',result)
                    reader.assert_not_called()


class ReportTests(unittest.TestCase):
    def test_partial_report_and_no_exception_secrets(self):
        def bad(): raise RuntimeError('secret-token')
        report = diagnostics.collect({'market':bad,'background':lambda:{'status':'ok'}})
        self.assertEqual(report['status'],'partial')
        self.assertNotIn('secret-token',json.dumps(report))
        self.assertEqual(report['areas']['background']['status'],'ok')

    def test_stale_cache_and_original_timestamp(self):
        value = diagnostics.market_snapshot({'status':'fresh','spots':{'spot_price_as_of':5,'token':'secret'}}, 10, now=1000)
        self.assertEqual(value['status'],'stale')
        self.assertEqual(value['source']['spot_price_as_of'],5)
        self.assertNotIn('secret',json.dumps(value))
        self.assertEqual(diagnostics.market_snapshot(None,0)['status'],'unavailable')

    def test_diagnostics_cannot_call_product_reader_or_accept_arguments(self):
        forbidden = Mock(side_effect=AssertionError('unexpected product read'))
        reader = Mock(return_value={'readOnly':True})
        request = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'bob_diagnostics','arguments':{}}}
        self.assertFalse(bob_mcp.handle(request, forbidden,reader)[1]['result']['isError'])
        request['params']['arguments']={'path':'/send'}
        self.assertIn('error',bob_mcp.handle(request,forbidden,reader)[1])
        self.assertEqual(reader.call_count,1)
        forbidden.assert_not_called()

    def test_push_snapshot_only_selects_and_excludes_private_rows(self):
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [({'enabled':True,'checkedAt':123,'token':'secret','isin':'private'},),(2,)]
        portfolios = Mock(POLICIES={'test':{}})
        portfolios.names.return_value={'bob_paper_control':'bob_paper_test_control'}
        evaluator = Mock(); evaluator.status.return_value={'ready':True,'token':'secret'}
        health = Mock(); health.snapshot.return_value={'state':'ok'}
        result = diagnostics.push_snapshot(conn,evaluator,health,portfolios)
        self.assertTrue(all(c.args[0].startswith('SELECT ') for c in conn.execute.call_args_list))
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(result['push']['deliveryStatus'],'not-verified')
