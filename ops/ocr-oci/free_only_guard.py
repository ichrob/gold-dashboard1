"""Fail-closed, OFFLINE Oracle Always Free deployment-plan validator.

This code neither connects to OCI nor provisions anything. It rejects
misconfigured local plans before a human uses the Oracle console. The
owner must separately confirm the real account type and eligibility there.
"""
import json
from pathlib import Path

_EXPECTED = {
    "provider": "oci",
    "plan": "always_free",
    "account_upgraded_to_paid": False,
    "allow_paid_resources": False,
    "region_scope": "home_region_only",
    "shape": "VM.Standard.A1.Flex",
    "ocpus": 1,
    "memory_gb": 4,
    "boot_volume_gb": 50,
    "boot_volume_type": "always_free_eligible",
    "os_image_type": "always_free_eligible_arm64",
    "extra_block_volumes": 0,
    "extra_instances": 0,
    "paid_network_services": False,
    "paid_api_services": False,
    "autoscaling": False,
    "allow_shape_upgrade": False,
    "requires_upgrade_for_capacity": False,
    "provisioning_enabled": False,
}


def validate(plan):
    """Reject non-exact/free-unverified plans, including unknown keys.

    This must not be confused with independent OCI billing verification.
    """
    if not isinstance(plan, dict):
        raise ValueError("oci_plan_not_object")
    if set(plan) != set(_EXPECTED) | {"owner_account_reviewed"}:
        raise ValueError("oci_plan_unknown_or_missing_fields")
    for key, expected in _EXPECTED.items():
        actual = plan[key]
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError("oci_free_only_lock_denied_" + key)
    if plan["owner_account_reviewed"] is not True:
        raise ValueError("oci_owner_console_review_required")
    return {
        "configuration_matches_free_only_template": True,
        "billing_tier_proven_by_provider_api": False,
        "provisioning_enabled": False,
    }


def check_file(path):
    data = Path(path).read_text(encoding="utf8")
    if len(data) > 16_000:
        raise ValueError("oci_plan_too_large")
    return validate(json.loads(data))


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("usage: python free_only_guard.py /private/path/plan.json")
    try:
        result = check_file(sys.argv[1])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("OCI_FREE_ONLY_LOCK=DENIED reason=" + str(exc))
        raise SystemExit(1)
    print("OCI_FREE_ONLY_LOCK=PLAN_VALIDATED; "
          "PROVISIONING=DISABLED; BILLING_NEEDS_PROVIDER_VERIFICATION")
