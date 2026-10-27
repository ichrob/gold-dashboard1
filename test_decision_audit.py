import os
import unittest
from datetime import datetime, timezone
import decision_audit as a

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000000
        self.payload=dict(ruleVersion=a.RULE_VERSION,direction='LONG',shadowDirection='NEUTRAL',barAt=self.now-300000,price=100,priceAt=self.now,products=[],selection=[],origin='background')
    def record(self):return a.normalize(self.payload,self.now)[1]
    def test_malformed_nested_evidence_rejected_before_persistence(self):
        from unittest.mock import Mock
        invalid=[{'products':[None]}, {'products':[[]]},
                 {'products':[{'reasons':'incorrect shape'}]},
                 {'products':[{'isin':[]}]}, {'products':[{'researchAt':{}}]},
                 {'gateReasons':'incorrect shape'}]
        for update in invalid:
            with self.subTest(update=update):
                conn=Mock()
                with self.assertRaises(ValueError):a.write(conn,{**self.payload,**update})
                conn.execute.assert_not_called()
    def test_optional_product_reasons_may_be_null(self):
        record=a.normalize({**self.payload,'products':[{'isin':'DE000BOB0018','reasons':None}]},self.now)[1]
        self.assertEqual(record['products'][0]['isin'],'DE000BOB0018')
    def test_idempotent_frozen_decision(self):
        key,r=a.normalize(self.payload,self.now)
        self.assertEqual(key,a.normalize(self.payload,self.now+1000)[0])
        self.assertNotEqual(key,a.normalize({**self.payload,'direction':'SHORT'},self.now)[0])
        self.assertTrue(r['marketEvaluable'])
    def test_invalid_or_stale_not_evaluated(self):
        for at in (None,self.now+1,self.now-180001):
            r=a.normalize({**self.payload,'priceAt':at},self.now)[1]
            self.assertIsNone(a.outcome(r,{'at':self.now+900000,'price':101},15))
        with self.assertRaises(ValueError):a.normalize({**self.payload,'barAt':self.now+1},self.now)
    def test_forward_only_outcome_and_neutral(self):
        r=self.record()
        for at in (self.now+899999,self.now+960001):self.assertIsNone(a.outcome(r,{'at':at,'price':101},15))
        self.assertAlmostEqual(a.outcome(r,{'at':self.now+900000,'price':101},15)['directionalPct'],1)
        r['direction']='NEUTRAL';self.assertIsNone(a.outcome(r,{'at':self.now+900000,'price':101},15)['directionalPct'])
    def test_duplicates_and_no_premature_learning(self):
        r=self.record();truths=[{'at':self.now+h*60000,'price':101} for h in (15,60,240)]
        report=a.summarize([(r,truths),(r,truths)])
        self.assertEqual(report['metrics']['60']['evaluated'],1)
        self.assertFalse(report['learning']['ready']);self.assertFalse(report['learning']['automaticRuleChange'])
    def test_intraday_parallel_outcomes_and_missing(self):
        p={**self.payload,'intraday':{'version':'intraday-v1','available':True,'direction':'SHORT','mode':'shadow'}}
        key,r=a.normalize(p,self.now)
        self.assertNotEqual(key,a.normalize(self.payload,self.now)[0])
        truths=[{'at':self.now+h*60000,'price':99} for h in (15,60,240)]
        report=a.summarize([(r,truths)])
        self.assertEqual(report['intraday']['60']['favorable'],1)
        self.assertEqual(report['metrics']['60']['unfavorable'],1)
        r['intraday']['available']=False
        self.assertEqual(a.summarize([(r,truths)])['intraday']['60']['evaluated'],0)
    def test_missing_reasons_are_separate_for_each_horizon_and_test(self):
        r=self.record()
        report=a.summarize([(r,[None,None,None])],now=self.now+3600000)
        self.assertEqual(report['metrics']['15']['missingReasons']['missingFollowup'],1)
        self.assertEqual(report['metrics']['240']['missingReasons']['pending'],1)
        self.assertEqual(report['intraday']['15']['missingReasons']['signalUnavailable'],1)
        self.assertEqual(report['metrics']['15']['evaluated'],0)
        r['marketEvaluable']=False
        self.assertEqual(a.summarize([(r,[None]*3)],now=self.now)['metrics']['15']['missingReasons']['invalidStart'],1)
    def test_product_diagnostics_do_not_invent_results(self):
        r=self.record()
        self.assertEqual(a.product_review([r],now=self.now)['diagnostics']['noSelection'],1)
        r['products']=[dict(isin='DE000FG5NMF2',selected=True,ask=10,quoteAt=self.now)]
        self.assertEqual(a.product_review([r],now=self.now)['diagnostics']['pending'],1)
        report=a.product_review([r],now=self.now+3900001)
        self.assertEqual(report['diagnostics']['missingFollowup'],1)
        self.assertEqual(report['evaluated'],0)
        r['products'][0]['quoteAt']=self.now-90001
        self.assertEqual(a.product_review([r],now=self.now)['diagnostics']['invalidStart'],1)

    def test_product_requires_real_fresh_bid(self):
        r=self.record();r['products']=[dict(isin='DE000FG5NMF2',selected=True,ask=10,quoteAt=self.now)]
        later={**r,'recordedAt':self.now+3600000,'products':[dict(isin='DE000FG5NMF2',bid=11,quoteAt=self.now+3600000)]}
        self.assertEqual(a.product_review([r,later])['evaluated'],1)
        later['products'][0]['quoteAt']=self.now
        self.assertEqual(a.product_review([r,later])['evaluated'],0)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'Postgres fixture unavailable')
class AuditDatabaseTests(unittest.TestCase):
    def test_durable_idempotency_and_report(self):
        import psycopg
        import bob_market_store
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            a.init(conn);bob_market_store.init(conn)
            now=datetime.now(timezone.utc).timestamp()*1000
            payload=dict(direction='NEUTRAL',barAt=now-300000,priceAt=now,price=4000,products=[])
            first=a.write(conn,payload);a.write(conn,payload)
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_decision_audit WHERE id=%s',(first['id'],)).fetchone()[0],1)
            a._harvest_at=0
            self.assertGreaterEqual(a.report(conn)['total'],1)
            conn.rollback()

class RuleIsolationTests(unittest.TestCase):
 def test_legacy_observations_are_not_new_policy_evidence(self):
  now=1800000000000
  payload=dict(direction='LONG',barAt=now-300000,price=100,priceAt=now,products=[],selection=[])
  legacy=a.normalize(payload,now)[1]
  current=a.normalize({**payload,'ruleVersion':a.RULE_VERSION},now)[1]
  truths=[{'at':now+h*60000,'price':101} for h in (15,60,240)]
  report=a.summarize([(legacy,truths),(current,truths)])
  self.assertEqual(report['legacyCount'],1)
  self.assertEqual(report['metrics']['60']['evaluated'],1)
  self.assertNotEqual(a.normalize(payload,now)[0],a.normalize({**payload,'ruleVersion':a.RULE_VERSION},now)[0])

class ReportCoalescingTests(unittest.TestCase):
 def setUp(self):
  a._report_cache=None;a._report_at=0
 def tearDown(self):
  a._report_cache=None;a._report_at=0
 def test_parallel_reads_share_computation_without_sharing_mutable_result(self):
  from concurrent.futures import ThreadPoolExecutor
  from unittest.mock import patch
  with patch.object(a,'_build_report',return_value={'metrics':{'count':1}}) as build:
   with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:a.report(None),range(4)))
   build.assert_called_once();results[0]['metrics']['count']=99
   self.assertEqual(results[1]['metrics']['count'],1)
   self.assertEqual(a.report(None)['metrics']['count'],1)
 def test_expiry_and_errors_do_not_become_successful_cached_report(self):
  from unittest.mock import patch
  with patch.object(a,'_build_report',side_effect=RuntimeError('database unavailable')):
   with self.assertRaises(RuntimeError):a.report(None)
   self.assertIsNone(a._report_cache)
  with patch.object(a,'_build_report',return_value={'metrics':{}}) as build,patch.object(a.time,'monotonic',side_effect=[100,100+a.REPORT_CACHE_SECONDS+1,100+a.REPORT_CACHE_SECONDS+1]):
   a.report(None);a.report(None);self.assertEqual(build.call_count,2)
 def test_report_query_is_bounded_for_interactive_reads(self):
  from unittest.mock import Mock,MagicMock,patch
  conn=MagicMock();rows=[]
  conn.execute.side_effect=[Mock(fetchall=lambda:rows),Mock(),Mock(fetchall=lambda:[]),Mock(),Mock(fetchone=lambda:(0,))]
  with patch.object(a,'harvest') as harvest,patch.object(a.rule_learning,'report',return_value={}),patch.object(a.intraday_comparison,'report',return_value={}):
   with patch.object(a.ranking_learning,'report',return_value={}),patch.object(a.precision_learning,'report',return_value={}),patch.object(a.metric_quality,'report',return_value={}),patch.object(a.product_precision,'report',return_value={}):
       result=a._build_report(conn)
  harvest.assert_not_called()
  query,params=conn.execute.call_args_list[0].args
  self.assertIn('LIMIT %s',query);self.assertEqual(params,(a.REPORT_LIMIT,))
  self.assertEqual(result['reportRecords'],0)



class EarlyImpulseAuditTests(unittest.TestCase):
    def test_normalization_identity_and_no_trade_permission(self):
        now=1800000000000
        payload=dict(ruleVersion=a.RULE_VERSION,direction='NEUTRAL',barAt=now-300000,price=4200,
                     priceAt=now,origin='background',earlyImpulse=dict(
                       version='early-impulse-v1',available=True,direction='LONG',barAt=now-300000,
                       comparisonOnly=True,affectsApproval=False,reason='gold price advancing'))
        key,record=a.normalize(payload,now)
        self.assertEqual(record['direction'],'NEUTRAL')
        self.assertEqual(record['earlyImpulse']['direction'],'LONG')
        self.assertFalse(record['earlyImpulse']['affectsApproval'])
        self.assertNotEqual(key,a.normalize({**payload,'earlyImpulse':{**payload['earlyImpulse'],'direction':'SHORT'}},now)[0])
        bad={**payload,'earlyImpulse':{**payload['earlyImpulse'],'affectsApproval':True}}
        self.assertIsNone(a.normalize(bad,now)[1]['earlyImpulse'])

    def test_forward_outcomes_both_directions_and_dedup(self):
        now=1800000000000
        def make(side,direction,price,offset=0,origin='background'):
            t=now+offset
            payload=dict(ruleVersion=a.RULE_VERSION,direction=direction,barAt=t-300000,price=100,
                         priceAt=t,origin=origin,earlyImpulse=dict(
                           version='early-impulse-v1',available=True,direction=side,
                           barAt=t-300000,comparisonOnly=True,affectsApproval=False))
            record=a.normalize(payload,t)[1]
            return (record,[None,{'at':t+3600000,'price':price},None])
        long=make('LONG','NEUTRAL',101)
        short=make('SHORT','NEUTRAL',99,3600000)
        duplicate=make('LONG','NEUTRAL',90,300000)
        browser=make('SHORT','NEUTRAL',90,7200000,'browser')
        result=a.early_impulse_review([duplicate,browser,short,long])
        self.assertEqual(result['evaluated'],2)
        self.assertEqual(result['favorable'],2)
        self.assertEqual(result['beforeApproval'],2)
        self.assertEqual(result['long']['evaluated'],1)
        self.assertEqual(result['short']['evaluated'],1)
        self.assertFalse(result['automaticRuleChange'])
        missing=make('LONG','NEUTRAL',101,10800000)
        missing=(missing[0],[None,None,None])
        result=a.early_impulse_review([long,short,missing])
        self.assertEqual(result['missing'],1)



class ProspectiveEarlyImpulseTests(unittest.TestCase):
    def _sample(self,timestamp,side,shift,active='NEUTRAL',include=True):
        payload=dict(ruleVersion=a.RULE_VERSION,direction=active,origin='background',
                     barAt=timestamp-300000,priceAt=timestamp,price=4000,
                     earlyImpulse={'version':'early-impulse-v1','available':True,
                                   'direction':side,'barAt':timestamp-300000,
                                   'comparisonOnly':True,'affectsApproval':False})
        row=a.normalize(payload,timestamp)[1]
        truth={'at':timestamp+3600000,'price':4000+shift}
        return row,(None,truth if include else None,None)

    def test_only_prospective_independent_validation_can_label_promising(self):
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        zone=ZoneInfo('Europe/Zurich')
        stamp=lambda date,hour:int(datetime.fromisoformat(date).replace(tzinfo=zone).timestamp()*1000)+hour*3600000
        samples=[]
        for date in ('2026-10-12','2026-10-13','2026-10-14','2026-10-15'):
            for hour,side in ((9,'LONG'),(11,'SHORT'),(13,'LONG'),(15,'SHORT')):
                samples.append(self._sample(stamp(date,hour),side,20 if side=='LONG' else -20))
        first=a.early_impulse_review(samples)
        self.assertEqual(first['phases']['collection']['evaluated'],16)
        self.assertFalse(first['promising'])
        self.assertIn('nicht ausreichend',first['status'])
        for date in ('2026-10-19','2026-10-20','2026-10-21','2026-10-22','2026-10-23'):
            for hour,side in ((9,'LONG'),(11,'SHORT'),(13,'LONG'),(15,'SHORT')):
                samples.append(self._sample(stamp(date,hour),side,20 if side=='LONG' else -20))
        report=a.early_impulse_review(samples)
        self.assertEqual(report['phases']['validation']['evaluated'],20)
        self.assertEqual(report['phases']['validation']['days'],5)
        self.assertTrue(report['promising'])
        self.assertFalse(report['automaticRuleChange'])
        self.assertEqual(report['evaluated'],36)
        self.assertEqual(report['beforeApproval'],36)
        self.assertEqual(report['unconfirmedFavorable'],36)
        self.assertAlmostEqual(report['baselineSumPct'],0)
        negative=[self._sample(stamp('2026-10-23',15),'SHORT',20)]
        loss_samples=samples[:-1]+negative
        # One isolated adverse event is not automatically evidence of failure;
        # replace the entire SHORT validation group to test an adverse alternative.
        changed=[]
        for r,t in loss_samples:
            if r['recordedAt']>=stamp('2026-10-19',0) and r['earlyImpulse']['direction']=='SHORT':
                changed.append((r,(None,{'at':r['recordedAt']+3600000,'price':4020},None)))
            else:
                changed.append((r,t))
        weak=a.early_impulse_review(changed)
        self.assertFalse(weak['promising'])
        self.assertIn('KEIN VORTEIL',weak['status'])

    def test_hourly_dedup_strict_future_and_baseline(self):
        now=int(datetime(2026,10,19,10,tzinfo=timezone.utc).timestamp()*1000)
        first=self._sample(now,'LONG',20,active='LONG')
        next_in_same_hour=self._sample(now+300000,'SHORT',-20)
        second=self._sample(now+3600000,'SHORT',-20)
        missed=self._sample(now+7200000,'LONG',20,include=False)
        r=a.early_impulse_review([next_in_same_hour,second,missed,first])
        self.assertEqual(r['evaluated'],2)
        self.assertEqual(r['missing'],1)
        self.assertEqual(r['matchedActive'],1)
        self.assertEqual(r['beforeApproval'],1)
        self.assertAlmostEqual(r['earlySumPct'],1.0,places=9)
        self.assertAlmostEqual(r['baselineSumPct'],0.5,places=9)
        self.assertAlmostEqual(r['incrementalPct'],0.25,places=9)
        self.assertEqual(r['horizons']['15']['missing'],3)
        self.assertEqual(r['horizons']['240']['missing'],3)


class UnattendedBackgroundAuditWriterTests(unittest.TestCase):
    def test_audit_writer_is_independent_of_push_subscription(self):
        from unittest.mock import Mock, patch
        from push_server import record_market_observation
        conn=Mock()
        market=dict(ruleVersion=a.RULE_VERSION,analysisBarAt=1800000000000-300000,
                    direction='NEUTRAL',ready=True,priceFresh=True,price=4200,dataAt=1800000000000,
                    earlyImpulse=dict(version='early-impulse-v1',available=True,
                                      direction='SHORT',comparisonOnly=True,
                                      affectsApproval=False,barAt=1800000000000-300000))
        with patch('push_server.time.time',return_value=1800000000),patch('push_server.decision_audit.write') as write,patch('push_server.decision_audit.harvest') as harvest:
            self.assertTrue(record_market_observation(conn,market))
            payload=write.call_args.args[1]
            self.assertEqual(payload['direction'],'NEUTRAL')
            self.assertEqual(payload['earlyImpulse']['direction'],'SHORT')
            self.assertFalse(payload['earlyImpulse']['affectsApproval'])
            harvest.assert_not_called()
            self.assertFalse(record_market_observation(conn,{}))
            self.assertEqual(write.call_count,1)

    def test_outcomes_are_backfilled_in_a_separate_transaction(self):
        from unittest.mock import MagicMock, patch
        from push_server import run_audit_harvest_once
        database=MagicMock()
        conn=database.return_value.__enter__.return_value
        with patch('push_server.decision_audit.harvest') as harvest, \
             patch('product_precision.harvest') as precision, \
             patch('push_server.ranking_learning.harvest') as ranking:
            result=run_audit_harvest_once(database)
        harvest.assert_called_once_with(conn)
        precision.assert_called_once_with(conn)
        ranking.assert_called_once_with(conn)
        self.assertEqual(result['failed'],[])
        self.assertEqual(conn.commit.call_count,3)

    def test_one_harvest_timeout_does_not_cancel_the_other_archives(self):
        from unittest.mock import MagicMock, patch
        import psycopg
        from push_server import run_audit_harvest_once
        database=MagicMock()
        conn=database.return_value.__enter__.return_value
        with patch('push_server.decision_audit.harvest',side_effect=psycopg.errors.QueryCanceled('timeout')), \
             patch('product_precision.harvest') as precision, \
             patch('push_server.ranking_learning.harvest') as ranking, \
             patch('builtins.print') as emit:
            result=run_audit_harvest_once(database)
        precision.assert_called_once_with(conn)
        ranking.assert_called_once_with(conn)
        self.assertEqual(result['failed'],['decision'])
        self.assertEqual(conn.commit.call_count,2)
        emit.assert_called_once_with('BOB_AUDIT_HARVEST stage=decision error=QueryCanceled',flush=True)


class ReportBatchRowsTests(unittest.TestCase):
    def test_batch_preserves_order_horizon_alignment_and_missing_evidence(self):
        from unittest.mock import Mock
        conn=Mock()
        conn.execute.side_effect=[
            Mock(fetchall=lambda:[('new',),('old',)]),
            Mock(fetchall=lambda:[('new',{'id':'new'}),('old',{'id':'old'})]),
            Mock(fetchall=lambda:[('old',240,{'price':240}),('new',60,{'price':60}),('old',15,{'price':15})])]
        self.assertEqual(a._load_report_rows(conn),[
            ({'id':'new'},None,{'price':60},None),
            ({'id':'old'},{'price':15},None,{'price':240})])
        self.assertEqual(conn.execute.call_count,3)
        self.assertEqual(conn.execute.call_args.args[1],(['new','old'],))

    def test_page_boundaries_preserve_selected_ids_and_outcome_alignment(self):
        from unittest.mock import Mock, patch
        conn=Mock()
        conn.execute.side_effect=[
            Mock(fetchall=lambda:[('new',),('middle',),('old',)]),
            Mock(fetchall=lambda:[('middle',{'id':'middle'}),('new',{'id':'new'})]),
            Mock(fetchall=lambda:[('middle',60,{'result':'middle'})]),
            Mock(fetchall=lambda:[('old',{'id':'old'})]),
            Mock(fetchall=lambda:[('old',15,{'result':'old'})])]
        with patch.object(a,'REPORT_ROW_BATCH',2):
            rows=a._load_report_rows(conn)
        self.assertEqual([r[0]['id'] for r in rows],['new','middle','old'])
        self.assertIsNone(rows[0][1])
        self.assertEqual(rows[1][2],{'result':'middle'})
        self.assertEqual(rows[2][1],{'result':'old'})
        self.assertEqual(conn.execute.call_count,5)
        # IDs are selected once: no OFFSET drift while fresh events are recorded.
        self.assertIn('ORDER BY recorded_at DESC LIMIT %s',
                      conn.execute.call_args_list[0].args[0])
        self.assertEqual(conn.execute.call_args_list[1].args[1],(['new','middle'],))
        self.assertEqual(conn.execute.call_args_list[3].args[1],(['old'],))

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'test database unavailable')
    def test_postgres_batch_matches_original_report_window(self):
        import psycopg
        from unittest.mock import patch
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_decision_audit (id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, payload JSONB)')
            conn.execute('CREATE TEMP TABLE bob_decision_outcomes (decision_id TEXT, horizon INTEGER, truth JSONB, PRIMARY KEY(decision_id,horizon))')
            for n in range(5):
                conn.execute("INSERT INTO bob_decision_audit VALUES (%s,now() + %s * interval '1 second',%s)",(str(n),n,Jsonb({'id':n})))
                for h in (15,60,240):
                    if n==4 and h!=60:continue
                    conn.execute('INSERT INTO bob_decision_outcomes VALUES (%s,%s,%s)',(str(n),h,Jsonb({'price':n+h})))
            expected=conn.execute("""SELECT a.payload,
              (SELECT truth FROM bob_decision_outcomes WHERE decision_id=a.id AND horizon=15),
              (SELECT truth FROM bob_decision_outcomes WHERE decision_id=a.id AND horizon=60),
              (SELECT truth FROM bob_decision_outcomes WHERE decision_id=a.id AND horizon=240)
              FROM bob_decision_audit a ORDER BY a.recorded_at DESC LIMIT 3""").fetchall()
            with patch.object(a,'REPORT_LIMIT',3):
                actual=a._load_report_rows(conn)
            self.assertEqual(actual,expected)
            self.assertEqual(len(actual),3)
            self.assertIsNone(actual[0][1])
            conn.rollback()


class ProspectiveBoundedRecoveryTests(unittest.TestCase):
    def test_query_fallback_only_adds_safe_fixed_time_constraint(self):
        full_sql,full_params=a._prospective_query()
        self.assertIn("recorded_at >= now()-interval '30 days'",full_sql)
        self.assertIn('WITH RECURSIVE sampled',full_sql)
        self.assertIn('CROSS JOIN LATERAL',full_sql)
        self.assertEqual(full_sql.count('AND recorded_at <= now()'), 2)
        self.assertNotIn('DISTINCT ON',full_sql)
        recent_sql,recent_params=a._prospective_query(recent=True)
        self.assertIn("recorded_at >= now()-interval '24 hours'",
                      recent_sql)
        self.assertEqual(recent_sql.count(
            'AND recorded_at <= now()'), 2)
        self.assertEqual(full_params,(a.RULE_VERSION,a.RULE_VERSION))
        self.assertEqual(recent_params,(a.RULE_VERSION,a.RULE_VERSION))

    def test_one_timeout_produces_explicit_partial_not_30_day_result(self):
        from unittest.mock import MagicMock, Mock, patch
        import psycopg
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=(0,)
        with patch.object(a,'_load_report_rows',return_value=[]), \
             patch.object(a,'_load_prospective_rows',
                          side_effect=[psycopg.errors.QueryCanceled('timeout'),[]]) as loader, \
             patch.object(a.rule_learning,'report',return_value={}), \
             patch.object(a.intraday_comparison,'report',return_value={}), \
             patch.object(a.ranking_learning,'report',return_value={}), \
             patch.object(a.precision_learning,'report',return_value={}), \
             patch.object(a.metric_quality,'report',return_value={}), \
             patch.object(a.product_precision,'report',return_value={}):
            with patch('builtins.print') as emitted:
                result=a._build_report(conn)
        self.assertEqual(loader.call_args_list[1].kwargs,{'recent':True})
        self.assertTrue(result['prospectiveReview']['available'])
        self.assertTrue(result['prospectiveReview']['partialHistory'])
        self.assertEqual(result['prospectiveReview']['validationCoverage'],
                         'last-24-hours-only')
        self.assertFalse(result['prospectiveReview']['automaticRuleChange'])
        timing_record=result['prospectiveReview']['queryTiming']
        self.assertEqual(timing_record['fullWindow'],'30-days')
        self.assertEqual(timing_record['fullState'],'query-timeout')
        self.assertEqual(timing_record['fallbackState'],'completed-partial')
        self.assertEqual(timing_record['fallbackWindow'],'24-hours')
        self.assertIsInstance(timing_record['fullDurationMs'],int)
        self.assertIsInstance(timing_record['fallbackDurationMs'],int)
        self.assertFalse(timing_record['fullWindowQueryCompleted'])
        statuses = [call.args[0] for call in emitted.call_args_list if call.args]
        timing = [line for line in statuses if line.startswith('BOB_AUDIT prospective_timing')]
        self.assertEqual(len(timing), 1)
        self.assertIn('full_state=query-timeout', timing[0])
        self.assertIn('fallback_state=completed-partial', timing[0])
        self.assertIn('full_ms=', timing[0])
        self.assertIn('fallback_ms=', timing[0])
        self.assertNotIn('timeout', timing[0].split('fallback_ms=')[-1])
        self.assertNotIn('password', timing[0])
        self.assertIn('keine 30-Tage-Validierung',result['prospectiveReview']['note'])

    def test_second_timeout_reports_unavailable_without_invented_result(self):
        from unittest.mock import MagicMock, patch
        import psycopg
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=(0,)
        with patch.object(a,'_load_report_rows',return_value=[]), \
             patch.object(a,'_load_prospective_rows',
                          side_effect=psycopg.errors.QueryCanceled('timeout')), \
             patch.object(a.rule_learning,'report',return_value={}), \
             patch.object(a.intraday_comparison,'report',return_value={}), \
             patch.object(a.ranking_learning,'report',return_value={}), \
             patch.object(a.precision_learning,'report',return_value={}), \
             patch.object(a.metric_quality,'report',return_value={}), \
             patch.object(a.product_precision,'report',return_value={}):
            with patch('builtins.print') as emitted:
                result=a._build_report(conn)
        self.assertFalse(result['prospectiveReview']['available'])
        self.assertTrue(result['prospectiveReview']['retryable'])
        self.assertTrue(result['prospectiveReview']['partialHistory'])
        self.assertFalse(result['prospectiveReview']['automaticRuleChange'])
        timing = [call.args[0] for call in emitted.call_args_list if call.args
                  and call.args[0].startswith('BOB_AUDIT prospective_timing')]
        self.assertEqual(len(timing), 1)
        self.assertIn('full_state=query-timeout', timing[0])
        self.assertIn('fallback_state=query-timeout', timing[0])
        self.assertFalse(result['prospectiveReview']['available'])
        timing_record=result['prospectiveReview']['queryTiming']
        self.assertEqual(timing_record['fullState'],'query-timeout')
        self.assertEqual(timing_record['fallbackState'],'query-timeout')
        self.assertFalse(timing_record['fullWindowQueryCompleted'])


class ReportTimeoutRecoveryTests(unittest.TestCase):
    def test_canceled_report_retries_a_smaller_window_and_labels_it(self):
        from unittest.mock import MagicMock, Mock, patch
        import psycopg
        conn=MagicMock()
        conn.execute.side_effect=[Mock(),Mock(fetchall=lambda:[]),Mock(),Mock(fetchone=lambda:(10000,))]
        with patch.object(a,'_load_report_rows',side_effect=[psycopg.errors.QueryCanceled('timeout'),[]]) as load, patch.object(a.rule_learning,'report',return_value={}), patch.object(a.intraday_comparison,'report',return_value={}):
            with patch.object(a.ranking_learning,'report',return_value={}),patch.object(a.precision_learning,'report',return_value={}),patch.object(a.metric_quality,'report',return_value={}),patch.object(a.product_precision,'report',return_value={}):
                result=a._build_report(conn)
        self.assertEqual(load.call_args_list[1].args,(conn,a.REPORT_BUSY_LIMIT))
        self.assertTrue(result['reportWindowReduced'])
        self.assertIn('verkleinertes Auswertungsfenster',result['scope'])
        self.assertEqual(conn.transaction.call_count,3)

    def test_second_timeout_is_not_reported_as_a_success(self):
        from unittest.mock import MagicMock, patch
        import psycopg
        with patch.object(a,'_load_report_rows',side_effect=psycopg.errors.QueryCanceled('timeout')):
            with self.assertRaises(psycopg.errors.QueryCanceled):a._build_report(MagicMock())

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'test database unavailable')
    def test_postgres_cancellation_rolls_back_savepoint_before_retry(self):
        import psycopg
        from unittest.mock import patch
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_decision_audit (id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, payload JSONB)')
            conn.execute('CREATE TEMP TABLE bob_decision_outcomes (decision_id TEXT, horizon INTEGER, truth JSONB, PRIMARY KEY(decision_id,horizon))')
            conn.execute("INSERT INTO bob_decision_audit VALUES ('kept', now(), '{}'::jsonb)")
            calls=[]
            def load(db,limit=None):
                calls.append(limit)
                if len(calls)==1:
                    db.execute("SET LOCAL statement_timeout='1ms'")
                    db.execute('SELECT pg_sleep(0.05)')
                return []
            with patch.object(a,'_load_report_rows',side_effect=load), patch.object(a.rule_learning,'report',return_value={}), patch.object(a.intraday_comparison,'report',return_value={}):
                with patch.object(a.ranking_learning,'report',return_value={}),patch.object(a.precision_learning,'report',return_value={}),patch.object(a.metric_quality,'report',return_value={}),patch.object(a.product_precision,'report',return_value={}):
                    result=a._build_report(conn)
            self.assertEqual(calls,[None,a.REPORT_BUSY_LIMIT])
            self.assertTrue(result['reportWindowReduced'])
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_decision_audit').fetchone()[0],1)
            conn.rollback()
