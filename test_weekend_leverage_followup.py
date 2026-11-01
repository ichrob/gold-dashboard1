"""Sunday issuer fallback: only missing leverage, no broker/device/order actions."""
import copy
import unittest
from contextlib import nullcontext
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

import weekend_leverage_followup as wk

SUNDAY = int(datetime(2026,11,1,9,30,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
DAY = 86400000
ISINS=['DE000FD0S0G4','DE000FE2JJ20','DE000FA96FJ2']
GEN=datetime.fromtimestamp((SUNDAY-3600000)/1000,ZoneInfo('Europe/Zurich')).isoformat()
RUN_AT=datetime.fromtimestamp((SUNDAY-3500000)/1000,ZoneInfo('Europe/Zurich')).isoformat()


def sample():
    feed=dict(listOrigin='degiro-screenshot',listUploadedAt=GEN,
              products=[dict(isin=i) for i in ISINS] + [dict(isin='DE000FE6B3G9')])
    rows=[dict(isin=i,code='PARTIAL',matchedCurrentList=True,
               requestedFields=['Geld','Brief','Anzeigezeit','Hebel'],
               observation=dict(missingFields=['Hebel'])) for i in ISINS]
    rows.append(dict(isin='DE000FE6B3G9',code='RETURN_FAILED',matchedCurrentList=True,
                     requestedFields=['Geld','Brief','Anzeigezeit','Hebel'],
                     observation=None))
    reader=dict(listUploadedAt=RUN_AT,listSource='degiro-gold-search',receivedAt=RUN_AT,
                results=rows)
    audit=dict(listUploadedAt=GEN,items=[dict(isin=i,state='incomplete',
        missing=['leverage','leverage-time'],tradeApproved=False) for i in ISINS])
    return feed,reader,audit


class Row:
    def __init__(self,x):self.x=x
    def fetchone(self):return (copy.deepcopy(self.x),) if self.x else None


class DB:
    def __init__(self, feed,reader,audit):
        self.feed=feed;self.reader=reader;self.audit=audit;self.writes=0
        self.lock=True
    def __call__(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def transaction(self):return nullcontext()
    def commit(self):pass
    def execute(self,sql,args=None):
        if 'FROM bob_paper_products' in sql:return Row(self.feed)
        if 'FROM bob_degiro_product_audit' in sql:return Row(self.audit)
        if 'FROM bob_android_read_runs' in sql:return Row(self.reader)
        if 'pg_try_advisory_xact_lock' in sql:return Row(self.lock)
        if 'UPDATE bob_degiro_product_audit' in sql:
            import json
            self.audit=json.loads(args[0]);self.writes+=1;return Row(True)
        raise AssertionError('Unexpected SQL: '+sql[:70])


class WeekendTests(unittest.TestCase):
    def test_only_the_three_incomplete_leverage_fields_are_selected(self):
        feed,reader,audit=sample()
        self.assertEqual(wk.targets(feed,reader,SUNDAY),ISINS)
        self.assertEqual(wk.plan(feed,reader,audit,SUNDAY),ISINS)
        reader['results'][0]['observation']['missingFields']=[]
        self.assertEqual(wk.targets(feed,reader,SUNDAY),ISINS[1:])
        reader['results'][0]['observation']['missingFields']=['Hebel']
        audit['items'][0]['weekendLeverageFollowup']={'retryAfterMs':SUNDAY+1000}
        self.assertEqual(wk.plan(feed,reader,audit,SUNDAY),ISINS[1:])
        reader['listUploadedAt']=datetime.fromtimestamp((SUNDAY-2*DAY)/1000,ZoneInfo('Europe/Zurich')).isoformat()
        self.assertEqual(wk.targets(feed,reader,SUNDAY),[])
        reader['listUploadedAt']=RUN_AT
        reader['receivedAt']=datetime.fromtimestamp((SUNDAY-DAY)/1000,ZoneInfo('Europe/Zurich')).isoformat()
        self.assertEqual(wk.targets(feed,reader,SUNDAY),[])

    def test_no_sunday_value_is_fabricated_from_unverified_or_mismatched_source(self):
        feed,reader,audit=sample()
        quote={i:dict(isin=i,productVerified=False) for i in ISINS}
        result=wk.update(audit,feed,ISINS,quote,SUNDAY)
        self.assertTrue(all(not x.get('leverageReference') for x in result['items']))
        self.assertTrue(all(x['weekendLeverageFollowup']['state']=='source-evidence-unavailable'
                            for x in result['items']))
        self.assertTrue(all('leverage' in x['missing'] and x['tradeApproved'] is False
                            for x in result['items']))
        self.assertFalse(any('weekendLeverageFollowup' in x for x in audit['items']))

    def test_issuer_provenance_separate_from_market_approval(self):
        feed,reader,audit=sample()
        reference=dict(value=11.25,at='2026-10-30T14:00:00Z',
                       current=False,tradeApproved=False,researchOnly=True,
                       kind='historical-issuer-leverage',source='SG',label='Letzter Originalhebel')
        raw=dict(isin=ISINS[0],productVerified=True)
        with patch('leverage_backup.historical_reference',return_value=reference):
            result=wk.update(audit,feed,[ISINS[0]],{ISINS[0]:raw},SUNDAY)
        item=result['items'][0]
        self.assertEqual(item['leverageReference']['value'],11.25)
        self.assertEqual(item['leverageReference']['at'],'2026-10-30T14:00:00Z')
        self.assertFalse(item['tradeApproved'])
        self.assertIn('leverage-time',item['missing'])
        self.assertEqual(result['items'][1],audit['items'][1])
        self.assertEqual(wk.plan(feed,reader,result,SUNDAY),ISINS[1:])

    def test_one_bounded_background_round_is_idempotent_with_no_market_orders(self):
        feed,reader,audit=sample();db=DB(feed,reader,audit)
        captured=[]
        def collector(products,active,now):
            captured.extend(p['isin'] for p in products)
            self.assertEqual(active,[])
            return {}
        x=wk.once(db,SUNDAY,collect=collector)
        self.assertEqual(x,dict(state='research-only',checked=3,ordersEnabled=False))
        self.assertEqual(captured,ISINS)
        self.assertEqual(db.writes,1)
        self.assertEqual(wk.once(db,SUNDAY,collect=lambda *_:self.fail('duplicate network')),
                         dict(state='no-missing-targets',checked=0,ordersEnabled=False))
        self.assertEqual(db.writes,1)
        self.assertEqual(wk.once(db,SUNDAY-DAY,collect=lambda *_:self.fail('weekday network'))['state'],'paused')
        db.feed['listUploadedAt']='2026-11-01T09:00:00Z'
        self.assertEqual(wk.once(db,SUNDAY+wk.RETRY_MS+1,
                                 collect=lambda *_:self.fail('changed list'))['checked'],0)


if __name__=='__main__':unittest.main()
