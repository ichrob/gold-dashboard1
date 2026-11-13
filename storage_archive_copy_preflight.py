"""Offline-only preflight for a previously decrypted reviewed-evidence ZIP.

No Google Drive client, network, database, decryption, restore, archive creation,
startup hook, deletion or runtime invocation. This module only inspects an
operator-supplied EXISTING plaintext ZIP (or synthetic CI fixture) and compares
its SHA-256 with a separately supplied EXPECTED plaintext-archive digest.

A matching supplied digest is not proof of where that digest came from. The
v3 manifest has no certified per-row original-clock range or bound evaluation
page manifests. Never turn this subset check into full replay/deletion permission.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile

_ARCHIVE_VERSION = "bob-evidence-archive-v3"
_ARCHIVE_SCOPE = "reviewed-evidence-tables-not-full-database-backup"
_REQUIRED = frozenset(("bob_diagnostic_history", "bob_decision_audit"))
_REQUIRED_COLUMNS = {
    "bob_diagnostic_history": frozenset(("id", "recorded_at", "stage", "payload")),
    "bob_decision_audit": frozenset(("id", "recorded_at", "payload")),
}
_ARCHIVE_MAX = 512 * 1024 * 1024
_RAW_MAX = 4 * 1024 * 1024 * 1024 + 2 * 1024 * 1024
_MANIFEST_MAX = 2 * 1024 * 1024
_SEGMENT_MAX = 32 * 1024 * 1024
_ENTRY_MAX = 2048
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")


def _result(status, *, segments=0, rows=0):
    return {
        "status": status,
        "scope": "offline-plaintext-archive-selected-copy-preflight-only",
        "inspectedSegments": segments,
        "inspectedRows": rows,
        "readOnly": True,
        "newArchiveOrRestoreStarted": False,
        "plaintextArchiveMatchedSuppliedDigest": status == "selected-copy-segments-matched",
        "independentExpectedDigestProvenanceVerified": False,
        "evaluationManifestBoundToArchive": False,
        "originalTimeRangeCoverageVerified": False,
        "fullOriginalReplayVerified": False,
        "archiveFileAndBatchBoundVerified": False,
        "sourceRowsModified": False,
        "deletionAuthorized": False,
        "physicalBytesFreed": None,
    }


def inspect(plaintext_zip, expected_sha256):
    """Check a bounded EXISTING ZIP, required COPY members and their manifests.

    No contents, row identifiers, file paths, original timestamps, SQL or hashes
    are ever returned. All errors fail closed to fixed safe statuses.
    """
    if type(expected_sha256) is not str or not _HEX.fullmatch(expected_sha256):
        return _result("invalid-expected-digest")
    try:
        path = Path(plaintext_zip)
        if path.is_symlink() or not path.is_file():
            return _result("archive-file-unavailable")
        size = path.stat().st_size
        if not 0 < size <= _ARCHIVE_MAX:
            return _result("invalid-archive-size")
        sha = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                sha.update(chunk)
        if sha.hexdigest() != expected_sha256:
            return _result("plaintext-archive-digest-mismatch")
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if (not 1 < len(members) <= _ENTRY_MAX + 1
                    or len({x.filename for x in members}) != len(members)
                    or sum(x.file_size for x in members) > _RAW_MAX
                    or any(x.is_dir() for x in members)):
                return _result("invalid-archive-members")
            member_map = {x.filename: x for x in members}
            manifest_info = member_map.get("manifest.json")
            if (manifest_info is None or
                    not 0 < manifest_info.file_size <= _MANIFEST_MAX):
                return _result("invalid-archive-manifest")
            manifest = json.loads(archive.read("manifest.json"))
            if (type(manifest) is not dict or
                    manifest.get("version") != _ARCHIVE_VERSION or
                    manifest.get("scope") != _ARCHIVE_SCOPE or
                    manifest.get("evidenceDeleted") is not False or
                    manifest.get("deletionPermitted") is not False):
                return _result("unverified-archive-scope")
            entries = manifest.get("tables")
            absent = manifest.get("absentTables")
            if (type(entries) is not list or
                    not 1 <= len(entries) <= _ENTRY_MAX or
                    type(absent) is not list or
                    any(type(name) is not str for name in absent)):
                return _result("invalid-archive-manifest")
            if any(name in absent for name in _REQUIRED):
                return _result("historical-source-table-absent")
            selected = []
            found = set()
            segments_seen = {}
            expected_names = {"manifest.json"}
            for i, entry in enumerate(entries):
                if type(entry) is not dict:
                    return _result("invalid-archive-manifest")
                name, filename = entry.get("name"), entry.get("file")
                segment = entry.get("segment")
                count, size_bytes, digest = (
                    entry.get("rows"), entry.get("bytes"), entry.get("sha256"))
                columns = entry.get("columns")
                if (type(name) is not str or not _NAME.fullmatch(name) or
                        filename != f"{i}.copy" or
                        type(segment) is not int or segment < 0 or
                        type(count) is not int or count < 0 or
                        type(size_bytes) is not int or
                        not 0 <= size_bytes <= _SEGMENT_MAX or
                        type(digest) is not str or not _HEX.fullmatch(digest) or
                        type(columns) is not list or not columns or
                        any(type(col) not in (list, tuple) or len(col) != 2 or
                            type(col[0]) is not str or not _NAME.fullmatch(col[0]) or
                            type(col[1]) is not str for col in columns)):
                    return _result("invalid-archive-manifest")
                prev = segments_seen.get(name, 0)
                if segment != prev:
                    return _result("invalid-archive-segment-order")
                segments_seen[name] = prev + 1
                info = member_map.get(filename)
                if info is None or info.file_size != size_bytes:
                    return _result("invalid-archive-segment-size")
                expected_names.add(filename)
                if name in _REQUIRED:
                    if not _REQUIRED_COLUMNS[name].issubset(
                            {column[0] for column in columns}):
                        return _result("required-original-columns-missing")
                    selected.append((name, filename, count, size_bytes, digest))
                    found.add(name)
            if set(member_map) != expected_names:
                return _result("unexpected-archive-members")
            if found != _REQUIRED:
                return _result("historical-source-table-absent")
            total_rows = 0
            rows_per_table = {name: 0 for name in _REQUIRED}
            for name, filename, count, bytes_expected, digest_expected in selected:
                actual_hash = hashlib.sha256()
                actual_size = actual_rows = 0
                with archive.open(filename) as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        actual_hash.update(chunk)
                        actual_size += len(chunk)
                        actual_rows += chunk.count(b"\n")
                        if actual_size > _SEGMENT_MAX:
                            return _result("invalid-archive-segment-size")
                if (actual_size != bytes_expected or actual_rows != count or
                        actual_hash.hexdigest() != digest_expected):
                    return _result("selected-copy-checksum-or-count-mismatch")
                total_rows += actual_rows
                rows_per_table[name] += actual_rows
            if any(rows_per_table[name] == 0 for name in _REQUIRED):
                return _result("historical-source-tables-empty")
            return _result("selected-copy-segments-matched",
                           segments=len(selected), rows=total_rows)
    except Exception:
        # Deliberately suppress paths, exception content, raw bytes and hashes.
        return _result("unavailable")
