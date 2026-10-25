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

# Lexical HINTS only: explicit local JS import/export/require literals.
# No Node imports, JS execution, third-party dependencies or dynamic evaluation.
_JS_IMPORT = re.compile(
    r"""(?m)^\s*(?:import|export)\s+(?:[^\n;]*?\s+from\s+)?["'](\.{1,2}/[A-Za-z0-9_./-]+)["']"""
)
_JS_REQUIRE = re.compile(
    r"""(?m)^\s*(?:const|let|var)\s+[^\n;=]+?=\s*require\(\s*["'](\.{1,2}/[A-Za-z0-9_./-]+)["']\s*\)"""
)
_JS_SUFFIXES = frozenset((".js", ".mjs", ".cjs"))



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


def _literal_js_imports(path):
    """Read-only bounded JS local import-string hints; no parser completeness."""
    file = Path(path)
    if file.stat().st_size > _MAX_SOURCE_BYTES:
        raise ValueError("source too large")
    source = file.read_text(encoding="utf-8")
    return tuple(sorted(set(_JS_IMPORT.findall(source) +
                            _JS_REQUIRE.findall(source))))


def _mapped_js_link(base, current, raw, allowed):
    """Resolve one literal import inside the inspected tree; never read target."""
    if not isinstance(raw, str) or not raw.startswith(("./", "../")):
        return None
    resolved = ((base / current).parent / raw).resolve()
    if not resolved.is_relative_to(base):
        return None
    # An omitted extension is ambiguous; only known mapped .js or .mjs
    # modules are recognized, never guessed external packages/directories.
    candidates = [resolved] if resolved.suffix else [
        Path(str(resolved) + ext) for ext in sorted(_JS_SUFFIXES)]
    for target in candidates:
        if target.is_relative_to(base):
            name = target.relative_to(base).as_posix()
            if name in allowed and name != current:
                return name
    return None


def inspect(root, tasks):
    """Map every goal to its source and only statically visible local imports.

    JavaScript literal imports are lexical hints only; non-source files unparsed.
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
    js_paths = {p for p in by_path if Path(p).suffix in _JS_SUFFIXES}
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
        elif name in js_paths:
            try:
                imports = _literal_js_imports(base / name)
            except (UnicodeError, OSError, ValueError):
                return {"status": "unavailable", "reason": "unreadable-js-source"}
            links = sorted({
                match for raw in imports
                if (match := _mapped_js_link(base, name, raw, js_paths)) is not None
            })
            # A JS lexical hint scan is NOT a compiler syntax parse and does
            # not prove absent dependencies (dynamic import, generated code).
            analysis = "javascript-literal-import-hints-only"
            total_edges += len(links)
        else:
            links = None  # Unknown is not empty.
            analysis = "non-source-not-parsed"
        items.append({"path": name, "goals": goals, "analysis": analysis,
                      "mappedDependencies": links, "featureVerified": False})
    return {
        "status": "structural-only",
        "moduleCount": len(items),
        "goalCount": sum(len(x["goals"]) for x in items),
        "pythonModulesParsed": sum(x["analysis"] == "python-static-imports-only" for x in items),
        "javascriptModulesScanned": sum(x["analysis"] == "javascript-literal-import-hints-only" for x in items),
        "otherModulesNotParsed": sum(x["analysis"] == "non-source-not-parsed" for x in items),
        "mappedDependencyEdges": total_edges,
        "items": items,
        "scope": "python-static-ast-plus-js-literal-import-hints-among-only-mapped-sources",
        "limitations": "JS scanning uses regex literals, not a JavaScript AST. "
                       "Dynamic, multiline or generated JS imports, indirect imports, "
                       "module health and actual feature behavior remain unverified.",
        "individuallyVerified": 0,
        "readOnly": True,
    }
