"""Dedicated maintenance supervisor. Never creates a paid job itself."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

TIMEOUT_SECONDS = 1200


def require_dedicated_runtime():
    if os.environ.get('BOB_SIZING_DEDICATED_RUNTIME') != '1':
        raise RuntimeError('Dedicated maintenance runtime required')
    # An opt-in flag alone must not permit running beside a serving Bob process.
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            args = (process / 'cmdline').read_bytes().split(b'\0')
        except FileNotFoundError:
            continue
        if any(Path(os.fsdecode(arg)).name in ('push_server.py', 'server.py')
               for arg in args if arg):
            raise RuntimeError('Serving Bob process detected')


def supervise(command, timeout=TIMEOUT_SECONDS):
    # Discard raw stderr: driver errors can contain credentials or original data.
    # Count it with constant memory; exit/signal and phase stdout are the evidence.
    child = subprocess.Popen(command, stderr=subprocess.PIPE, start_new_session=True)
    stderr_bytes = 0
    def drain():
        nonlocal stderr_bytes
        while True:
            block = child.stderr.read(4096)
            if not block:
                break
            stderr_bytes += len(block)
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        code = child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(child.pid, signal.SIGKILL)
        code = child.wait()
    reader.join(timeout=5)
    child.stderr.close()
    result = {'phase':'supervisor-exit', 'exitCode':code,
              'signal':-code if code < 0 else None, 'timedOut':timed_out,
              'stderrBytes':stderr_bytes, 'productionRowsModified':False}
    print(json.dumps(result), flush=True)
    return 124 if timed_out else (code if code >= 0 else 128-code)


if __name__ == '__main__':
    try:
        require_dedicated_runtime()
    except Exception as exc:
        print(json.dumps({'phase':'runtime-refused','errorType':type(exc).__name__}), flush=True)
        sys.exit(2)
    sys.exit(supervise([sys.executable, '-u', str(Path(__file__).with_name('storage_isolated_sizing.py'))]))
