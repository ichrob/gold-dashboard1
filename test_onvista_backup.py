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
    def test_explicit_knockout_overrides_stale_active_metadata(self):
        data=page();data['derivativesDetails']['hasBarrierBeenHit']=True
        evidence=b.parse_knockout_evidence(html(data),ISIN,NOW)
        self.assertTrue(evidence['knockoutReported'])
        primary=dict(isin=ISIN,productVerified=True,metadata=dict(status=1,underlyingType='SPOT',direction='LONG'),analysisQuote={'ask':4},leverage=10)
        with patch.object(b,'fetch',return_value=evidence):
            out=b.apply_backup(primary,ISIN,NOW)
        self.assertEqual(out['metadata']['status'],2)
        self.assertFalse(out['eligible'])
        self.assertNotIn('analysisQuote',out)
        self.assertNotIn('leverage',out)
        data['instrument']['isin']='DE000FG4JXV7'
        self.assertIsNone(b.parse_knockout_evidence(html(data),ISIN,NOW))

    def test_static_model_survives_stale_quotes_without_promoting_them(self):
        data=page()
        data['derivativesDetails'].update(quanto=False,hasIndicativeDetails=False)
        data['derivativesUnderlyingList']['list'][0].update(isoCurrency='USD',coverRatio=.1)
        data['quoteList']['list'][0]['datetimeAsk']=OLD
        evidence=b.parse_model_evidence(html(data),ISIN,NOW)
        primary=dict(isin=ISIN,productVerified=True,eligible=False,metadata=dict(status=1,
            underlyingType='SPOT',direction='LONG',ratio=.1,simpleTurbo=True,
            quantoState='unknown',simpleNonQuantoTurbo=False))
        import time
        with patch.dict(b._MODEL,{ISIN:(time.monotonic(),evidence)},clear=True), patch.object(b,'fetch',return_value=None):
            result=b.apply_backup(primary,ISIN,NOW)
            self.assertTrue(result['metadata']['simpleNonQuantoTurbo'])
            self.assertFalse(result['eligible']);self.assertNotIn('ask',result)
            self.assertFalse(primary['metadata']['simpleNonQuantoTurbo'])
            for key,value in [('direction','SHORT'),('ratio',.01),('quantoState','quanto'),('simpleTurbo',False)]:
                wrong=copy.deepcopy(primary);wrong['metadata'][key]=value
                self.assertFalse(b.apply_backup(wrong,ISIN,NOW)['metadata']['simpleNonQuantoTurbo'])
        with self.assertRaises(ValueError):b.parse_page(html(data),ISIN,NOW)
        for value in [True,None,0,'false']:
            data['derivativesDetails']['quanto']=value
            with self.assertRaises(ValueError):b.parse_model_evidence(html(data),ISIN,NOW)

    def test_bnp_identity_model_and_analysis_pair(self):
        import time
        for isin in ('DE000PJ9NB98', 'DE000PJ9NCK0', 'DE000PG0XK25', 'DE000FG7HZY3'):
            data=page()
            data['instrument'].update(isin=isin,wkn=isin[5:11],entityValue=str(b.IDS[isin]))
            data['quoteList']['list'][0]['idInstrument']=str(b.IDS[isin])
            data['derivativesDetails'].update(quanto=False,hasIndicativeDetails=False)
            data['derivativesUnderlyingList']['list'][0].update(isoCurrency='USD',coverRatio=.1)
            evidence=b.parse_model_evidence(html(data),isin,NOW)
            parsed=b.parse_page(html(data),isin,NOW)
            primary=dict(isin=isin,productVerified=True,metadata=dict(status=1,underlyingType='SPOT',direction='LONG',ratio=.1,simpleTurbo=True,quantoState='unknown'))
            with patch.dict(b._MODEL,{isin:(time.monotonic(),evidence)},clear=True), patch.object(b,'fetch',return_value=parsed):
                result=b.apply_backup(primary,isin,NOW)
            self.assertTrue(result['metadata']['simpleNonQuantoTurbo'])
            self.assertEqual(result['analysisQuote']['askAt'],AT)
            self.assertEqual(result['analysisQuote']['priceKind'],'secondary-market')
            self.assertFalse(result['eligible'])
            data['instrument']['isin']=ISIN
            with self.assertRaises(ValueError):b.parse_page(html(data),isin,NOW)

    def test_missing_leverage_does_not_discard_current_pair(self):
        data=page();data['derivativesFigure']={}
        result=b.parse_page(html(data),ISIN,NOW)
        self.assertEqual(result['ask'],4.72)
        self.assertEqual(result['askAt'],AT)
        self.assertIsNone(result['leverageAt'])
        self.assertIsNone(result['leverage'])

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
    def test_extended_analysis_window_keeps_source_time_and_no_clearance(self):
        from datetime import timedelta
        data=page()
        at=(NOW-timedelta(seconds=300)).isoformat()
        data['quoteList']['list'][0].update(datetimeBid=at,datetimeAsk=at)
        parsed=b.parse_page(html(data),ISIN,NOW)
        self.assertEqual(parsed['askAt'],at)
        self.assertEqual(parsed['analysisMaxAgeSeconds'],300)
        primary=dict(isin=ISIN,productVerified=True,metadata=dict(status=1,underlyingType='SPOT',direction='LONG'))
        with patch.object(b,'fetch',return_value=parsed):
            out=b.apply_backup(primary,ISIN,NOW)
        self.assertTrue(out['found']);self.assertFalse(out['eligible'])
        data['quoteList']['list'][0]['datetimeAsk']=(NOW-timedelta(seconds=301)).isoformat()
        with self.assertRaises(ValueError):b.parse_page(html(data),ISIN,NOW)
if __name__=='__main__':unittest.main()
