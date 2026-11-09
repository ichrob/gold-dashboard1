"""Offline, no-credential Gemini CLI version probe for the owner's Termux.

Three bounded, separate invocations:
  python gemini_termux_offline_probe.py inspect
  python gemini_termux_offline_probe.py extract
  python gemini_termux_offline_probe.py version

This NEVER performs an OAuth login, accesses Bob data, downloads software,
updates packages, or starts any background process. Not a general installer.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

VERSION = "0.67.0"
ARCHIVE = "google-gemini-cli-" + VERSION + ".tgz"
ROOT = Path.home() / ".cache" / "bob-gemini-cli"
TARBALL = ROOT / ARCHIVE
PROBE = ROOT / "isolated-probe"
BUNDLE = PROBE / "bundle" / "gemini.js"
MAX_TARBALL = 35 * 1024 * 1024
MAX_BUNDLE = 110 * 1024 * 1024


def manifest_and_member(tarball=TARBALL):
    """Return validated metadata and ONE regular archive member, never extractall."""
    if not tarball.is_file() or tarball.is_symlink():
        raise ValueError("archive-missing")
    if tarball.stat().st_size > MAX_TARBALL:
        raise ValueError("archive-too-large")
    with tarfile.open(tarball, "r:gz") as tf:
        names = ("package/package.json", "package/bundle/gemini.js")
        if any(sum(m.name == n for m in tf.getmembers()) != 1 for n in names):
            raise ValueError("ambiguous-package")
        meta, bundle = (tf.getmember(n) for n in names)
        if not meta.isfile() or not bundle.isfile() or meta.size > 65536 or not 0 < bundle.size <= MAX_BUNDLE:
            raise ValueError("unsafe-package-member")
        stream = tf.extractfile(meta)
        if stream is None:
            raise ValueError("missing-package-metadata")
        data = json.loads(stream.read(65537).decode("utf-8"))
        if (data.get("name") != "@google/gemini-cli"
                or data.get("version") != VERSION
                or data.get("bin", {}).get("gemini") != "bundle/gemini.js"):
            raise ValueError("unexpected-package")
        return {"name": data["name"], "version": data["version"], "bundle_bytes": bundle.size}


def extract_only_bundle():
    manifest_and_member()
    if PROBE.is_symlink() or (PROBE.exists() and not PROBE.is_dir()):
        raise ValueError("unsafe-probe-directory")
    PROBE.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = BUNDLE.parent
    if directory.is_symlink():
        raise ValueError("unsafe-probe-directory")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if BUNDLE.exists() or BUNDLE.is_symlink():
        raise ValueError("bundle-already-exists-no-overwrite")
    partial = directory / "gemini.js.partial"
    fd = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as sink:
            with tarfile.open(TARBALL, "r:gz") as tf:
                source = tf.extractfile("package/bundle/gemini.js")
                if source is None:
                    raise ValueError("missing-bundle")
                with source:
                    shutil.copyfileobj(source, sink, 1024 * 1024)
        if partial.stat().st_size != manifest_and_member()["bundle_bytes"]:
            raise ValueError("bundle-size-mismatch")
        os.rename(partial, BUNDLE)
    finally:
        if partial.exists():
            partial.unlink()
    return "EXTRACTED_OFFLINE_NO_SECRETS"


def version_only():
    if not BUNDLE.is_file() or BUNDLE.is_symlink():
        raise ValueError("missing-extracted-bundle")
    node = shutil.which("node")
    if not node:
        raise ValueError("node-missing")
    # Empty HOME prevents the CLI from reading real ~/.gemini, API keys
    # and OAuth token cache. An explicit seven-second timeout is enforced.
    with tempfile.TemporaryDirectory(prefix="bob-gemini-version-") as temp:
        env = {"HOME": temp, "XDG_CONFIG_HOME": temp,
               "PATH": os.environ.get("PATH", ""),
               "NO_COLOR": "1", "CI": "1",
               "GEMINI_CLI_DISABLE_UPDATE_NOTIFIER": "true"}
        try:
            result = subprocess.run(
                [node, str(BUNDLE), "--version"], cwd=temp, env=env,
                capture_output=True, text=True, timeout=7, check=False,
            )
        except subprocess.TimeoutExpired:
            return "VERSION_TIMEOUT"
    reply = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout.strip())
    return ("VERSION_CONFIRMED_" + VERSION if result.returncode == 0
            and reply == VERSION else "VERSION_UNVERIFIED")


def main(argv):
    if len(argv) != 2 or argv[1] not in ("inspect", "extract", "version"):
        print("USAGE: inspect | extract | version")
        return 2
    try:
        if argv[1] == "inspect":
            data = manifest_and_member()
            print("PACKAGE_VALIDATED " + data["version"] +
                  " BUNDLE_BYTES=" + str(data["bundle_bytes"]))
        elif argv[1] == "extract":
            print(extract_only_bundle())
        else:
            print(version_only())
        return 0
    except (OSError, ValueError, tarfile.TarError, json.JSONDecodeError) as exc:
        # Fixed safe error type only; never show file contents or secrets.
        print("PROBE_BLOCKED_" + type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
