import json
import unittest
from datetime import datetime, timezone, timedelta
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

    def test_night_session_explains_stale_candle_without_hiding_it(self):
        from datetime import datetime, timezone
        nighttime = datetime(2026, 10, 22, 21, 14, tzinfo=timezone.utc).timestamp()
        report = diagnostics.market_snapshot({'status': 'observed'}, nighttime-10, now=nighttime)
        self.assertEqual(report['sessionMode'], 'night')
        self.assertEqual(report['candles']['1m']['integrity']['state'], 'missing')
        evidence = {'market': {'sessionMode': report['sessionMode'],
                               'candles': {'1m': {'integrity': {
                                   'state': 'stale',
                                   'source': 'biquote · XAU/USD Broker/MT5'}}}}}
        result = diagnostics.summary(evidence)
        item = next(x for x in result['attention'] if x['area'] == 'market.candles.1m.integrity')
        self.assertEqual(item['state'], 'stale')
        self.assertEqual(item['sessionMode'], 'night')
        self.assertIn('not-proof-of-worker-outage', item['meaning'])
        self.assertEqual(result['assessment'], 'needs-attention')

    def test_source_history_does_not_create_live_alerts(self):
        sources={'xaus/1h':{'state':'current','events':[{'state':'stale'},{'state':'current'}]},
                 'biquote/1m':{'state':'current','events':[{'state':'stale'}]},
                 'xaus/1m':{'state':'stale','events':[{'state':'current'},{'state':'stale'}]}}
        original={'status':'observed','sources':sources}
        report=diagnostics.summary({'sourceReliability':original})
        self.assertEqual(report['attention'],
                         [{'area':'sourceReliability.sources.xaus/1m','state':'stale','sourceRole':'undetermined','severity':'warning'}])
        self.assertEqual(report['assessment'],'needs-attention')
        self.assertEqual(len(original['sources']['xaus/1h']['events']),2)

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
        conn.execute.return_value.fetchone.side_effect = [({'enabled':True,'checkedAt':123,'token':'secret','isin':'private'},),(2, 3)]
        portfolios = Mock(POLICIES={'test':{}})
        portfolios.names.return_value={'bob_paper_control':'bob_paper_test_control'}
        evaluator = Mock(); evaluator.status.return_value={'ready':True,'token':'secret'}
        health = Mock(); health.snapshot.return_value={'state':'ok'}
        result = diagnostics.push_snapshot(conn,evaluator,health,portfolios)
        self.assertTrue(all(c.args[0].startswith('SELECT ') for c in conn.execute.call_args_list))
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(result['push']['deliveryStatus'],'not-verified')
        self.assertEqual(result['push']['registeredSubscriptions'],3)
        self.assertEqual(result['push']['subscriptionState'],'enabled')
        self.assertEqual(result['push']['devicePermissionStatus'],'not-verified')
        self.assertEqual(result['push']['monitorState'],'subscriptions-observed')
        self.assertIn('nicht nachgewiesen',result['push']['deliveryNote'])

    def test_zero_push_subscriptions_are_not_declared_failed_deliveries(self):
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [({'enabled':True},),(0, 2)]
        portfolios = Mock(POLICIES={'test':{}})
        portfolios.names.return_value={'bob_paper_control':'bob_paper_test_control'}
        evaluator = Mock(); evaluator.status.return_value={'completed':1,'failed':0}
        health = Mock(); health.snapshot.return_value={'state':'ok'}
        row = diagnostics.push_snapshot(conn,evaluator,health,portfolios)['push']
        self.assertEqual(row['activeMonitors'],0)
        self.assertEqual(row['registeredSubscriptions'],2)
        self.assertEqual(row['subscriptionState'],'registered-disabled')
        self.assertEqual(row['monitorState'],'none-enabled')
        self.assertEqual(row['deliveryStatus'],'not-verified')
        self.assertIn('keine aktiven',row['deliveryNote'])
        self.assertNotIn('token',json.dumps(row))
        self.assertEqual(conn.execute.call_count,2)
        self.assertIn('count(*) FILTER',conn.execute.call_args.args[0])

    def test_no_registered_push_subscription_is_not_a_provider_failure(self):
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [({'enabled':True},),(0, 0)]
        portfolios = Mock(POLICIES={'test':{}})
        portfolios.names.return_value={'bob_paper_control':'bob_paper_test_control'}
        evaluator = Mock(); evaluator.status.return_value={'completed':1}
        health = Mock(); health.snapshot.return_value={'state':'ok'}
        row = diagnostics.push_snapshot(conn,evaluator,health,portfolios)['push']
        self.assertEqual(row['registeredSubscriptions'],0)
        self.assertEqual(row['subscriptionState'],'not-registered')
        self.assertEqual(row['deliveryStatus'],'not-verified')
        self.assertEqual(row['devicePermissionStatus'],'not-verified')
        self.assertNotIn('endpoint',json.dumps(row))




class EntryBlockEvidenceTests(unittest.TestCase):
    def test_saved_entry_blocks_are_bounded_and_separate_from_seven_day_journal(self):
        conn = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = ('2026-10-27', {
            'entryBlockCounts': {'Frühwarn-Test: Mindest-CRV nicht erfüllt': 3},
            'entryBlocks': [
                {'at': 1000, 'lastAt': 2000, 'goldAt': 900, 'checks': 2,
                 'direction': 'LONG', 'signalSource': 'early-warning-v2',
                 'ruleVersion': 'intraday-responsive-v6',
                 'plan': {'kind': 'candidate', 'entry': 100, 'stop': 90,
                          'target': 120, 'unit': 'USD/oz',
                          'private': 'must-not-pass'},
                 'reason': 'Frühwarn-Test: Mindest-CRV nicht erfüllt',
                 'isin': 'private-isin', 'token': 'secret'},
                {'at': 3000, 'lastAt': 3000, 'checks': 1, 'direction': 'SHORT',
                 'reason': 'Kein bestätigter gültiger Goldplan',
                 'isin': 'another-private-isin'},
            ],
            'entryBlocksTruncated': True,
        })
        conn.execute.return_value = cursor
        portfolios = Mock(POLICIES={'early1000oct': {}})
        portfolios.names.return_value = {'bob_paper_days': 'bob_paper_test_days'}

        evidence = diagnostics.entry_block_evidence(conn, portfolios)

        self.assertEqual(evidence['status'], 'observed')
        self.assertEqual(evidence['entryBlockRecordLimitPerAccountDay'], 200)
        self.assertEqual(evidence['diagnosticJournalRetentionDays'], 7)
        account = evidence['accounts'][0]
        self.assertEqual(account['day'], '2026-10-27')
        self.assertEqual(account['totalChecks'], 3)
        self.assertEqual(account['storedRecords'], 2)
        self.assertEqual(account['returnedRecords'], 2)
        self.assertTrue(account['sourceTruncated'])
        self.assertEqual(account['latest'][0]['direction'], 'LONG')
        self.assertEqual(account['latest'][0]['sourceAt'], 900)
        self.assertEqual(account['latest'][0]['signalSource'], 'early-warning-v2')
        self.assertEqual(account['latest'][0]['plan']['stop'], 90)
        self.assertNotIn('must-not-pass', json.dumps(evidence))
        self.assertNotIn('private-isin', json.dumps(evidence))
        self.assertNotIn('secret', json.dumps(evidence))
        collected = diagnostics.collect({'simulationAndPush': lambda: {
            'status': 'observed', 'entryBlockEvidence': evidence}})
        self.assertEqual(collected['areas']['entryBlockEvidence'], evidence)
        self.assertNotIn('entryBlockEvidence',
                         collected['areas']['simulationAndPush'])
        self.assertTrue(all(call.args[0].startswith('SELECT ') for call in conn.execute.call_args_list))


class ExpandedReportTests(unittest.TestCase):
    def test_gap_counts_survive_omission_of_oversized_simulation(self):
        evidence={'counts':{'original':10,'estimated':3,'unavailable':2,'pending':1},'total':16}
        simulation={'status':'observed','gapEvidence':evidence,'signalHistory':{'large':'x'*20000}}
        result=diagnostics.bounded_report(diagnostics.collect({'simulationAndPush':lambda:simulation}),2000)
        self.assertEqual(result['areas']['gapEvidence'],evidence)
        self.assertEqual(result['areas']['simulationAndPush']['status'],'observed')
        self.assertIn('signalHistory', result['areas']['simulationAndPush']['omittedSections'])
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
        self.assertIn({'area':'simulationAndPush.details.areas.learning','state':'unavailable','severity':'warning'},result['summary']['attention'])
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


    def test_large_signal_history_keeps_simulation_accounts_and_costs(self):
        original=diagnostics.collect({'simulationAndPush': lambda: {
            'status':'observed',
            'accounts':[{'profile':'100', 'cash':98, 'costsDebitedEur':2,
                         'recentCases':{'status':'observed','items':[
                             {'raw':'a'*4000} for _ in range(5)]}}],
            'paper':{'lastSuccessAt':123},
            'signalHistory':{'records':['b'*5000 for _ in range(5)]},
            'push':{'evaluator':{'completed':42}}}})
        result=diagnostics.bounded_report(original,2400)
        simulation=result['areas']['simulationAndPush']
        self.assertEqual(simulation['accounts'][0]['cash'],98)
        self.assertEqual(simulation['accounts'][0]['costsDebitedEur'],2)
        self.assertEqual(simulation['push']['evaluator']['completed'],42)
        self.assertIn('signalHistory',simulation['omittedSections'])
        self.assertIn('accounts.recentCases',simulation['omittedSections'])
        self.assertEqual(simulation['accounts'][0]['recentCases']['status'],'unavailable')
        self.assertNotIn('simulationAndPush',result['omittedAreas'])
        self.assertLess(len(json.dumps(result).encode()),2400)

    def test_missing_process_local_analysis_is_not_conflated_with_live_outage(self):
        with patch.object(diagnostics, '_analyses', {}):
            local = diagnostics.analysis_snapshot()
        self.assertEqual(local['status'], 'unavailable')
        self.assertEqual(local['availabilityReason'], 'no-evaluation-observed-in-this-process')
        report = diagnostics.summary({'analysis': local})
        self.assertEqual(report['assessment'], 'needs-attention')
        self.assertEqual(report['attention'][0]['meaning'],
                         'no-local-evaluator-capture-not-a-confirmed-global-outage')

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


class NewFeatureReadAccessTests(unittest.TestCase):
    def test_new_feature_read_is_passive_and_does_not_claim_phone_access(self):
        areas = {'runtime': {'snaptradePersonal': {'code':'READ_OK', 'fresh':True,
                                                   'token':'must-not-appear'}}}
        result = diagnostics.new_feature_snapshot(areas, mobile_asset_loaded=True)
        self.assertEqual(result['androidCompanion']['runtime'], 'not-observable')
        self.assertEqual(result['unifiedMobileWorkspace']['browserSession'], 'not-observable')
        self.assertEqual(result['unifiedMobileWorkspace']['serverAsset'], 'loaded')
        self.assertEqual(result['androidCompanion']['remotePairing'],'not-implemented')
        self.assertTrue(result['androidCompanion']['deviceConsentRequired'])
        self.assertFalse(result['snaptradeReadOnly']['liveBrokerQuotes'])
        self.assertEqual(result['snaptradeReadOnly']['sourceRole'],
                         'depot-history-and-issuer-observations-only')
        self.assertEqual(result['researchSelfReview']['status'], 'unavailable')
        self.assertIsNone(result['researchSelfReview']['sourceReportAt'])
        self.assertEqual(result['snaptradeReadOnly']['connectionCode'], 'READ_OK')
        self.assertFalse(result['snaptradeReadOnly']['tradingEnabled'])
        self.assertNotIn('must-not-appear', json.dumps(result))

    def test_only_saved_research_review_is_visible_with_original_report_time(self):
        review = {'mode':'RESEARCH_ONLY', 'status':'collecting',
                  'sessions':3, 'trades':4, 'automaticOrder':False,
                  'liveRuleChanged':False, 'token':'never-leak'}
        areas = {'strategyReport': {'status':'observed', 'items':[
            {'calculatedAt':'2026-10-22T11:00:00+00:00',
             'report': {'learningCycle': {'selfReview':review}}}]}}
        result = diagnostics.new_feature_snapshot(areas)
        item = result['researchSelfReview']
        self.assertEqual(item['status'], 'observed')
        self.assertEqual(item['sourceReportAt'], '2026-10-22T11:00:00+00:00')
        self.assertEqual(item['result']['status'], 'collecting')
        self.assertFalse(item['result']['automaticOrder'])
        self.assertNotIn('never-leak', json.dumps(result))

    def test_research_success_without_self_review_is_not_false_success(self):
        areas = {'strategyReport': {'status':'observed','items':[
            {'calculatedAt':'2026-10-22T07:47:45+00:00',
             'report': {'learningCycle': {'status':'collecting'}}}]}}
        item = diagnostics.new_feature_snapshot(areas)['researchSelfReview']
        self.assertEqual(item['status'], 'unavailable')
        self.assertEqual(item['sourceReportAt'], '2026-10-22T07:47:45+00:00')
        self.assertIsNone(item['result'])



class RecentPaperEvidenceStatusTests(unittest.TestCase):
    def test_unconfirmed_paper_outcomes_are_not_loss_or_filled_orders(self):
        accounts=[
            {'recentCases':{'status':'observed','items':[
                {'status':'closed','ledgerModelNetEur':5},
                {'status':'inconclusive','ledgerModelNetEur':None},
                {'status':'open'}]}},
            {'recentCases':{'status':'observed','items':[
                {'status':'inconclusive','ledgerModelNetEur':None}]}},
            {'recentCases':{'status':'unavailable'}},
        ]
        result=diagnostics.recent_paper_outcomes(accounts)
        self.assertEqual(result['state'],'partial')
        self.assertEqual(result['observedCases'],4)
        self.assertEqual(result['closed'],1)
        self.assertEqual(result['open'],1)
        self.assertEqual(result['inconclusive'],2)
        self.assertEqual(result['accountsUnavailable'],1)
        self.assertFalse(result['realOrders'])
        self.assertFalse(result['missingResultsAreLosses'])
        self.assertNotIn('5',json.dumps(result.get('ledgerNet',None)))

    def test_inconclusive_causes_are_recorded_without_invented_fills(self):
        cases=[
            {'status':'inconclusive','events':[{'kind':'data-gap'}]},
            {'status':'inconclusive','events':[{'kind':'product-terminated'}]},
            {'status':'inconclusive','events':[{'kind':'deferred-sale'},{'kind':'data-gap'}]},
            {'status':'inconclusive','events':[{'kind':'other','secret':'hidden'}]},
            {'status':'closed','events':[{'kind':'data-gap'}]},
        ]
        result=diagnostics.recent_paper_outcomes(
            [{'recentCases':{'status':'observed','items':cases}}])
        self.assertEqual(result['observedCases'],5)
        self.assertEqual(result['inconclusive'],4)
        self.assertEqual(result['closed'],1)
        self.assertEqual(result['inconclusiveRecordedCauses'],{
            'recordedGoldDataGap':2,
            'recordedKoOrProductEnd':1,
            'deferredModelSale':1,
            'unclassified':1})
        self.assertEqual(result['causeScope'],
                         'overlap-possible-recorded-events-only-not-ground-truth')
        self.assertNotIn('secret',json.dumps(result))
        self.assertFalse(result['missingResultsAreLosses'])

    def test_later_priced_paper_case_never_relabels_missing_exit_as_verified(self):
        cases=[{"status":"inconclusive","productReturnKnown":True,
                "events":[{"kind":"data-gap"},{"kind":"deferred-sale"}]},
               {"status":"inconclusive","productReturnKnown":False,
                "events":[{"kind":"data-gap"}]}]
        data=diagnostics.recent_paper_outcomes([
            {"recentCases":{"status":"observed","items":cases}}])
        evidence=data["inconclusivePriceEvidence"]
        self.assertEqual(evidence["laterModelPricePresentButOriginalExitUnverified"],1)
        self.assertEqual(evidence["noConfirmedLaterModelPrice"],1)
        self.assertEqual(evidence["originalExitStillUnverified"],2)
        self.assertFalse(data["missingResultsAreLosses"])
        self.assertIn("cannot reconstruct",evidence["note"])

    def test_all_observed_paper_cases_are_not_whole_account_profit(self):
        result=diagnostics.recent_paper_outcomes([
            {'recentCases':{'status':'observed','items':[]}} for _ in range(5)])
        self.assertEqual(result['state'],'observed')
        self.assertEqual(result['observedCases'],0)
        self.assertIn('last-five',result['scope'])


class PrivateWorkerClockProjectionTests(unittest.TestCase):
    def sample(self):
        return dict(status='observed', readOnly=True,
                    workerMissedCyclesVerified=False,
                    scope='process-local-worker-starts-not-market-tick-proof',
                    observedCycles=2, comparableStartIntervals=1,
                    maxObservedStartGapSeconds=30.2,
                    lastStartedAt='2026-10-26T08:35:30+00:00',
                    lastCompletedAt='2026-10-26T08:35:30.600+00:00',
                    lastDurationMs=600, configuredSeconds=30,
                    plannedWaitSeconds=29.4, lastObservedStartGapSeconds=30.2)

    def test_private_worker_clock_is_limited_and_not_a_market_tick_claim(self):
        sample = self.sample()
        sample['password'] = 'NEVER-ECHO-THIS'
        result = diagnostics.collection_cycle_snapshot(
            sample, now=datetime(2026, 10, 26, 8, 35, 31, tzinfo=timezone.utc))
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['observedCycles'], 2)
        self.assertEqual(result['lastDurationMs'], 600)
        self.assertFalse(result['workerMissedCyclesVerified'])
        self.assertTrue(result['readOnly'])
        self.assertNotIn('password', json.dumps(result))
        self.assertNotIn('NEVER-ECHO-THIS', json.dumps(result))

    def test_stale_cycle_is_not_reported_as_a_fresh_worker(self):
        sample = self.sample()
        base = datetime(2026, 10, 26, 8, 35, 31, tzinfo=timezone.utc)
        current = diagnostics.collection_cycle_snapshot(sample, now=base)
        self.assertEqual(current['status'], 'observed')
        self.assertEqual(current['freshness'], 'current')
        self.assertLess(current['lastCompletionAgeSeconds'], 2)
        old = diagnostics.collection_cycle_snapshot(sample, now=base+timedelta(minutes=5))
        self.assertEqual(old['status'], 'stale')
        self.assertEqual(old['freshness'], 'stale')
        self.assertEqual(old['staleAfterSeconds'], 90)
        self.assertGreater(old['lastCompletionAgeSeconds'], 90)
        self.assertFalse(old['workerMissedCyclesVerified'])
        self.assertNotIn('workerStoppedVerified', old)
        night = dict(sample, configuredSeconds=300, plannedWaitSeconds=298)
        in_window = diagnostics.collection_cycle_snapshot(night, now=base+timedelta(minutes=5))
        self.assertEqual(in_window['freshness'], 'current')
        self.assertEqual(in_window['staleAfterSeconds'], 900)

    def test_future_clock_and_unknown_now_fail_closed(self):
        sample = self.sample()
        now = datetime(2026, 10, 26, 8, 35, 26, tzinfo=timezone.utc)
        future = diagnostics.collection_cycle_snapshot(sample, now=now)
        self.assertEqual(future['status'], 'unavailable')
        self.assertEqual(diagnostics.collection_cycle_snapshot(
            sample, now=datetime(2026, 10, 26, 8, 35, 31))['status'], 'unavailable')

    def test_forged_clock_or_verified_missed_worker_is_unavailable(self):
        original = self.sample()
        cases = (
            ('workerMissedCyclesVerified', True),
            ('readOnly', False),
            ('observedCycles', 21),
            ('observedCycles', True),
            ('comparableStartIntervals', 9),
            ('configuredSeconds', -1),
            ('plannedWaitSeconds', '30'),
            ('lastDurationMs', -1),
            ('lastStartedAt', '2099-10-26T08:35:30Z'),
            ('lastCompletedAt', '2026-10-25T08:35:30Z'),
            ('maxObservedStartGapSeconds', float('nan')),
            ('scope', 'all-systems-verified'),
        )
        for key, val in cases:
            case = dict(original, **{key:val})
            with self.subTest(key=key):
                self.assertEqual(diagnostics.collection_cycle_snapshot(case)['status'],
                                 'unavailable')
        future = dict(original, lastStartedAt='2099-10-26T08:35:30Z',
                      lastCompletedAt='2099-10-26T08:35:31Z')
        self.assertEqual(diagnostics.collection_cycle_snapshot(future)['status'],
                         'unavailable')
        self.assertEqual(diagnostics.collection_cycle_snapshot({})['status'], 'unavailable')
        waiting = dict(status='not-observed', observedCycles=0,
                       readOnly=True, workerMissedCyclesVerified=False,
                       scope=original['scope'])
        self.assertEqual(diagnostics.collection_cycle_snapshot(waiting)['status'],
                         'not-observed')


class EvaluatorQueueSampleTests(unittest.TestCase):
    """Caller-supplied samples are not full provider coverage or lost-tick proof."""
    def log(self, at, instance, completed, **changes):
        counters = dict(completed=completed, failed=0, queueTimeouts=0,
                        shared=0, waiting=0, lastWaitMs=2, lastDurationMs=400)
        counters.update(changes)
        return {'timestamp':at, 'message':'BOB_EVALUATOR '+json.dumps(counters),
                'labels':[{'name':'resource','value':'srv-demo123'},
                          {'name':'type','value':'app'},
                          {'name':'instance','value':'srv-demo123-'+instance}]}

    def report(self, rows, **kwargs):
        return diagnostics.evaluator_queue_log_sample(
            rows, window_start='2026-10-26T10:12:00Z',
            window_end='2026-10-26T10:19:00Z',
            resource_id='srv-demo123', **kwargs)

    def test_rollout_counters_are_separate_and_only_sampled(self):
        rows=[self.log('2026-10-26T10:12:01Z','old-PRIVATE',251,
                       waiting=2, lastWaitMs=2623),
              self.log('2026-10-26T10:12:31Z','old-PRIVATE',252,
                       waiting=0, lastWaitMs=2),
              self.log('2026-10-26T10:13:01Z','new-PRIVATE',1,
                       waiting=1, lastWaitMs=835)]
        result=self.report(rows)
        self.assertEqual(result['status'],'classified-sample')
        self.assertEqual(result['distinctProcessInstances'],2)
        self.assertEqual(result['sameInstanceCounterRegressions'],0)
        self.assertEqual(result['validEvaluatorRecords'],3)
        self.assertEqual(result['maxObservedWaiting'],2)
        self.assertEqual(result['maxLastWaitMs'],2623)
        self.assertFalse(result['observedNonzeroFailureCounter'])
        self.assertFalse(result['observedNonzeroQueueTimeoutCounter'])
        self.assertFalse(result['queueLossVerified'])
        self.assertFalse(result['liveVerified'])
        self.assertFalse(result['completeTrafficProven'])
        self.assertNotIn('old-PRIVATE', json.dumps(result))
        self.assertNotIn('new-PRIVATE', json.dumps(result))

    def test_partial_invalid_rows_and_counter_rollback_fail_open_not_healed(self):
        rows=[self.log('2026-10-26T10:12:01Z','one',4),
              self.log('2026-10-26T10:12:31Z','one',3,
                       failed=1, queueTimeouts=2)]
        cross=self.log('2026-10-26T10:13:01Z','other',1)
        cross['labels'][0]['value']='srv-other'
        future=self.log('2099-01-01T00:00:00Z','other',1)
        invalid=self.log('2026-10-26T10:13:15Z','bad',1,waiting=True)
        rows.extend((cross,future,invalid, {'message':'SECRET','timestamp': 'bad'}))
        x=self.report(rows,has_more=True)
        self.assertEqual(x['validEvaluatorRecords'],2)
        self.assertEqual(x['distinctProcessInstances'],1)
        self.assertEqual(x['sameInstanceCounterRegressions'],1)
        self.assertTrue(x['observedNonzeroFailureCounter'])
        self.assertTrue(x['observedNonzeroQueueTimeoutCounter'])
        self.assertEqual(x['invalidOrIgnoredRecords'],4)
        self.assertTrue(x['sampleTruncated'])
        self.assertFalse(x['queueLossVerified'])
        self.assertNotIn('SECRET',json.dumps(x))
        empty=self.report([])
        self.assertEqual(empty['status'],'insufficient-evidence')
        self.assertFalse(empty['liveVerified'])
        self.assertEqual(self.report([cross])['status'],'insufficient-evidence')


class DatabaseContentionLogSampleTests(unittest.TestCase):
    """SQL state classifier only; no database is accessed by these tests."""
    @staticmethod
    def row(message, at='2026-10-26T08:03:23Z', resource='srv-sampled'):
        return dict(timestamp=at, message=message, labels=[
            dict(name='resource', value=resource),
            dict(name='instance', value=resource+'-one'),
            dict(name='type', value='app')])

    def sample(self, lines, **extra):
        return diagnostics.database_contention_log_sample(
            lines, resource_id='srv-sampled',
            window_start='2026-10-26T08:03:05Z',
            window_end='2026-10-26T08:04:16Z', **extra)

    def test_original_observed_error_categories_are_separate(self):
        rows=[
            self.row('BOB_PUSH database_busy path=/diagnostic-history error=QueryCanceled'),
            self.row('BOB_PUSH database_busy path=/market-validations/write error=LockNotAvailable'),
            self.row('BOB_RANKING error=LockNotAvailable'),
            self.row('BOB_METRIC_PRODUCT error=LockNotAvailable'),
            self.row('BOB_PRECISION_CAPTURE error=LockNotAvailable'),
            self.row('BOB_METRIC_CAPTURE error=LockNotAvailable'),
            self.row('BOB_VIDEO_OCR error=LockNotAvailable'),
        ]
        result=self.sample(rows)
        self.assertEqual(result['status'], 'classified-sample')
        self.assertEqual(result['errorTypes'], {'QueryCanceled':1,'LockNotAvailable':6})
        self.assertEqual(result['validDatabaseErrorRecords'], 7)
        self.assertFalse(result['providerVerified'])
        self.assertFalse(result['fullDatabaseAuditVerified'])
        self.assertFalse(result['causeVerified'])
        self.assertFalse(result['completeTrafficProven'])
        self.assertFalse(result['realOrders'])
        source={r['source']:r for r in result['sources']}
        self.assertEqual(source['/diagnostic-history']['QueryCanceled'],1)
        self.assertEqual(source['/market-validations/write']['LockNotAvailable'],1)

    def test_wrong_service_clocks_errors_and_secrets_fail_closed(self):
        rows=[
            self.row('BOB_PUSH database_busy path=/user/ACCOUNT?key=SECRET error=QueryCanceled'),
            self.row('BOB_PUSH database_busy path=/diagnostic-history error=RuntimeError'),
            self.row('BOB_PUSH database_busy path=/diagnostic-history error=QueryCanceled',
                     resource='srv-other'),
            self.row('BOB_METRIC_PRODUCT error=LockNotAvailable',at='2099-01-01T00:00:00Z'),
            self.row('BOB_RANKING error=LockNotAvailable',at='no-clock'),
            self.row('BOB_PUSH database_busy path=/diagnostic-history error=QueryCanceled'),
        ]
        report=self.sample(rows,has_more=True)
        self.assertEqual(report['status'],'classified-sample')
        self.assertEqual(report['validDatabaseErrorRecords'],2)
        self.assertEqual(report['invalidOrIgnoredRecords'],4)
        self.assertTrue(report['sampleTruncated'])
        self.assertIn('other-unclassified',str(report['sources']))
        self.assertNotIn('ACCOUNT',json.dumps(report))
        self.assertNotIn('SECRET',json.dumps(report))
        self.assertNotIn('srv-other',json.dumps(report))
        self.assertFalse(report['causeVerified'])
        self.assertEqual(self.sample([])['status'],'insufficient-evidence')
        self.assertEqual(self.sample([self.row('BOB_RANKING error=PermissionDenied')])['status'],
                         'insufficient-evidence')


class ReadAccessManifestMappingTests(unittest.TestCase):
    def test_exact_100_items_are_file_mapped_not_falsely_live_verified(self):
        from pathlib import Path
        manifest=json.loads((Path(__file__).resolve().parent/
            'Besser_werden/lesezugriff_100_status.json').read_text(encoding='utf-8'))
        report=diagnostics.read_access_coverage(manifest)
        self.assertEqual(report['status'],'inventory-only')
        self.assertEqual(report['total'],100)
        self.assertEqual(report['verified'],6)
        self.assertEqual(report['unverified'],94)
        self.assertEqual(report['buildBoundAcceptance']['acceptedGoalIds'],[2,7,8,13,18,69])
        expected_paths = {row['codeEvidence'] for row in manifest['tasks']}
        self.assertEqual(report['codeFilesMapped'], len(expected_paths))
        self.assertGreaterEqual(report['codeFilesMapped'], 10)
        self.assertEqual(report['codeFilesPresent'], len(expected_paths))
        self.assertEqual(report['codeFilesMissing'], 0)
        self.assertEqual(sum(report['counts'].values()),100)
        evidence = report['evidenceReview']
        self.assertEqual(evidence['status'],'historical-evidence-baseline-not-feature-validation')
        self.assertEqual(evidence['goalsReviewed'],100)
        self.assertEqual(evidence['goalsWithPartialLiveObservations'],35)
        self.assertEqual(evidence['individuallyVerified'],0)
        self.assertNotIn('positionsReceived',json.dumps(evidence))

    def test_untrusted_inventory_paths_are_rejected_without_file_reads(self):
        from pathlib import Path
        manifest=json.loads((Path(__file__).resolve().parent/
            'Besser_werden/lesezugriff_100_status.json').read_text(encoding='utf-8'))
        for fake in ('../secret', '/etc/passwd', 'a//b', 'x/./y'):
            variant={**manifest, 'tasks':[dict(t) for t in manifest['tasks']]}
            variant['tasks'][0]['codeEvidence']=fake
            self.assertEqual(diagnostics.read_access_coverage(variant)['status'],'unavailable')


class FocusedReadAccessTests(unittest.TestCase):

    def test_simulation_triage_groups_recorded_gaps_without_invented_fills(self):
        cases=[{'status':'inconclusive',
                'events':[{'kind':'data-gap'},{'kind':'deferred-sale'}]},
               {'status':'inconclusive','events':[{'kind':'deferred-sale'}]},
               {'status':'closed','events':[{'kind':'data-gap'}]}]
        evidence={'background':{'status':'ok'},
                  'simulationAndPush':{'status':'observed',
                      'accounts':[{'recentCases':{'items':cases}}]}}
        result=diagnostics.triage_snapshot(evidence)
        rows=[x for x in result['items'] if x['code']=='SIMULATION_OUTCOMES_UNKNOWN']
        self.assertEqual(len(rows),1)
        self.assertIn('2 gespeicherte',rows[0]['finding'])
        self.assertIn('1 mit protokollierter Datenlücke',rows[0]['finding'])
        self.assertIn('2 mit verschobenem Modellverkauf',rows[0]['finding'])
        self.assertFalse(rows[0]['tradeApproval'])

    def test_only_allowlisted_focus_can_read_existing_diagnostics(self):
        diagnostics_reader=Mock(return_value=diagnostics.collect({
            'market':lambda:{'status':'observed','token':'other-area-secret'},
            'simulationAndPush':lambda:{'status':'observed',
                'accounts':[{'profile':'100','cash':98}],
                'details':{'status':'observed','areas':{
                    'tradeMonitoring':{'status':'observed','items':[{'active':False}]},
                    'repairs':{'status':'observed','items':[{'code':'WORKER'}]}}}}}))
        req={'jsonrpc':'2.0','id':1,'method':'tools/call',
             'params':{'name':'bob_diagnostics','arguments':{'focus':'trades'}}}
        _,resp=bob_mcp.handle(req,Mock(),diagnostics_reader)
        self.assertFalse(resp['result']['isError'])
        data=json.loads(resp['result']['content'][0]['text'])
        self.assertEqual(data['focus'],'trades')
        self.assertEqual(data['areas']['simulationAndPush']['details']['areas']
                         ['tradeMonitoring']['items'][0]['active'],False)
        self.assertNotIn('accounts',json.dumps(data))
        self.assertNotIn('other-area-secret',json.dumps(data))
        self.assertNotIn('repairs',json.dumps(data))
        self.assertTrue(data['readOnly'])
        self.assertFalse(data['realOrders'])
        self.assertEqual(diagnostics_reader.call_count,1)

    def test_invalid_focus_rejected_without_starting_reader(self):
        reader=Mock(side_effect=AssertionError('reader must not run'))
        for args in ({'focus':'../../secret'}, {'focus':5},
                     {'focus':'mobile','path':'/trading'},
                     {'focus':None}, {'focus':[]}, []):
            request={'jsonrpc':'2.0','id':1,'method':'tools/call',
                     'params':{'name':'bob_diagnostics','arguments':args}}
            _,result=bob_mcp.handle(request,Mock(),reader)
            self.assertEqual(result['error']['code'],-32602)
        reader.assert_not_called()

    def test_focused_repair_detail_isolated_and_missing_is_honest(self):
        raw={'readOnly':True,'realOrders':False,'observedAt':'old-time','schemaVersion':2,
             'areas':{'simulationAndPush':{'status':'observed','details':{
                 'status':'observed','areas':{'repairs':{'status':'observed',
                      'items':[{'code':'SAVED'}]},'tradeEvents':{'secret':'exclude'}}}},
                      'selfHealing':{'status':'observed'},
                      'market':{'price':'exclude-me'}}}
        result=diagnostics.focused_report(raw,'repairs')
        self.assertEqual(result['observedAt'],'old-time')
        self.assertEqual(result['areas']['simulationAndPush']['details']['areas']
                         ['repairs']['items'][0]['code'],'SAVED')
        self.assertNotIn('tradeEvents',json.dumps(result))
        self.assertNotIn('exclude-me',json.dumps(result))
        missing=diagnostics.focused_report(raw,'signals')
        self.assertEqual(missing['areas']['simulationAndPush']['signalHistory']['status'],
                         'unavailable')

    def test_summary_distinguishes_explained_conflicts_and_backup_failures(self):
        areas={'products':{'items':[{'fieldRecovery':{'state':'conflict','conflicts':['ko'],
               'sourceDecisions':{'ko':{'state':'dated-issuer-selected'}}}}]},
            'market':{'candles':{'1m':{'integrity':{'source':'biquote','state':'ok'}}}},
            'sourceReliability':{'sources':{'xaus/1m':{'state':'stale'}}}}
        result=diagnostics.summary(areas)
        self.assertEqual(result['assessment'],'observed-only')
        self.assertEqual(result['attention'][0]['severity'],'info')
        areas['products']['items'][0]['fieldRecovery']['unresolvedConflicts']=['ko']
        self.assertEqual(diagnostics.summary(areas)['assessment'],'needs-attention')

    def test_stale_backup_not_marked_active_market_outage(self):
        evidence={
            'background':{'status':'ok'},
            'market':{'candles':{
                '1m':{'integrity':{'source':'biquote · XAU/USD Broker/MT5','state':'ok'}},
                '5m':{'integrity':{'source':'biquote · XAU/USD Broker/MT5','state':'ok'}}}},
            'sourceReliability':{'sources':{
                'xaus/1m':{'state':'stale'},
                'xaus/5m':{'state':'stale'},
                'biquote/1m':{'state':'current'},
                'biquote/5m':{'state':'current'}}},
            'simulationAndPush':{'status':'observed'}}
        rows=diagnostics.triage_snapshot(evidence)['items']
        codes=[a['code'] for a in rows]
        self.assertIn('SOURCE_ALTERNATIVE_STALE',codes)
        self.assertNotIn('SOURCE_SELECTED_DEGRADED',codes)
        self.assertNotIn('SOURCE_HEALTH_HISTORY',codes)
        self.assertIn('alternative Kerzenquellen',next(
            a['finding'] for a in rows if a['code']=='SOURCE_ALTERNATIVE_STALE'))

    def test_selected_source_stale_is_high_priority(self):
        evidence={'background':{'status':'ok'},'market':{'candles':{
            '1m':{'integrity':{'source':'biquote · XAU/USD Broker/MT5','state':'recent-gap'}}}},
            'sourceReliability':{'sources':{'biquote/1m':{'state':'stale'},
                                           'xaus/1m':{'state':'current'}}},
            'simulationAndPush':{'status':'observed'}}
        rows=diagnostics.triage_snapshot(evidence)['items']
        active=next(a for a in rows if a['code']=='SOURCE_SELECTED_DEGRADED')
        self.assertEqual(active['priority'],'high')
        self.assertFalse(active['tradeApproval'])
        self.assertFalse(active['repairVerified'])

    def test_priorities_avoid_false_live_market_and_trade_approval(self):
        source={'sources':{'archive/1m':{'state':'stale','events':[{'state':'stale'}]}}}
        areas={'background':{'status':'ok'},
            'products':{'lastCheckedAt':'original-time',
                        'items':[{'isin':'DE000FG8NHQ3','state':'incomplete'},
                                 {'isin':'DE000FG7UE38','state':'terminated'}]},
            'sourceReliability':source,
            'simulationAndPush':{'status':'observed','accounts':[{
                'recentCases':{'items':[{'status':'inconclusive'}]}}]},
            'newFeatures':{'researchSelfReview':{'status':'unavailable','sourceReportAt':'old'}}}
        t=diagnostics.triage_snapshot(areas)
        issues={x['code']:x for x in t['items']}
        self.assertIn('PRODUCT_EVIDENCE_GAPS',issues)
        self.assertIn('SOURCE_HEALTH_HISTORY',issues)
        self.assertIn('SIMULATION_OUTCOMES_UNKNOWN',issues)
        self.assertIn('RESEARCH_SELF_REVIEW_PENDING',issues)
        self.assertNotIn('BACKGROUND_NOT_CONFIRMED',issues)
        self.assertEqual(issues['PRODUCT_EVIDENCE_GAPS']['evidenceAt'],'original-time')
        self.assertNotIn('DE000FG7UE38',issues['PRODUCT_EVIDENCE_GAPS']['finding'])
        self.assertTrue(all(x['tradeApproval'] is False and x['repairVerified'] is False
                            for x in t['items']))


class FastSimulationStatusTests(unittest.TestCase):
    def test_current_day_uses_indexed_scope_without_historical_reports(self):
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        portfolios = Mock()
        portfolios.names.return_value = {'bob_paper_cases':'bob_paper_cases'}
        core = {'status':'observed', 'accounts':[{'profile':'balanced', 'status':'running', 'checkedAt':123}], 'paper':{'state':'ok'}}
        with patch.object(diagnostics, 'push_snapshot', return_value=core) as base, patch.object(diagnostics, 'analysis_snapshot', return_value={'status':'observed'}), patch('comparison_health.report') as history:
            result = diagnostics.simulation_status(conn, Mock(), Mock(), portfolios)
        self.assertFalse(base.call_args.kwargs['extended'])
        history.assert_not_called()
        selects = [c for c in conn.execute.call_args_list if c.args[0].startswith('SELECT')]
        self.assertEqual(len(selects), 1)
        self.assertIn('WHERE day=%s ORDER BY started_at DESC LIMIT 5', selects[0].args[0])
        self.assertEqual(result['accounts'][0]['recentCases']['items'], [])
        self.assertEqual(result['historicalEvidence']['status'], 'not-requested')

    def test_case_timeout_preserves_actual_control_and_heartbeat(self):
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute.return_value.fetchall.side_effect = TimeoutError()
        portfolios = Mock()
        portfolios.names.return_value = {'bob_paper_cases':'bob_paper_cases'}
        core = {'status':'observed', 'accounts':[{'profile':'balanced', 'status':'running', 'reason':'wait', 'checkedAt':123}], 'paper':{'state':'ok'}}
        with patch.object(diagnostics, 'push_snapshot', return_value=core), patch.object(diagnostics, 'analysis_snapshot', return_value={}):
            result = diagnostics.simulation_status(conn, Mock(), Mock(), portfolios)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['paper']['state'], 'ok')
        self.assertEqual(result['accounts'][0]['reason'], 'wait')
        self.assertEqual(result['accounts'][0]['recentCases']['status'], 'unavailable')

    def test_comparison_status_is_bounded_and_separate_from_live_controls(self):
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [({'status':'inconclusive'},)]
        portfolios = Mock()
        portfolios.POLICIES = {'balanced':{}}
        portfolios.names.return_value = {
            'bob_paper_cases':'bob_paper_balanced_cases',
            'bob_paper_days':'bob_paper_balanced_days'}
        with patch('comparison_health.report', return_value={'status':'observed','items':{}}), \
             patch.object(diagnostics, 'entry_block_evidence',
                          return_value={'status':'observed','accounts':[]}), \
             patch('paper_case_review.project_case',
                   return_value={'status':'inconclusive'}):
            result = diagnostics.comparison_status(conn, portfolios)
        self.assertEqual(result['status'],'observed')
        self.assertTrue(result['readOnly'])
        self.assertFalse(result['realOrders'])
        self.assertEqual(result['accountSamples'][0]['profile'],'balanced')
        self.assertEqual(result['accountSamples'][0]['recentCases']['status'],'observed')
        selects=[call.args[0] for call in conn.execute.call_args_list
                 if call.args and call.args[0].startswith('SELECT')]
        self.assertEqual(selects,[
            'SELECT payload FROM bob_paper_balanced_cases ORDER BY started_at DESC LIMIT 5',
            """SELECT observed_at, payload FROM bob_diagnostic_history
WHERE stage='paper-input' AND recorded_at >= now() - interval '7 days'
ORDER BY recorded_at DESC LIMIT 1"""])
        self.assertIn('paperInputLatest',result['gapEvidence'])
