import copy
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import paper_comparison_report as report


def clock(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()*1000


def episode(at=None, rule='r1', trend='strong-trend'):
    at=at or clock('2026-11-05T10:00:00')
    def arm(profit):
        return dict(status='closed',modelNetEur=profit,entryAt=at,exitAt=at+60000,
            entryQuoteAt=at,exitQuoteAt=at+60000,entryAsk=10.,exitBid=11.,
            units=10,entryDebit=101.,isin='TEST-PRODUCT',observedPeakPnlEur=20.,observedTroughPnlEur=-10.)
    return dict(version=report.VERSION,ruleVersion=rule,startedAt=at,checkedAt=at+60000,
        trend=trend,arms={'confirmed:fixed:0':arm(5.),'confirmed:trailing:0':arm(12.)})


def evaluate(rows):
    starts={}
    for r in rows:
        if report.day(r.get('startedAt')):
            starts[r['ruleVersion']]=min(starts.get(r['ruleVersion'],report.day(r['startedAt'])),report.day(r['startedAt']))
    return report.build(iter(rows),starts)


def pair(result,phase='exploration',trend='all',rule='r1'):
    group=next(g for g in result['groups'] if (g['phase'],g['trend'],g['ruleVersion'])==(phase,trend,rule))
    return next(p for p in group['comparisons'] if p['a']=='confirmed:fixed:0' and p['b']=='confirmed:trailing:0')


class ReportTests(unittest.TestCase):
    def test_stream_query_materializes_scalar_anchors_not_json_window(self):
        class Cursor:
            def __init__(self): self.query = None; self.itersize = None
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, query): self.query = query
            def __iter__(self): return iter(())
        class Conn:
            def __init__(self): self.cursor_value = Cursor()
            def cursor(self, name=None):
                self.name = name
                return self.cursor_value
        conn = Conn()
        out = report.report(conn)
        query = conn.cursor_value.query
        self.assertEqual(conn.name, 'bob_comparison_evaluation')
        self.assertIn('WITH anchors AS MATERIALIZED', query)
        self.assertIn("GROUP BY payload->>'ruleVersion'", query)
        self.assertNotIn(' OVER (PARTITION BY ', query)
        self.assertEqual(out['episodes'], 0)

    def test_full_history_over_200_and_paired_exclusion(self):
        rows=[episode() for _ in range(205)]
        missing=episode();missing['arms']['confirmed:trailing:0'].update(status='inconclusive',modelNetEur=999)
        rows.append(missing)
        original=copy.deepcopy(rows)
        r=evaluate(rows);p=pair(r)
        self.assertEqual(r['episodes'],206)
        self.assertEqual(p['difference']['cases'],205)
        self.assertEqual(p['excluded'],1)
        self.assertEqual(p['difference']['meanEur'],7)
        self.assertEqual(p['candidate']['meanGivebackEur'],8)
        self.assertEqual(p['baseline']['meanGivebackEur'],15)
        self.assertEqual(rows,original)
        self.assertFalse(r['strategyWinnerConfirmed'])
        self.assertFalse(r['historyComplete'])

    def test_no_entry_unknown_open_nan_are_not_zero_results(self):
        rows=[]
        for state in ('no-entry','open','pending','inconclusive','closed'):
            r=episode();r['arms']['confirmed:trailing:0'].update(status=state,modelNetEur=float('nan'))
            rows.append(r)
        out=evaluate(rows);p=pair(out)
        self.assertEqual(p['difference']['cases'],0)
        self.assertIsNone(p['difference']['meanEur'])
        self.assertEqual(p['excluded'],5)
        json.dumps(out,allow_nan=False)

    def test_exit_requires_identical_product_and_entry(self):
        for field,value in (('isin','OTHER'),('entryAsk',9),('entryDebit',100),('entryQuoteAt',1)):
            r=episode();r['arms']['confirmed:trailing:0'][field]=value
            p=pair(evaluate([r]));self.assertEqual(p['entryMismatch'],1)
            self.assertEqual(p['difference']['cases'],0)

    def test_phases_rules_and_regimes_never_mix(self):
        first=episode(clock('2026-11-05T10:00:00'))
        later=episode(clock('2026-11-19T10:00:00'),trend='sideways')
        other=episode(clock('2026-11-19T10:00:00'),rule='r2')
        out=evaluate([first,later,other])
        self.assertEqual(out['cohorts'][0]['validationFrom'],'2026-11-19')
        self.assertEqual(pair(out)['difference']['cases'],1)
        self.assertEqual(pair(out,'validation','sideways')['difference']['cases'],1)
        self.assertEqual(pair(out,rule='r2')['difference']['cases'],1)
        # 23:30 UTC is already the next Zurich day (validation).
        self.assertEqual(report.day(clock('2026-11-18T23:30:00')).isoformat(),'2026-11-19')

    def test_missing_excursions_and_negative_outcome(self):
        r=episode();a=r['arms']['confirmed:trailing:0'];a['modelNetEur']=-8
        a.pop('observedPeakPnlEur')
        p=pair(evaluate([r]))
        self.assertEqual(p['candidate']['meanLossEur'],-8)
        self.assertEqual(p['candidate']['worstEur'],-8)
        self.assertIsNone(p['candidate']['meanGivebackEur'])
        self.assertEqual(p['difference']['meanEur'],-13)

    def test_failure_budget_does_not_return_partial_success(self):
        with self.assertRaises(TimeoutError):report.build(iter([episode()]),{},deadline=0)
        out=evaluate([])
        self.assertEqual(out['status'],'awaiting-first-original-input')
        self.assertFalse(out['actualNetKnown'])

    def test_overview_preserves_readonly_evaluation(self):
        import bob_test_overview
        data=evaluate([episode()])
        out=bob_test_overview.snapshot({'areas':{'simulationAndPush':{'shadowStudies':{'entryExitComparison':{'evaluation':data}}}}},0)
        self.assertEqual(out['entryExitEvaluation'],data)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_streaming_projection_all_rows_and_no_original_mutation(self):
        import uuid
        import psycopg
        from psycopg import sql
        import paper_entry_exit_comparison
        schema='comparison_report_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                paper_entry_exit_comparison.init(conn)
                r=episode()
                for a in r['arms'].values():
                    a['choice']={'isin':a.pop('isin')}
                    a['entryQuote']={'private':'not part of report'}
                payload=json.dumps(r)
                with conn.cursor() as cursor:
                    cursor.executemany('INSERT INTO bob_entry_exit_comparison VALUES(%s,TRUE,%s::jsonb)',[(str(i),payload) for i in range(205)])
                before=conn.execute('SELECT md5(string_agg(payload::text,id ORDER BY id)) FROM bob_entry_exit_comparison').fetchone()
                out=report.report(conn)
                self.assertEqual(pair(out)['difference']['cases'],205)
                self.assertEqual(out['episodes'],205)
                self.assertNotIn('TEST-PRODUCT',json.dumps(out))
                self.assertNotIn('private',json.dumps(out))
                self.assertEqual(before,conn.execute('SELECT md5(string_agg(payload::text,id ORDER BY id)) FROM bob_entry_exit_comparison').fetchone())
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                conn.commit()

if __name__=='__main__':unittest.main()
