"""The manual CLI closes its archive on success and on an interrupted query."""
import sqlite3
import unittest
from unittest.mock import patch

import twelve_research_extension as td


class ArchiveCleanupTests(unittest.TestCase):
    def test_archive_closed_after_success_and_query_error(self):
        for fails in (False, True):
            with self.subTest(fails=fails):
                db = sqlite3.connect(':memory:', isolation_level=None)
                argv = ['research', '--symbol', 'XAU/USD', '--interval', '1h',
                        '--earliest-only', '--archive', 'synthetic-unused.sqlite']
                try:
                    with patch('sys.argv', argv), \
                         patch.object(td.sqlite3, 'connect', return_value=db), \
                         patch.object(td, 'fetch_earliest_timestamp',
                                      side_effect=RuntimeError('synthetic') if fails else None,
                                      return_value={'code': 'SYNTHETIC'}), \
                         patch('builtins.print'):
                        if fails:
                            with self.assertRaises(RuntimeError):
                                td.main()
                        else:
                            td.main()
                    with self.assertRaises(sqlite3.ProgrammingError):
                        db.execute('SELECT 1')
                finally:
                    db.close()
