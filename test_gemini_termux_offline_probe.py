"""Tests for the isolated, no-login Termux Gemini CLI offline probe."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import gemini_termux_offline_probe as probe


def tarball(path, *, name="@google/gemini-cli", version="0.67.0", symlink=False):
    metadata = json.dumps({
        "name": name, "version": version,
        "bin": {"gemini": "bundle/gemini.js"},
    }).encode("utf-8")
    script = b'console.log("0.67.0");\n'
    with tarfile.open(path, "w:gz") as archive:
        m = tarfile.TarInfo("package/package.json")
        m.size = len(metadata)
        archive.addfile(m, io.BytesIO(metadata))
        m = tarfile.TarInfo("package/bundle/gemini.js")
        if symlink:
            m.type = tarfile.SYMTYPE
            m.linkname = "../../../home/.gemini/settings.json"
            archive.addfile(m)
        else:
            m.size = len(script)
            archive.addfile(m, io.BytesIO(script))


class GeminiTermuxOfflineProbeTests(unittest.TestCase):
    def test_valid_package_manifest_and_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "google-gemini-cli-0.67.0.tgz"
            tarball(path)
            data = probe.manifest_and_member(path)
            self.assertEqual(data["name"], "@google/gemini-cli")
            self.assertEqual(data["version"], "0.67.0")
            self.assertGreater(data["bundle_bytes"], 0)

    def test_wrong_release_or_linked_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package.tgz"
            tarball(path, version="0.66.0")
            with self.assertRaises(ValueError):
                probe.manifest_and_member(path)
            tarball(path, symlink=True)
            with self.assertRaises(ValueError):
                probe.manifest_and_member(path)

    def test_extract_exact_bundle_only_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cache"
            root.mkdir()
            target = root / "isolated-probe" / "bundle" / "gemini.js"
            tarball(root / probe.ARCHIVE)
            with (patch.object(probe, "TARBALL", root / probe.ARCHIVE),
                  patch.object(probe, "ROOT", root),
                  patch.object(probe, "PROBE", target.parent.parent),
                  patch.object(probe, "BUNDLE", target)):
                self.assertEqual(probe.extract_only_bundle(), "EXTRACTED_OFFLINE_NO_SECRETS")
                self.assertEqual(target.read_text(), 'console.log("0.67.0");\n')
                with self.assertRaises(ValueError):
                    probe.extract_only_bundle()

    def test_version_probe_uses_isolated_home_and_no_auth_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "gemini.js"
            cli.write_text('console.log("0.67.0");\n')
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="0.67.0\n", stderr="")
            with (patch.object(probe, "BUNDLE", cli),
                  patch.object(probe.shutil, "which", return_value="/bin/node"),
                  patch.object(probe.subprocess, "run", return_value=completed) as call,
                  patch.dict(probe.os.environ, {
                      "GEMINI_API_KEY": "do-not-forward-to-child",
                      "BOB_PRIVATE_TOKEN": "do-not-forward-to-child",
                  })):
                self.assertEqual(probe.version_only(), "VERSION_CONFIRMED_0.67.0")
            kwargs = call.call_args.kwargs
            self.assertEqual(kwargs["timeout"], 7)
            self.assertNotIn("GEMINI_API_KEY", kwargs["env"])
            self.assertNotIn("BOB_PRIVATE_TOKEN", kwargs["env"])
            self.assertNotEqual(kwargs["env"]["HOME"], str(Path.home()))
            self.assertEqual(call.call_args.args[0][-1], "--version")

    def test_missing_package_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                probe.manifest_and_member(Path(tmp) / "missing.tgz")
            with patch.object(probe, "BUNDLE", Path(tmp) / "missing.js"):
                with self.assertRaises(ValueError):
                    probe.version_only()

    def test_no_external_or_order_apis(self):
        source = Path("gemini_termux_offline_probe.py").read_text()
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("extractall", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("GEMINI_API_KEY\"", source)


if __name__ == "__main__":
    unittest.main()
