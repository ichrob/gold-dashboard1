"""Synthetic-only offline COPY/manifest checks; no real archive or Render access."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import storage_archive_copy_preflight as preflight


def synthetic_archive(path, *, omit=None, altered_bytes=False,
                      missing_columns=False, invalid_scope=False,
                      extra_member=False, empty_decisions=False):
    blobs = []
    for name, data in (
        ("bob_decision_audit",
         b"synthetic-decision-1\n" if not empty_decisions else b""),
        ("bob_diagnostic_history",
         b"synthetic-diagnostic-1\nsynthetic-diagnostic-2\n"),
    ):
        if name == omit:
            continue
        columns = ([["id", "text"], ["recorded_at", "timestamp with time zone"],
                    ["payload", "jsonb"]])
        if name == "bob_diagnostic_history":
            columns.insert(2, ["stage", "text"])
        if missing_columns and name == "bob_diagnostic_history":
            columns = [c for c in columns if c[0] != "recorded_at"]
        blobs.append((name, data, columns))
    members = {}
    manifest = {
        "version": "bob-evidence-archive-v3",
        "scope": ("wrong-scope" if invalid_scope else
                  "reviewed-evidence-tables-not-full-database-backup"),
        "evidenceDeleted": False,
        "deletionPermitted": False,
        "absentTables": [],
        "tables": [],
    }
    for i, (name, data, columns) in enumerate(blobs):
        manifest["tables"].append({
            "name": name, "file": f"{i}.copy", "segment": 0,
            "columns": columns, "bytes": len(data),
            "rows": data.count(b"\n"),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
        members[f"{i}.copy"] = data + (b"X" if altered_bytes and i == 0 else b"")
    if extra_member:
        members["private-extra"] = b"private"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
        archive.writestr("manifest.json", json.dumps(manifest))
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PlaintextArchivePreflightTests(unittest.TestCase):
    def test_two_historical_tables_are_checksum_bound_but_not_replay_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.zip"
            digest = synthetic_archive(path)
            result = preflight.inspect(path, digest)
            self.assertEqual(result["status"], "selected-copy-segments-matched")
            self.assertEqual(result["inspectedRows"], 3)
            self.assertEqual(result["inspectedSegments"], 2)
            self.assertTrue(result["plaintextArchiveMatchedSuppliedDigest"])
            self.assertFalse(result["independentExpectedDigestProvenanceVerified"])
            self.assertFalse(result["evaluationManifestBoundToArchive"])
            self.assertFalse(result["originalTimeRangeCoverageVerified"])
            self.assertFalse(result["fullOriginalReplayVerified"])
            self.assertFalse(result["archiveFileAndBatchBoundVerified"])
            self.assertFalse(result["deletionAuthorized"])
            self.assertIsNone(result["physicalBytesFreed"])
            self.assertNotIn("synthetic-", json.dumps(result))
            self.assertNotIn(str(path), json.dumps(result))
            self.assertNotIn(digest, json.dumps(result))

    def test_wrong_sha_and_invalid_supplied_digest_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.zip"
            digest = synthetic_archive(path)
            self.assertEqual(preflight.inspect(path, "0"*64)["status"],
                             "plaintext-archive-digest-mismatch")
            self.assertEqual(preflight.inspect(path, "private")["status"],
                             "invalid-expected-digest")
            self.assertEqual(preflight.inspect(path, digest.upper())["status"],
                             "invalid-expected-digest")

    def test_member_checksum_mismatch_and_missing_source_are_not_approved(self):
        for opts, expected in (
            ({"altered_bytes": True}, "invalid-archive-segment-size"),
            ({"omit": "bob_diagnostic_history"}, "historical-source-table-absent"),
            ({"missing_columns": True}, "required-original-columns-missing"),
            ({"invalid_scope": True}, "unverified-archive-scope"),
            ({"extra_member": True}, "unexpected-archive-members"),
            ({"empty_decisions": True}, "historical-source-tables-empty"),
        ):
            with self.subTest(opts=opts), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "synthetic.zip"
                digest = synthetic_archive(path, **opts)
                result = preflight.inspect(path, digest)
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["deletionAuthorized"])
                self.assertFalse(result["fullOriginalReplayVerified"])

    def test_repackaged_corrupt_copy_even_with_matching_outer_hash_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.zip"
            synthetic_archive(path)
            with zipfile.ZipFile(path) as original:
                members = {name: original.read(name) for name in original.namelist()}
            members["0.copy"] = b"DIFFERENT-CONTENT\n"
            with zipfile.ZipFile(path, "w") as changed:
                for name, body in members.items():
                    changed.writestr(name, body)
            result = preflight.inspect(
                path, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(result["status"], "selected-copy-checksum-or-count-mismatch")
            self.assertFalse(result["archiveFileAndBatchBoundVerified"])

    def test_missing_file_symlink_and_invalid_zip_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "not-created.zip"
            self.assertEqual(preflight.inspect(path, "0"*64)["status"],
                             "archive-file-unavailable")
            path.write_bytes(b"not-a-zip")
            result = preflight.inspect(
                path, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(result["status"], "unavailable")
            link = Path(tmp) / "link.zip"
            link.symlink_to(path)
            self.assertEqual(preflight.inspect(link, "0"*64)["status"],
                             "archive-file-unavailable")


if __name__ == "__main__":
    unittest.main()
