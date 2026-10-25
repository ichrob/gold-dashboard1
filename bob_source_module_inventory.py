"""Bounded, source-only module-list changes against a dated repository baseline.

Never import, execute, open module contents, call network/DB/broker APIs,
or infer that an added/removed file is deployed, healthy or used at runtime.
"""
import re
from pathlib import Path

_MAX_ROOT_ENTRIES = 1500
_MAX_MODULES = 900
_MODULE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,139}\.(?:py|js|mjs|cjs)\Z")
_SUFFIXES = (".py", ".js", ".mjs", ".cjs")


def _eligible(name):
    return (isinstance(name, str) and _MODULE.fullmatch(name) is not None
            and not name.startswith(("test_", "browser_"))
            and name not in ("setup.py",))


def inspect(root, baseline, mapped_sources):
    """Only counts from the local, directly observed repository-root files."""
    invalid = {"status": "unavailable", "readOnly": True,
               "reason": "invalid-or-unavailable-module-baseline",
               "individualGoalsVerified": 0}
    if (not isinstance(baseline, dict) or baseline.get("schemaVersion") != 1
            or baseline.get("scope") != "repository-root-source-files-only"
            or baseline.get("recordedOn") != "2026-10-25"
            or not isinstance(mapped_sources, (tuple, list))
            or len(mapped_sources) != 100
            or not all(isinstance(x, str) for x in mapped_sources)):
        return invalid
    original = baseline.get("sourceModules")
    if (not isinstance(original, list) or not 1 <= len(original) <= _MAX_MODULES
            or any(not _eligible(s) for s in original)
            or sorted(set(original)) != original):
        return invalid
    base = Path(root).resolve()
    try:
        current = set()
        count = 0
        for entry in base.iterdir():
            count += 1
            if count > _MAX_ROOT_ENTRIES:
                return invalid
            # Directory traversals, symlinks and indirect package imports
            # are out of scope. Nothing outside the given root is opened.
            if (not entry.is_symlink() and entry.is_file()
                    and _eligible(entry.name)):
                current.add(entry.name)
                if len(current) > _MAX_MODULES:
                    return invalid
    except (OSError, ValueError):
        return invalid
    if not current:
        return invalid
    known = set(original)
    added = current - known
    removed = known - current
    mapped = set(s for s in mapped_sources if _eligible(s))
    return {
        "status": "changed-since-recorded-tree" if (added or removed)
                  else "same-as-recorded-tree",
        "readOnly": True, "realOrders": False,
        "sourceBaselineDay": baseline["recordedOn"],
        "recordedSourceModules": len(known),
        "currentlySeenSourceModules": len(current),
        "newPathsNotInBaseline": len(added),
        "missingPathsFromBaseline": len(removed),
        "goalMappedSourceModulesPresent": len(current & mapped),
        "sourceModulesNotDirectlyGoalMapped": len(current - mapped),
        "sourceKinds": {ext[1:]: sum(s.endswith(ext) for s in current)
                        for ext in _SUFFIXES},
        "traversal": "bounded-direct-repository-root-only",
        "individualGoalsVerified": 0,
        "runtimeHealthVerified": False,
        "newModulesFunctioningVerified": False,
        "note": "A file difference is a candidate for developer review, not a "
                "running module, a new feature, an outage or an automatic fix. "
                "Nested packages, generated files and dynamic dependencies "
                "are not inspected.",
    }
