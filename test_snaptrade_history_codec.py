import copy
import json
import os
import unittest
from unittest.mock import patch
import snaptrade_history_codec as codec
import snaptrade_bridge as b
from test_snaptrade_bridge import CONFIG, A


class CodecTests(unittest.TestCase):
    def test_missing_null_empty_and_zero_are_preserved(self):
        rows = [{'key':'a','fee':0,'date':'2026-10-26','name':''},
                {'key':'b','fee':None,'date':'2026-10-25'},
                {'key':'c','date':'2026-10-25','quantity':1.25}]
        self.assertEqual(codec.unpack(codec.pack(rows)), rows)
        self.assertEqual(codec.unpack(codec.pack([])), [])

    def test_corrupt_and_oversized_archives_fail_closed(self):
        valid = codec.pack([{'key':'a','date':'2026-10-26'}])
        for change in ({'columnEncoding':2}, {'columnEncoding':True},
                       {'columns':[['key','key']]}, {'columns':[['x'*65]]},
                       {'records':[[False,'a','b']]}, {'records':[[9,'a','b']]},
                       {'records':[[0,'a']]}, {'records':[[0,'a','b','c']]},
                       {'records':valid['records']*(codec.MAX_ROWS+1)}):
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                codec.unpack({**valid, **change})
        with patch.object(codec,'MAX_EXPANDED_BYTES',5),self.assertRaises(ValueError):
            codec.unpack(valid)

    def test_legacy_ledger_and_encrypted_restart(self):
        rows=[{'key':'a','date':'2026-10-26','fee':0,'price':12.25}]
        original={'owner':b.portfolio.identity(CONFIG['clientId']), 'history':[], 'changes':[],
                  'journal':{'a':{'activities':{'rows':rows,'complete':True,'nextOffset':1}}}}
        self.assertEqual(codec.decode_ledger(copy.deepcopy(original)),original)
        db={}
        def storage(action,payload=None):
            if action=='state-save':db.update(payload);return {'saved':True}
            return db
        with patch.dict(os.environ,PUSH_SERVICE_TOKEN='local-test'),patch.object(b,'storage',side_effect=storage),patch.object(b,'_LEDGER',original),patch.object(b,'_LEDGER_OWNER',None):
            b.save_ledger()
            self.assertEqual(b.load_ledger(CONFIG),original)
        self.assertEqual(original['journal']['a']['activities']['rows'],rows)

    def test_rich_history_exceeding_old_byte_limit_completes_after_restarts(self):
        raw=[dict(id=str(i),type='BUY' if i%4==0 else 'FEE',trade_date='2026-10-26T10:00:00+00:00',
                  description='Synthetic activity description with full source detail',
                  currency={'code':'CHF'},units=1,price=12.25,amount=-12.25,fee=0,
                  fx_rate=0.97, external_reference_id='synthetic-reference-'+str(i)) for i in range(12599)]
        self.assertGreater(len(json.dumps(b.activity_rows(raw)).encode()), b.HISTORY_JOURNAL_BYTES)
        state=None
        def get(path,config,params=None):
            if path.endswith('/orders'): return []
            calls.append(params['offset']); start=params['offset']
            return {'data':raw[start:start+500], 'pagination':{'total':len(raw)}}
        for cycle in range(8):
            calls=[]
            with patch.object(b.time,'time',return_value=2000000000+cycle*601):
                state=b.read_journal(A,CONFIG,state,get=get)
            self.assertLessEqual(len(calls),5)
            encoded=codec.encode_ledger({'journal':{'a':state}})
            self.assertLess(len(json.dumps(encoded,separators=(',',':')).encode()),b.HISTORY_MAX_BYTES)
            state=codec.decode_ledger(json.loads(json.dumps(encoded)))['journal']['a']
            if state['activities']['complete']:break
            self.assertEqual(state['activities']['activityCoverageReason'],'PAGE_LIMIT')
        self.assertTrue(state['activities']['complete'])
        self.assertEqual(len(state['activities']['rows']),12599)

    def test_version_one_partial_archive_resumes_without_starting_over(self):
        from test_snaptrade_history_resume import HistoryResumeTests
        fixture=HistoryResumeTests(); fixture.calls=[]
        with patch.object(b.time,'time',return_value=2000000000):
            old=b.read_journal(A,CONFIG,get=fixture.provider())
        old['activities']['pagingVersion']=1
        old['activities']['activityCoverageReason']='SIZE_LIMIT'
        fixture.calls=[]
        with patch.object(b.time,'time',return_value=2000000601):
            new=b.read_journal(A,CONFIG,old,get=fixture.provider())
        self.assertEqual(fixture.calls,[0,2500,3000,3500,4000])
        self.assertEqual(len(new['activities']['rows']),4500)
