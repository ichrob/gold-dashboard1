"""A new source filename is never proof that its code was imported or healthy."""
import json
import tempfile
import unittest
from pathlib import Path

import bob_source_module_inventory as discovery


ROOT = Path(__file__).resolve().parent


def rows(names):
    return {"schemaVersion": 1, "scope": "repository-root-source-files-only",
            "recordedOn": "2026-10-25", "sourceModules": sorted(names)}


class DiscoveryTests(unittest.TestCase):
    def test_saved_20261025_baseline_is_a_direct_source_snapshot(self):
        saved=json.loads((ROOT/"Besser_werden/module_root_baseline_20261025.json")
                         .read_text(encoding="utf-8"))
        manifest=json.loads((ROOT/"Besser_werden/lesezugriff_100_status.json")
                            .read_text(encoding="utf-8"))
        result=discovery.inspect(ROOT,saved,
             [row["codeEvidence"] for row in manifest["tasks"]])
        self.assertEqual(result["status"],"same-as-recorded-tree")
        self.assertEqual(result["newPathsNotInBaseline"],0)
        self.assertEqual(result["missingPathsFromBaseline"],0)
        self.assertEqual(result["recordedSourceModules"],len(saved["sourceModules"]))
        self.assertGreater(result["sourceModulesNotDirectlyGoalMapped"],0)
        self.assertEqual(result["individualGoalsVerified"],0)
        self.assertFalse(result["newModulesFunctioningVerified"])
        self.assertFalse(result["runtimeHealthVerified"])
        self.assertNotIn("sourceModules", result)
        self.assertNotIn("token",json.dumps(result))

    def test_detects_new_and_missing_files_without_executing_them(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"existing.py").write_text("raise RuntimeError('DO NOT EXECUTE')")
            (root/"added.js").write_text("throw Error('DO NOT EXECUTE')")
            (root/"test_private.py").write_text("bad")
            (root/"browser_private.cjs").write_text("bad")
            sub=root/"directory"
            sub.mkdir()
            (sub/"nested.py").write_text("bad")
            data=rows(["existing.py","removed.py"])
            report=discovery.inspect(root,data,["existing.py"]*100)
            self.assertEqual(report["status"],"changed-since-recorded-tree")
            self.assertEqual(report["newPathsNotInBaseline"],1)
            self.assertEqual(report["missingPathsFromBaseline"],1)
            self.assertEqual(report["goalMappedSourceModulesPresent"],1)
            self.assertEqual(report["sourceModulesNotDirectlyGoalMapped"],1)
            self.assertEqual(report["sourceKinds"]["py"],1)
            self.assertEqual(report["sourceKinds"]["js"],1)
            self.assertNotIn("added.js",json.dumps(report))
            self.assertFalse(report["runtimeHealthVerified"])

    def test_symlinks_and_external_files_are_not_traversed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"a.py").write_text("x=1")
            (root/"outside.js").symlink_to("/etc/passwd")
            report=discovery.inspect(root,rows(["a.py"]),["a.py"]*100)
            self.assertEqual(report["status"],"same-as-recorded-tree")
            self.assertEqual(report["currentlySeenSourceModules"],1)

    def test_invalid_baseline_is_unavailable_not_empty(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"a.py").write_text("x=1")
            for invalid in (
                rows([]),rows(["../secret.py"]),rows(["b.js","b.js"]),
                rows(["./a.py"]),rows(["other.txt"]),
                {"schemaVersion": 9, "scope": "repository-root-source-files-only",
                 "recordedOn": "2026-10-25", "sourceModules":["a.py"]},
            ):
                self.assertEqual(
                    discovery.inspect(root, invalid, ["a.py"]*100)["status"],
                    "unavailable")
            self.assertEqual(
                discovery.inspect(root,rows(["a.py"]),["a.py"]*99)["status"],
                "unavailable")

    def test_bounded_directory_and_max_modules_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/"a.py").write_text("x=1")
            with unittest.mock.patch.object(discovery,"_MAX_ROOT_ENTRIES",0):
                self.assertEqual(discovery.inspect(root,rows(["a.py"]),
                                                  ["a.py"]*100)["status"],"unavailable")
            with unittest.mock.patch.object(discovery,"_MAX_MODULES",0):
                self.assertEqual(discovery.inspect(root,rows(["a.py"]),
                                                  ["a.py"]*100)["status"],"unavailable")


if __name__ == "__main__":
    unittest.main()
