"""Original-only November paper entry blocker classifications.

These are bounded diagnostic labels, not a new trading model or recovery of
missing historical decisions.
"""
import copy
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import paper_simulation as simulation
import bob_diagnostics


def at(hour=14, minute=2):
    return int(datetime(2026, 11, 16, hour, minute,
        tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)


class MemoryDb:
    def __init__(self):
        self.days = {}
        self.next = None
    def execute(self, sql, params=()):
        if sql.startswith('SELECT payload FROM bob_paper_days WHERE day='):
            item = self.days.get(params[0])
            self.next = (copy.deepcopy(item),) if item is not None else None
        elif sql.startswith('INSERT INTO bob_paper_days VALUES'):
            self.days[params[0]] = json.loads(params[1])
            self.next = None
        elif sql.startswith('SELECT day,payload FROM bob_paper_'):
            row = self.days.get('2026-11-16')
            self.next = ('2026-11-16', copy.deepcopy(row)) if row else None
        else:
            raise AssertionError('Unexpected SQL: '+sql[:100])
        return self
    def fetchone(self):
        return self.next


class NovemberPaperEntryClassificationTests(unittest.TestCase):
    def test_three_frequent_blockers_remain_distinct_but_non_trading(self):
        cases={
            'Einstieg wartet: Aktueller Spot und letzter Kerzenschluss weichen über 0,8 ATR ab':
                'spot-close-distance',
            'Einstieg wartet: Aktueller Spot und letzter Kerzenschluss weichen über 1,2 ATR ab':
                'spot-close-distance',
            'Einstieg wartet: Haupttrend SHORT intakt · kurzfristiger Rücksetzer; Einstieg abwarten, bestehenden Stop beibehalten · Trendstärke schwach: zweite Schlusskerze zur Bestätigung erforderlich':
                'weak-trend-confirmation',
            'Einstieg wartet: Unterstützung vor dem Ziel: 3880 USD/oz · bis dorthin 0.01R vor Kosten. Mindest-CRV bis zur Hürde nicht erfüllt; neuen Einstieg abwarten.':
                'crv-obstacle',
            'Einstieg wartet: Bestätigtes Einstiegssignal älter als 15 Minuten ohne neuen Rücksetzer':
                'signal-age',
            'Goldkurs nicht aktuell bestätigt; Quellenzeit prüfen':
                'gold-stale',
            'ABWARTEN: kein bestätigter gültiger Goldplan':'gold-plan-missing',
        }
        for text, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(simulation.paper_entry_reason_code(text), expected)
        self.assertEqual(simulation.paper_entry_reason_code(
            'Einstieg wartet: private details / secret'), 'plan-or-timing')

    def test_forward_only_bounded_one_bucket_per_november_profile(self):
        messages=[
            'Einstieg wartet: Aktueller Spot und letzter Kerzenschluss weichen über 0,8 ATR ab',
            'Einstieg wartet: Haupttrend SHORT intakt · Trendstärke schwach: zweite Schlusskerze zur Bestätigung erforderlich',
            'Einstieg wartet: Unterstützung vor dem Ziel · Mindest-CRV bis zur Hürde nicht erfüllt',
        ]
        for profile in ('trend800nov','normal1000nov','ema3000nov','noema5000nov'):
            db=MemoryDb()
            original={ 'direction':'SHORT', 'isin':'PRIVATE_ISIN',
                        'goldAt':at()-3000, 'signalBarAt':at()-300000}
            for reason in messages:
                simulation.day_update(db,'2026-11-16',now=at(),wait=reason,
                    capital={'portfolio':profile,'cash':800,'equity':800,
                             'initialCapital':800,'realizedProfit':0},entry=original)
            buckets=db.days['2026-11-16']['entryTimeBuckets15mV1']
            self.assertEqual(len(buckets),1)
            bucket=next(iter(buckets.values()))
            self.assertEqual(bucket['reasonCodes'],{
                'spot-close-distance':1,'weak-trend-confirmation':1,
                'crv-obstacle':1})
            self.assertNotIn('PRIVATE_ISIN',json.dumps(buckets))
            class Portfolios:
                POLICIES={profile:{}}
                @staticmethod
                def names(_):
                    return {'bob_paper_days':'bob_paper_test_days'}
            output=bob_diagnostics.entry_block_evidence(db,Portfolios())
            self.assertEqual(output['accounts'][0]['timeWindows15m'][0]
                             ['reasonCodes'],bucket['reasonCodes'])
            self.assertEqual(output['accounts'][0]['timeWindowsStored'],1)
            self.assertTrue(output['readOnly'])
            self.assertFalse(output['realOrders'])

    def test_old_bucket_codes_not_rewritten_or_backfilled(self):
        before={'entryTimeBuckets15mV1':{
            str(at(14,0)):{'checks':7,'directions':{'SHORT':7},
                          'reasonCodes':{'plan-or-timing':7}}}}
        original=copy.deepcopy(before)
        simulation.paper_entry_time_bucket(before,at(14,16),
            'Einstieg wartet: Aktueller Spot und letzter Kerzenschluss weichen über 1,2 ATR ab',
            {'direction':'SHORT'})
        self.assertEqual(before['entryTimeBuckets15mV1'][str(at(14,0))],
                         original['entryTimeBuckets15mV1'][str(at(14,0))])
        self.assertEqual(before['entryTimeBuckets15mV1'][str(at(14,15))]
                         ['reasonCodes'],{'spot-close-distance':1})


if __name__=='__main__':
    unittest.main()
