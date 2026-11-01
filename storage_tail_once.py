"""One-time, fail-closed table-tail space reuse. Never delete historical rows.

An existing maintenance worker may call run_once() *only* on a separately
opted-in weekend. The persistent claim makes a restart unable to repeat it.
VACUUM is regular, not FULL, and remains 10-second SKIP_LOCKED. No archives
or content-addressed product pointers are created by this module.
"""
import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_TARGETS = {
    "bob_diagnostic_history": "reclaim_analysis_tail",
    "bob_improvement_observations": "reclaim_observation_tail",
    "bob_metric_checks": "reclaim_metric_tail",
    "bob_android_list_images": "reclaim_image_tail",
}
_RESOURCE = "dpg-datjno1srm7s738vv500-a"


def configuration():
    try:
        value = json.loads(os.environ.get("BOB_STORAGE_TAIL_RECLAIM_ONCE", ""))
    except (ValueError, TypeError):
        return None
    if (type(value) is not dict or set(value) != {"id", "table", "confirmed"}
            or type(value.get("id")) is not str
            or not _ID.fullmatch(value["id"])
            or type(value.get("table")) is not str
            or value["table"] not in _TARGETS
            or value.get("confirmed") is not True):
        return None
    return value


def _weekend(now):
    """Reserve extra tail-truncation locks for closed Gold-market periods."""
    clock = datetime.fromtimestamp(now, ZoneInfo("Europe/Zurich"))
    return clock.weekday() == 5 or (clock.weekday() == 6 and clock.hour < 20)


def _preflight(conn, seconds):
    """No storage SQL writes before independent, time-bounded proof."""
    import archive_worker
    import cold_decision_product_writer as proof_gate
    import render_disk_metrics
    import storage_budget

    try:
        if archive_worker.status().get("status") == "running":
            return "archive-running"
        proof = storage_budget.archive_status(conn)
        if proof_gate._proof_state(proof, seconds) != "verified-fresh":
            return "backup-proof-not-fresh"
        volume = render_disk_metrics.report()
        observed = volume.get("observedAt")
        if (volume.get("status") != "observed"
                or volume.get("resource") != _RESOURCE
                or volume.get("unit") != "bytes"
                or type(observed) not in (int, float)
                or not 0 <= seconds - observed <= 300
                or type(volume.get("diskUsage")) is not int
                or volume["diskUsage"] > 750_000_000):
            return "fresh-volume-proof-unavailable"
    except Exception:
        return "proof-unavailable"
    return "approved-for-one-table-vacuum"


def _init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_storage_tail_reclaim_attempts (
        id TEXT PRIMARY KEY,
        target_table TEXT NOT NULL,
        status TEXT NOT NULL,
        relation_bytes_reduced BIGINT NOT NULL DEFAULT 0,
        error_type TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")


def run_once(*, factory=None, vacuum=None, now=None):
    """At most one weekend table-tail VACUUM per durable claim.

    This function does not set any environment flag. Skip results must not
    become success. No claim is cleared after interruption or failure.
    """
    config = configuration()
    if config is None:
        return {"status": "disabled", "diskBytesFreed": None}
    seconds = time.time() if now is None else now
    if not _weekend(seconds):
        return {"status": "market-hours-deferred", "diskBytesFreed": None}

    import storage_maintenance as maintenance
    factory = maintenance.connect if factory is None else factory
    vacuum = maintenance.run_once if vacuum is None else vacuum
    try:
        with factory() as conn:
            if not conn.autocommit:
                return {"status": "non-autocommit-connection", "diskBytesFreed": None}
            gate = _preflight(conn, seconds)
            if gate != "approved-for-one-table-vacuum":
                return {"status": gate, "diskBytesFreed": None}
            # Claim is recorded before the VACUUM on a dedicated connection;
            # it cannot be replayed after a process restart or a failed step.
            with conn.transaction():
                _init(conn)
                claim = conn.execute("""INSERT INTO bob_storage_tail_reclaim_attempts
                    (id,target_table,status) VALUES(%s,%s,'running')
                    ON CONFLICT(id) DO NOTHING RETURNING id""",
                    (config["id"], config["table"])).fetchone()
            if not claim:
                return {"status": "already-claimed", "diskBytesFreed": None}
            status = "failed"
            reduction = 0
            error_type = None
            try:
                result = vacuum(factory=factory, target_table=config["table"],
                                **{_TARGETS[config["table"]]: True})
                entries = result.get("tables") if type(result) is dict else None
                if (result.get("status") == "checked" and type(entries) is list
                        and len(entries) == 1
                        and entries[0].get("table") == config["table"]
                        and entries[0].get("status") == "command-completed"
                        and type(entries[0].get("observedRelationBytesDecrease")) is int
                        and entries[0]["observedRelationBytesDecrease"] >= 0):
                    status = "completed"
                    reduction = entries[0]["observedRelationBytesDecrease"]
                elif result.get("status") == "busy":
                    status = "deferred-busy"
                else:
                    status = "deferred"
            except Exception as exc:
                error_type = type(exc).__name__
            try:
                conn.execute("""UPDATE bob_storage_tail_reclaim_attempts
                    SET status=%s, relation_bytes_reduced=%s,
                        error_type=%s, updated_at=now() WHERE id=%s""",
                    (status, reduction, error_type, config["id"]))
            except Exception:
                return {"status": "receipt-write-failed", "diskBytesFreed": None}
            receipt = {"status": status, "targetTable": config["table"],
                       "observedRelationBytesDecrease": reduction,
                       "diskBytesFreed": None, "evidenceDeleted": False}
            if error_type and _ID.fullmatch(error_type):
                receipt["errorType"] = error_type
            return receipt
    except Exception as exc:
        return {"status": "failed", "errorType": type(exc).__name__,
                "diskBytesFreed": None, "evidenceDeleted": False}
