import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import android_list as a
import android_telemetry_http as http
from test_android_observations import MemoryDb, run, ISIN
from test_android_telemetry import Handler

NOW=1793271600

class DetailsTest(unittest.TestCase):
    def test_complete_skipped_but_each_missing_field_and_expired_quote_requested(self):
        items=[{'isin':ISIN}]
        p=dict(isin=ISIN,price=10,leverage=20,ko=4000,basisPrice=3999,ratio=.1,currency='EUR',
               quote=dict(bid=10,ask=11,quoteAt=datetime.fromtimestamp(NOW,timezone.utc).isoformat()))
        self.assertEqual(a.detail_plan(items,[p],NOW),[])
        for field in ('leverage','ko','basisPrice','ratio','currency'):
            x=copy.deepcopy(p);x.pop(field)
            self.assertEqual(len(a.detail_plan(items,[x],NOW)),1)
        for change in ({'bid':None},{'ask':float('nan')},{'bid':12},{'quoteAt':'2020-01-01T00:00:00Z'},{'quoteAt':'2030-01-01T00:00:00Z'}):
            x=copy.deepcopy(p);x['quote'].update(change)
            self.assertTrue(a.detail_plan(items,[x],NOW))
        # Missing products must not disappear from the detail queue.
        self.assertEqual(a.detail_plan(items*2,[],NOW)[0]['isin'],ISIN)
        self.assertEqual(len(a.detail_plan(items*2,[],NOW)),1)
        self.assertEqual(a.detail_plan([{'isin':ISIN,'listRow':{'excluded':True}}],[],NOW),[])

    def test_details_require_device_credential(self):
        h=Handler({},auth=True)
        http.route(h,'POST','/api/android-list/details',lambda *_:self.fail('cookie cannot upload'))
        self.assertEqual(h.code,401)
        sent=[];h=Handler({},headers={'Authorization':'Bearer '+'a'*64})
        http.route(h,'POST','/api/android-list/details',lambda p,remote=False:sent.append((p,remote)) or {'ok':True})
        self.assertEqual(sent[0][0]['action'],'list-details');self.assertTrue(sent[0][1])

    def test_owned_list_only_idempotent_saved_run_and_no_live_session_required(self):
        class Db(MemoryDb):
            owned=True
            def execute(self,sql,params=()):
                if sql.startswith('DELETE FROM bob_android_list_images'):return self
                if sql.startswith('SELECT token_hash FROM'):self.result=('device',);return self
                if sql.startswith('SELECT import_receipt, parsed_items'):
                    self.result=({'stage':'synced'},[{'isin':ISIN}]) if self.owned else None
                    return self
                return super().execute(sql,params)
        db=Db();payload={'action':'list-details','token':'a'*64,'value':{'batchId':'b'*32,'run':run()}}
        original=__import__('android_observations').prepare
        with patch('android_observations.prepare',side_effect=lambda r,f:original(r,f,datetime.fromtimestamp(NOW,timezone.utc))):
            answer=a.handle(db,payload,NOW)
            self.assertTrue(answer['saved']);self.assertFalse(answer['verified'])
            self.assertTrue(a.handle(db,payload,NOW)['duplicate'])
            db.owned=False
            with self.assertRaises(PermissionError):a.handle(db,payload,NOW)
            db.owned=True
            payload['value']['run']['isins']=['DE000FG77MY4']
            with self.assertRaises(ValueError):a.handle(db,payload,NOW)
        self.assertFalse(any('UPDATE bob_paper' in s for s in db.sql))

if __name__=='__main__':unittest.main()
