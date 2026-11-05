"""Signed-APK Termux supervisor. No network server or credentials; NOT a sandbox."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time


def execute(script, timeout=20, output_limit=8192):
    if not isinstance(script,str) or not 1<=len(script.encode())<=6000 or '\x00' in script:
        raise ValueError('Invalid task')
    prefix=os.environ.get('PREFIX','/data/data/com.termux/files/usr')
    work=Path.home()/'bob-work';work.mkdir(mode=0o700,exist_ok=True)
    # No inherited tokens or stdin/password prompts. This is still the Termux UID.
    env={k:v for k,v in os.environ.items() if k in ('HOME','PREFIX','PATH','TMPDIR','LANG','ANDROID_ROOT','ANDROID_DATA','LD_LIBRARY_PATH')}
    shell=str(Path(prefix)/'bin/bash')
    process=subprocess.Popen([shell,'--noprofile','--norc','-c',script],cwd=work,env=env,
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    output=bytearray();status='completed';deadline=time.monotonic()+timeout
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    try:
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:status='timeout';break
            events=selector.select(min(.2,remaining))
            if events:
                block=os.read(process.stdout.fileno(),4096)
                if not block:break
                available=output_limit-len(output)
                output.extend(block[:available])
                if len(block)>available:
                    status='output-limit';break
        # Kill remaining children even after shell exits; detached daemons forbidden.
    finally:
        if status=='completed':
            try:process.wait(timeout=.2)
            except subprocess.TimeoutExpired:pass
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait();selector.close();process.stdout.close()
    return dict(status=status,output=output.decode('utf-8',errors='replace').encode()[:output_limit].decode('utf-8',errors='ignore'),exitCode=process.returncode)


if __name__=='__main__':
    try:result=execute(sys.argv[1])
    except Exception:result=dict(status='launch-failed',output='',exitCode=-999)
    print(json.dumps(result,ensure_ascii=True))
