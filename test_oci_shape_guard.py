"""No metadata network requests: Oracle Always Free VM shape gate tests."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location(
    "oci_shape", Path(__file__).resolve().parent/"ops"/"ocr-oci"/"verify_always_free_shape.py")
shape=importlib.util.module_from_spec(spec)
spec.loader.exec_module(shape)


class ShapeTests(unittest.TestCase):
    def test_one_arm_ocpu_four_gb_accepted_but_billing_stays_unknown(self):
        result=shape.check_shape({"shape":"VM.Standard.A1.Flex",
                                  "shapeConfig":{"ocpus":1.0,"memoryInGBs":4.0}})
        self.assertFalse(result["billingTierVerified"])
        self.assertEqual(result["memoryInGBs"],4)

    def test_wrong_or_larger_shape_denied(self):
        for meta in [
            {},
            {"shape":"VM.Standard.E2.1.Micro","shapeConfig":{"ocpus":1,"memoryInGBs":1}},
            {"shape":"VM.Standard.A1.Flex","shapeConfig":{"ocpus":2,"memoryInGBs":12}},
            {"shape":"VM.Standard.A1.Flex","shapeConfig":{"ocpus":1,"memoryInGBs":8}},
            {"shape":"VM.Standard.A1.Flex","shapeConfig":{"ocpus":1}},
            {"shape":"VM.Standard.A1.Flex","shapeConfig":{"ocpus":True,"memoryInGBs":4}},
            {"shape":"VM.Standard.A1.Flex","shapeConfig":{"ocpus":1,"memoryInGBs":float("nan")}},
        ]:
            with self.assertRaises(ValueError):
                shape.check_shape(meta)


if __name__=="__main__":
    unittest.main()
