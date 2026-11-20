"""Offline regressions for the read-only Oracle Cloud Shell preflight."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parent / "ops" / "oracle_a1_retry" / "cloudshell_preflight.py"
spec = importlib.util.spec_from_file_location("cloudshell_preflight", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

STACK = "ocid1.ormstack.oc1.eu-zurich-1." + "a" * 45
COMPARTMENT = "ocid1.compartment.oc1.." + "a" * 50

class OraclePreflightReadOnlyTest(unittest.TestCase):
    def run_probe(self, compute):
        seen = []
        def mock_call(*args, output_file=None):
            seen.append(args)
            if args[:3] == ("resource-manager", "stack", "get"):
                return json.dumps({"data":{"id":STACK,"compartment-id":COMPARTMENT}})
            if args[:3] == ("compute", "instance", "list"):
                return json.dumps({"data":compute})
            if args[:3] == ("resource-manager", "stack", "get-stack-tf-state"):
                path = Path(args[args.index("--file") + 1])
                path.write_text(json.dumps({"version":4,"resources":[
                    {"mode":"managed","type":"oci_core_vcn","name":"bob","instances":[{"attributes":{"id":"vcn"}}]}
                ]}), encoding="utf-8")
                return None
            if args[:3] == ("resource-manager", "job", "list"):
                return json.dumps({"data":[]})
            raise AssertionError(f"unexpected command category: {args[:3]!r}")
        buf = io.StringIO()
        with patch.object(mod, "call", side_effect=mock_call), contextlib.redirect_stdout(buf):
            status = mod.main(STACK)
        for cmd in seen:
            self.assertIn(cmd[0], ("resource-manager","compute"))
            self.assertIn(cmd[2], ("get","get-stack-tf-state","list"))
        return status,buf.getvalue()

    def test_live_instance_without_state_is_detected(self):
        status, output = self.run_probe([{
            "display-name":"bob-ocr-zurich","shape":"VM.Standard.A1.Flex",
            "lifecycle-state":"RUNNING"
        }])
        self.assertEqual(status, 0)
        self.assertIn("COMPUTE_INSTANCE=ONE_RUNNING",output)
        self.assertIn("TERRAFORM_STATE_INSTANCE=ABSENT",output)
        self.assertIn("COMPUTE_TF_DISAGREEMENT=true",output)
        self.assertIn("RESULT=PLAN_REQUIRED",output)

    def test_no_live_instance_is_reported_without_mutation(self):
        status, output = self.run_probe([])
        self.assertEqual(status, 0)
        self.assertIn("COMPUTE_INSTANCE=ABSENT",output)
        self.assertIn("COMPUTE_TF_DISAGREEMENT=false",output)
        self.assertIn("RESULT=PLAN_REQUIRED",output)

if __name__ == "__main__":
    unittest.main()
