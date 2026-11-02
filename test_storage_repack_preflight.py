"""No destructive SQL or production changes from physical space preflight."""
import json
import os
import unittest
from unittest.mock import patch

import storage_repack_preflight as candidate


class CapacityTests(unittest.TestCase):
    def kwargs(self):
        return dict(pg_major=18,table_bytes=66_838_528,
                    disk_usage=686_571_500,current_backup=True,
                    has_primary_key=True,extension_version="1.5.3",
                    client_available=True,wal_bytes_observed=False)

    def test_conservative_headroom_is_not_execution_permission(self):
        result=candidate.evaluate(**self.kwargs())
        self.assertGreater(result['estimatedHeadroomAfterTwoCopies'],120_000_000)
        self.assertTrue(result['conservativeCapacityThresholdMet'])
        self.assertFalse(result['readyToExecute'])
        self.assertTrue(result['requiresIndependentActualWALScratchAndLockBudget'])
        self.assertFalse(result['deletionAuthorized'])
        self.assertIsNone(result['diskBytesFreed'])
        self.assertEqual(result['table'],'public.bob_improvement_observations')

    def test_insufficient_capacity_or_restore_blocks_but_not_claims_savings(self):
        for override in ({'disk_usage':890_000_000},
                         {'disk_usage':755_000_000},
                         {'table_bytes':120_000_000},
                         {'current_backup':False},
                         {'pg_major':15},
                         {'extension_version':None},
                         {'has_primary_key':False},
                         {'client_available':False}):
            with self.subTest(override=override):
                r=candidate.evaluate(**{**self.kwargs(),**override})
                self.assertFalse(r['readyToExecute'])
                self.assertIsNone(r['diskBytesFreed'])
                if 'disk_usage' in override:
                    self.assertFalse(r['conservativeCapacityThresholdMet'])

    def test_no_execution_verb_and_no_database_connection_for_invalid_args(self):
        import io
        from contextlib import redirect_stdout
        output=io.StringIO()
        with patch.object(candidate,'inspect_live',
                          side_effect=AssertionError('must not inspect')):
            with redirect_stdout(output):
                ret=candidate.main(['execute','--force'])
        self.assertEqual(ret,2)
        self.assertNotIn('execute --force',output.getvalue())

    def test_errors_redacted(self):
        import io
        from contextlib import redirect_stdout
        output=io.StringIO()
        with patch.object(candidate,'inspect_live',side_effect=ValueError(
                'private password and database url')):
            with redirect_stdout(output):
                code=candidate.main(['preflight'])
        self.assertEqual(code,3)
        result=json.loads(output.getvalue())
        self.assertEqual(result['status'],'preflight-unavailable')
        self.assertNotIn('password',output.getvalue())
        self.assertNotIn('url',output.getvalue())
        self.assertIsNone(result['diskBytesFreed'])


if __name__=='__main__':
    unittest.main()
