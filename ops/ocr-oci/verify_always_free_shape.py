"""Fail-closed OCI VM shape sanity check. Run on OCI host before deployment.

Metadata cannot prove account billing tier or resource labels; the owner must
separately confirm Always Free in OCI Console before any external OCR.
"""
import json
import math
from urllib.request import Request, ProxyHandler, build_opener

IMDS = "http://169.254.169.254/opc/v2/instance/"


def check_shape(metadata):
    if not isinstance(metadata, dict) or metadata.get("shape") != "VM.Standard.A1.Flex":
        raise ValueError("oci_always_free_shape_mismatch")
    cfg = metadata.get("shapeConfig")
    if not isinstance(cfg, dict):
        raise ValueError("oci_shape_configuration_missing")
    cpu, ram = cfg.get("ocpus"), cfg.get("memoryInGBs")
    if (type(cpu) not in (int, float) or type(ram) not in (int, float)
            or not math.isfinite(cpu) or not math.isfinite(ram)
            or cpu != 1 or ram != 4):
        raise ValueError("oci_shape_budget_mismatch")
    return {"shape": "VM.Standard.A1.Flex", "ocpus": 1, "memoryInGBs": 4,
            "billingTierVerified": False}


def verify():
    req = Request(IMDS, headers={"Authorization": "Bearer Oracle"})
    with build_opener(ProxyHandler({})).open(req, timeout=5) as response:
        body = response.read(65537)
    if len(body) > 65536:
        raise ValueError("oci_metadata_too_large")
    return check_shape(json.loads(body))


if __name__ == "__main__":
    result = verify()
    print("oci_arm_shape_verified=true cpu=1 ram_gb=4 billing_tier_owner_check_required=true")
