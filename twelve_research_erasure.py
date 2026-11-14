"""Fail-closed local erasure for Twelve Data research-only SQLite archives.

This does not delete Drive backups or prove contractual erasure on its own.
No automatic job, no provider network, no trading data access.
"""
import os
import sqlite3
import stat
from pathlib import Path


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
        st = os.lstat(path)
        parent = os.lstat(path.parent)
        if (not stat.S_ISREG(st.st_mode) or not stat.S_ISDIR(parent.st_mode)
                or st.st_mode & 0o077 or parent.st_mode & 0o077
                or st.st_uid != os.geteuid() or parent.st_uid != os.geteuid()):
            return {"code": "INVALID_PRIVATE_ARCHIVE"}
        with sqlite3.connect(str(path), timeout=10, isolation_level=None) as db:
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
        return {"code": "LOCAL_RESEARCH_ERASED" if remaining == 0 else "ERASURE_UNVERIFIED",
                "remoteCopiesErased": False, "backupCopiesErased": False}
    except (OSError, sqlite3.Error):
        return {"code": "ERASURE_UNVERIFIED", "remoteCopiesErased": False,
                "backupCopiesErased": False}
