"""Structural inventory tests: no execution, no outside paths and no false verification."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertGreater(result["javascriptModulesScanned"], 0)
        self.assertEqual(result["individuallyVerified"], 0)
        self.assertTrue(result["readOnly"])
        self.assertTrue(all(item["featureVerified"] is False for item in result["items"]))
        for item in result["items"]:
            if item["analysis"] == "non-source-not-parsed":
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

    def test_javascript_literal_imports_are_sanitized_static_hints(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "module_a.js").write_text(
                "import {safe} from './module_b.js';\n"
                "const dep = require('./module_b');\n"
                "export * from './module_c.js';\n"
                "const secret = require('../private-secret');\n"
                "const dynamic = import(userProvidedModule);\n"
                "throw Error('NOT EXECUTED');\n",
                encoding="utf-8")
            (root / "module_b.js").write_text("export const safe = 1;\n", encoding="utf-8")
            (root / "module_c.js").write_text("export const other = 1;\n", encoding="utf-8")
            (root / "README.md").write_text("not a parseable module",encoding="utf-8")
            goals = [{"id":i,"codeEvidence":(
                "module_a.js" if i<=97 else
                "module_b.js" if i==98 else
                "module_c.js" if i==99 else "README.md")}
                for i in range(1,101)]
            report = module_map.inspect(root,goals)
            self.assertEqual(report["status"],"structural-only")
            self.assertEqual(report["javascriptModulesScanned"],3)
            self.assertEqual(report["otherModulesNotParsed"],1)
            self.assertEqual(report["mappedDependencyEdges"],2)
            main=next(x for x in report["items"] if x["path"]=="module_a.js")
            self.assertEqual(main["mappedDependencies"],["module_b.js","module_c.js"])
            self.assertEqual(main["analysis"],"javascript-literal-import-hints-only")
            self.assertFalse(main["featureVerified"])
            self.assertNotIn("private-secret",json.dumps(report))
            self.assertIn("not a JavaScript AST",report["limitations"])

    def test_large_unreadable_javascript_fails_closed_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            js=root/"app.js"
            js.write_text("const x=1;\n",encoding="utf-8")
            goals=[{"id":i,"codeEvidence":"app.js"} for i in range(1,101)]
            with patch.object(module_map,"_MAX_SOURCE_BYTES",3):
                self.assertEqual(module_map.inspect(root,goals)["status"],"unavailable")
            # Never infer a linked module outside the declared mapped tree.
            self.assertEqual(module_map.inspect(root,goals)["mappedDependencyEdges"],0)

    def test_same_path_edit_replaces_cached_dependencies_and_rechecks_syntax(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "main.py"
            source.write_text("import left\n", encoding="utf-8")
            for name in ("left.py", "next.py"):
                (root / name).write_text("pass\n", encoding="utf-8")
            goals = [{"id": i, "codeEvidence": "main.py" if i < 99 else
                      "left.py" if i == 99 else "next.py"} for i in range(1, 101)]
            def dependencies():
                report = module_map.inspect(root, goals)
                return next(x for x in report["items"] if x["path"] == "main.py")["mappedDependencies"]
            self.assertEqual(dependencies(), ["left.py"])
            # Same-length edit, without process restart or cache clearing.
            source.write_text("import next\n", encoding="utf-8")
            self.assertEqual(dependencies(), ["next.py"])
            source.write_text("def broken(:\n", encoding="utf-8")
            self.assertEqual(module_map.inspect(root, goals)["status"], "unavailable")

    def test_extensionless_js_link_does_not_guess_between_mapped_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            allowed = {"main.js", "dep.js", "dep.mjs"}
            self.assertIsNone(module_map._mapped_js_link(root, "main.js", "./dep", allowed))
            self.assertEqual(module_map._mapped_js_link(root, "main.js", "./dep.js", allowed), "dep.js")

    def test_cached_python_still_obeys_current_read_size_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "main.py"
            path.write_text("import os\n", encoding="utf-8")
            self.assertEqual(module_map._static_imports(path), ("os",))
            with patch.object(module_map, "_MAX_SOURCE_BYTES", 3):
                with self.assertRaises(ValueError):
                    module_map._static_imports(path)

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
