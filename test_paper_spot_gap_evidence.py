"""Original spot availability checks for six shared paper gap clocks.

Tests use a fake indexed archive and never touch a broker or run a simulation.
"""
import json
import unittest

import paper_spot_gap_evidence as coverage
import bob_diagnostics as diag


class Rows:
    def __init__(self, value):
        self.value=value
    def fetchone(self):
        return (self.value,) if self.value is not None else None


class SpotArchive:
    def __init__(self, points):
        self.points=points
        self.queries=[]
    def execute(self, sql, args):
        assert sql.startswith('SELECT (extract(epoch from quote_at)*1000)::double precision')
        assert 'bob_spot_observations' in sql
        assert args[0]==coverage.STREAM
        assert len(args)==3
        self.queries.append((sql,args))
        _,low,high=args
        found=[p for p in self.points if low<=p<=high]
        if not found:
            return Rows(None)
        return Rows(max(found) if 'DESC LIMIT 1' in sql else min(found))


def case(at, state='inconclusive'):
    return {'status':state,'events':[{'kind':'data-gap','recordedAt':at}]}


class ArchivedSpotCoverageTests(unittest.TestCase):
    def test_shared_gap_clock_queries_once_and_never_exports_price(self):
        now=1_800_000_000_000
        at=now-100_000
        db=SpotArchive([at-35_000,at+24_000,at+400_000])
        accounts=[
            {'profile':'conservative','recentCases':{'status':'observed','items':[case(at)]}},
            {'profile':'balanced','recentCases':{'status':'observed','items':[case(at)]}},
        ]
        report=coverage.snapshot(db,accounts,now_ms=now)
        self.assertEqual(report['status'],'observed')
        self.assertEqual(report['sampledDistinctGapClocks'],1)
        self.assertEqual(report['instants'][0]['affectedVirtualCases'],2)
        self.assertEqual(report['instants'][0]['state'],'bracketed-original-observations')
        self.assertEqual(report['instants'][0]['originalBeforeAt'],at-35_000)
        self.assertEqual(report['instants'][0]['originalAfterAt'],at+24_000)
        self.assertEqual(len(db.queries),2)
        self.assertNotIn('"price":',json.dumps(report).lower())
        self.assertFalse(report['realOrders'])

    def test_one_sided_or_absent_original_is_not_recovered(self):
        now=1_800_000_000_000
        at=now-100_000
        account=[{'recentCases':{'status':'observed','items':[case(at)]}}]
        one=coverage.snapshot(SpotArchive([at-6_000]),account,now_ms=now)
        self.assertEqual(one['instants'][0]['state'],'one-sided-original-observation')
        empty=coverage.snapshot(SpotArchive([]),account,now_ms=now)
        self.assertEqual(empty['instants'][0]['state'],
                         'no-original-observation-within-five-minutes')

    def test_expired_and_invalid_archive_inputs_never_become_evidence(self):
        now=1_800_000_000_000
        old=now-coverage.RETENTION_MS-1000
        db=SpotArchive([old])
        result=coverage.snapshot(db,[{'recentCases':{
            'status':'observed','items':[case(old),case(float('nan'))]}}],now_ms=now)
        self.assertEqual(result['sampledDistinctGapClocks'],1)
        self.assertEqual(result['instants'][0]['state'],'outside-archive-retention')
        self.assertEqual(len(db.queries),0)
        self.assertFalse(result['caseObservationsComplete'])
        self.assertEqual(coverage.snapshot(db,None,now_ms=now)['status'],'unavailable')

    def test_private_diagnostics_marks_absent_archive_unknown(self):
        s={'status':'observed','accounts':[{'profile':'conservative',
            'recentCases':{'status':'observed','items':[case(1234)]}}]}
        result=diag.simulation_evidence_snapshot(s)
        self.assertEqual(result['originalSpotArchive']['status'],'unavailable')
        s['spotGapArchive']={'status':'observed','readOnly':True,'instants':[]}
        result=diag.simulation_evidence_snapshot(s)
        self.assertEqual(result['originalSpotArchive']['status'],'observed')
