"""Quarter-hour entry-block evidence is forward-only, bounded and non-trading."""
import copy
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import paper_simulation as sim
import bob_diagnostics
from vollautomatisch_panel import PANEL


class PaperDayConnection:
    def __init__(self):
        self.row = None
        self.next_row = None
        self.commands = []

    def execute(self, sql, params=()):
        self.commands.append(sql)
        if sql.startswith('SELECT payload FROM bob_paper_days WHERE day='):
            self.next_row = (copy.deepcopy(self.row),) if self.row is not None else None
        elif sql.startswith('INSERT INTO bob_paper_days VALUES'):
            self.row = json.loads(params[1])
            self.next_row = None
        elif sql.startswith('SELECT day,payload FROM bob_paper_'):
            self.next_row = ('2026-11-10', copy.deepcopy(self.row)) if self.row else None
        else:
            raise AssertionError('Unexpected SQL: '+sql[:100])
        return self

    def fetchone(self):
        return self.next_row


def timestamp(hour, minute):
    return int(datetime(2026, 11, 10, hour, minute,
                        tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)


class QuarterHourEntryEvidenceTests(unittest.TestCase):
    def entry(self, now, direction='LONG'):
        return {'direction':direction,'goldAt':now-15000,'signalBarAt':now-300000,
                'isin':'private-isin','ruleVersion':'test'}

    def capital(self, profile):
        return {'portfolio':profile,'cash':800.,'initialCapital':800.,'equity':800.,
                'realizedProfit':0.}

    def test_november_accounts_preserve_15_minute_reasons_after_200_detail_rollover(self):
        for profile in ('trend800nov','normal1000nov'):
            db = PaperDayConnection()
            first = timestamp(9,2)
            block = 'Einstieg wartet: Preis über 1,5 ATR von EMA20 in Trendrichtung entfernt · Bestätigtes Einstiegssignal älter als 15 Minuten ohne neuen Rücksetzer'
            for at,reason,direction in (
                (first,block,'LONG'),(timestamp(9,10),block,'SHORT'),
                (timestamp(9,17),'Goldkurs nicht aktuell bestätigt; Quellenzeit prüfen','NEUTRAL')):
                sim.day_update(db,'2026-11-10',wait=reason,now=at,
                               capital=self.capital(profile),entry=self.entry(at,direction))
            buckets=db.row['entryTimeBuckets15mV1']
            self.assertEqual(len(buckets),2)
            key=str(timestamp(9,0))
            self.assertEqual(buckets[key]['checks'],2)
            self.assertEqual(buckets[key]['reasonCodes']['ema-stretch-and-signal-age'],2)
            self.assertEqual(buckets[key]['directions'],{'LONG':1,'SHORT':1})
            self.assertEqual(buckets[key]['firstAt'],first)
            self.assertEqual(buckets[key]['lastAt'],timestamp(9,10))
            self.assertEqual(db.row['entryTimeBucketsFirstObservedAt'],first)
            self.assertEqual(db.row['waitChecks'],3)
            self.assertNotIn('private-isin',json.dumps(buckets))
            self.assertEqual(buckets[str(timestamp(9,15))]['reasonCodes']['gold-stale'],1)
            self.assertFalse(db.row.get('entryTimeBucketsTruncated',False))
            # Old 200-row cap can truncate without erasing the new aggregate.
            db.row['entryBlocksTruncated']=True
            db.row['entryBlocks']=[]
            self.assertEqual(sum(x['checks'] for x in db.row['entryTimeBuckets15mV1'].values()),3)

    def test_old_accounts_are_not_modified_by_the_new_window_schema(self):
        db=PaperDayConnection()
        at=timestamp(9,2)
        sim.day_update(db,'2026-11-10',wait='no plan',now=at,
                       capital=self.capital('trend800'),entry=self.entry(at))
        self.assertNotIn('entryTimeBuckets15mV1',db.row)
        self.assertEqual(db.row['waitChecks'],1)

    def test_fixed_reason_codes_no_fabricated_history_and_96_slot_cap(self):
        db=PaperDayConnection()
        start=timestamp(9,2)
        sim.day_update(db,'2026-11-10',wait='A private arbitrary issue /secret/isins',
                       now=start,capital=self.capital('normal1000nov'),entry=self.entry(start))
        self.assertEqual(db.row['entryTimeBuckets15mV1'][str(timestamp(9,0))]['reasonCodes'],{'other':1})
        self.assertNotIn('private',json.dumps(db.row['entryTimeBuckets15mV1']))
        self.assertEqual(db.row['entryTimeBucketsFirstObservedAt'],start)
        data={'entryTimeBuckets15mV1':{str(i*900000):{'checks':1} for i in range(1,97)}}
        sim.paper_entry_time_bucket(data, timestamp(16,10), 'new',self.entry(timestamp(16,10)))
        self.assertTrue(data['entryTimeBucketsTruncated'])
        self.assertEqual(len(data['entryTimeBuckets15mV1']),96)

    def test_read_only_projection_is_bounded_and_redacts_raw_identifiers(self):
        db=PaperDayConnection()
        at=timestamp(9,2)
        sim.day_update(db,'2026-11-10',wait='Goldkurs nicht aktuell bestätigt; Quellenzeit prüfen',
                       now=at,capital=self.capital('trend800nov'),entry=self.entry(at))
        class SingleProfile:
            POLICIES={'trend800nov':{}}
            @staticmethod
            def names(_):
                return {'bob_paper_days':'bob_paper_trend800nov_days'}
        out=bob_diagnostics.entry_block_evidence(db,SingleProfile())
        account=out['accounts'][0]
        self.assertEqual(account['timeWindowsStored'],1)
        self.assertTrue(account['timeWindowsForwardOnly'])
        self.assertEqual(account['timeWindows15m'][0]['startAt'],timestamp(9,0))
        self.assertEqual(account['timeWindows15m'][0]['reasonCodes'],{'gold-stale':1})
        self.assertNotIn('private-isin',json.dumps(out))
        self.assertTrue(all(query.startswith('SELECT ') for query in db.commands
                            if query.startswith('SELECT day,payload')))

    def test_authenticated_ui_explains_exact_scope_and_no_trade_approval(self):
        self.assertIn('entryTimeBuckets15mV1||{}',PANEL)
        self.assertIn('Zeitfenster (ab tatsächlicher Einführung',PANEL)
        self.assertIn('Prüfungen, keine verpassten Trades',PANEL)
        self.assertIn('Hauptsignal allein genügt nicht',PANEL)


if __name__=='__main__':
    unittest.main()
