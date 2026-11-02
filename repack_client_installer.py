"""Provision a hash-pinned pg_repack 1.5.3 CLI as a PRIVATE, non-root tool.

Only invoked by explicit opt-in BOB_REPACK_CLIENT_PREPARE=1 after Bob startup.
This is NOT a database extension installer and NEVER connects to Postgres,
runs pg_repack on a table, schedules maintenance, or changes source data.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import urllib.request

_PACKAGE = "postgresql-18-repack_1.5.3-1.pgdg12+2_amd64.deb"
_PACKAGE_URL = ("https://apt.postgresql.org/pub/repos/apt/pool/main/"
                "p/pg-repack/" + _PACKAGE)
_EXPECTED_SHA256 = "b52898b683ba371dc06273e4ea326c6275bb6cd0b51bd130331ce00f9dfa7e05"
_EXPECTED_BYTES = 104764
_VERSION = "1.5.3"
_BINARY_REL = Path("usr/lib/postgresql/18/bin/pg_repack")
_HOME = Path("/tmp/bob-repack-client-v153")
_LOCK = threading.Lock()
_STATUS = {"status":"not-requested", "databaseModified":False,
           "readyToRepack":False, "diskBytesFreed":None}


def _clean_status(status, kind=None):
    out={"status":status,"version":_VERSION,
         "databaseModified":False, "readyToRepack":False,
         "extensionEnabledByInstaller":False,
         "diskBytesFreed":None}
    if kind and re.fullmatch("[A-Za-z][A-Za-z0-9_]{0,79}",kind):
        out["errorType"]=kind
    return out


def _preconditions():
    if platform.machine() not in ("x86_64", "AMD64"):
        raise ValueError("Unsupported architecture")
    if shutil.which("dpkg-deb") is None or shutil.which("pg_config") is None:
        raise ValueError("Debian PostgreSQL client prerequisites missing")
    conf=subprocess.run(["pg_config","--version"],check=True,
        capture_output=True,text=True,timeout=4)
    if not conf.stdout.startswith("PostgreSQL 18."):
        raise ValueError("PostgreSQL 18 client tools required")


def _fetch():
    class RejectRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    req=urllib.request.Request(_PACKAGE_URL,headers={"Accept":"application/vnd.debian.binary-package"})
    with urllib.request.build_opener(RejectRedirect()).open(req,timeout=12) as response:
        if response.geturl()!=_PACKAGE_URL:
            raise ValueError("Unexpected package host")
        raw=response.read(_EXPECTED_BYTES+1)
    if (len(raw)!=_EXPECTED_BYTES or
            hashlib.sha256(raw).hexdigest()!=_EXPECTED_SHA256):
        raise ValueError("Pinned signed-repository package mismatch")
    return raw


def _verified_binary(path):
    if path.is_symlink() or not path.is_file() or not (0 < path.stat().st_size < 2_000_000):
        raise ValueError("Invalid binary file")
    with path.open("rb") as file:
        if file.read(4)!=b"\x7fELF":
            raise ValueError("Not a native executable")
    proc=subprocess.run([str(path),"--version"],check=True,timeout=5,
                        capture_output=True,text=True,
                        env={"PATH":os.environ.get("PATH","/usr/bin"),"LANG":"C"})
    if not re.search(r"\b1\.5\.3\b",proc.stdout):
        raise ValueError("pg_repack client version mismatch")


def prepare_once():
    """Install only an inert binary and prove --version; never call the DB."""
    _preconditions()
    destination=_HOME
    if destination.exists() and (destination.is_symlink() or destination.stat().st_uid!=os.getuid()):
        raise ValueError("Unsafe private client directory")
    destination.mkdir(mode=0o700,parents=True,exist_ok=True)
    destination.chmod(0o700)
    final=destination/"pg_repack"
    if final.exists():
        _verified_binary(final)
        return _clean_status("client-verified")

    with tempfile.TemporaryDirectory(prefix="bob-repack-stage-",dir=destination) as temp:
        work=Path(temp)
        deb=work/_PACKAGE
        deb.write_bytes(_fetch())
        deb.chmod(0o600)
        info=subprocess.run(["dpkg-deb","-f",str(deb),"Package","Version","Architecture"],
                            check=True,timeout=5,capture_output=True,text=True)
        fields=info.stdout.splitlines()
        if fields != ["postgresql-18-repack","1.5.3-1.pgdg12+2","amd64"]:
            raise ValueError("Wrong PGDG package identity")
        extracted=work/"unpacked"
        subprocess.run(["dpkg-deb","-x",str(deb),str(extracted)],
                       check=True,timeout=8,capture_output=True)
        client=extracted/_BINARY_REL
        if not client.is_file() or client.is_symlink():
            raise ValueError("Missing isolated client")
        # Copy JUST the client binary: never install the package extension,
        # server .so, postgresql files, services or system libraries.
        candidate=work/"pg_repack"
        shutil.copyfile(client,candidate)
        candidate.chmod(0o700)
        _verified_binary(candidate)
        os.replace(candidate,final)
    _verified_binary(final)
    return _clean_status("client-verified")



def client_available():
    """Pure private binary check for existing read-only storage preflight."""
    try:
        _verified_binary(_HOME/"pg_repack")
        return True
    except Exception:
        return False


def start_if_enabled():
    """Fire-and-forget one opt-in, nonblocking startup probe, without DB I/O."""
    if os.environ.get("BOB_REPACK_CLIENT_PREPARE")!="1":
        return
    def run():
        global _STATUS
        if not _LOCK.acquire(blocking=False):
            return
        try:
            try:
                _STATUS=prepare_once()
            except Exception as error:
                _STATUS=_clean_status("client-unavailable",type(error).__name__)
            print("BOB_REPACK_CLIENT "+json.dumps(_STATUS,sort_keys=True),flush=True)
        finally:
            _LOCK.release()
    threading.Thread(target=run,name="bob-repack-binary-only",
                     daemon=True).start()


def status():
    return dict(_STATUS)


if __name__=="__main__":
    import sys
    if tuple(sys.argv[1:])!=("status",):
        print("Usage: python -m repack_client_installer status")
        raise SystemExit(2)
    print(json.dumps(status(),sort_keys=True))
