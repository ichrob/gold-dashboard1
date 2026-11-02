"""Prove Drive-backed diagnostic pruning never touches unarchived source rows."""
import os
import unittest
import uuid
from contextlib import nullcontext
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch

import diagnostic_archived_catchup as catchup

NOW=datetime(2026,11,3,1,0,tzinfo=timezone.utc)
VERIFIED_AT=NOW-timedelta(minutes=30)
ARCHIVE_DAY=date(2026,11,3)


def receipt(**changes):
    proof={
        "version":"bob-evidence-archive-v3",
        "scope":"reviewed-evidence-tables-not-full-database-backup",
        "restoreVerified":True,
        "remoteDownloadVerified":True,
        "restoreIsolation":"separate-database-instance",
        "deletionPermitted":False,
        "evidenceDeleted":False,
        "archiveSha256":"a"*64,
        "driveFileId":"drive-private-placeholder",
    }
    proof.update(changes)
    return (ARCHIVE_DAY,"verified",VERIFIED_AT,{"receipt":proof})


class FakeConnection:
    autocommit=True
    def __init__(self,row):self.row=row;self.sql=[]
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def transaction(self):return nullcontext()
    def execute(self,q,*args):self.sql.append(q);return self
    def fetchone(self):return self.row


class ProofTests(unittest.TestCase):
    def test_verified_remote_restore_retains_only_previous_day_cutoff(self):
        c=FakeConnection(receipt())
        expected=datetime(2026,11,2,0,0,tzinfo=timezone.utc)
        self.assertEqual(catchup.backup_cutoff(c,NOW),expected)
        self.assertEqual(len(c.sql),1)

    def test_stale_wrong_scope_or_unverified_restores_cannot_prune(self):
        failures=[
            (ARCHIVE_DAY,"verified",NOW-timedelta(hours=7),receipt()[3]),
            (ARCHIVE_DAY,"failed",VERIFIED_AT,receipt()[3]),
            receipt(scope="partial-folder"),
            receipt(restoreVerified=False),
            receipt(remoteDownloadVerified=False),
            receipt(restoreIsolation="same-schema"),
            receipt(deletionPermitted=True),
            receipt(archiveSha256="bad"),
            receipt(driveFileId=None),
            (date(2026,11,4),"verified",VERIFIED_AT,receipt()[3]),
        ]
        for item in failures:
            with self.subTest(item=item):
                self.assertIsNone(catchup.backup_cutoff(FakeConnection(item),NOW))

    def test_disabled_or_no_capacity_no_db_access(self):
        forbidden=lambda: (_ for _ in ()).throw(AssertionError("No DB"))
        with patch.dict(os.environ,{"BOB_DRIVE_VERIFIED_DIAGNOSTIC_CATCHUP":"0"}):
            self.assertEqual(catchup.run_once(factory=forbidden,now=NOW)["status"],
                             "disabled")
        with patch.dict(os.environ,{"BOB_DRIVE_VERIFIED_DIAGNOSTIC_CATCHUP":"1"}), \
             patch("archive_worker.status",return_value={"status":"idle"}):
            no={"status":"observed","resource":"dpg-datjno1srm7s738vv500-a",
                "unit":"bytes","diskUsage":750_000_000,
                "observedAt":NOW.timestamp()-1}
            self.assertEqual(catchup.run_once(factory=forbidden,now=NOW,volume=no)
                             ["status"],"physical-reserve-unavailable")

    def test_calls_bounded_original_prune_only_after_backup_check(self):
        c=FakeConnection(receipt())
        volume={"status":"observed","resource":"dpg-datjno1srm7s738vv500-a",
                "unit":"bytes","diskUsage":670_000_000,
                "observedAt":NOW.timestamp()-1}
        with patch.dict(os.environ,{"BOB_DRIVE_VERIFIED_DIAGNOSTIC_CATCHUP":"1"}), \
             patch("archive_worker.status",return_value={"status":"idle"}), \
             patch("diagnostic_history.prune",return_value=500) as prune:
            result=catchup.run_once(factory=lambda:c,now=NOW,volume=volume)
        self.assertEqual(result["status"],"checked")
        self.assertEqual(result["journalRowsPruned"],500)
        self.assertFalse(result["evidenceOutsideJournalDeleted"])
        self.assertIsNone(result["diskBytesFreed"])
        prune.assert_called_once_with(
            c,archive_cutoff=datetime(2026,11,2,tzinfo=timezone.utc))

    def test_missing_proof_never_changes_journal(self):
        c=FakeConnection(None)
        volume={"status":"observed","resource":"dpg-datjno1srm7s738vv500-a",
                "unit":"bytes","diskUsage":670_000_000,
                "observedAt":NOW.timestamp()-1}
        with patch.dict(os.environ,{"BOB_DRIVE_VERIFIED_DIAGNOSTIC_CATCHUP":"1"}), \
             patch("archive_worker.status",return_value={"status":"idle"}), \
             patch("diagnostic_history.prune") as prune:
            result=catchup.run_once(factory=lambda:c,now=NOW,volume=volume)
        self.assertEqual(result["status"],"fresh-separate-Drive-restore-required")
        prune.assert_not_called()


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "isolated PostgreSQL integration")
class SourcePreservationTests(unittest.TestCase):
    def test_existing_cap_never_prunes_after_archived_source_cutoff(self):
        import psycopg
        from psycopg import sql
        import diagnostic_history as h
        schema="diag_drive_catchup_"+uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as c:
            c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                c.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                h.init(c)
                # 4 already archived entries, six unarchived newer entries.
                # No 7-day deletion; only cap applies in this fixture.
                for i in range(10):
                    stamp=datetime(2026,10,29,tzinfo=timezone.utc) if i<4 else NOW
                    c.execute("""INSERT INTO bob_diagnostic_history
                        (id,trace_id,stage,observed_at,recorded_at,payload)
                        VALUES(%s,'test','health',0,%s,'{}'::jsonb)""",
                        ("row-"+str(i),stamp))
                before=c.execute("""SELECT id,payload FROM
                    bob_diagnostic_history ORDER BY id""").fetchall()
                with patch.object(h,"_PRUNE_MAX_EVENTS",3):
                    with c.transaction():
                        removed=h.prune(c,archive_cutoff=datetime(2026,11,2,
                                                                  tzinfo=timezone.utc))
                self.assertEqual(removed,4)
                remaining=c.execute("SELECT id,payload FROM bob_diagnostic_history ORDER BY id").fetchall()
                self.assertEqual(remaining,before[4:])
                self.assertEqual(len(remaining),6)
            finally:
                c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__=="__main__":
    unittest.main()
