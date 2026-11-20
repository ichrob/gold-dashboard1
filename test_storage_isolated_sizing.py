"""Bounded transport and exact multiset checks for the manual sizing model."""
import contextlib
import unittest
from unittest.mock import patch

import storage_isolated_sizing as sizing


class Cursor:
    def __init__(self, rows):
        self.rows=list(rows)
        self.requests=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,query): pass
    def fetchmany(self,n):
        self.requests.append(n)
        rows=self.rows[:n]
        del self.rows[:n]
        return rows


class Connection:
    def __init__(self,rows): self.cur=Cursor(rows)
    def transaction(self): return contextlib.nullcontext()
    def cursor(self,*,name):
        assert name=='sizing_fingerprint'
        return self.cur


class SizingTests(unittest.TestCase):
    @patch.object(sizing,'memory_guard')
    def test_fingerprint_ignores_order_but_detects_change_and_duplicates(self,guard):
        rows=[('a','{"number": 0.12345678901234567890}'),('b',None),('a','{"number": 0.12345678901234567890}')]
        baseline=sizing.fingerprint(Connection(rows),'ignored')
        self.assertEqual(baseline,sizing.fingerprint(Connection(rows[::-1]),'ignored'))
        self.assertNotEqual(baseline,sizing.fingerprint(Connection(rows[:-1]),'ignored'))
        changed=[*rows[:-1],('a','{"number": 0.12345678901234567891}')]
        self.assertNotEqual(baseline,sizing.fingerprint(Connection(changed),'ignored'))

    @patch.object(sizing,'memory_guard')
    def test_server_cursor_fetches_at_most_32_rows(self,guard):
        conn=Connection([(str(n),None) for n in range(100)])
        proof=sizing.fingerprint(conn,'ignored')
        self.assertEqual(proof['rows'],100)
        self.assertEqual(conn.cur.requests,[32]*5)
        self.assertEqual(guard.call_count,5)

    def test_oversized_row_fails(self):
        with self.assertRaises(ValueError): sizing.row_hash(('x'*(2*1024*1024),))

    @patch.object(sizing,'Path')
    @patch.object(sizing.time,'sleep')
    @patch.object(sizing.time,'monotonic',side_effect=[0,0,31])
    def test_persistent_memory_pressure_stops(self,clock,sleep,path):
        path.return_value.exists.return_value=True
        path.return_value.read_text.return_value=str(421*1024*1024)
        with self.assertRaises(MemoryError): sizing.memory_guard()
        sleep.assert_called_once_with(0.5)

    @patch.object(sizing,'Path')
    @patch.object(sizing.time,'sleep')
    @patch.object(sizing.time,'monotonic',side_effect=[0,0])
    def test_transient_pressure_pauses_without_raising_limit(self,clock,sleep,path):
        path.return_value.exists.return_value=True
        path.return_value.read_text.side_effect=[str(421*1024*1024),str(300*1024*1024)]
        sizing.memory_guard()
        sleep.assert_called_once_with(0.5)


if __name__=='__main__': unittest.main()
