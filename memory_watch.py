"""Low-overhead memory diagnostics for Bob's Render push service.

Only process counts and memory sizes are logged. Never log subprocess arguments,
environment variables, request payloads, credentials, or market/trade data.
This module intentionally has no third-party dependencies.
"""
import json
import os
import threading
import time

_MIB = 1024 * 1024
_CGROUP = "/sys/fs/cgroup"
_WARN_FRACTION = 0.85


def _text(path):
    try:
        with open(path, encoding="ascii") as stream:
            return stream.read(4096).strip()
    except (OSError, UnicodeError):
        return None


def _number(path):
    value = _text(path)
    if value is None or value == "max":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _rss(pid):
    status = _text(f"/proc/{pid}/status")
    if not status:
        return None
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            try:
                return int(line.split()[1]) * 1024  # Linux reports kB.
            except (ValueError, IndexError):
                return None
    return None


def _child_pids(pid):
    """Find direct children of all Python threads, including short-lived Node."""
    children = set()
    try:
        tasks = os.listdir(f"/proc/{pid}/task")
    except OSError:
        return children
    for task in tasks:
        if not task.isdigit():
            continue
        listing = _text(f"/proc/{pid}/task/{task}/children") or ""
        for item in listing.split():
            if item.isdigit():
                children.add(int(item))
    return children


def _mib(value):
    return round(value / _MIB, 1) if value is not None else None


def snapshot():
    """Best-effort cgroup usage and direct-child attribution (not additive PSS)."""
    pid = os.getpid()
    current = _number(f"{_CGROUP}/memory.current")
    limit = _number(f"{_CGROUP}/memory.max")
    peak = _number(f"{_CGROUP}/memory.peak")
    # Older cgroup versions are still useful for baseline diagnostics.
    if current is None:
        current = _number(f"{_CGROUP}/memory/memory.usage_in_bytes")
    if limit is None:
        limit = _number(f"{_CGROUP}/memory/memory.limit_in_bytes")
    if limit is not None and limit > (1 << 55):
        limit = None  # cgroup v1 "unlimited" sentinel, not a real RAM limit.

    parent = _rss(pid)
    total_children = 0
    node = 0
    python = 0
    count = 0
    for child in _child_pids(pid):
        size = _rss(child)
        if size is None:
            continue  # Process already exited; next sample may capture another.
        count += 1
        total_children += size
        comm = (_text(f"/proc/{child}/comm") or "").lower()
        if comm.startswith("node"):
            node += size
        elif comm.startswith("python"):
            python += size
    return {
        "containerMiB": _mib(current),
        "limitMiB": _mib(limit),
        "kernelPeakMiB": _mib(peak),
        "parentMiB": _mib(parent),
        "childrenMiB": _mib(total_children),
        "nodeMiB": _mib(node),
        "pythonChildrenMiB": _mib(python),
        "children": count,
        "threads": threading.active_count(),
    }


def _report(s, high, highest_node, highest_children):
    return "BOB_MEMORY " + json.dumps({
        **s,
        "observedHighMiB": round(high, 1),
        "observedNodeHighMiB": round(highest_node, 1),
        "observedChildrenHighMiB": round(highest_children, 1),
    }, separators=(",", ":"), allow_nan=False)


def release_free_pages():
    """Ask glibc to return already-free pages; never discard live Python data.

    malloc_trim is MT-Safe and examines all arenas on modern glibc.
    Unsupported runtimes simply retain their normal allocator behaviour.
    https://man7.org/linux/man-pages/man3/malloc_trim.3.html
    """
    try:
        import ctypes
        trim = ctypes.CDLL(None).malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        return bool(trim(0))
    except (ImportError, AttributeError, OSError):
        return None


def reclaim_due(sample, now, last_attempt):
    used, limit = sample.get('containerMiB'), sample.get('limitMiB')
    parent = sample.get('parentMiB')
    return (used is not None and limit is not None and limit > 0
            and parent is not None and parent >= 128
            and used >= 0.60 * limit and now - last_attempt >= 120)


def watch(interval=0.5, stop=None, emit=print, reclaim=False):
    """Sample short subprocess peaks; throttle logs to protect Render capacity."""
    high = 0.0
    node_high = 0.0
    children_high = 0.0
    last_log = -120.0
    last_reported_high = 0.0
    last_warning = -120.0
    last_reclaim = -120.0
    while stop is None or not stop.is_set():
        try:
            sample = snapshot()
            now = time.monotonic()
            if reclaim and reclaim_due(sample, now, last_reclaim):
                last_reclaim = now
                started = time.monotonic()
                released = release_free_pages()
                after = snapshot()
                emit('BOB_MEMORY_RECLAIM ' + json.dumps({
                    'supported': released is not None, 'released': released,
                    'beforeParentMiB': sample['parentMiB'],
                    'afterParentMiB': after['parentMiB'],
                    'beforeContainerMiB': sample['containerMiB'],
                    'afterContainerMiB': after['containerMiB'],
                    'durationMs': round((time.monotonic()-started)*1000),
                    'scope': 'already-free-allocator-pages-only',
                }, separators=(',', ':'), allow_nan=False), flush=True)
            used = sample["containerMiB"]
            limit = sample["limitMiB"]
            if used is not None:
                high = max(high, used)
            node_high = max(node_high, sample["nodeMiB"] or 0.0)
            children_high = max(children_high, sample["childrenMiB"] or 0.0)
            danger = used is not None and limit is not None and limit > 0 and used >= _WARN_FRACTION * limit
            periodic = now - last_log >= 120
            new_peak = high >= last_reported_high + 32 and now - last_log >= 10
            warn = danger and now - last_warning >= 30
            if periodic or new_peak or warn:
                emit(_report(sample, high, node_high, children_high), flush=True)
                last_log = now
                last_reported_high = high
                if warn:
                    last_warning = now
        except Exception as exc:
            # Diagnostics must never interrupt market analysis or Push.
            if time.monotonic() - last_log >= 120:
                emit("BOB_MEMORY status=unavailable reason=" + type(exc).__name__, flush=True)
                last_log = time.monotonic()
        if stop is None:
            time.sleep(interval)
        elif stop.wait(interval):
            break


def start(reclaim=False):
    threading.Thread(target=watch, kwargs={'reclaim': reclaim},
                     name="bob-memory-watch", daemon=True).start()
