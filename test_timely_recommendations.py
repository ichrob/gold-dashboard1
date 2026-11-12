import copy
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch,Mock
import paper_simulation as sim
import spot_data
import push_delivery_history
import product_repair_learning
import paper_forward_validation as validation
from test_paper_reflection import settled

NOW=1793844000000

def bundle(at):
    return {'spots':{'is_genuine_xauusd_spot':True,'xaus_is_spot':True,
        'spot_price_as_of':datetime.fromtimestamp(at/1000,timezone.utc).isoformat()},
        'history':{'bars_by_tf':{'15m':[{'openTime':NOW-900000,'isOpen':False}]}}}


class TimelyTests(unittest.TestCase):
    def test_stale_analysis_retries_one_complete_newer_snapshot(self):
        old=bundle(NOW-65000);new=bundle(NOW-5000)
        analyze=Mock(side_effect=[{'dataAt':NOW-65000},{'dataAt':NOW-5000}])
        used,market=sim.analyze_latest_bundle(old,{},lambda:new,analyze,lambda:NOW)
        self.assertIs(used,new);self.assertEqual(market['dataAt'],NOW-5000)
        self.assertEqual(analyze.call_count,2)
        self.assertIs(analyze.call_args_list[1].args[0],new)
        newer=bundle(NOW-1000)
        analyze=Mock(return_value={'dataAt':NOW-65000})
        # Even a still-stale second result cannot create an unbounded retry loop.
        sim.analyze_latest_bundle(old,{},lambda:newer,analyze,lambda:NOW)
        self.assertEqual(analyze.call_count,2)

    def test_partial_or_fresh_input_never_retries_or_mixes_quotes(self):
        old=bundle(NOW-65000);partial=bundle(NOW-1000);partial['history']={}
        analyze=Mock(return_value={'dataAt':NOW-65000})
        self.assertIs(sim.analyze_latest_bundle(old,{},lambda:partial,analyze,lambda:NOW)[0],old)
        self.assertEqual(analyze.call_count,1)
        analyze=Mock(return_value={'dataAt':NOW-5000})
        sim.analyze_latest_bundle(old,{},lambda:bundle(NOW),analyze,lambda:NOW)
        self.assertEqual(analyze.call_count,1)
        analyze=Mock(side_effect=[{'dataAt':NOW-5000,'ready':False},{'dataAt':NOW-1000,'ready':True}])
        fresh=bundle(NOW-1000)
        self.assertIs(sim.analyze_latest_bundle(old,{},lambda:fresh,analyze,lambda:NOW)[0],fresh)
        self.assertEqual(analyze.call_count,2)

    def test_quote_focus_keeps_active_and_overdue_products_ahead(self):
        result=product_repair_learning.request_order(['focus','active','overdue','other'],['active'],
            {'focus':NOW-30000,'active':NOW-30000,'overdue':NOW-95000,'other':NOW-30000},NOW,preferred=['focus'])
        self.assertEqual(result[:3],['overdue','active','focus'])
        products=[{'isin':'factor','name':'Gold Faktor','productDirection':'LONG'},
                  {'isin':'good','productDirection':'LONG'},
                  {'isin':'ko','productDirection':'LONG','knockedOut':True}]
        market={'ready':True,'priceFresh':True,'direction':'NEUTRAL','entryPreparation':{'direction':'LONG'}}
        self.assertEqual(sim.quote_focus(products,market),['good'])
        self.assertEqual(sim.quote_focus(products,{**market,'priceFresh':False}),[])

    def test_refresh_lock_does_not_hold_up_a_fresh_quote_or_standby(self):
        now=datetime.now(timezone.utc)
        fresh={'price':4100.,'at':now.isoformat(),'source':'Gold-API.com · XAU/USD Spot'}
        with patch.object(spot_data,'_quote',fresh),patch.object(spot_data,'_error',None), \
             patch('product_quotes.issuer_json',side_effect=AssertionError('duplicate fetch')):
            spot_data._lock.acquire()
            try:
                actual=spot_data.current();self.assertEqual(actual['at'],fresh['at'])
                actual['price']=9999
                self.assertEqual(spot_data._quote['price'],4100.)
            finally:spot_data._lock.release()
        backup={**fresh,'source':'standby'}
        with patch.object(spot_data,'_quote',{**fresh,'at':(now-timedelta(seconds=61)).isoformat()}), \
             patch('xaus_spot.peek',return_value=backup):
            spot_data._lock.acquire()
            try:self.assertTrue(spot_data.current()['backupActive'])
            finally:spot_data._lock.release()

    def test_latency_does_not_invent_missing_negative_or_android_receipts(self):
        r=dict(dataAt=NOW-10000,generatedAt=NOW-1000,analysisRequestedAt=NOW-3000,
               analysisCompletedAt=NOW-2000,providerStartedAt=NOW)
        out=push_delivery_history.latency(r)
        self.assertEqual(out['sourceToGeneratedMs'],9000)
        self.assertEqual(out['analysisPipelineMs'],1000)
        self.assertEqual(out['generatedToProviderMs'],1000)
        self.assertIsNone(out['sourceToBrowserReceiptMs'])
        self.assertIsNone(push_delivery_history.latency({**r,'dataAt':NOW+1})['sourceToGeneratedMs'])
        self.assertIsNone(push_delivery_history.latency({})['analysisPipelineMs'])

    def test_forward_validation_never_backfills_or_tunes_rules(self):
        market={'ready':True,'priceFresh':True,'dataAt':NOW,'ruleVersion':'fixed-v1','learningPolicy':'baseline'};control={}
        validation.start(control,market,NOW)
        def case(start):
            c=settled();c.update(startedAt=start,closedAt=start+60000,
                entryQuote={'isin':'test','ask':10,'source':'observed','askAt':start},
                product={'isin':'test'},analysis={**market,'dataAt':start-1000},
                entryChecklist={'decision':'entry','ruleVersion':'fixed-v1'},
                selectionEvidence={'capturedAt':start,'selectedIsin':'test','rankedShortlist':[{'isin':'test'}]},
                entryTiming={'version':1,'sourceAt':start-1000,'decisionAt':start})
            return c
        old=case(NOW-1);validation.record(control,old,NOW+60000)
        self.assertEqual(control['forwardValidation']['excluded'],1)
        first=case(NOW+1);validation.record(control,first,NOW+60001)
        validation.record(control,first,NOW+60002)
        second=case(NOW+validation.DAY+1)
        validation.record(control,second,NOW+validation.DAY+60001)
        state=control['forwardValidation']
        self.assertEqual(state['calibration']['cases'],1)
        self.assertEqual(state['validation']['cases'],1)
        self.assertFalse(state['automaticPolicyChanges']);self.assertFalse(state['actualNetKnown'])
        changed=case(NOW+2);changed['analysis']={'ruleVersion':'changed'}
        validation.record(control,changed,NOW+60002)
        gap=case(NOW+3);gap['events'].append({'kind':'data-gap'})
        validation.record(control,gap,NOW+60003)
        self.assertEqual(control['forwardValidation']['excluded'],3)
        self.assertEqual(control['forwardValidation']['calibration']['cases'],1)

    def test_provider_attempt_has_clock_metadata_without_notification_contents(self):
        import json
        import push_server
        from types import SimpleNamespace
        clocks=dict(dataAt=NOW-10000,generatedAt=NOW-1000,
                    analysisRequestedAt=NOW-3000,analysisCompletedAt=NOW-2000)
        with patch.object(push_server,'_webpush',return_value=SimpleNamespace(status_code=201)), \
             patch.object(push_server.diagnostic_history,'emit') as emit:
            push_server.webpush(data=json.dumps(dict(body='PRIVATE',data=clocks)),subscription_info={'endpoint':'SECRET'})
        data=emit.call_args.args[2]
        for key,value in clocks.items():self.assertEqual(data[key],value)
        self.assertIsInstance(data['providerStartedAt'],int)
        self.assertGreaterEqual(data['providerDurationMs'],0)
        self.assertNotIn('PRIVATE',str(data));self.assertNotIn('SECRET',str(data))

    def test_optional_metric_failure_is_atomic_and_cannot_break_the_ledger(self):
        market={'ready':True,'priceFresh':True,'dataAt':NOW,'ruleVersion':'fixed-v1'}
        control={'cash':100.};validation.start(control,market,NOW)
        control['forwardValidation']['excluded']='damaged counter'
        before=copy.deepcopy(control)
        case=settled()
        self.assertFalse(validation.record(control,case,NOW+60000))
        self.assertEqual(control,before)
        self.assertNotIn('forwardValidationRecorded',case)
