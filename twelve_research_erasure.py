"""Fail-closed local erasure for Twelve Data research-only SQLite archives.

This does not delete Drive backups or prove contractual erasure on its own.
No automatic job, no provider network, no trading data access.
"""
import os
from contextlib import closing
import sqlite3
import stat
from pathlib import Path

# SQLite may retain licensed raw rows in rollback journals or write-ahead-log
# sidecars. A logical DELETE must never be presented as complete while these
# files exist or the archive uses a non-DELETE journal mode.
JOURNAL_SUFFIXES = ("-wal", "-shm", "-journal")


def _incomplete(code):
    return {"code": code, "remoteCopiesErased": False,
            "backupCopiesErased": False}


def _sidecar_present(path):
    return any(os.path.lexists(str(path) + suffix) for suffix in JOURNAL_SUFFIXES)


def erase_local_research(archive_path, *, confirmed=False):
    """Erase research tables and VACUUM after an explicit operator action.

    Refuse symlinks, non-private files and missing authorization. A full
    retention sign-off must also independently erase encrypted remote copies.
    """
    if confirmed is not True:
        return {"code": "ERASURE_NOT_AUTHORIZED"}
    if not archive_path or not os.path.isabs(archive_path):
        return {"code": "INVALID_PRIVATE_ARCHIVE"}
    path = Path(archive_path)
    try:
        # A live WAL/SHM or stale rollback journal can still contain original
        # vendor data. Require an independently quiesced, checkpointed file.
        # Never remove these sidecars automatically: another connection could
        # be using them, and blind unlinking risks data corruption.
        if _sidecar_present(path):
            return _incomplete("ERASURE_REQUIRES_OFFLINE_JOURNAL_REVIEW")
        st = os.lstat(path)
        parent = os.lstat(path.parent)
        if (not stat.S_ISREG(st.st_mode) or not stat.S_ISDIR(parent.st_mode)
                or st.st_mode & 0o077 or parent.st_mode & 0o077
                or st.st_uid != os.geteuid() or parent.st_uid != os.geteuid()):
            return {"code": "INVALID_PRIVATE_ARCHIVE"}
        with closing(sqlite3.connect(str(path), timeout=10, isolation_level=None)) as db:
            # WAL, PERSIST, TRUNCATE and MEMORY modes need a different,
            # independently verified retention procedure. In particular WAL
            # can recreate sidecars as soon as the database is opened.
            mode = db.execute("PRAGMA journal_mode").fetchone()[0].lower()
            if mode != "delete":
                return _incomplete("ERASURE_REQUIRES_OFFLINE_JOURNAL_REVIEW")
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
            names = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("td_research_bars", "td_research_depth"):
                if table in names:
                    db.execute("DELETE FROM " + table)
            db.execute("COMMIT")
            db.execute("VACUUM")
            remaining = sum(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                            for table in ("td_research_bars", "td_research_depth")
                            if table in names)
        # Report only logical deletion in the local SQLite file. This cannot
        # certify filesystem snapshots, backup media, SSD remanence or Drive.
        if _sidecar_present(path):
            return _incomplete("ERASURE_UNVERIFIED")
        return _incomplete("LOCAL_RESEARCH_ERASED" if remaining == 0
                           else "ERASURE_UNVERIFIED")
    except (OSError, sqlite3.Error):
        return {"code": "ERASURE_UNVERIFIED", "remoteCopiesErased": False,
                "backupCopiesErased": False}
