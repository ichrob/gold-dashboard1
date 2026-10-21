import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
import snaptrade_bridge as b
import snaptrade_csv_link as c
from test_snaptrade_bridge import fixtures, CONFIG, A

ISIN='DE000FG309G0'  # Existing public issuer fixture; not an account holding.


def snapshot():
    data=fixtures()
    position=data['/accounts/'+A+'/positions/all']['results'][0]
    position.update(units='3',price='8',cost_basis='10')
    position['instrument'].update(id='33333333-3333-4333-8333-333333333333',kind='other',description='Example Faktor 3',symbol='OPAQUE')
    return b.read_snapshot(CONFIG,lambda path,_:data[path])


def payload(snap):
    a=snap['accounts'][0];p=a['positions'][0]
    return dict(accountKey=a['accountKey'],importedAt=datetime.now(timezone.utc).isoformat(),
                records=[dict(isin=ISIN,name='Example Faktor 3',quantity='2',currency='CHF',price='7',value='14',costBasis='6')],
                links=[dict(positionKey=p['positionKey'],isin=ISIN,confirmed=True)])


class CsvLinkTests(unittest.TestCase):
    def test_names_and_quantities_never_create_automatic_identity(self):
        snap=snapshot();data=payload(snap);data['links'][0]['confirmed']=False
        with self.assertRaises(ValueError):c.prepare(data,snap,b.number,b.text,b.source_time)
        snap['accounts'][0]['positions'][0]['stableInstrumentId']=False
        data['links'][0]['confirmed']=True
        with self.assertRaises(ValueError):c.prepare(data,snap,b.number,b.text,b.source_time)

    def test_exact_provider_isin_needs_no_name_guess_and_conflict_is_rejected(self):
        snap=snapshot();p=snap['accounts'][0]['positions'][0]
        p['providerIsin']=p['isin']=ISIN
        data=payload(snap);data['links'][0]['confirmed']=False
        self.assertEqual(c.prepare(data,snap,b.number,b.text,b.source_time)['links'][p['positionKey']]['method'],'provider-isin')
        p['providerIsin']='DE000FG14AV8'
        with self.assertRaises(ValueError):c.prepare(data,snap,b.number,b.text,b.source_time)

    def test_historical_value_not_current_value_and_broker_cost_wins(self):
        snap=snapshot();data=payload(snap)
        entry=c.prepare(data,snap,b.number,b.text,b.source_time)
        c.apply(snap,{data['accountKey']:entry})
        p=snap['accounts'][0]['positions'][0]
        self.assertEqual(p['csvEvidence']['value'],'14')
        self.assertEqual(p['csvEvidence']['quantity'],'2')
        self.assertIsNone(p['csvEvidence']['exportAt'])
        self.assertEqual(p['marketValue'],'24')
        self.assertEqual(p['unrealizedPnl'],'-6')
        self.assertEqual(p['costBasis'],'10')
        self.assertEqual(p['valuationBasis'],'csv-calculated-unit-quotation')
        self.assertEqual(p['isin'],ISIN);self.assertFalse(p['identityVerified']);self.assertFalse(p['tradeApproved'])
        self.assertFalse(snap['realOrders']);self.assertFalse(snap['liveQuotes'])

    def test_no_multiplier_guess_from_converted_value_or_unknown_asset(self):
        for kind,price,value in [('other','7','13'),('future','7','14'),('option','7','14'),('bond','7','14')]:
            with self.subTest(kind=kind,value=value):
                snap=snapshot();snap['accounts'][0]['positions'][0]['kind']=kind
                data=payload(snap);data['records'][0].update(price=price,value=value)
                c.apply(snap,{data['accountKey']:c.prepare(data,snap,b.number,b.text,b.source_time)})
                self.assertIsNone(snap['accounts'][0]['positions'][0]['marketValue'])
        snap=snapshot();data=payload(snap);data['records'][0]['currency']='EUR'
        with self.assertRaises(ValueError):c.prepare(data,snap,b.number,b.text,b.source_time)

    def test_removal_and_replacement_revoke_derived_values_and_quotes(self):
        snap=snapshot();data=payload(snap);entry=c.prepare(data,snap,b.number,b.text,b.source_time)
        c.apply(snap,{data['accountKey']:entry})
        p=snap['accounts'][0]['positions'][0];p['issuerQuote']={'bid':'8'}
        c.apply(snap,{})
        self.assertIsNone(p['isin']);self.assertIsNone(p['marketValue']);self.assertIsNone(p['unrealizedPnl'])
        self.assertNotIn('csvEvidence',p);self.assertNotIn('issuerQuote',p)
        c.apply(snap,{data['accountKey']:entry})
        entry['records'][ISIN]['value']='999'
        c.apply(snap,{data['accountKey']:entry})
        self.assertIsNone(p['marketValue']);self.assertNotIn('valuationBasis',p)

    def test_changed_provider_identity_or_currency_is_not_overridden(self):
        snap=snapshot();data=payload(snap);entry=c.prepare(data,snap,b.number,b.text,b.source_time)
        for field,value in [('symbol','ANOTHER'),('currency','EUR'),('providerIsin','DE000FG14AV8')]:
            changed=copy.deepcopy(snap);changed['accounts'][0]['positions'][0][field]=value
            c.apply(changed,{data['accountKey']:entry})
            self.assertTrue(changed['accounts'][0]['positions'][0]['csvLinkConflict'])
            self.assertNotIn('csvEvidence',changed['accounts'][0]['positions'][0])

    def test_no_duplicate_or_unknown_or_unbounded_mapping(self):
        for mutate in (lambda d:d.update(accountKey='wrong'), lambda d:d['records'].append(copy.deepcopy(d['records'][0])),
                       lambda d:d['records'][0].update(price='NaN'),lambda d:d['links'][0].update(positionKey='wrong')):
            snap=snapshot();data=payload(snap);mutate(data)
            with self.assertRaises(ValueError):c.prepare(data,snap,b.number,b.text,b.source_time)

    def test_failed_save_never_publishes_or_retains_mapping(self):
        old_state,old_config,old_ledger=copy.deepcopy(b._STATE),b._CONFIG,copy.deepcopy(b._LEDGER)
        try:
            snap=snapshot();b._STATE.update(code='READ_OK',snapshot=snap);b._CONFIG=CONFIG
            ledger={'owner':'test','history':[],'changes':[],'journal':{}}
            b._LEDGER.clear();b._LEDGER.update(ledger)
            with patch.object(b,'load_ledger',return_value=copy.deepcopy(ledger)),patch.object(b,'save_ledger',side_effect=b.ReadError('STORE_UNAVAILABLE')):
                with self.assertRaises(b.ReadError):b.handle('csv-import',payload(snap))
            self.assertNotIn('csv',b._LEDGER)
            self.assertNotIn('csvEvidence',b._STATE['snapshot']['accounts'][0]['positions'][0])
        finally:
            b._STATE.clear();b._STATE.update(old_state);b._CONFIG=old_config;b._LEDGER.clear();b._LEDGER.update(old_ledger)


if __name__=='__main__':unittest.main()
