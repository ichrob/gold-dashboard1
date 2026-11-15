"""Read-only, offline Aiven host-capacity reconciliation for Bob's restore target.

Aiven PostgreSQL SQL observations do NOT measure host RAM or OOM. Only an
explicit, timestamped Aiven Console host-metric sample can fill that gap.
This module does not connect, collect, alter settings, restore or resize.
"""
import math
from datetime import datetime, timezone

HOST_MAX_AGE_SECONDS = 1200
SQL_MAX_SKEW_SECONDS = 300


def _instant(text):
    if not isinstance(text,str):
        raise ValueError("Timestamp missing")
    try:
        value=datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc
    if value.tzinfo is None:
        raise ValueError("Timezone required")
    return value.astimezone(timezone.utc)


def _ratio(sample, used_key, capacity_key):
    used,capacity=sample.get(used_key),sample.get(capacity_key)
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (used,capacity)):
        return None
    if not 0 < capacity or not 0 <= used <= capacity:
        return None
    return 100*used/capacity


def _percent(sample, prefix):
    key = prefix + "UsedPct"
    if key not in sample:
        return _ratio(sample, prefix + "UsedBytes", prefix + "TotalBytes")
    value = sample[key]
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
        return None
    # Conflicting representations must not silently become trusted evidence.
    if prefix + "UsedBytes" in sample or prefix + "TotalBytes" in sample:
        ratio = _ratio(sample, prefix + "UsedBytes", prefix + "TotalBytes")
        if ratio is None or abs(value - ratio) > 0.01:
            return None
    return value


def _previous_high(previous, current, seen):
    if not isinstance(previous, dict) or previous.get("source") != current.get("source"):
        return False
    # Require the same explicit target, never compare different nodes/services.
    for key in ("project", "service", "node"):
        if not current.get(key) or previous.get(key) != current[key]:
            return False
    try:
        gap = (seen - _instant(previous["observedAt"])).total_seconds()
    except (KeyError, ValueError):
        return False
    value = _percent(previous, "memory")
    return 0 < gap <= 7200 and value is not None and value >= 85


def review(host_sample=None, sql_sample=None, *, now=None, previous_host_sample=None):
    """Fail-closed evidence grade; never describe lack of log evidence as no OOM."""
    now=datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    out={
        "kind":"aiven-free-host-capacity-review",
        "readOnly":True,
        "automaticRestoreAllowed":False,
        "productionMutationAllowed":False,
        "billingChangeAllowed":False,
        "hostMemoryStatus":"unverified",
        "oomCause":"unknown",
        "findings":[],
    }
    if not isinstance(host_sample,dict) or host_sample.get("source")!="aiven-console-host-metrics":
        out["findings"].append("host-memory-source-unavailable")
        return out
    try:
        seen=_instant(host_sample["observedAt"])
    except (KeyError,ValueError):
        out["findings"].append("host-memory-time-unverified")
        return out
    delta=(now-seen).total_seconds()
    if not 0 <= delta <= HOST_MAX_AGE_SECONDS:
        out["findings"].append("host-memory-sample-stale-or-future")
        return out
    used_pct=_percent(host_sample, "memory")
    disk_pct=_percent(host_sample, "disk")
    if used_pct is None:
        out["findings"].append("host-memory-values-unverified")
        return out
    out["hostMemoryStatus"]="observed"
    out["ramUsedPct"]=used_pct
    if disk_pct is not None:
        out["diskUsedPct"]=disk_pct
    if used_pct>=95:
        out["findings"].append("critical-memory-pressure")
    elif used_pct>=85:
        if _previous_high(previous_host_sample, host_sample, seen):
            out["findings"].append("elevated-memory-pressure")
        else:
            out["memoryConfirmationPending"] = True
    if disk_pct is not None and disk_pct>=85:
        out["findings"].append("elevated-disk-pressure")
    # An OOM confirmation needs explicit original host logs; no SQL inference.
    if host_sample.get("oomLogEvidence")=="confirmed":
        out["findings"].append("oom-confirmed-by-host-log")
        out["oomCause"]="not-attributed"
    if isinstance(sql_sample,dict) and sql_sample.get("status")=="observed":
        try:
            sql_at=_instant(sql_sample["observedAt"])
            if abs((seen-sql_at).total_seconds())<=SQL_MAX_SKEW_SECONDS:
                out["dbConnectionUtilizationPct"]=_ratio(
                    sql_sample,"clientConnections","maxConnections")
                out["databaseBytes"]=sql_sample.get("databaseBytes")
                if (type(sql_sample.get("idleTransactions")) is int
                        and sql_sample["idleTransactions"]>0):
                    out["findings"].append("idle-transactions")
                if (type(sql_sample.get("longActiveClients")) is int
                        and sql_sample["longActiveClients"]>0):
                    out["findings"].append("long-active-client")
                out["sqlCorrelated"]=True
            else:
                out["findings"].append("sql-time-not-aligned")
                out["sqlCorrelated"]=False
        except (KeyError,ValueError):
            out["findings"].append("sql-time-not-verified")
            out["sqlCorrelated"]=False
    else:
        out["sqlCorrelated"]=False
    # A one-off observation is never evidence of sustained free-tier safety.
    out["recommendation"]="manual-review-only; keep isolated restores serialized and small"
    return out
