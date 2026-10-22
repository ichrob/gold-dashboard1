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
                self.assertEqual(result['result']['isError'], not allowed)
                if not allowed:
                    self.assertIn('insufficient_scope', result['result']['_meta']['mcp/www_authenticate'][0])
            if allowed:
                payload['params']['name'] = 'bob_product_audit'
                with patch.object(server,'read_private_product_audit_for_mcp') as reader:
                    result = json.loads(self.request('POST','/mcp',json.dumps(payload),headers)[2])
                    self.assertTrue(result['result']['isError'])
                    reader.assert_not_called()


class ReportTests(unittest.TestCase):
    def test_optional_degiro_sdk_not_started_is_not_an_outage(self):
        blank={'code':'NOT_STARTED','running':False,'fresh':False,
               'liveOrdersEnabled':False,'liveQuotes':False,'snapshot':None}
        with patch('degiro_readonly.status',return_value={'ready':False}):
            result=diagnostics.broker_sync_snapshot(blank)
        self.assertEqual(result['status'],'not-configured')
        self.assertEqual(result['connectionKind'],'optional-direct-degiro-sdk-readonly')
        self.assertFalse(result['liveOrdersEnabled'])
        self.assertNotIn('degiroSync',str(diagnostics.summary({'degiroSync':result})['attention']))
        with patch('degiro_readonly.status',return_value={'ready':True}):
            result=diagnostics.broker_sync_snapshot(blank)
        self.assertEqual(result['status'],'not-started')
        failed=dict(blank,code='SDK_ERROR')
        with patch('degiro_readonly.status',return_value={'ready':False}):
            result=diagnostics.broker_sync_snapshot(failed)
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(diagnostics.summary({'degiroSync':result})['assessment'],'needs-attention')

    def test_summary_does_not_hide_product_or_shadow_dmi_gaps(self):
        summary = diagnostics.summary({'products': {'status':'ok', 'items':[{'state':'incomplete'}]},
            'analysis': {'dmi': {'available': False}}})
        self.assertEqual(summary['assessment'], 'needs-attention')
        self.assertEqual(len(summary['attention']), 2)

    def test_dmi_frame_evidence_survives_projection_without_raw_fields(self):
        result = diagnostics.project({'dmi': {'available': False, 'mode': 'shadow',
            'frames': {'5m': {'available': True, 'plusDI': 27, 'minusDI': 13, 'adx': 25},
                       '15m': {'available': False, 'reason': 'gap', 'secret': 'omit'}}}},
            diagnostics.ANALYSIS)
        self.assertEqual(result['dmi']['frames']['5m']['plusDI'], 27)
        self.assertEqual(result['dmi']['frames']['15m']['reason'], 'gap')
        self.assertNotIn('secret', result['dmi']['frames']['15m'])

    def test_discovery_and_scope_challenge_never_read_data(self):
        forbidden = Mock(side_effect=AssertionError('unexpected read'))
        request = {'jsonrpc':'2.0','id':1,'method':'tools/list'}
        definitions = bob_mcp.handle(request, forbidden)[1]['result']['tools']
        diagnostic = next(t for t in definitions if t['name'] == 'bob_diagnostics')
        self.assertEqual(diagnostic['securitySchemes'], [{'type':'oauth2','scopes':[store.DIAGNOSTICS_SCOPE]}])
        self.assertEqual(diagnostic['_meta']['securitySchemes'], diagnostic['securitySchemes'])
        request.update(method='tools/call', params={'name':'bob_diagnostics'})
        result = bob_mcp.handle(request, forbidden)[1]['result']
        self.assertTrue(result['isError'])
        challenge = result['_meta']['mcp/www_authenticate'][0]
        self.assertIn(store.SCOPE, challenge)
        self.assertIn(store.DIAGNOSTICS_SCOPE, challenge)
        self.assertIn(store.ORIGIN+'/.well-known/oauth-protected-resource', challenge)
        forbidden.assert_not_called()

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

class ExpandedReportTests(unittest.TestCase):
    def test_gap_counts_survive_omission_of_oversized_simulation(self):
        evidence={'counts':{'original':10,'estimated':3,'unavailable':2,'pending':1},'total':16}
        simulation={'status':'observed','gapEvidence':evidence,'signalHistory':{'large':'x'*20000}}
        result=diagnostics.bounded_report(diagnostics.collect({'simulationAndPush':lambda:simulation}),2000)
        self.assertEqual(result['areas']['gapEvidence'],evidence)
        self.assertEqual(result['areas']['simulationAndPush']['status'],'unavailable')
        self.assertIn('gapEvidence',simulation)

    def test_oversized_journal_does_not_also_discard_fitting_trade_and_learning_details(self):
        details={'status':'observed','areas':{
            'tradeMonitoring':{'status':'observed','items':[{'updatedAt':123,'active':False}]},
            'learning':{'status':'unavailable'},
            'repairs':{'status':'observed','items':[{'kind':'repair-verified'}]}}}
        simulation={'status':'observed','paper':{'state':'ok'},
                    'history':{'journal':'x'*20000},'details':details}
        original=diagnostics.collect({'simulationAndPush':lambda:simulation})
        result=diagnostics.bounded_report(original,3000)
        kept=result['areas']['simulationAndPush']
        self.assertEqual(kept['details'],details)
        self.assertEqual(kept['omittedSections'],['history'])
        self.assertIn({'area':'simulationAndPush.details.areas.learning','state':'unavailable'},result['summary']['attention'])
        self.assertLess(len(json.dumps(result).encode()),3000)
        self.assertIn('history',simulation)
        self.assertNotIn('omittedSections',simulation)

    def test_large_history_preserves_simulation_heartbeat_and_accounts(self):
        simulation = {'status':'observed', 'paper':{'lastSuccessAt':123},
                      'accounts':[{'profile':'100', 'cash':98, 'costsDebitedEur':2}],
                      'push':{'evaluator':{'completed':9}},
                      'history':{'large':'x'*20000}, 'details':{'large':'x'*20000}}
        original = diagnostics.collect({'simulationAndPush':lambda:simulation})
        result = diagnostics.bounded_report(original, 2000)
        kept = result['areas']['simulationAndPush']
        self.assertEqual(kept['paper']['lastSuccessAt'],123)
        self.assertEqual(kept['accounts'][0]['costsDebitedEur'],2)
        self.assertEqual(kept['push']['evaluator']['completed'],9)
        self.assertEqual(kept['omittedSections'],['history','details'])
        self.assertLess(len(json.dumps(result).encode()),2000)
        self.assertIn('history',simulation)

    def test_worker_analysis_fills_only_missing_local_observation(self):
        worker = {'status':'observed','timeframes':{'15m':{'capturedAt':123}}}
        result = diagnostics.collect({'analysis':lambda:{'status':'unavailable'},
            'simulationAndPush':lambda:{'analysis':worker}})
        self.assertEqual(result['areas']['analysis']['timeframes'],worker['timeframes'])
        self.assertEqual(result['areas']['analysis']['observationSource'],'push-worker')
        local = {'status':'observed','timeframes':{'5m':{'capturedAt':124}}}
        result = diagnostics.collect({'analysis':lambda:local,
            'simulationAndPush':lambda:{'analysis':worker}})
        self.assertEqual(result['areas']['analysis'],local)

    def test_projection_redacts_and_bounds_untrusted_payload(self):
        value = {'items':[{'title':'token=secret https://example.com/private', 'body':'private raw transcript'}]*40}
        result = diagnostics.research_snapshot(value)
        self.assertEqual(len(result['items']),20)
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('example.com',json.dumps(result))
        self.assertNotIn('private raw transcript',json.dumps(result))
        self.assertIsNone(diagnostics.project(float('nan'),None))

    def test_actual_indicators_are_captured_without_recalculation(self):
        with patch.object(diagnostics,'_analyses',{}):
            result={'direction':'LONG','decisionReason':'closed bars','analysisSnapshot':{'R':51,'e200':2000,'at':4},'token':'private'}
            diagnostics.observe_analysis(result,'15m')
            result['analysisSnapshot']['R']=99
            captured=diagnostics.analysis_snapshot()
            self.assertEqual(captured['timeframes']['15m']['result']['analysisSnapshot']['R'],51)
            self.assertNotIn('private',json.dumps(captured))
            captured['timeframes'].clear()
            self.assertTrue(diagnostics.analysis_snapshot()['timeframes'])

    def test_missing_table_does_not_hide_other_evidence(self):
        from unittest.mock import MagicMock
        conn=MagicMock()
        def execute(sql):
            self.assertTrue(sql.startswith('SELECT '))
            if 'bob_real_trades ' in sql:raise RuntimeError('secret connection URL')
            cursor=Mock();cursor.fetchall.return_value=[({'kind':'observed','token':'secret'},)]
            return cursor
        conn.execute.side_effect=execute
        result=diagnostics.stored_details(conn)
        self.assertEqual(result['areas']['tradeMonitoring']['status'],'unavailable')
        self.assertEqual(result['areas']['repairs']['status'],'observed')
        self.assertNotIn('secret',json.dumps(result))
        self.assertEqual(conn.transaction.call_count,8)
        self.assertEqual(result['areas']['gapModels']['status'],'unavailable')

    def test_recovery_state_is_preserved_and_summarized(self):
        products=diagnostics.product_snapshot({'items':[{'sourceRecovery':[{'stage':'comdirect-fetch','state':'failed','retryAfterSeconds':30}]}]})
        self.assertEqual(products['items'][0]['sourceRecovery'][0]['retryAfterSeconds'],30)
        self.assertEqual(diagnostics.summary({'products':products})['assessment'],'needs-attention')

    def test_simulation_retains_cost_assumptions_and_unknown_result(self):
        case=diagnostics.project({'modelOnly':True,'netReturnKnown':False,'ledgerModelNetEur':None,'ledgerCostsDebited':2,'ledgerCostModel':{'feeEurPerOrder':1,'token':'secret'},'entryQuote':{'raw':'private'}},diagnostics.CASE)
        self.assertIsNone(case['ledgerModelNetEur'])
        self.assertFalse(case['netReturnKnown'])
        self.assertEqual(case['ledgerCostModel']['feeEurPerOrder'],1)
        self.assertNotIn('secret',json.dumps(case))
        self.assertNotIn('private',json.dumps(case))
