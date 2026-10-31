"""Old metric evidence and cold pointers must survive the reporting window."""
import unittest
import metric_quality as metric


class RetentionTests(unittest.TestCase):
    def test_capture_retention_hook_never_deletes_history(self):
        class Connection:
            def execute(self, *args):
                raise AssertionError('No retention deletion is permitted')
        for now in (0, 1_800_000_000_000, 2_000_000_000_000):
            self.assertFalse(metric._prune_expired_checks(Connection(), now))


if __name__ == '__main__':
    unittest.main()
