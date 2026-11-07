"""Manual, read-only Render-provider volume snapshots for separately authorized work.

This script never initiates maintenance, SQL, archive runs, deploys or secret
changes. No production startup/scheduler imports it. Local receipt is not a
cryptographic signature or proof that a database operation caused a decrease.
"""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import time

import render_disk_metrics

VERSION = "bob-render-provider-volume-pair-v1"
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MAX_SAMPLE_AGE_SECONDS = 120
MAX_POST_WAIT_SECONDS = 900
MAX_OPERATION_SECONDS = 7200


class MeasurementBlocked(Exception):
    pass


def _sample(now, reporter):
    value = reporter()
    if not isinstance(value, dict):
        raise MeasurementBlocked("provider-observation-unavailable")
    observed = value.get("observedAt")
    bytes_used = value.get("diskUsage")
    if (value.get("status") != "observed"
            or value.get("source") != "render-metrics-api"
            or value.get("scope") != "volume-usage"
            or value.get("resource") != render_disk_metrics.RESOURCE
            or value.get("unit") != "bytes"
            or type(bytes_used) is not int
            or not 0 <= bytes_used <= 10**12
            or type(observed) not in (int, float)
            or not 0 <= now - observed <= MAX_SAMPLE_AGE_SECONDS):
        raise MeasurementBlocked("provider-observation-not-current-or-valid")
    return {"observedAt": observed, "capturedAt": now,
            "usedBytes": bytes_used, "source": "render-metrics-api",
            "unit": "bytes", "resource": render_disk_metrics.RESOURCE}


def _load(path):
    if path.is_symlink() or not path.is_file():
        raise MeasurementBlocked("receipt-not-regular-file")
    if path.stat().st_size > 4096 or path.stat().st_mode & 0o077:
        raise MeasurementBlocked("receipt-insecure-or-too-large")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise MeasurementBlocked("receipt-invalid") from None
    if (type(record) is not dict or record.get("version") != VERSION
            or type(record.get("measurementId")) is not str
            or not IDENTIFIER.fullmatch(record["measurementId"])
            or record.get("resource") != render_disk_metrics.RESOURCE
            or record.get("state") not in ("before", "ended", "paired")
            or type(record.get("before")) is not dict):
        raise MeasurementBlocked("receipt-invalid")
    return record


def _write(path, value, *, create):
    path = Path(path)
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > 4096:
        raise MeasurementBlocked("receipt-too-large")
    if create:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        with os.fdopen(os.open(path, flags, 0o600), "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
    else:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".bob-volume-", dir=path.parent,
                                         delete=False) as output:
            staged = Path(output.name)
            try:
                os.chmod(staged, 0o600)
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            except Exception:
                staged.unlink(missing_ok=True)
                raise
        try:
            os.replace(staged, path)
        finally:
            staged.unlink(missing_ok=True)


def before(receipt, measurement_id, *, clock=time.time, reporter=render_disk_metrics.report):
    if type(measurement_id) is not str or not IDENTIFIER.fullmatch(measurement_id):
        raise MeasurementBlocked("invalid-measurement-id")
    path = Path(receipt)
    observed = _sample(clock(), reporter)
    record = {"version": VERSION, "measurementId": measurement_id,
              "resource": render_disk_metrics.RESOURCE, "state": "before",
              "before": observed, "maintenanceEndedAt": None, "after": None,
              "physicalVolumeNetDecreaseBytes": None,
              "diskBytesFreedByMaintenance": None}
    _write(path, record, create=True)
    return {"status": "before-recorded", "measurementId": measurement_id,
            "providerUsedBytes": observed["usedBytes"],
            "providerObservedAt": observed["observedAt"],
            "diskBytesFreedByMaintenance": None}


def mark_ended(receipt, *, clock=time.time):
    path = Path(receipt)
    record = _load(path)
    if record["state"] != "before" or record.get("maintenanceEndedAt") is not None:
        raise MeasurementBlocked("measurement-already-ended")
    ended = clock()
    begun = record["before"].get("capturedAt")
    if type(begun) not in (int, float) or not 0 <= ended - begun <= MAX_OPERATION_SECONDS:
        raise MeasurementBlocked("maintenance-boundary-unverifiable")
    record["state"] = "ended"
    record["maintenanceEndedAt"] = ended
    _write(path, record, create=False)
    return {"status": "end-recorded", "measurementId": record["measurementId"],
            "diskBytesFreedByMaintenance": None}


def after(receipt, *, clock=time.time, reporter=render_disk_metrics.report):
    path = Path(receipt)
    record = _load(path)
    if record["state"] != "ended" or record.get("after") is not None:
        raise MeasurementBlocked("measurement-not-pending")
    now = clock()
    ended = record["maintenanceEndedAt"]
    started = record["before"].get("capturedAt")
    previous = record["before"].get("observedAt")
    used_before = record["before"].get("usedBytes")
    if (type(ended) not in (int, float) or type(started) not in (int, float)
            or type(previous) not in (int, float) or type(used_before) is not int
            or not 0 <= now - ended <= MAX_POST_WAIT_SECONDS
            or not previous <= started <= ended):
        raise MeasurementBlocked("measurement-boundary-unverifiable")
    observed = _sample(now, reporter)
    if observed["observedAt"] <= ended or observed["observedAt"] <= previous:
        raise MeasurementBlocked("provider-post-sample-not-yet-available")
    delta = used_before - observed["usedBytes"]
    record["state"] = "paired"
    record["after"] = observed
    # Provider NET decrease across a bounded pair, not causality or row savings.
    record["physicalVolumeNetDecreaseBytes"] = max(delta, 0)
    _write(path, record, create=False)
    return {"status": "paired-provider-net-decrease" if delta > 0 else
            "paired-provider-no-net-decrease",
            "measurementId": record["measurementId"],
            "providerBeforeBytes": used_before,
            "providerAfterBytes": observed["usedBytes"],
            "physicalVolumeNetDecreaseBytes": max(delta, 0),
            "diskBytesFreedByMaintenance": None,
            "scope": "provider-net-usage-only-not-causal-attribution"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Render-volume evidence; no maintenance")
    actions = parser.add_subparsers(dest="action", required=True)
    first = actions.add_parser("before")
    first.add_argument("--receipt", required=True)
    first.add_argument("--id", required=True)
    for name in ("end", "after"):
        actions.add_parser(name).add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "before":
            result = before(args.receipt, args.id)
        elif args.action == "end":
            result = mark_ended(args.receipt)
        else:
            result = after(args.receipt)
    except MeasurementBlocked as exc:
        result = {"status": "blocked", "reason": str(exc),
                  "diskBytesFreedByMaintenance": None}
    except Exception as exc:
        # No provider body, secret, local path or traceback in output.
        result = {"status": "blocked", "reason": "local-or-provider-error",
                  "errorType": type(exc).__name__,
                  "diskBytesFreedByMaintenance": None}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
