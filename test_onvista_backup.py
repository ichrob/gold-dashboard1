import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import onvista_backup as b

ISIN='DE000FG5GUT0'
NOW=datetime(2026,10,7,9,14,10,tzinfo=timezone.utc)
AT='2026-10-07T09:14:01+00:00'
OLD='2026-10-07T08:53:53+00:00'
def page():
    return {'derivativesDetails':dict(dataStatus=1,hasBarrierBeenHit=False,numberUnderlyings=1,isoCurrency='EUR',nameExerciseRight='CALL'),
            'derivativesUnderlyingList':{'list':[{'instrument':{'isin':'XC0009655157'}}]},
            'instrument':{'isin':ISIN,'wkn':'FG5GUT','entitySubType':'KNOCKOUT_CERTIFICATE','entityValue':'336000321'},
            'quoteList':{'list':[dict(idInstrument='336000321',isoCurrency='EUR',codeQualityPriceBidAsk='RLT',bid=4.71,ask=4.72,datetimeBid=AT,datetimeAsk=AT,market={'name':'Stuttgart'})]},
            'derivativesFigure':dict(gearingAsk=74.7,datetimeCalculation=AT,datetimeAskPrice=OLD,datetimePriceUnderlyingCalculation=OLD)}
def html(data):
    return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'data':{'snapshot':data}}}})+'</script>'
class BackupTests(unittest.TestCase):
    def test_source_clocks(self):
        r=b.parse_page(html(page()),ISIN,NOW)
        self.assertEqual(r['askAt'],AT)
        self.assertEqual(r['leverageAt'],OLD)
        self.assertEqual(r['leverageCalculatedAt'],AT)
        self.assertEqual(r['source'],'Onvista · Stuttgart')
    def test_identity_currency_delay_and_invalid_price(self):
        for key,val in [('isoCurrency','USD'),('codeQualityPriceBidAsk','DLY'),('bid',5),('ask',float('inf')),('datetimeAsk',OLD),('datetimeBid','2026-10-08T09:14:01Z')]:
            p=page();p['quoteList']['list'][0][key]=val
            with self.assertRaises(ValueError):b.parse_page(html(p),ISIN,NOW)
        p=page();p['instrument']['isin']='DE000PJ9NCK0'
        with self.assertRaises(ValueError):b.parse_page(html(p),ISIN,NOW)
    def test_fallback_and_recovery(self):
        primary=dict(isin=ISIN,productVerified=True,eligible=False,metadata=dict(status=1,underlyingType='SPOT',direction='LONG',ko=4074.35),conditions={'ko':{'value':4074.35}},source='SG')
        original=copy.deepcopy(primary)
        r=b.parse_page(html(page()),ISIN,NOW)
        with patch.object(b,'fetch',return_value=r) as fetch:
            merged=b.apply_backup(primary,ISIN,NOW)
            self.assertEqual(merged['conditions'],primary['conditions'])
            self.assertEqual(merged['ko'],4074.35)
            self.assertTrue(merged['found']);self.assertTrue(merged['backupActive'])
            self.assertFalse(merged['eligible']);self.assertFalse(merged['fresh'])
            self.assertEqual(primary,original)
            fetch.reset_mock()
            current=dict(primary,eligible=True)
            self.assertEqual(b.apply_backup(current,ISIN,NOW),current)
            fetch.assert_not_called()
            ended=dict(primary,metadata=dict(status=2,underlyingType='SPOT'))
            self.assertEqual(b.apply_backup(ended,ISIN,NOW),ended)
            fetch.assert_not_called()
            newer=dict(primary,found=True,bidAt='2026-10-07T09:14:05Z',askAt='2026-10-07T09:14:05Z')
            self.assertEqual(b.apply_backup(newer,ISIN,NOW),newer)
    def test_cache_does_not_renew_time(self):
        r=b.parse_page(html(page()),ISIN,NOW)
        primary=dict(isin=ISIN,productVerified=True,metadata=dict(status=1,underlyingType='SPOT',direction='LONG'))
        with patch.object(b,'fetch',return_value=r):
            self.assertEqual(b.apply_backup(primary,ISIN,datetime(2026,10,7,10,tzinfo=timezone.utc)),primary)
if __name__=='__main__':unittest.main()
