from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
from typing import Any

from .identity import canonical_json_sha256
from .intelligence_config import normalize_path
from .intelligence_graph import validate_project_graph
from .io import load_data
from .ledger import verify_ledger


REGROUND_SCHEMA_VERSION = "1.0"
FILE_STATUSES = {"CURRENT", "CHANGED", "MISSING"}
RELATION_STATUSES = {"CURRENT", "STALE"}
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REASON_ORDER = (
    "SOURCE_CHANGED",
    "SOURCE_MISSING",
    "TARGET_CHANGED",
    "TARGET_MISSING",
)


class RegroundError(RuntimeError):
    pass


class RegroundVerificationError(RegroundError):
    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("invalid Reground report: " + "; ".join(errors))


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegroundError(f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: str | None, field: str) -> str:
    text = _required_text(value, field)
    if not _TIMESTAMP_RE.fullmatch(text):
        raise RegroundError(f"{field} must use UTC format YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RegroundError(f"{field} is invalid: {text}") from exc
    return text


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            return True
    return False


def _safe_input_file(path: str | Path, field: str) -> Path:
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise RegroundError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise RegroundError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise RegroundError(f"{field} is not a file: {resolved}")
    return resolved


def _safe_repository_root(path: str | Path) -> Path:
    root = Path(path).expanduser()
    if _path_has_symlink(root):
        raise RegroundError(f"repository root must not contain symlinks: {root}")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise RegroundError(f"repository root not found: {root}") from exc
    if not resolved.is_dir():
        raise RegroundError(f"repository root is not a directory: {resolved}")
    return resolved


def _safe_output(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise RegroundError(f"output path must not contain symlinks: {target}")
    return target.resolve()


def _file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _tracked_file(root: Path, value: str) -> tuple[str, Path | None]:
    try:
        normalized = normalize_path(value)
    except ValueError as exc:
        raise RegroundError(f"unsafe Graph file path: {value!r}: {exc}") from exc
    parts = PurePosixPath(normalized).parts
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise RegroundError(f"Graph file path must not traverse a symlink: {normalized}")
    candidate = root.joinpath(*parts)
    if not candidate.exists():
        return normalized, None
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RegroundError(f"Graph file path escapes repository root: {normalized}") from exc
    if not resolved.is_file():
        raise RegroundError(f"Graph file path is not a regular file: {normalized}")
    return normalized, resolved


def _load_graph(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "Project Graph")
    graph = load_data(source)
    if not isinstance(graph, dict):
        raise RegroundError("Project Graph must contain an object")
    errors = validate_project_graph(graph)
    if errors:
        raise RegroundError("invalid Project Graph: " + "; ".join(errors))
    return source, graph


def _file_nodes(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    by_path: dict[str, dict[str, Any]] = {}
    node_paths: dict[str, str] = {}
    for index, node in enumerate(graph.get("nodes", [])):
        if not isinstance(node, dict) or node.get("type") != "file":
            continue
        try:
            path = normalize_path(node.get("path", ""))
        except ValueError as exc:
            raise RegroundError(f"Graph file node {index} path is invalid: {exc}") from exc
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise RegroundError(f"Graph file node {index} id is invalid")
        if node_id != f"file:{path}":
            raise RegroundError(f"Graph file node id does not match normalized path: {node_id}")
        recorded = node.get("sha256")
        if not isinstance(recorded, str) or not _HASH_RE.fullmatch(recorded):
            raise RegroundError(f"Graph file node {path} sha256 is invalid")
        if path in by_path:
            raise RegroundError(f"duplicate normalized Graph file path: {path}")
        by_path[path] = {"node_id": node_id, "recorded_sha256": recorded}
        node_paths[node_id] = path
    return by_path, node_paths


def _file_state(root: Path, path: str, node: dict[str, Any]) -> dict[str, Any]:
    normalized, current = _tracked_file(root, path)
    recorded = str(node["recorded_sha256"])
    if current is None:
        return {
            "node_id": node["node_id"],
            "path": normalized,
            "recorded_sha256": recorded,
            "current_sha256": None,
            "size_bytes": None,
            "status": "MISSING",
            "reasons": ["FILE_MISSING"],
        }
    current_hash, current_size = _file_digest(current)
    if current_hash == recorded:
        status = "CURRENT"
        reasons: list[str] = []
    else:
        status = "CHANGED"
        reasons = ["HASH_CHANGED"]
    return {
        "node_id": node["node_id"],
        "path": normalized,
        "recorded_sha256": recorded,
        "current_sha256": current_hash,
        "size_bytes": current_size,
        "status": status,
        "reasons": reasons,
    }


def _relation_reasons(source_status: str, target_status: str) -> list[str]:
    reasons: list[str] = []
    if source_status == "CHANGED":
        reasons.append("SOURCE_CHANGED")
    elif source_status == "MISSING":
        reasons.append("SOURCE_MISSING")
    if target_status == "CHANGED":
        reasons.append("TARGET_CHANGED")
    elif target_status == "MISSING":
        reasons.append("TARGET_MISSING")
    return [reason for reason in _REASON_ORDER if reason in reasons]


def _relations(
    graph: dict[str, Any],
    node_paths: dict[str, str],
    files_by_path: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    relations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    skipped = 0
    for index, edge in enumerate(graph.get("edges", [])):
        if not isinstance(edge, dict):
            raise RegroundError(f"Graph edge {index} is invalid")
        source_path = node_paths.get(str(edge.get("source")))
        target_path = node_paths.get(str(edge.get("target")))
        if source_path is None or target_path is None:
            skipped += 1
            continue
        edge_type = edge.get("type")
        if not isinstance(edge_type, str) or not edge_type:
            raise RegroundError(f"Graph edge {index} type is invalid")
        key = (source_path, target_path, edge_type)
        if key in seen:
            raise RegroundError(
                f"duplicate file relation: {source_path} -> {target_path} ({edge_type})"
            )
        seen.add(key)
        reasons = _relation_reasons(
            str(files_by_path[source_path]["status"]),
            str(files_by_path[target_path]["status"]),
        )
        natural_key = {"source": source_path, "target": target_path, "type": edge_type}
        relations.append(
            {
                "relation_id": f"relation-{canonical_json_sha256(natural_key)[:32]}",
                "source_path": source_path,
                "target_path": target_path,
                "type": edge_type,
                "status": "STALE" if reasons else "CURRENT",
                "reasons": reasons,
            }
        )
    return sorted(
        relations,
        key=lambda item: (item["source_path"], item["target_path"], item["type"]),
    ), skipped


def _impacted_rechecks(
    files: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    impacted: dict[str, dict[str, set[str]]] = {}

    def entry(path: str) -> dict[str, set[str]]:
        return impacted.setdefault(
            path,
            {"reasons": set(), "relation_ids": set(), "changed_dependencies": set()},
        )

    for item in files:
        if item.get("status") == "CHANGED":
            entry(str(item["path"]))["reasons"].add("FILE_CHANGED")
        elif item.get("status") == "MISSING":
            entry(str(item["path"]))["reasons"].add("FILE_MISSING")

    for relation in relations:
        if relation.get("status") != "STALE":
            continue
        source = str(relation["source_path"])
        target = str(relation["target_path"])
        record = entry(source)
        record["relation_ids"].add(str(relation["relation_id"]))
        for reason in relation.get("reasons", []):
            record["reasons"].add(str(reason))
            if reason in {"TARGET_CHANGED", "TARGET_MISSING"}:
                record["changed_dependencies"].add(target)

    return [
        {
            "path": path,
            "reasons": sorted(values["reasons"]),
            "relation_ids": sorted(values["relation_ids"]),
            "changed_dependencies": sorted(values["changed_dependencies"]),
        }
        for path, values in sorted(impacted.items())
    ]


def _summary(
    files: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    impacted: list[dict[str, Any]],
) -> dict[str, Any]:
    changed = sum(1 for item in files if item.get("status") == "CHANGED")
    missing = sum(1 for item in files if item.get("status") == "MISSING")
    stale_relations = sum(1 for item in relations if item.get("status") == "STALE")
    return {
        "status": "STALE" if changed or missing or stale_relations else "CURRENT",
        "tracked_files": len(files),
        "changed_files": changed,
        "missing_files": missing,
        "relations_checked": len(relations),
        "stale_relations": stale_relations,
        "impacted_rechecks": len(impacted),
    }


def _warnings(skipped_non_file_edges: int, last_run: dict[str, Any] | None) -> list[str]:
    warnings: list[str] = []
    if skipped_non_file_edges:
        warnings.append(f"NON_FILE_EDGES_SKIPPED:{skipped_non_file_edges}")
    if last_run is None:
        warnings.append("NO_VERIFIED_RUN")
    return warnings


def _open_ledger_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _last_verified_run(database: Path, project_id: str) -> dict[str, Any] | None:
    verification = verify_ledger(database)
    if not verification.get("valid"):
        errors = verification.get("errors", [])
        raise RegroundError("invalid Evidence Ledger: " + "; ".join(str(item) for item in errors))
    with _open_ledger_read_only(database) as connection:
        row = connection.execute(
            """
            SELECT run_id, run_key_sha256, project_id, run_type, source_revision,
                   source_identifier, manifest_sha256, imported_at
            FROM runs
            WHERE project_id = ?
            ORDER BY imported_at DESC, run_id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return dict(row) if row is not None else None


_LAST_RUN_FIELDS = (
    "run_id",
    "run_key_sha256",
    "project_id",
    "run_type",
    "source_revision",
    "source_identifier",
    "manifest_sha256",
    "imported_at",
)
_STABLE_LAST_RUN_FIELDS = tuple(field for field in _LAST_RUN_FIELDS if field != "imported_at")


def _stable_last_run(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {field: deepcopy(value.get(field)) for field in _STABLE_LAST_RUN_FIELDS}


def _snapshot_payload(report: dict[str, Any]) -> dict[str, Any]:
    ledger = report.get("ledger") if isinstance(report.get("ledger"), dict) else {}
    return {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "graph_sha256": report.get("graph", {}).get("graph_sha256")
        if isinstance(report.get("graph"), dict)
        else None,
        "last_verified_run": _stable_last_run(ledger.get("last_verified_run")),
        "files": deepcopy(report.get("files")),
        "relations": deepcopy(report.get("relations")),
        "impacted_rechecks": deepcopy(report.get("impacted_rechecks")),
        "warnings": deepcopy(report.get("warnings")),
    }


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(report)
    payload.pop("report_sha256", None)
    return payload


def _expected_report_id(report: dict[str, Any], snapshot_sha256: str) -> str:
    graph = report.get("graph") if isinstance(report.get("graph"), dict) else {}
    ledger = report.get("ledger") if isinstance(report.get("ledger"), dict) else {}
    last_run = ledger.get("last_verified_run") if isinstance(ledger, dict) else None
    key = {
        "project_id": report.get("project_id"),
        "graph_sha256": graph.get("graph_sha256"),
        "last_verified_run_id": last_run.get("run_id") if isinstance(last_run, dict) else None,
        "last_verified_run_key_sha256": (
            last_run.get("run_key_sha256") if isinstance(last_run, dict) else None
        ),
        "snapshot_sha256": snapshot_sha256,
    }
    return f"reground-{canonical_json_sha256(key)[:32]}"


def analyze_reground(
    *,
    project_id: str,
    repository_root: str | Path,
    graph: str | Path,
    ledger: str | Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    project = _required_text(project_id, "project_id")
    root = _safe_repository_root(repository_root)
    graph_path, graph_data = _load_graph(graph)
    ledger_path = _safe_input_file(ledger, "Evidence Ledger")
    created = _timestamp(generated_at or utc_now(), "generated_at")

    graph_files, node_paths = _file_nodes(graph_data)
    file_items = [
        _file_state(root, path, graph_files[path])
        for path in sorted(graph_files)
    ]
    files_by_path = {str(item["path"]): item for item in file_items}
    relation_items, skipped = _relations(graph_data, node_paths, files_by_path)
    impacted = _impacted_rechecks(file_items, relation_items)
    last_run = _last_verified_run(ledger_path, project)
    warnings = _warnings(skipped, last_run)

    report: dict[str, Any] = {
        "schema_version": REGROUND_SCHEMA_VERSION,
        "report_id": "",
        "project_id": project,
        "generated_at": created,
        "graph": {
            "source": graph_path.name,
            "graph_sha256": graph_data["graph_sha256"],
            "tracked_file_count": len(file_items),
            "file_relation_count": len(relation_items),
            "skipped_non_file_edges": skipped,
        },
        "ledger": {
            "database": ledger_path.name,
            "last_verified_run": last_run,
        },
        "summary": _summary(file_items, relation_items, impacted),
        "files": file_items,
        "relations": relation_items,
        "impacted_rechecks": impacted,
        "warnings": warnings,
    }
    report["snapshot_sha256"] = canonical_json_sha256(_snapshot_payload(report))
    report["report_id"] = _expected_report_id(report, report["snapshot_sha256"])
    report["report_sha256"] = canonical_json_sha256(_report_payload(report))
    errors = verify_reground_report_data(report)
    if errors:
        raise RegroundVerificationError(errors)
    return report


def _validate_file_record(item: Any, index: int, errors: list[str]) -> dict[str, Any] | None:
    prefix = f"files[{index}]"
    if not isinstance(item, dict):
        errors.append(f"{prefix} must be an object")
        return None
    try:
        path = normalize_path(item.get("path", ""))
    except ValueError as exc:
        errors.append(f"{prefix}.path: {exc}")
        return None
    if item.get("node_id") != f"file:{path}":
        errors.append(f"{prefix}.node_id mismatch")
    recorded = item.get("recorded_sha256")
    current = item.get("current_sha256")
    size = item.get("size_bytes")
    if not isinstance(recorded, str) or not _HASH_RE.fullmatch(recorded):
        errors.append(f"{prefix}.recorded_sha256 is invalid")
    if current is not None and (not isinstance(current, str) or not _HASH_RE.fullmatch(current)):
        errors.append(f"{prefix}.current_sha256 is invalid")
    if current is None:
        expected_status = "MISSING"
        expected_reasons = ["FILE_MISSING"]
        if size is not None:
            errors.append(f"{prefix}.size_bytes must be null for MISSING")
    elif current == recorded:
        expected_status = "CURRENT"
        expected_reasons = []
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"{prefix}.size_bytes is invalid")
    else:
        expected_status = "CHANGED"
        expected_reasons = ["HASH_CHANGED"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"{prefix}.size_bytes is invalid")
    if item.get("status") != expected_status:
        errors.append(f"{prefix}.status mismatch")
    if item.get("reasons") != expected_reasons:
        errors.append(f"{prefix}.reasons mismatch")
    return {
        "node_id": f"file:{path}",
        "path": path,
        "recorded_sha256": recorded,
        "current_sha256": current,
        "size_bytes": size,
        "status": expected_status,
        "reasons": expected_reasons,
    }


def verify_reground_report_data(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["report must contain an object"]
    errors: list[str] = []
    if report.get("schema_version") != REGROUND_SCHEMA_VERSION:
        errors.append(f"schema_version must be {REGROUND_SCHEMA_VERSION!r}")
    try:
        _required_text(report.get("project_id"), "project_id")
        _timestamp(report.get("generated_at"), "generated_at")
    except RegroundError as exc:
        errors.append(str(exc))

    graph = report.get("graph")
    if not isinstance(graph, dict):
        errors.append("graph must be an object")
        graph = {}
    graph_hash = graph.get("graph_sha256")
    if not isinstance(graph_hash, str) or not _HASH_RE.fullmatch(graph_hash):
        errors.append("graph.graph_sha256 is invalid")
    if not isinstance(graph.get("source"), str) or not graph.get("source"):
        errors.append("graph.source is required")
    skipped = graph.get("skipped_non_file_edges")
    if not isinstance(skipped, int) or isinstance(skipped, bool) or skipped < 0:
        errors.append("graph.skipped_non_file_edges is invalid")
        skipped = 0

    ledger = report.get("ledger")
    if not isinstance(ledger, dict):
        errors.append("ledger must be an object")
        ledger = {}
    if not isinstance(ledger.get("database"), str) or not ledger.get("database"):
        errors.append("ledger.database is required")
    last_run = ledger.get("last_verified_run")
    if last_run is not None:
        if not isinstance(last_run, dict):
            errors.append("ledger.last_verified_run must be an object or null")
            last_run = None
        else:
            if set(last_run) != set(_LAST_RUN_FIELDS):
                errors.append("ledger.last_verified_run fields mismatch")
            for field in _LAST_RUN_FIELDS:
                if not isinstance(last_run.get(field), str) or not last_run[field]:
                    errors.append(f"ledger.last_verified_run.{field} is required")
            if last_run.get("project_id") != report.get("project_id"):
                errors.append("ledger.last_verified_run.project_id mismatch")

    files_raw = report.get("files")
    if not isinstance(files_raw, list):
        errors.append("files must be an array")
        files_raw = []
    files: list[dict[str, Any]] = []
    paths: set[str] = set()
    for index, item in enumerate(files_raw):
        normalized = _validate_file_record(item, index, errors)
        if normalized is None:
            continue
        path = str(normalized["path"])
        if path in paths:
            errors.append(f"duplicate file path: {path}")
        paths.add(path)
        files.append(normalized)
    files = sorted(files, key=lambda item: item["path"])
    if files_raw != files:
        errors.append("files canonical projection mismatch")
    files_by_path = {str(item["path"]): item for item in files}

    relations_raw = report.get("relations")
    if not isinstance(relations_raw, list):
        errors.append("relations must be an array")
        relations_raw = []
    relations: list[dict[str, Any]] = []
    relation_keys: set[tuple[str, str, str]] = set()
    for index, item in enumerate(relations_raw):
        prefix = f"relations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        try:
            source = normalize_path(item.get("source_path", ""))
            target = normalize_path(item.get("target_path", ""))
        except ValueError as exc:
            errors.append(f"{prefix}: {exc}")
            continue
        edge_type = item.get("type")
        if not isinstance(edge_type, str) or not edge_type:
            errors.append(f"{prefix}.type is required")
            continue
        key = (source, target, edge_type)
        if key in relation_keys:
            errors.append(f"duplicate relation: {source} -> {target} ({edge_type})")
        relation_keys.add(key)
        if source not in files_by_path or target not in files_by_path:
            errors.append(f"{prefix} references unknown file")
            continue
        expected_id = f"relation-{canonical_json_sha256({'source': source, 'target': target, 'type': edge_type})[:32]}"
        if item.get("relation_id") != expected_id:
            errors.append(f"{prefix}.relation_id mismatch")
        reasons = _relation_reasons(
            str(files_by_path[source]["status"]),
            str(files_by_path[target]["status"]),
        )
        expected_status = "STALE" if reasons else "CURRENT"
        if item.get("status") != expected_status:
            errors.append(f"{prefix}.status mismatch")
        if item.get("reasons") != reasons:
            errors.append(f"{prefix}.reasons mismatch")
        relations.append(
            {
                "relation_id": expected_id,
                "source_path": source,
                "target_path": target,
                "type": edge_type,
                "status": expected_status,
                "reasons": reasons,
            }
        )
    relations = sorted(
        relations,
        key=lambda item: (item["source_path"], item["target_path"], item["type"]),
    )
    if relations_raw != relations:
        errors.append("relations canonical projection mismatch")

    expected_impacted = _impacted_rechecks(files, relations)
    if report.get("impacted_rechecks") != expected_impacted:
        errors.append("impacted_rechecks mismatch")
    expected_summary = _summary(files, relations, expected_impacted)
    if report.get("summary") != expected_summary:
        errors.append("summary mismatch")
    if graph.get("tracked_file_count") != len(files):
        errors.append("graph.tracked_file_count mismatch")
    if graph.get("file_relation_count") != len(relations):
        errors.append("graph.file_relation_count mismatch")
    expected_warnings = _warnings(skipped, last_run if isinstance(last_run, dict) else None)
    if report.get("warnings") != expected_warnings:
        errors.append("warnings mismatch")

    snapshot = canonical_json_sha256(_snapshot_payload(report))
    if report.get("snapshot_sha256") != snapshot:
        errors.append("snapshot_sha256 mismatch")
    expected_report_id = _expected_report_id(report, snapshot)
    if report.get("report_id") != expected_report_id:
        errors.append("report_id mismatch")
    expected_report_hash = canonical_json_sha256(_report_payload(report))
    if report.get("report_sha256") != expected_report_hash:
        errors.append("report_sha256 mismatch")
    return sorted(set(errors))


def write_reground_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_reground_report_data(report)
    if errors:
        raise RegroundVerificationError(errors)
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def load_reground_report(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "Reground report")
    data = load_data(source)
    errors = verify_reground_report_data(data)
    if errors:
        raise RegroundVerificationError(errors)
    return source, data
