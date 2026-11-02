"""Repack binary provisioning is opt-in, pinned and never database-active."""
import hashlib
import io
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import repack_client_installer as bootstrap


class StubResponse:
    def __init__(self, data, url):
        self.data=data
        self.url=url
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.data[:n]
    def geturl(self):return self.url


class InstallerTests(unittest.TestCase):
    def test_unconfigured_start_is_inert(self):
        with patch.dict(os.environ,{"BOB_REPACK_CLIENT_PREPARE":""}), \
             patch.object(bootstrap,"prepare_once",side_effect=AssertionError("must not run")):
            self.assertIsNone(bootstrap.start_if_enabled())

    def test_signed_apt_pinned_binary_hash_and_size_gate(self):
        raw=b"FAKE CI DATA"  # synthetic, never a real Debian binary.
        with patch.object(bootstrap,"_EXPECTED_BYTES",len(raw)), \
             patch.object(bootstrap,"_EXPECTED_SHA256",hashlib.sha256(raw).hexdigest()), \
             patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value=StubResponse(raw,bootstrap._PACKAGE_URL)
            self.assertEqual(bootstrap._fetch(),raw)
            opener.return_value.open.return_value=StubResponse(raw+b"x",bootstrap._PACKAGE_URL)
            with self.assertRaises(ValueError):
                bootstrap._fetch()
            opener.return_value.open.return_value=StubResponse(raw,"https://attacker.test/pkg")
            with self.assertRaises(ValueError):
                bootstrap._fetch()
        # Normal production hash is immutable; no dependency on HTTP metadata.
        self.assertEqual(bootstrap._EXPECTED_BYTES,104764)
        self.assertEqual(bootstrap._EXPECTED_SHA256,
            "b52898b683ba371dc06273e4ea326c6275bb6cd0b51bd130331ce00f9dfa7e05")

    def test_version_and_elf_reject_corrupt_binary(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"pg_repack"
            p.write_bytes(b"not executable")
            with self.assertRaises(ValueError):
                bootstrap._verified_binary(p)
            p.write_bytes(bytes.fromhex("7f454c46")+b"FAKE")
            with patch("subprocess.run",return_value=Mock(stdout="pg_repack 1.5.3\n")) as call:
                bootstrap._verified_binary(p)
                self.assertEqual(call.call_args.args[0],[str(p),"--version"])
            with patch("subprocess.run",return_value=Mock(stdout="pg_repack 1.5.2\n")):
                with self.assertRaises(ValueError):
                    bootstrap._verified_binary(p)

    def test_only_version_execution_no_database_calls(self):
        source=inspect.getsource(bootstrap)
        for prohibited in ("psycopg.connect","CREATE EXTENSION","VACUUM FULL",
                           "DELETE FROM","UPDATE bob_","pg_repack --table",
                           "shell=True","DATABASE_URL","BOB_RENDER_METRICS_API_KEY"):
            self.assertNotIn(prohibited,source)
        self.assertIn("BOB_REPACK_CLIENT_PREPARE",source)

    def test_unexpected_architecture_fails_closed(self):
        with patch("platform.machine",return_value="aarch64"):
            with self.assertRaises(ValueError):
                bootstrap._preconditions()

    def test_status_does_not_claim_disk_reclamation(self):
        state=bootstrap.status()
        self.assertFalse(state["databaseModified"])
        self.assertFalse(state["readyToRepack"])
        self.assertIsNone(state["diskBytesFreed"])


if __name__=="__main__":
    unittest.main()
