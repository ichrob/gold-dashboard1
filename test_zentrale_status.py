import unittest
from zentrale_status import phone_view, priority

class PhoneViewTests(unittest.TestCase):
    def data(self):
        return {'androidTelemetry':{'devices':[{'revoked':False,'expiresAt':3000,'receivedAt':990,
            'report':{'observedAt':980,'appVersionCode':10001,'running':True,'lastCode':'COMPLETE','lastEventAt':970,'pinProbe':{'secret':'SECRET'}}}],
            'listImports':[{'uploadedAt':990,'import':{'stage':'synced','count':10,'at':991},'recognitionAttachments':{'localOcrImages':2,'appTextImages':0,'imageOnly':1}}]},
            'androidReader':{'runs':[{'receivedAt':900,'requested':2,'results':[{'code':'COMPLETE','isin':'SECRET'},{'code':'PARTIAL'}]}]}}
    def test_bounded_real_reports_and_distinct_clocks(self):
        r=phone_view(self.data(),1000)
        self.assertEqual(r['state'],'running')
        self.assertEqual((r['complete'],r['partial'],r['requested']),(1,1,2))
        self.assertEqual(r['runAt'],900)
        self.assertEqual(r['observedAt'],980)
        self.assertEqual(r['lastSuccessfulImportAt'],991)
        self.assertNotIn('SECRET',str(r))
        self.assertEqual(r['recognitionScope'],'attachments-not-processing-proof')
    def test_old_running_device_is_not_live(self):
        self.assertEqual(phone_view(self.data(),2000)['state'],'unknown')
    def test_missing_reports_are_unknown_not_zero_success(self):
        r=phone_view({},1000)
        self.assertEqual(r['state'],'unknown')
        self.assertIsNone(r['complete']);self.assertIsNone(r['appVersion'])
        self.assertIsNone(r['lastSuccessfulImportAt'])
    def test_revoked_expired_future_and_invalid_reports(self):
        d=self.data();d['androidTelemetry']['devices'][0]['revoked']=True
        self.assertIsNone(phone_view(d,1000)['appVersion'])
        d=self.data();d['androidTelemetry']['devices'][0]['report']['observedAt']=1100
        self.assertEqual(phone_view(d,1000)['state'],'unknown')
        d=self.data();d['androidReader']['runs'][0]['requested']=1
        self.assertIsNone(phone_view(d,1000)['complete'])
    def test_market_outage_precedes_research(self):
        self.assertLess(priority({'code':'market-missing'}),priority({'code':'research-missing'}))

if __name__=='__main__':unittest.main()
