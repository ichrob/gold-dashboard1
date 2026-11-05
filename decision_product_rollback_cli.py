"""Terminal-only command for restoring exactly one cold decision original.

No service hook, scheduler, network route or automatic replay. The decision
identity is read from a private runtime variable and never echoed to logs.
"""
import json
import os
import sys
import time

import cold_metrics as codec
import decision_product_single_rollback as rollback

_STATES = frozenset({"disabled", "invalid-id", "not-a-pointer",
                    "invalid-pointer", "original-unavailable",
                    "concurrent-change", "restored-original-inline",
                    "failed"})
_USAGE = "Usage: python -m decision_product_rollback_cli execute --acknowledge-one-original"


def main(argv=None):
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args != ("execute", "--acknowledge-one-original"):
        print(_USAGE)
        return 2
    try:
        with codec.connect() as conn:
            outcome = rollback.restore_one(
                conn, os.environ.get("BOB_DECISION_ROLLBACK_TARGET_ID", ""),
                approval={"confirmed": True, "observedAt": time.time()})
    except Exception as error:
        outcome = {"status": "failed", "errorType": type(error).__name__}
    state = outcome.get("status")
    if state not in _STATES:
        state = "failed"
    rows = outcome.get("restoredRows", 0)
    if type(rows) is not int or rows not in (0, 1):
        rows = 0
        state = "failed"
    print(json.dumps({"status": state, "restoredRows": rows,
                      "diskBytesFreed": None, "archiveObjectsDeleted": 0},
                     sort_keys=True))
    return 0 if state == "restored-original-inline" and rows == 1 else 3


if __name__ == "__main__":
    raise SystemExit(main())
