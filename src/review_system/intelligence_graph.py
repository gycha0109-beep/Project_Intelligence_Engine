from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .intelligence_config import normalize_path


_TEXT_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts", ".sql", ".md", ".mdx", ".json", ".yml",
    ".yaml", ".toml", ".xml", ".gradle", ".properties", ".sh", ".ps1", ".txt", ".log", ".tsv", ".csv", ".css", ".scss", ".html", ".svg", ".graphql",
}
_LANGUAGE_BY_SUFFIX = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".sql": "sql", ".md": "markdown", ".mdx": "markdown",
    ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml",
    ".xml": "xml", ".gradle": "gradle", ".properties": "properties",
    ".sh": "shell", ".ps1": "powershell", ".txt": "text", ".log": "text", ".tsv": "text", ".csv": "text",
    ".css": "css", ".scss": "css", ".html": "html", ".svg": "xml", ".graphql": "graphql",
}
_JS_IMPORT_RE = re.compile(
    r"(?:from\s+|require\s*\(\s*|import\s*\(\s*|^\s*import\s+)[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+)\s*;?\s*$", re.MULTILINE)
_JAVA_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;?\s*$", re.MULTILINE)
_DECL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+|internal\s+|abstract\s+|final\s+|open\s+|static\s+)*"
    r"(?:class|interface|enum|record|object|type|function|const|let|var|fun)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)
_SQL_DEF_RE = re.compile(
    r"\bcreate\s+(?:or\s+replace\s+)?(?:table|view|materialized\s+view|function|procedure|trigger)\s+"
    r"(?:if\s+not\s+exists\s+)?([\w.\"]+)",
    re.IGNORECASE,
)
_SQL_REF_RE = re.compile(r"\b(?:from|join|update|into|references)\s+([\w.\"]+)", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class FileRecord:
    path: str
    absolute_path: Path
    language: str
    size_bytes: int
    sha256: str
    text: str


def _normalized(path: str | Path) -> str:
    return normalize_path(str(path))


def _matches(path: str, patterns: Iterable[str]) -> bool:
    normalized = _normalized(path)
    return any(fnmatch.fnmatchcase(normalized, _normalized(pattern)) for pattern in patterns)


def _safe_file(root: Path, candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(root)
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return False
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return resolved.is_file()


def _iter_files(root: Path, include: list[str], exclude: list[str]) -> Iterable[Path]:
    seen: set[Path] = set()
    patterns = include or ["**/*"]
    safe_patterns = [normalize_path(pattern) for pattern in patterns]
    built_in_excludes = [".git/**", ".hg/**", ".svn/**", ".venv/**", "**/__pycache__/**"]
    safe_excludes = [normalize_path(pattern) for pattern in [*exclude, *built_in_excludes]]
    for pattern in safe_patterns:
        for candidate in root.glob(pattern):
            if candidate in seen:
                continue
            seen.add(candidate)
            if not _safe_file(root, candidate):
                continue
            relative = _normalized(candidate.resolve().relative_to(root))
            if safe_excludes and _matches(relative, safe_excludes):
                continue
            yield candidate


def _read_record(root: Path, path: Path, max_file_size_bytes: int) -> tuple[FileRecord | None, str | None]:
    relative = _normalized(path.relative_to(root))
    size = path.stat().st_size
    suffix = path.suffix.lower()
    if suffix not in _TEXT_EXTENSIONS:
        return None, f"skipped unsupported text type: {relative}"
    if size > max_file_size_bytes:
        return None, f"skipped oversized file ({size} bytes): {relative}"
    raw = path.read_bytes()
    if b"\x00" in raw:
        return None, f"skipped binary-like file: {relative}"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"skipped non-UTF-8 file: {relative}"
    return FileRecord(
        path=relative,
        absolute_path=path,
        language=_LANGUAGE_BY_SUFFIX.get(suffix, "text"),
        size_bytes=size,
        sha256=hashlib.sha256(raw).hexdigest(),
        text=text,
    ), None


def _lexical_join(base: PurePosixPath, relative: str) -> PurePosixPath | None:
    parts = list(base.parts)
    for part in PurePosixPath(relative).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return PurePosixPath(*parts)


def _resolve_relative_import(source: str, specifier: str, file_paths: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    source_dir = PurePosixPath(source).parent
    base = _lexical_join(source_dir, specifier)
    if base is None:
        return None
    candidates = [
        base,
        PurePosixPath(str(base) + ".ts"), PurePosixPath(str(base) + ".tsx"),
        PurePosixPath(str(base) + ".js"), PurePosixPath(str(base) + ".jsx"),
        PurePosixPath(str(base) + ".mjs"), PurePosixPath(str(base) + ".cjs"),
        PurePosixPath(str(base) + ".md"), PurePosixPath(str(base) + ".mdx"),
        base / "index.ts", base / "index.tsx", base / "index.js", base / "index.jsx",
    ]
    for candidate in candidates:
        try:
            normalized = _normalized(candidate)
        except ValueError:
            return None
        if normalized in file_paths:
            return normalized
    return None


def _resolve_python_import(source: str, module: str, level: int, file_paths: set[str]) -> str | None:
    source_dir = PurePosixPath(source).parent
    if level:
        base = source_dir
        for _ in range(max(level - 1, 0)):
            base = base.parent
        module_path = base.joinpath(*([part for part in module.split(".") if part]))
    else:
        module_path = PurePosixPath(*([part for part in module.split(".") if part]))
    candidates = [PurePosixPath(str(module_path) + ".py"), module_path / "__init__.py"]
    for candidate in candidates:
        normalized = _normalized(candidate)
        if normalized in file_paths:
            return normalized
    return None


def _python_facts(record: FileRecord, file_paths: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    warnings: list[str] = []
    try:
        tree = ast.parse(record.text, filename=record.path)
    except SyntaxError as exc:
        warnings.append(f"python parse failed: {record.path}:{exc.lineno}: {exc.msg}")
        return nodes, edges, warnings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbol_id = f"symbol:{record.path}#{node.name}"
            nodes.append({"id": symbol_id, "type": "symbol", "name": node.name, "path": record.path, "kind": type(node).__name__})
            edges.append({"source": f"file:{record.path}", "target": symbol_id, "type": "defines"})
        elif isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_python_import(record.path, alias.name, 0, file_paths)
                if target:
                    edges.append({"source": f"file:{record.path}", "target": f"file:{target}", "type": "imports"})
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_python_import(record.path, node.module or "", node.level, file_paths)
            if target:
                edges.append({"source": f"file:{record.path}", "target": f"file:{target}", "type": "imports"})
    return nodes, edges, warnings


def _js_facts(record: FileRecord, file_paths: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for name in sorted(set(_DECL_RE.findall(record.text))):
        symbol_id = f"symbol:{record.path}#{name}"
        nodes.append({"id": symbol_id, "type": "symbol", "name": name, "path": record.path, "kind": "declaration"})
        edges.append({"source": f"file:{record.path}", "target": symbol_id, "type": "defines"})
    for specifier in sorted(set(_JS_IMPORT_RE.findall(record.text))):
        target = _resolve_relative_import(record.path, specifier, file_paths)
        if target:
            edges.append({"source": f"file:{record.path}", "target": f"file:{target}", "type": "imports"})
    return nodes, edges


def _jvm_facts(record: FileRecord, package_index: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for name in sorted(set(_DECL_RE.findall(record.text))):
        symbol_id = f"symbol:{record.path}#{name}"
        nodes.append({"id": symbol_id, "type": "symbol", "name": name, "path": record.path, "kind": "declaration"})
        edges.append({"source": f"file:{record.path}", "target": symbol_id, "type": "defines"})
    for imported in sorted(set(_JAVA_IMPORT_RE.findall(record.text))):
        target = package_index.get(imported)
        if target:
            edges.append({"source": f"file:{record.path}", "target": f"file:{target}", "type": "imports"})
    return nodes, edges


def _sql_facts(record: FileRecord) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for raw in sorted(set(_SQL_DEF_RE.findall(record.text))):
        name = raw.strip('"').lower()
        object_id = f"db:{name}"
        nodes.append({"id": object_id, "type": "database_object", "name": name, "path": record.path})
        edges.append({"source": f"file:{record.path}", "target": object_id, "type": "defines"})
    for raw in sorted(set(_SQL_REF_RE.findall(record.text))):
        name = raw.strip('"').lower()
        edges.append({"source": f"file:{record.path}", "target": f"db:{name}", "type": "references"})
    return nodes, edges


def _markdown_facts(record: FileRecord, file_paths: set[str]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for link in sorted(set(_MARKDOWN_LINK_RE.findall(record.text))):
        if "://" in link or link.startswith("#"):
            continue
        target = _resolve_relative_import(record.path, link.split("#", 1)[0], file_paths)
        if not target:
            candidate_path = _lexical_join(PurePosixPath(record.path).parent, link.split("#", 1)[0])
            if candidate_path is not None:
                candidate = _normalized(candidate_path)
                if candidate in file_paths:
                    target = candidate
        if target:
            edges.append({"source": f"file:{record.path}", "target": f"file:{target}", "type": "documents"})
    return edges


def _component_memberships(path: str, components: list[dict[str, Any]]) -> list[str]:
    memberships: list[str] = []
    for component in components:
        component_id = component.get("id")
        patterns = component.get("paths", [])
        if isinstance(component_id, str) and component_id and isinstance(patterns, list) and _matches(path, patterns):
            memberships.append(component_id)
    return memberships


def _test_target(record: FileRecord, file_paths: set[str]) -> str | None:
    path = PurePosixPath(record.path)
    lowered = path.name.lower()
    if not any(token in lowered for token in ("test", "spec")) and not any(part.lower() in {"test", "tests", "__tests__"} for part in path.parts):
        return None
    stem = re.sub(r"(?:^test[_-]?|[._-](?:test|spec)$)", "", path.stem, flags=re.IGNORECASE)
    candidates = [candidate for candidate in file_paths if PurePosixPath(candidate).stem.lower() == stem.lower() and candidate != record.path]
    if not candidates:
        return None
    return sorted(candidates, key=lambda candidate: (len(PurePosixPath(candidate).parts), candidate))[0]


def calculate_graph_sha256(graph: dict[str, Any]) -> str:
    payload = {key: value for key, value in graph.items() if key != "graph_sha256"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_project_graph(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if graph.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list):
        errors.append("nodes must be an array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        edges = []
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            errors.append(f"nodes[{index}] is invalid")
            continue
        node_id = node["id"]
        if node_id in node_ids:
            errors.append(f"duplicate node id: {node_id}")
        node_ids.add(node_id)
        if node.get("type") == "file":
            try:
                normalize_path(node.get("path", ""))
            except ValueError as exc:
                errors.append(f"nodes[{index}].path: {exc}")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{index}] is invalid")
            continue
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            errors.append(f"edges[{index}] references unknown node")
        if not isinstance(edge.get("type"), str) or not edge.get("type"):
            errors.append(f"edges[{index}].type is invalid")
    declared = graph.get("graph_sha256")
    if not isinstance(declared, str) or declared != calculate_graph_sha256(graph):
        errors.append("graph_sha256 does not match graph contents")
    return errors


def build_project_graph(
    repository_root: str | Path,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    components: list[dict[str, Any]] | None = None,
    max_file_size_bytes: int = 1_000_000,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {root}")
    if not isinstance(max_file_size_bytes, int) or isinstance(max_file_size_bytes, bool) or not 1_024 <= max_file_size_bytes <= 10_000_000:
        raise ValueError("max_file_size_bytes must be an integer between 1024 and 10000000")
    include_patterns = include or ["**/*"]
    exclude_patterns = exclude or []
    component_defs = components or []
    records: list[FileRecord] = []
    warnings: list[str] = []
    for path in sorted(_iter_files(root, include_patterns, exclude_patterns)):
        record, warning = _read_record(root, path, max_file_size_bytes)
        if warning:
            warnings.append(warning)
        if record:
            records.append(record)
    file_paths = {record.path for record in records}

    package_index: dict[str, str] = {}
    for record in records:
        if record.language in {"java", "kotlin"}:
            package_match = _JAVA_PACKAGE_RE.search(record.text)
            package = package_match.group(1) if package_match else ""
            for name in _DECL_RE.findall(record.text):
                package_index[f"{package}.{name}".strip(".")] = record.path

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for component in component_defs:
        component_id = component.get("id")
        if isinstance(component_id, str) and component_id:
            nodes.append({"id": f"component:{component_id}", "type": "component", "name": component.get("name", component_id)})

    for record in records:
        nodes.append({
            "id": f"file:{record.path}",
            "type": "file",
            "path": record.path,
            "language": record.language,
            "size_bytes": record.size_bytes,
            "sha256": record.sha256,
        })
        for component_id in _component_memberships(record.path, component_defs):
            edges.append({"source": f"component:{component_id}", "target": f"file:{record.path}", "type": "contains"})
        if record.language == "python":
            new_nodes, new_edges, new_warnings = _python_facts(record, file_paths)
            nodes.extend(new_nodes)
            edges.extend(new_edges)
            warnings.extend(new_warnings)
        elif record.language in {"javascript", "typescript"}:
            new_nodes, new_edges = _js_facts(record, file_paths)
            nodes.extend(new_nodes)
            edges.extend(new_edges)
        elif record.language in {"java", "kotlin"}:
            new_nodes, new_edges = _jvm_facts(record, package_index)
            nodes.extend(new_nodes)
            edges.extend(new_edges)
        elif record.language == "sql":
            new_nodes, new_edges = _sql_facts(record)
            nodes.extend(new_nodes)
            edges.extend(new_edges)
        elif record.language == "markdown":
            edges.extend(_markdown_facts(record, file_paths))
        test_target = _test_target(record, file_paths)
        if test_target:
            edges.append({"source": f"file:{record.path}", "target": f"file:{test_target}", "type": "likely_verifies"})

    node_map = {node["id"]: node for node in nodes}
    for edge in edges:
        if edge["target"].startswith("db:") and edge["target"] not in node_map:
            name = edge["target"].split(":", 1)[1]
            node_map[edge["target"]] = {"id": edge["target"], "type": "database_object", "name": name, "external": True}
    unique_edges = {
        (edge["source"], edge["target"], edge["type"]): edge
        for edge in edges
        if edge["source"] in node_map and edge["target"] in node_map
    }
    ordered_nodes = sorted(node_map.values(), key=lambda item: item["id"])
    ordered_edges = sorted(unique_edges.values(), key=lambda item: (item["source"], item["target"], item["type"]))
    graph = {
        "schema_version": "1.0",
        "repository": {"root": "."},
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "stats": {
            "files": sum(1 for node in ordered_nodes if node["type"] == "file"),
            "symbols": sum(1 for node in ordered_nodes if node["type"] == "symbol"),
            "components": sum(1 for node in ordered_nodes if node["type"] == "component"),
            "database_objects": sum(1 for node in ordered_nodes if node["type"] == "database_object"),
            "edges": len(ordered_edges),
        },
        "warnings": sorted(set(warnings)),
    }
    graph["graph_sha256"] = calculate_graph_sha256(graph)
    return graph
