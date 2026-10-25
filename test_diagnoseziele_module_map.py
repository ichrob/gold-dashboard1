"""Structural inventory tests: no execution, no outside paths and no false verification."""
import json
import tempfile
import unittest
from pathlib import Path

import diagnoseziele_module_map as module_map


ROOT = Path(__file__).resolve().parent


class ModuleMapTests(unittest.TestCase):
    def test_real_100_goals_have_bounded_structural_inventory_only(self):
        goals = json.loads((ROOT / "Besser_werden/lesezugriff_100_status.json")
                          .read_text(encoding="utf-8"))["tasks"]
        result = module_map.inspect(ROOT, goals)
        self.assertEqual(result["status"], "structural-only")
        self.assertEqual(result["goalCount"], 100)
        self.assertEqual(result["moduleCount"], len({g["codeEvidence"] for g in goals}))
        self.assertGreater(result["pythonModulesParsed"], 0)
        self.assertGreater(result["otherModulesNotParsed"], 0)
        self.assertEqual(result["individuallyVerified"], 0)
        self.assertTrue(result["readOnly"])
        self.assertTrue(all(item["featureVerified"] is False for item in result["items"]))
        for item in result["items"]:
            if item["analysis"] == "non-python-not-parsed":
                self.assertIsNone(item["mappedDependencies"])

    def test_ast_parser_reports_local_direct_deps_but_never_imports_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "safe_a.py").write_text(
                "import safe_b\nimport os\nraise RuntimeError('MUST NOT EXECUTE')\n",
                encoding="utf-8")
            (root / "safe_b.py").write_text("number = 1\n", encoding="utf-8")
            (root / "README.md").write_text("documentation\n", encoding="utf-8")
            goals = [
                {"id": i, "codeEvidence": "safe_a.py" if i <= 98 else
                    "safe_b.py" if i == 99 else "README.md"}
                for i in range(1, 101)
            ]
            report = module_map.inspect(root, goals)
            self.assertEqual(report["status"], "structural-only")
            self.assertEqual(report["moduleCount"], 3)
            self.assertEqual(report["mappedDependencyEdges"], 1)
            mod = next(i for i in report["items"] if i["path"] == "safe_a.py")
            self.assertEqual(mod["mappedDependencies"], ["safe_b.py"])
            self.assertEqual(report["goalCount"], 100)

    def test_bad_paths_and_invalid_inventory_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "safe.py").write_text("import os\n", encoding="utf-8")
            good = [{"id": i, "codeEvidence": "safe.py"} for i in range(1, 101)]
            for unsafe in ("../secret.txt", "/etc/passwd", "a//b",
                           "safe/./x.py", "outside.py"):
                rows = [dict(r) for r in good]
                rows[0]["codeEvidence"] = unsafe
                self.assertEqual(module_map.inspect(root, rows)["status"], "unavailable")
            self.assertEqual(module_map.inspect(root, good[:-1])["status"], "unavailable")
            rows = [dict(r) for r in good]
            rows[0]["id"] = 2
            self.assertEqual(module_map.inspect(root, rows)["status"], "unavailable")

    def test_broken_python_source_does_not_claim_complete_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            goals = [{"id": i, "codeEvidence": "broken.py"} for i in range(1, 101)]
            self.assertEqual(module_map.inspect(root, goals)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
