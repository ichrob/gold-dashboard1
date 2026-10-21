import copy
import json
import unittest
from unittest.mock import Mock,patch
import snaptrade_identity as m
from test_snaptrade_csv_link import snapshot,payload,ISIN
import snaptrade_csv_link as c
import snaptrade_bridge as b


def inputs():
    snap=snapshot();data=payload(snap)
    entry=c.prepare({**data,'links':[]},snap,b.number,b.text,b.source_time,allow_empty=True)
    return entry,snap['accounts'][0]


class IdentityTests(unittest.TestCase):
    def test_equal_name_quantity_and_currency_never_prove_identity(self):
        entry,a=inputs()
        result=m.reconcile(entry,a,lookup=Mock(side_effect=AssertionError('no FIGI needed')))
        self.assertEqual(result['report']['matched'],0)
        self.assertEqual(len(result['report']['unresolved']),1)
        self.assertEqual(result['links'],{})

    def test_exact_provider_isin_and_explicit_wkn_are_automatic(self):
        entry,a=inputs();p=a['positions'][0]
        for field,value,method in [('providerIsin',ISIN,'provider-isin'),('rawSymbol','WKN:'+ISIN[5:11],'provider-wkn')]:
            account=copy.deepcopy(a);account['positions'][0][field]=value
            result=m.reconcile(entry,account)
            self.assertEqual(result['report']['matched'],1)
            self.assertEqual(result['links'][p['positionKey']]['method'],method)
        a['positions'][0]['rawSymbol']=ISIN[5:11]
        self.assertEqual(m.reconcile(entry,a)['report']['matched'],0,'Unlabeled ticker is not WKN proof')

    def test_figi_cross_reference_matches_only_exact_listing_and_currency(self):
        entry,a=inputs();p=a['positions'][0];p['figi']='BBG000000001'
        good=m.reconcile(entry,a,lookup=lambda _: {ISIN:{p['figi']}})
        self.assertEqual(good['report']['matched'],1)
        self.assertEqual(good['links'][p['positionKey']]['method'],'figi-verified')
        for matches in ({ISIN:{'BBG000000002'}}, {}, {ISIN:set()}):
            self.assertEqual(m.reconcile(entry,a,lookup=lambda _:matches)['report']['matched'],0)
        a['positions'][0]['currency']='EUR'
        self.assertEqual(m.reconcile(entry,a,lookup=lambda _: {ISIN:{p['figi']}})['report']['matched'],0)

    def test_conflicting_provider_isin_never_overridden_by_figi(self):
        entry,a=inputs();p=a['positions'][0];p.update(providerIsin='DE000FG14AV8',figi='BBG000000001')
        self.assertEqual(m.reconcile(entry,a,lookup=lambda _: {ISIN:{p['figi']}})['report']['matched'],0)

    def test_duplicate_positions_or_isins_remain_unresolved(self):
        entry,a=inputs();p=a['positions'][0];p['figi']='BBG000000001'
        other=copy.deepcopy(p);other['positionKey']='other';a['positions'].append(other)
        result=m.reconcile(entry,a,lookup=lambda _: {ISIN:{p['figi']}})
        self.assertEqual(result['report']['matched'],0);self.assertEqual(len(result['report']['unresolved']),2)
        a['positions'].pop()
        entry['records']['DE000FG14AV8']={**entry['records'][ISIN],'isin':'DE000FG14AV8'}
        self.assertEqual(m.reconcile(entry,a,lookup=lambda _: {k:{p['figi']} for k in entry['records']})['report']['matched'],0)

    def test_prior_confirmed_identity_is_retained_only_for_same_stable_instrument(self):
        entry,a=inputs();data=payload(snapshot());old=c.prepare(data,{'accounts':[a]},b.number,b.text,b.source_time)
        self.assertEqual(m.reconcile(entry,a,old)['report']['matched'],1)
        a['positions'][0]['symbol']='DIFFERENT'
        self.assertEqual(m.reconcile(entry,a,old)['report']['matched'],0)

    def test_lookup_failure_and_missing_stable_ids_do_not_create_links(self):
        entry,a=inputs();a['positions'][0]['figi']='BBG000000001'
        result=m.reconcile(entry,a,lookup=Mock(side_effect=RuntimeError('PRIVATE')))
        self.assertEqual(result['report']['matched'],0)
        self.assertNotIn('PRIVATE',json.dumps(result))
        a['positions'][0]['stableInstrumentId']=False
        self.assertEqual(m.reconcile(entry,a,lookup=lambda _: {ISIN:{'BBG000000001'}})['report']['matched'],0)

    def test_auto_route_stores_unresolved_csv_without_client_forged_confirmations(self):
        old_state,old_config,old_ledger=copy.deepcopy(b._STATE),b._CONFIG,copy.deepcopy(b._LEDGER)
        try:
            snap=snapshot();data=payload(snap);data['links']=[]
            b._STATE.update(code='READ_OK',snapshot=snap);b._CONFIG={'clientId':'test'}
            ledger={'owner':'test','history':[],'changes':[],'journal':{}}
            with patch.object(b,'load_ledger',return_value=copy.deepcopy(ledger)),patch.object(b,'save_ledger') as save:
                status=b.handle('csv-auto',data)
            self.assertEqual(status['snapshot']['accounts'][0]['csvAutoReport']['matched'],0)
            self.assertTrue(b._LEDGER['csv'][data['accountKey']]['automatic'])
            save.assert_called_once()
            data['links']=[dict(positionKey=snap['accounts'][0]['positions'][0]['positionKey'],isin=ISIN,confirmed=True)]
            with self.assertRaises(ValueError):b.handle('csv-auto',data)
        finally:
            b._STATE.clear();b._STATE.update(old_state);b._CONFIG=old_config;b._LEDGER.clear();b._LEDGER.update(old_ledger)

    def test_public_lookup_is_bounded_identifier_only_and_cached(self):
        entry,a=inputs();old_cache,old_next=copy.deepcopy(m._CACHE),m._NEXT;m._CACHE.clear();m._NEXT=0
        response=Mock();response.read.return_value=json.dumps([{'data':[{'figi':'BBG000000001'}]}]).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        try:
            with patch.object(m,'build_opener',return_value=opener):
                self.assertEqual(m.lookup_figis(entry['records'])[ISIN],{'BBG000000001'})
                m.lookup_figis(entry['records'])
            opener.open.assert_called_once()
            request=opener.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.openfigi.com/v3/mapping')
            self.assertEqual(json.loads(request.data),[{'idType':'ID_ISIN','idValue':ISIN,'currency':'CHF'}])
            self.assertNotIn('Authorization',request.headers)
            self.assertIsNone(m.NoRedirect().redirect_request(None,None,None,None,None,None))
        finally:m._CACHE.clear();m._CACHE.update(old_cache);m._NEXT=old_next


if __name__=='__main__':unittest.main()
