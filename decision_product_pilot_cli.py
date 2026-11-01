"""Explicit terminal-only interface for the manual one-row decision pilot.

Never imported by service startup, workers, routes or scheduled jobs.
No arguments contain credentials or product data. Exact operator command only.
"""
import json
import re
import sys
import time

import decision_product_pilot as pilot


_USAGE = (
    "Usage: python -m decision_product_pilot_cli status | preflight | "
    "execute --acknowledge-one-row-only"
)
_STATES = frozenset({
    "disabled", "no-attempt", "not-observed", "running", "failed",
    "backup-proof-not-fresh", "full-archive-running",
    "fresh-volume-proof-unavailable", "approved-for-single-row-pilot",
    "already-claimed", "verified-offload", "no-change",
    "deferred-sweep-completed", "deferred-no-eligible-rows",
    "deferred-page-scanned", "deferred-busy",
    "deferred-backup-proof-not-fresh",
    "deferred-fresh-volume-proof-unavailable",
})
_ERROR_TYPE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,79}\Z")


def _report(result, *, read_only=False, configured=None):
    """Output an allowlisted receipt: never IDs, keys, payloads or exceptions."""
    status = result.get("status") if type(result) is dict else None
    if status not in _STATES:
        status = "not-observed" if read_only else "failed"
    receipt = {"status": status, "diskBytesFreed": None}
    if read_only:
        receipt["readOnly"] = True
    else:
        count = result.get("movedRows") if type(result) is dict else None
        if type(count) is not int or not 0 <= count <= 1:
            count = 0
            status = "failed"
            receipt["status"] = status
        receipt["movedRows"] = count
    if configured is not None:
        receipt["executionConfigured"] = bool(configured)
    if type(result) is dict:
        kind = result.get("errorType")
        if type(kind) is str and _ERROR_TYPE.fullmatch(kind):
            receipt["errorType"] = kind
        # The timestamp is an optional, strictly formatted informational field.
        stamp = result.get("updatedAt")
        if read_only and type(stamp) is str and len(stamp) <= 64 and re.fullmatch(
            r"[0-9:. +\-TZ]{8,64}", stamp
        ):
            receipt["updatedAt"] = stamp
    print(json.dumps(receipt, sort_keys=True))
    return receipt


def main(argv=None):
    args = tuple(sys.argv[1:] if argv is None else argv)
    # Intentionally do not echo invalid arguments: a caller may accidentally
    # have supplied a private token on the command line.
    if args not in (("status",), ("preflight",),
                    ("execute", "--acknowledge-one-row-only")):
        print(_USAGE)
        return 2

    if args[0] == "execute" and pilot.configuration() is None:
        _report({"status": "disabled", "movedRows": 0})
        return 3

    try:
        if args[0] == "status":
            with pilot.codec.connect() as conn:
                _report(pilot.status(conn), read_only=True)
            return 0
        if args[0] == "preflight":
            # Nonmutating independent backup + current Render volume probe.
            # This does not create a pilot ledger, authorize or execute a write.
            with pilot.codec.connect() as conn:
                state = pilot._preflight(conn, time.time())
            _report({"status": state}, read_only=True,
                    configured=(pilot.configuration() is not None))
            return 0

        # An explicit one-row acknowledgement is *in addition to* the
        # strict one-use env claim, backup, disk and writer CAS gates.
        result = pilot.run_once()
        receipt = _report(result)
        return 0 if (receipt["status"] == "verified-offload" and
                     receipt["movedRows"] == 1) else 3
    except Exception as exc:
        # Never print exception messages, URLs, SQL, credentials or originals.
        _report({"status": "failed", "movedRows": 0,
                 "errorType": type(exc).__name__})
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
