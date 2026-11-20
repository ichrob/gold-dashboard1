"""Manual, synthetic-only Aiven scratch admission test.

This module is NOT imported by Bob's services and never touches Render rows.
It uses the already provisioned Aiven test URI and verified CA, takes the
existing restore-target session lock, performs two tiny TEMP-only writes and
rolls back explicitly. No persistent schema, order, subscription or scheduler.
"""
import json
import os
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlsplit

from aiven_readonly_probe import _temporary_ca_certificate, _valid_aiven_uri
from aiven_research_admission import assess
from aiven_provider_host_metrics import read as read_aiven_provider_metrics


def _result(status):
    return {"status": status, "syntheticOnly": True, "persisted": False}


def run(environ=None, connect=None, metrics_reader=None):
    env = os.environ if environ is None else environ
    if env.get("BOB_AIVEN_SYNTHETIC_CHECK") != "1":
        return _result("disabled")

    target = env.get("BOB_AIVEN_TEST_DATABASE_URL", "")
    source = env.get("DATABASE_URL", "")
    pem = env.get("BOB_AIVEN_TEST_CA_PEM", "").strip()
    ca_file = env.get("BOB_AIVEN_TEST_CA_FILE", "") or "/etc/secrets/bob_aiven_ca.pem"
    if not target or not source or not (pem or Path(ca_file).is_file()):
        return _result("not-configured")
    if not _valid_aiven_uri(target):
        return _result("invalid-target")
    try:
        source_host = urlsplit(source).hostname
        if not source_host or source_host == urlsplit(target).hostname:
            return _result("target-not-independent")
    except (ValueError, TypeError):
        return _result("target-not-independent")
    if pem and (len(pem) > 32768 or
                not pem.startswith("-----BEGIN CERTIFICATE-----") or
                not pem.endswith("-----END CERTIFICATE-----")):
        return _result("invalid-certificate")

    # The host RAM/disk sample MUST be original recent Aiven Console evidence.
    # SQL health or the free-plan label cannot substitute for a host sample.
    # This manual-only JSON stays outside the repository and is never printed.
    try:
        evidence = json.loads(env.get("BOB_AIVEN_CAPACITY_EVIDENCE_JSON", ""))
        if not isinstance(evidence, dict):
            return _result("capacity-evidence-unverified")
        # When the official provider-metrics mode is explicitly enabled,
        # obtain original host evidence directly from Aiven's API. A failed
        # or unknown response must NOT fall back to operator-supplied values.
        if env.get("BOB_AIVEN_METRICS_ONCE") == "1":
            reader = read_aiven_provider_metrics if metrics_reader is None else metrics_reader
            metrics = reader(environ=env)
            if metrics.get("status") != "observed" or not isinstance(metrics.get("host"), dict):
                return _result("capacity-evidence-unverified")
            evidence["host"] = metrics["host"]
        admission = assess(
            evidence.get("host"), evidence.get("sql"), evidence.get("archive"),
            requested_bytes=1024,
        )
        if admission["status"] != "candidate-for-manual-synthetic-test-only":
            return _result("capacity-evidence-unverified")
    except (ValueError, TypeError, KeyError):
        return _result("capacity-evidence-unverified")

    try:
        if connect is None:
            import psycopg
            connect = psycopg.connect
        ca = _temporary_ca_certificate(pem + "\n") if pem else nullcontext(ca_file)
        with ca as ca_path:
            with connect(
                target, sslmode="verify-full", sslrootcert=ca_path,
                connect_timeout=5, autocommit=True,
                application_name="bob_aiven_synthetic_scratch",
                options=("-c statement_timeout=1500 -c lock_timeout=250 "
                         "-c idle_in_transaction_session_timeout=3000"),
            ) as conn:
                started = False
                try:
                    conn.execute("BEGIN")
                    started = True
                    locked = conn.execute(
                        "SELECT pg_try_advisory_lock(hashtext('bob_restore_target_v1'))"
                    ).fetchone()
                    if locked != (True,):
                        return _result("restore-busy")
                    conn.execute(
                        "CREATE TEMP TABLE bob_aiven_synthetic_scratch "
                        "(tag text NOT NULL) ON COMMIT DROP"
                    )
                    conn.execute(
                        "INSERT INTO bob_aiven_synthetic_scratch(tag) "
                        "VALUES ('synthetic-a'), ('synthetic-b')"
                    )
                    count = conn.execute(
                        "SELECT count(*) FROM bob_aiven_synthetic_scratch"
                    ).fetchone()
                    if count != (2,):
                        return _result("scratch-not-confirmed")
                    return _result("synthetic-scratch-rolled-back")
                finally:
                    if started:
                        conn.execute("ROLLBACK")
    except Exception:
        return _result("connection-or-scratch-not-confirmed")


def main():
    result = run()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "synthetic-scratch-rolled-back" else 2


if __name__ == "__main__":
    raise SystemExit(main())
