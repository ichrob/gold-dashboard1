"""OCI zero-paid-resource lock tests: offline, no Oracle credentials/network."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "oci_free_lock", ROOT / "ops" / "ocr-oci" / "free_only_guard.py")
lock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lock)


class OCIAlwaysFreeLockTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(
            (ROOT / "ops" / "ocr-oci" / "always_free_plan.example.json")
            .read_text(encoding="utf8"))

    def test_repository_template_denied_until_owner_review(self):
        with self.assertRaisesRegex(ValueError, "owner_console_review_required"):
            lock.validate(self.plan)

    def test_explicit_owner_review_validates_plan_but_not_billing(self):
        self.plan["owner_account_reviewed"] = True
        result = lock.validate(self.plan)
        self.assertTrue(result["configuration_matches_free_only_template"])
        self.assertFalse(result["billing_tier_proven_by_provider_api"])
        self.assertFalse(result["provisioning_enabled"])

    def test_paid_plan_upgrade_scaling_and_wrong_shape_denied(self):
        for key, value in [
            ("plan", "pay_as_you_go"),
            ("account_upgraded_to_paid", True),
            ("allow_paid_resources", True),
            ("shape", "VM.Standard.E5.Flex"),
            ("ocpus", 2),
            ("memory_gb", 8),
            ("boot_volume_gb", 250),
            ("boot_volume_type", "paid"),
            ("os_image_type", "marketplace_paid"),
            ("region_scope", "other_region"),
            ("extra_block_volumes", 1),
            ("extra_instances", 1),
            ("paid_network_services", True),
            ("paid_api_services", True),
            ("autoscaling", True),
            ("allow_shape_upgrade", True),
            ("requires_upgrade_for_capacity", True),
            ("provisioning_enabled", True),
        ]:
            plan = dict(self.plan, owner_account_reviewed=True)
            plan[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, "oci_free_only_lock_denied_"):
                    lock.validate(plan)

    def test_unknown_fields_missing_fields_and_bool_number_confusion_denied(self):
        self.plan["owner_account_reviewed"] = True
        for modified in (
            dict(self.plan, prepaid_credit_automatic_purchase=True),
            {k: v for k, v in self.plan.items() if k != "extra_instances"},
            dict(self.plan, ocpus=True),
            dict(self.plan, boot_volume_gb=50.0),
            dict(self.plan, owner_account_reviewed="yes"),
        ):
            with self.assertRaises(ValueError):
                lock.validate(modified)


if __name__ == "__main__":
    unittest.main()
