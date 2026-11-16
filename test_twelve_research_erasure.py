import sqlite3
import tempfile
import unittest
from pathlib import Path

from twelve_research_erasure import erase_local_research


class ResearchErasureTests(unittest.TestCase):
    def test_explicit_erasure_only_and_other_tables_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            dbfile = root / "research.sqlite"
            with sqlite3.connect(dbfile) as db:
                db.execute("CREATE TABLE td_research_bars (x TEXT)")
                db.execute("INSERT INTO td_research_bars VALUES ('synthetic')")
                db.execute("CREATE TABLE td_research_depth (x TEXT)")
                db.execute("INSERT INTO td_research_depth VALUES ('synthetic')")
                db.execute("CREATE TABLE td_credit_ledger (x INTEGER)")
                db.execute("INSERT INTO td_credit_ledger VALUES (1)")
            dbfile.chmod(0o600)
            self.assertEqual(erase_local_research(str(dbfile))["code"], "ERASURE_NOT_AUTHORIZED")
            with sqlite3.connect(dbfile) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM td_research_bars").fetchone()[0], 1)
            result = erase_local_research(str(dbfile), confirmed=True)
            self.assertEqual(result["code"], "LOCAL_RESEARCH_ERASED")
            self.assertFalse(result["remoteCopiesErased"])
            with sqlite3.connect(dbfile) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM td_research_bars").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM td_research_depth").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM td_credit_ledger").fetchone()[0], 1)

    def test_wal_mode_is_not_mistaken_for_verified_erasure(self):
        # The WAL mode persists even after the last connection closes.
        # A separate checkpoint/retention review must occur before erasure.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            dbfile = root / "research.sqlite"
            db = sqlite3.connect(dbfile)
            try:
                self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
                db.execute("CREATE TABLE td_research_bars (x TEXT)")
                db.execute("INSERT INTO td_research_bars VALUES ('synthetic secret')")
                db.commit()
            finally:
                db.close()
            dbfile.chmod(0o600)
            result = erase_local_research(str(dbfile), confirmed=True)
            self.assertEqual(result["code"], "ERASURE_REQUIRES_OFFLINE_JOURNAL_REVIEW")
            self.assertFalse(result["backupCopiesErased"])
            with sqlite3.connect(dbfile) as check:
                self.assertEqual(check.execute(
                    "SELECT COUNT(*) FROM td_research_bars").fetchone()[0], 1)

    def test_sidecars_block_erasure_without_unlinking_or_data_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            dbfile = root / "research.sqlite"
            with sqlite3.connect(dbfile) as db:
                db.execute("CREATE TABLE td_research_bars (x TEXT)")
                db.execute("INSERT INTO td_research_bars VALUES ('synthetic')")
            dbfile.chmod(0o600)
            sidecar = Path(str(dbfile) + "-journal")
            sidecar.write_bytes(b"synthetic sidecar - not a valid SQLite journal")
            result = erase_local_research(str(dbfile), confirmed=True)
            self.assertEqual(result["code"], "ERASURE_REQUIRES_OFFLINE_JOURNAL_REVIEW")
            self.assertTrue(sidecar.exists())  # the routine never blindly unlinks
            with sqlite3.connect(dbfile) as check:
                self.assertEqual(check.execute(
                    "SELECT COUNT(*) FROM td_research_bars").fetchone()[0], 1)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            target = root / "target.sqlite"
            sqlite3.connect(target).close()
            target.chmod(0o600)
            link = root / "link.sqlite"
            link.symlink_to(target)
            self.assertEqual(erase_local_research(str(link), confirmed=True)["code"],
                             "INVALID_PRIVATE_ARCHIVE")


if __name__ == "__main__":
    unittest.main()
