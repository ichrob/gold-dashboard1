"""Bounded structural module inventory for Bob's 100 diagnostic objectives.

Read existing repository files only. No imports or module execution, no network,
secrets, runtime health assumptions, trading data or automatic approvals.
The inventory is *not* an end-to-end feature validation.
"""
import ast
from functools import lru_cache
from pathlib import Path
import re


_VALID_PATH = re.compile(r"[A-Za-z0-9_./-]{1,160}\Z")
_MAX_SOURCE_BYTES = 1_000_000


@lru_cache(maxsize=64)
def _static_imports(path):
    file = Path(path)
    if file.stat().st_size > _MAX_SOURCE_BYTES:
        raise ValueError("source too large")
    # Parse source syntax only. Never use importlib, import, exec, or eval.
    tree = ast.parse(file.read_text(encoding="utf-8"), filename=file.name)
    deps = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            deps.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            deps.add(node.module.split(".")[0])
    return tuple(sorted(deps))


def inspect(root, tasks):
    """Map every goal to its source and only statically visible local imports.

    Non-Python files are recorded as unparsed, never declared dependency-free.
    Fail closed for paths outside the source tree or invalid/incomplete goals.
    """
    if (not isinstance(tasks, list) or len(tasks) != 100
            or not all(isinstance(x, dict) and type(x.get("id")) is int for x in tasks)
            or sorted(x["id"] for x in tasks) != list(range(1, 101))):
        return {"status": "unavailable", "reason": "invalid-goal-inventory"}
    base = Path(root).resolve()
    by_path = {}
    for goal in tasks:
        name = goal.get("codeEvidence")
        if (not isinstance(name, str) or not _VALID_PATH.fullmatch(name)
                or any(part in ("", ".", "..") for part in name.split("/"))
                or name.startswith("/")):
            return {"status": "unavailable", "reason": "invalid-source-path"}
        path = (base / name).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return {"status": "unavailable", "reason": "unavailable-source-path"}
        by_path.setdefault(name, []).append(goal["id"])
    python_paths = {p.removesuffix(".py"): p for p in by_path if p.endswith(".py")}
    items = []
    total_edges = 0
    for name, goals in sorted(by_path.items()):
        if name.endswith(".py"):
            try:
                imports = _static_imports(str(base / name))
            except (SyntaxError, UnicodeError, OSError, ValueError):
                return {"status": "unavailable", "reason": "unparseable-source"}
            links = sorted({python_paths[dep] for dep in imports if dep in python_paths
                            and python_paths[dep] != name})
            analysis = "python-static-imports-only"
            total_edges += len(links)
        else:
            links = None  # Unknown is not empty.
            analysis = "non-python-not-parsed"
        items.append({"path": name, "goals": goals, "analysis": analysis,
                      "mappedDependencies": links, "featureVerified": False})
    return {
        "status": "structural-only",
        "moduleCount": len(items),
        "goalCount": sum(len(x["goals"]) for x in items),
        "pythonModulesParsed": sum(x["analysis"] == "python-static-imports-only" for x in items),
        "otherModulesNotParsed": sum(x["analysis"] == "non-python-not-parsed" for x in items),
        "mappedDependencyEdges": total_edges,
        "items": items,
        "scope": "static-direct-imports-among-only-the-100-mapped-sources",
        "limitations": "Dynamic imports, JS dependencies, indirect imports, module health "
                       "and actual feature behavior are not proven or evaluated.",
        "individuallyVerified": 0,
        "readOnly": True,
    }
