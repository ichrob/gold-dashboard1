import unittest
from diagram_evidence import signal_evidence

class SignalEvidenceTests(unittest.TestCase):
    def test_spacing_is_reserved_before_outcome_and_duplicates_do_not_inflate(self):
        start=1800000000000
        def row(minute,value,origin='background'):
            return ({'recordedAt':start+minute*60000,'barAt':start+minute*60000,'direction':'LONG','origin':origin},[value]*3)
        score=lambda r,t,h: {'directionalPct':t} if t is not None else None
        rows=[row(0,None),row(1,99),row(15,-1),row(15,999,'interactive'),row(30,2)]
        report=signal_evidence(rows,score)
        self.assertEqual(report['15']['selected'],3)
        self.assertEqual(report['15']['separated'],2)
        self.assertEqual(report['15']['missing'],1)
        self.assertEqual(report['15']['blocks'][0]['total'],1)
        self.assertEqual(report['60']['separated'],0)
    def test_neutral_invalid_and_nonfinite_excluded(self):
        rows=[({'recordedAt':1800000000000,'direction':'NEUTRAL'},[1]*3),
              ({'recordedAt':float('nan'),'direction':'LONG'},[1]*3)]
        self.assertEqual(signal_evidence(rows,lambda *args:None)['15']['selected'],0)
