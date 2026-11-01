"""Regression checks for the off-hours, no-quote screenshot audit.

No browser, broker, issuer network or live database access is required.
"""
import copy
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import paper_simulation as sim


class Rows:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value


class Database:
    def __init__(self, feed=None, checked=None, lock=True):
        self.feed = copy.deepcopy(feed)
        self.checked = copy.deepcopy(checked)
        self.lock = lock
        self.queries = []
        self.commits = 0

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return nullcontext()

    def execute(self, sql):
        self.queries.append(sql)
        if 'pg_try_advisory_xact_lock' in sql:
            return Rows((self.lock,))
        if 'SELECT payload FROM bob_paper_products' in sql:
            return Rows((copy.deepcopy(self.feed),) if self.feed else None)
        if 'SELECT payload FROM bob_degiro_product_audit' in sql:
            return Rows((copy.deepcopy(self.checked),) if self.checked else None)
        raise AssertionError('Unexpected SQL')

    def commit(self):
        self.commits += 1


GEN = '2026-10-30T02:58:46+00:00'
FEED = {'listOrigin': 'degiro-screenshot', 'listUploadedAt': GEN,
        'products': [{'isin': 'DE000FG4JXV7', 'isinConfirmed': True}]}


class OffHoursAuditTests(unittest.TestCase):
    def test_new_night_list_is_recorded_once_without_provider_queries(self):
        db = Database(FEED)
        captured = []

        def save(_, feed, quotes, at):
            captured.append((copy.deepcopy(feed), quotes, at))
            db.checked = {'listUploadedAt': feed['listUploadedAt'],
                          'marketContext': 'Handelszeit und Quellzeit je Produkt getrennt prüfen',
                          'items': [], 'tradeApproved': False}

        with patch.object(sim.background_push, 'degiro_session', return_value='night'), \
             patch.object(sim, 'quote_cache', side_effect=AssertionError('provider called')), \
             patch('degiro_product_audit.store', side_effect=save):
            first = sim.audit_offhours_once(db, now_ms=12345)
            second = sim.audit_offhours_once(db, now_ms=12346)

        self.assertEqual(first, {'state': 'evidence-only', 'auditUpdated': True, 'ordersEnabled': False})
        self.assertEqual(second['state'], 'already-checked')
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0], (FEED, {}, 12345))
        self.assertEqual(db.feed, FEED, 'Original timestamps and identity must not change')
        self.assertFalse(db.checked['tradeApproved'])

    def test_sunday_migrates_previous_audit_once_without_network_or_quotes(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        sunday = int(datetime(2026, 11, 1, 9, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        old={'listUploadedAt': GEN, 'items': [{'isin': FEED['products'][0]['isin'],
             'leverageObservation': {'value': 12.0, 'at': '2026-10-30T08:00:00Z',
                                     'current': True, 'kind': 'calculated-gearing'}}]}
        db=Database(FEED, checked=old)
        events=[]
        def save(_, feed, quotes, at):
            events.append((copy.deepcopy(feed), quotes, at))
            db.checked={'listUploadedAt': feed['listUploadedAt'],
                        'marketContext': 'DEGIRO-Wochenende · letzter datierter Handelswert bleibt historisch',
                        'items': old['items'], 'tradeApproved': False}
        with patch.object(sim.background_push,'degiro_session',return_value='weekend'), \
             patch.object(sim,'quote_cache',side_effect=AssertionError('weekend network call')), \
             patch('degiro_product_audit.store',side_effect=save):
            first=sim.audit_offhours_once(db,now_ms=sunday)
            second=sim.audit_offhours_once(db,now_ms=sunday+300000)
        self.assertEqual(first['state'],'evidence-only')
        self.assertEqual(second['state'],'already-checked')
        self.assertEqual(len(events),1)
        self.assertEqual(events[0],(FEED,{},sunday))
        self.assertFalse(db.checked['tradeApproved'])

    def test_existing_worker_schedules_offhours_audit_without_trading(self):
        class StopLoop(Exception):
            pass

        def stop(_seconds):
            raise StopLoop

        with patch.object(sim.background_push, 'degiro_session', return_value='night'), \
             patch.object(sim.background_push, 'degiro_seconds_to_transition', return_value=3600), \
             patch.object(sim, 'audit_offhours_once',
                          return_value={'state': 'already-checked',
                                        'auditUpdated': False}) as audit:
            with self.assertRaises(StopLoop):
                sim._preflight_loop(lambda: None, wait=stop)
            audit.assert_called_once()

    def test_trading_and_preparation_never_use_offhours_path(self):
        for phase in ('trading', 'preparation'):
            with self.subTest(phase=phase), patch.object(sim.background_push, 'degiro_session', return_value=phase):
                result = sim.audit_offhours_once(lambda: self.fail('DB opened'), now_ms=12345)
                self.assertEqual(result['state'], 'paused')
                self.assertFalse(result['auditUpdated'])

    def test_missing_or_non_screenshot_list_is_not_certified(self):
        for feed in (None, {}, {'listOrigin': 'degiro-screenshot',
                               'listUploadedAt': GEN, 'products': []},
                     {'listOrigin': 'external', 'listUploadedAt': GEN, 'products': FEED['products']}):
            with self.subTest(feed=feed), patch.object(sim.background_push, 'degiro_session', return_value='weekend'), \
                 patch('degiro_product_audit.store', side_effect=AssertionError('unexpected audit')):
                db = Database(feed)
                result = sim.audit_offhours_once(db, now_ms=12345)
                self.assertEqual(result['state'], 'waiting-for-screenshot')
                self.assertEqual(db.commits, 0)

    def test_busy_lock_does_not_write_or_approve(self):
        db = Database(FEED, lock=False)
        with patch.object(sim.background_push, 'degiro_session', return_value='night'), \
             patch('degiro_product_audit.store', side_effect=AssertionError('unexpected audit')):
            result = sim.audit_offhours_once(db, now_ms=12345)
        self.assertEqual(result['state'], 'busy')
        self.assertFalse(result['auditUpdated'])


if __name__ == '__main__':
    unittest.main()
