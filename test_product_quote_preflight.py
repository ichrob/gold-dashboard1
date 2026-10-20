"""Read-only 07:30 issuer warm-up; never open a paper/live position."""
import contextlib
import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch
from zoneinfo import ZoneInfo

import background_push
import paper_simulation as sim
import degiro_product_audit


def clock(hour, minute=0, weekday=20):
    return int(datetime(2026, 10, weekday, hour, minute,
                        tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)


class FakeConn:
    def __init__(self, rows=None, locked=True):
        self.rows = rows or {}
        self.locked = locked
        self.commits = 0
        self.queries = []
    def execute(self, sql, *args):
        self.queries.append(sql)
        cursor=Mock()
        if 'pg_try_advisory_xact_lock' in sql:
            cursor.fetchone.return_value=(self.locked,)
        elif 'SELECT payload FROM bob_paper_products' in sql:
            payload=self.rows.get('bob_paper_products')
            cursor.fetchone.return_value=(payload,) if payload else None
        else:
            raise AssertionError('Unexpected DB query: '+sql)
        return cursor
    def transaction(self):
        return contextlib.nullcontext()
    def commit(self):
        self.commits+=1


def database(conn):
    @contextlib.contextmanager
    def connect():
        yield conn
    return connect


class MorningIssuerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.feed={
            'listOrigin':'degiro-screenshot',
            'listUploadedAt':'2026-10-19T06:29:07.754Z',
            'products':[{'isin':'DE000FG7K366','productDirection':'LONG'}]
        }

    def test_session_schedule_and_boundary(self):
        self.assertEqual(background_push.degiro_session(clock(5, 15)), 'night')
        self.assertEqual(background_push.degiro_session(clock(7, 29)), 'night')
        self.assertEqual(background_push.degiro_session(clock(7, 30)), 'preparation')
        self.assertEqual(background_push.degiro_session(clock(7, 59)), 'preparation')
        self.assertEqual(background_push.degiro_session(clock(8, 0)), 'trading')
        self.assertEqual(background_push.degiro_session(clock(21, 59)), 'trading')
        self.assertEqual(background_push.degiro_session(clock(22, 0)), 'night')
        self.assertEqual(background_push.degiro_session(clock(12, 0, 18)), 'weekend')

    def test_off_hours_cannot_fetch_audit_or_trade(self):
        db = database(FakeConn({'bob_paper_products':self.feed}))
        with patch.object(sim,'quote_cache') as fetch, patch.object(degiro_product_audit,'store') as audit, \
             patch.object(sim,'run_once') as paper, patch.object(sim.background_push,'analyze') as market:
            for at in (clock(5, 15),clock(7, 29),clock(8, 0),clock(22, 0),clock(12,0,18)):
                self.assertEqual(sim.preflight_once(db,at)['state'],'paused')
            fetch.assert_not_called()
            audit.assert_not_called()
            paper.assert_not_called()
            market.assert_not_called()

    def test_morning_checks_only_source_and_audit_not_simulation(self):
        conn=FakeConn({'bob_paper_products':self.feed})
        quote={'DE000FG7K366':{'isin':'DE000FG7K366',
              'bid':5.0,'ask':5.01,'bidAt':'2026-10-19T21:58:00+02:00',
              'askAt':'2026-10-19T21:58:00+02:00'}}
        with patch.object(sim,'quote_cache',return_value=quote) as fetch, \
             patch.object(degiro_product_audit,'store',return_value={'status':'ok'}) as audit, \
             patch.object(sim,'run_once') as paper, patch.object(sim,'new_case') as new_case, \
             patch.object(sim.background_push,'analyze') as analyze:
            at=clock(7, 31)
            result=sim.preflight_once(database(conn),at)
            self.assertEqual(result,{'state':'research-only','auditUpdated':True,'ordersEnabled':False})
            fetch.assert_called_once_with(self.feed['products'],[],at)
            audit.assert_called_once_with(conn,self.feed,quote,at)
            self.assertEqual(conn.commits,1)
            paper.assert_not_called()
            new_case.assert_not_called()
            analyze.assert_not_called()
        # This preflight is not proof of a source quote being fresh or executable.
        self.assertEqual(quote['DE000FG7K366']['bidAt'],'2026-10-19T21:58:00+02:00')

    def test_no_screenshot_feed_is_never_replaced_by_fallback(self):
        conn=FakeConn({'bob_paper_products':{'listOrigin':'legacy',
                                            'products':[{'isin':'DE000FG7K366'}]}})
        with patch.object(sim,'quote_cache') as fetch, patch.object(degiro_product_audit,'store') as audit:
            result=sim.preflight_once(database(conn),clock(7, 40))
            self.assertEqual(result['state'],'waiting-for-screenshot')
            self.assertEqual(conn.commits,0)
            fetch.assert_not_called()
            audit.assert_not_called()

    def test_advisory_lock_skips_without_requests(self):
        conn=FakeConn({'bob_paper_products':self.feed},locked=False)
        with patch.object(sim,'quote_cache') as fetch:
            self.assertEqual(sim.preflight_once(database(conn),clock(7, 30))['state'],'busy')
            fetch.assert_not_called()

    def test_no_duplicate_preflight_thread_and_server_starts_it(self):
        import pathlib
        self.assertIn('paper_simulation.start_preflight(db)',
                      pathlib.Path('push_server.py').read_text(encoding='utf-8'))
        worker=Mock();worker.is_alive.return_value=True
        with patch.object(sim,'_PREFLIGHT_THREAD',worker):
            self.assertFalse(sim.start_preflight(database(FakeConn())))
            worker.start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
