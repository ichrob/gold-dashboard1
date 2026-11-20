"""Regression tests for offline source maps: no Cloudflare or network use."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.cloudflare_source_map_check import inspect_maps


class SourceMapProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make(self, name="worker.js.map", **overrides):
        doc = {
            "version": 3,
            "sources": ["../../worker.mjs"],
            "names": ["test"],
            "mappings": "AAAA",
            # Never output this field, including on failures.
            "sourcesContent": ["test private literal - NEVER PRINT"],
        }
        doc.update(overrides)
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc), encoding="utf-8")
        return p

    def test_valid_offline_build_is_not_a_live_upload(self):
        self.make()
        proof = inspect_maps(self.root)
        self.assertEqual(proof["maps"], 1)
        self.assertTrue(proof["valid"])
        self.assertFalse(proof["uploaded"])

    def test_missing_maps_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "source_maps_missing"):
            inspect_maps(self.root)

    def test_invalid_maps_do_not_leak_source(self):
        p = self.make()
        p.write_text('{"bad": "test private literal - NEVER PRINT"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source_map_bad_version") as cm:
            inspect_maps(self.root)
        self.assertNotIn("NEVER PRINT", str(cm.exception))

    def test_empty_source_or_mappings_rejected(self):
        self.make(sources=[])
        with self.assertRaisesRegex(ValueError, "source_map_invalid_sources"):
            inspect_maps(self.root)
        self.make(sources=["worker.mjs"], mappings="")
        with self.assertRaisesRegex(ValueError, "source_map_missing_mappings"):
            inspect_maps(self.root)

    def test_corrupt_extra_map_rejects_entire_build(self):
        self.make()
        (self.root / "other.map").write_bytes(b'not-json')
        with self.assertRaisesRegex(ValueError, "source_map_invalid_json"):
            inspect_maps(self.root)

    def test_non_directory_fails(self):
        with self.assertRaisesRegex(ValueError, "build_directory_missing"):
            inspect_maps(self.root / "missing")


if __name__ == "__main__":
    unittest.main()
