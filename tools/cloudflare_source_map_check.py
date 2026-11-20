"""Offline Cloudflare Worker source-map build proof.

This script reads ONLY a Wrangler --dry-run --outdir build directory. It does
not deploy, invoke a Worker, access Cloudflare, or print sourcesContent. A
successful check proves that valid source maps were generated locally, NOT that
the running Cloudflare Worker version already has those maps uploaded.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


MAX_MAP_SIZE = 16 * 1024 * 1024
MAX_FILES = 100


def inspect_maps(directory: Path) -> dict:
    """Fail closed on missing, unreadable or malformed source maps."""
    path = Path(directory)
    if not path.is_dir():
        raise ValueError("build_directory_missing")
    files = sorted(path.rglob("*.map"))
    if not files:
        raise ValueError("source_maps_missing")
    if len(files) > MAX_FILES:
        raise ValueError("too_many_source_maps")
    checked = 0
    for source_map in files:
        if not source_map.is_file() or source_map.is_symlink():
            raise ValueError("source_map_not_regular")
        if source_map.stat().st_size > MAX_MAP_SIZE:
            raise ValueError("source_map_too_large")
        try:
            doc = json.loads(source_map.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError, OSError) as exc:
            raise ValueError("source_map_invalid_json") from exc
        if not isinstance(doc, dict) or doc.get("version") != 3:
            raise ValueError("source_map_bad_version")
        sources = doc.get("sources")
        if (not isinstance(sources, list) or not 1 <= len(sources) <= 10000
                or any(not isinstance(s, str) or not s or len(s) > 4096 for s in sources)):
            raise ValueError("source_map_invalid_sources")
        if not isinstance(doc.get("mappings"), str) or not doc["mappings"]:
            raise ValueError("source_map_missing_mappings")
        checked += 1
    return {"maps": checked, "valid": True, "uploaded": False}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/cloudflare_source_map_check.py OUTDIR")
    try:
        report = inspect_maps(Path(sys.argv[1]))
    except (ValueError, OSError) as exc:
        # Only fixed error categories; never print private generated contents.
        raise SystemExit("Bob Cloudflare source map check failed: " + str(exc))
    print("Bob Cloudflare source maps generated and validated:", report["maps"],
          "(offline proof only; not a deployment)")
