import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import product_source_recovery as recovery
import product_quotes

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        recovery._FAILURES.clear()

    def test_retry_backoff_and_restored_call(self):
        events=[]
        def fail(): raise OSError('private upstream text')
        for now, delay in [(0,30),(30,60),(90,120),(210,240),(450,300),(750,300)]:
            self.assertEqual(recovery.attempt('comdirect-fetch','test',fail,{},events,now=now),{})
            self.assertEqual(events[-1]['retryAfterSeconds'],delay)
        self.assertEqual(recovery.attempt('comdirect-fetch','test',lambda:self.fail('must wait'),{},events,now=751),{})
        self.assertEqual(events[-1]['state'],'waiting')
        self.assertEqual(recovery.attempt('comdirect-fetch','test',lambda:{'state':'pending'},{},events,now=1050),{'state':'pending'})
        self.assertEqual(events[-1]['state'],'call-restored')
        self.assertNotIn('private upstream text',str(events))
        self.assertFalse(recovery._FAILURES)

    def test_partial_mutation_and_invalid_result_discarded(self):
        original={'metadata':{'status':1},'bidAt':'original'};events=[]
        def broken(q,isin):
            q['metadata']['status']=2
            raise ValueError('bad parser')
        self.assertEqual(recovery.enrich('comdirect-terms','test',broken,original,events),original)
        self.assertEqual(original['metadata']['status'],1)
        self.assertEqual(recovery.attempt('swissquote-fetch','test',lambda:None,{},events),{})
        with self.assertRaises(ValueError):recovery.attempt('unapproved','test',lambda:{},{},events)

    def test_other_sources_continue_and_safety_checks_still_run(self):
        isin='DE000FG7N6Z2';original={'isin':isin,'metadata':{},'eligible':False,'bidAt':'original'}
        calls=[]
        def broken(*args):raise OSError('source parser failure')
        def secondary(q,i):
            calls.append('secondary');q['secondaryQuote']={'bidAt':'real source time'};return q
        def validate(q,i):calls.append('validate');return q
        with ExitStack() as stack:
            for name,value in [('comdirect_quotes.get_observation',broken),
                    ('swissquote_quotes.get_observation',lambda i:{}),
                    ('product_quotes._get_quote_primary',lambda i:copy.deepcopy(original)),
                    ('comdirect_fields.apply',broken),('finanzen_terms.apply',lambda q,i:q),
                    ('product_quotes._restore_exact_sg_metadata',lambda q,i:q),
                    ('comdirect_quotes.apply',broken),('swissquote_quotes.apply',secondary),
                    ('leverage_backup.select_analysis_quote',lambda q:{}),
                    ('leverage_backup.apply',lambda q:q),('secondary_validity.apply',validate),
                    ('hybrid_product_price.apply',lambda q:q)]:
                stack.enter_context(patch(name,side_effect=value))
            result=product_quotes._get_quote_bounded(isin)
            self.assertEqual(calls,['secondary','validate'])
            self.assertEqual(result['bidAt'],'original')
            self.assertEqual(result['secondaryQuote']['bidAt'],'real source time')
            self.assertFalse(result['eligible'])
            self.assertEqual(len(result['sourceRecovery']),3)
            with patch('secondary_validity.apply',side_effect=ValueError('invalid evidence')):
                with self.assertRaises(ValueError):product_quotes._get_quote_bounded(isin)

if __name__=='__main__':unittest.main()
