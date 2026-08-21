from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import shlex
from pathlib import PurePosixPath
from typing import Any, Iterable

WORKFLOW_SEMANTICS_SCHEMA_VERSION = "1.0"
WORKFLOW_CLASSIFICATIONS = (
    "CI_TEST_WIRING_ONLY",
    "AUTHORITY_MUTATION",
    "UNKNOWN",
)

_SHA40_RE = re.compile(r"^(?:git:)?([0-9a-f]{40})$", re.IGNORECASE)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WRITE_PERMISSION_RE = re.compile(
    r"^(?:permissions:\s*write-all|"
    r"(?:actions|attestations|checks|contents|deployments|id-token|issues|packages|pages|"
    r"pull-requests|repository-projects|security-events|statuses):\s*write)\s*(?:#.*)?$",
    re.IGNORECASE,
)
_SECRET_REFERENCE_RE = re.compile(r"\$\{\{[^}\n]*\bsecrets\.[A-Za-z0-9_]+", re.IGNORECASE)
_MUTATING_API_RE = re.compile(
    r"(?:gh\s+api\b[^\n]*--method\s+(?:POST|PUT|PATCH|DELETE)\b|"
    r"curl\b[^\n]*(?:-X|--request)\s+(?:POST|PUT|PATCH|DELETE)\b)",
    re.IGNORECASE,
)
_DEPLOY_RELEASE_RE = re.compile(
    r"(?:"
    r"actions/deploy-pages|softprops/action-gh-release|actions/create-release|"
    r"\bgh\s+release\s+(?:create|upload|edit|delete)\b|"
    r"\bnpm\s+publish\b|\bdocker\s+push\b|\bkubectl\s+(?:apply|delete|patch|replace)\b|"
    r"\bterraform\s+apply\b|\bvercel\b[^\n]*--prod\b|\bsupabase\s+db\s+push\b"
    r")",
    re.IGNORECASE,
)
_TEST_KEYWORD_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:test|tests|verify|verification|lint|check|build)(?:[^A-Za-z0-9]|$)",
    re.IGNORECASE,
)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_revision(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source revision must be a non-empty exact git SHA")
    match = _SHA40_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError("source revision must be an exact 40-hex git SHA")
    return f"git:{match.group(1).lower()}"


def _normalize_changed_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("changed file path must be a non-empty string")
    raw = path.strip().replace("\\", "/")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe changed file path: {path}")
    normalized = candidate.as_posix()
    if normalized in {"", "."}:
        raise ValueError("changed file path must not be empty")
    return normalized


def _normalize_changed_files(paths: Iterable[str]) -> list[str]:
    source = list(paths)
    normalized = sorted({_normalize_changed_path(path) for path in source})
    if not normalized:
        raise ValueError("changed files must not be empty")
    if len(normalized) != len(source):
        raise ValueError("changed files must not contain normalized duplicates")
    return normalized


def _normalize_workflow_path(path: str) -> str:
    normalized = _normalize_changed_path(path)
    lowered = normalized.lower()
    if not lowered.startswith(".github/workflows/") or PurePosixPath(lowered).suffix not in {".yml", ".yaml"}:
        raise ValueError(f"not a GitHub Actions workflow path: {path}")
    return normalized


def is_workflow_path(path: str) -> bool:
    try:
        _normalize_workflow_path(path)
    except ValueError:
        return False
    return True


def _changed_patch_lines(patch: str) -> list[tuple[str, str]]:
    if not isinstance(patch, str):
        raise TypeError("workflow patch must be a string")
    changed: list[tuple[str, str]] = []
    for raw in patch.splitlines():
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("+"):
            changed.append(("+", raw[1:]))
        elif raw.startswith("-"):
            changed.append(("-", raw[1:]))
    return changed


def _authority_signals(changed_lines: list[tuple[str, str]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for direction, body in changed_lines:
        stripped = body.strip()
        reason_id: str | None = None
        if _WRITE_PERMISSION_RE.search(stripped):
            reason_id = "WORKFLOW_WRITE_PERMISSION"
        elif _SECRET_REFERENCE_RE.search(body):
            reason_id = "WORKFLOW_SECRET_REFERENCE"
        elif _MUTATING_API_RE.search(body):
            reason_id = "WORKFLOW_MUTATING_API_CALL"
        elif _DEPLOY_RELEASE_RE.search(body):
            reason_id = "WORKFLOW_DEPLOY_OR_RELEASE"
        if reason_id:
            signals.append(
                {
                    "reason_id": reason_id,
                    "direction": "ADDED" if direction == "+" else "REMOVED",
                    "line": stripped,
                }
            )
    return sorted(
        signals,
        key=lambda item: (item["reason_id"], item["direction"], item["line"]),
    )


def _is_test_wiring_line(body: str) -> bool:
    stripped = body.strip()
    if not stripped or stripped.startswith("#"):
        return True
    if stripped.startswith("- name:") or stripped.startswith("name:"):
        return bool(_TEST_KEYWORD_RE.search(stripped))
    if stripped.startswith("- run:") or stripped.startswith("run:"):
        return bool(_TEST_KEYWORD_RE.search(stripped))
    return False


def analyze_workflow_patch(path: str, patch: str) -> dict[str, Any]:
    """Reduce a GitHub Actions patch into a conservative deterministic semantic class.

    CI_TEST_WIRING_ONLY is emitted only when every changed YAML line is a
    test/verify/lint/check/build step or its name. Any explicit write permission,
    secret reference, mutating API call, or deployment/release command is
    AUTHORITY_MUTATION. Everything else is UNKNOWN and is intended to remain
    fail-safe high risk when Trust integration is added later.
    """

    normalized_path = _normalize_workflow_path(path)
    changed_lines = _changed_patch_lines(patch)
    patch_sha256 = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    authority_signals = _authority_signals(changed_lines)

    if authority_signals:
        classification = "AUTHORITY_MUTATION"
        reason_ids = sorted({item["reason_id"] for item in authority_signals})
    elif changed_lines and all(_is_test_wiring_line(body) for _, body in changed_lines):
        classification = "CI_TEST_WIRING_ONLY"
        reason_ids = ["WORKFLOW_TEST_WIRING_ONLY"]
    else:
        classification = "UNKNOWN"
        reason_ids = ["WORKFLOW_SEMANTICS_UNKNOWN"]

    return {
        "schema_version": WORKFLOW_SEMANTICS_SCHEMA_VERSION,
        "path": normalized_path,
        "patch_sha256": patch_sha256,
        "classification": classification,
        "reason_ids": reason_ids,
        "authority_signals": authority_signals,
        "changed_line_count": len(changed_lines),
    }


def _git_diff_path(header: str) -> str:
    try:
        parts = shlex.split(header.strip())
    except ValueError as exc:
        raise ValueError(f"invalid git diff header: {header.rstrip()}") from exc
    if len(parts) != 4 or parts[:2] != ["diff", "--git"]:
        raise ValueError(f"invalid git diff header: {header.rstrip()}")
    right = parts[3]
    if not right.startswith("b/"):
        raise ValueError(f"git diff target path is not b/<path>: {header.rstrip()}")
    return _normalize_changed_path(right[2:])


def split_git_diff_by_path(diff_text: str) -> dict[str, str]:
    if not isinstance(diff_text, str):
        raise TypeError("git diff must be a string")
    sections: dict[str, str] = {}
    current_path: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_path, current_lines
        if current_path is None:
            current_lines = []
            return
        if current_path in sections:
            raise ValueError(f"git diff contains duplicate file section: {current_path}")
        sections[current_path] = "".join(current_lines)
        current_path = None
        current_lines = []

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            flush()
            current_path = _git_diff_path(line)
            current_lines = [line]
        elif current_path is not None:
            current_lines.append(line)
    flush()
    return sections


def build_workflow_diff_evidence(
    *,
    source_revision: str,
    source_evidence_sha256: str,
    changed_files: Iterable[str],
    diff_text: str,
) -> dict[str, Any]:
    revision = _normalize_revision(source_revision)
    source_hash = str(source_evidence_sha256).strip().lower()
    if _SHA256_RE.fullmatch(source_hash) is None:
        raise ValueError("source_evidence_sha256 must be a 64-hex SHA-256")
    files = _normalize_changed_files(changed_files)
    sections = split_git_diff_by_path(diff_text)
    workflow_paths = sorted(path for path in files if is_workflow_path(path))
    missing = sorted(set(workflow_paths) - set(sections))
    if missing:
        raise ValueError("git diff is missing changed workflow sections: " + ", ".join(missing))

    workflows = [analyze_workflow_patch(path, sections[path]) for path in workflow_paths]
    projection = {
        "schema_version": WORKFLOW_SEMANTICS_SCHEMA_VERSION,
        "source_revision": revision,
        "source_evidence_sha256": source_hash,
        "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
        "changed_files_sha256": _canonical_sha256(files),
        "workflow_count": len(workflows),
        "workflows": workflows,
    }
    return {
        **projection,
        "evidence_sha256": _canonical_sha256(projection),
    }


def normalize_workflow_diff_evidence(
    value: Any,
    *,
    source_revision: str,
    changed_files: Iterable[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("workflow diff evidence must be an object")
    required = {
        "schema_version",
        "source_revision",
        "source_evidence_sha256",
        "diff_sha256",
        "changed_files_sha256",
        "workflow_count",
        "workflows",
        "evidence_sha256",
    }
    if set(value) != required:
        raise ValueError("workflow diff evidence fields do not match the v1 contract")
    if value.get("schema_version") != WORKFLOW_SEMANTICS_SCHEMA_VERSION:
        raise ValueError("unsupported workflow diff evidence schema_version")

    expected_revision = _normalize_revision(source_revision)
    if value.get("source_revision") != expected_revision:
        raise ValueError("workflow diff evidence source_revision mismatch")
    files = _normalize_changed_files(changed_files)
    if value.get("changed_files_sha256") != _canonical_sha256(files):
        raise ValueError("workflow diff evidence changed_files_sha256 mismatch")
    for field in ("source_evidence_sha256", "diff_sha256", "changed_files_sha256", "evidence_sha256"):
        candidate = value.get(field)
        if not isinstance(candidate, str) or _SHA256_RE.fullmatch(candidate) is None:
            raise ValueError(f"workflow diff evidence {field} must be a 64-hex SHA-256")

    raw_workflows = value.get("workflows")
    if not isinstance(raw_workflows, list):
        raise ValueError("workflow diff evidence workflows must be an array")
    expected_paths = sorted(path for path in files if is_workflow_path(path))
    normalized_workflows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_workflows):
        if not isinstance(item, dict):
            raise ValueError(f"workflow diff evidence workflows[{index}] must be an object")
        path = _normalize_workflow_path(item.get("path", ""))
        if path in seen:
            raise ValueError(f"duplicate workflow semantic path: {path}")
        seen.add(path)
        classification = item.get("classification")
        if classification not in WORKFLOW_CLASSIFICATIONS:
            raise ValueError(f"invalid workflow semantic classification: {classification}")
        patch_sha = item.get("patch_sha256")
        if not isinstance(patch_sha, str) or _SHA256_RE.fullmatch(patch_sha) is None:
            raise ValueError(f"workflow patch_sha256 invalid for {path}")
        reason_ids = item.get("reason_ids")
        if not isinstance(reason_ids, list) or not reason_ids or reason_ids != sorted(set(reason_ids)):
            raise ValueError(f"workflow reason_ids must be sorted unique for {path}")
        authority_signals = item.get("authority_signals")
        if not isinstance(authority_signals, list):
            raise ValueError(f"workflow authority_signals must be an array for {path}")
        changed_line_count = item.get("changed_line_count")
        if not isinstance(changed_line_count, int) or isinstance(changed_line_count, bool) or changed_line_count < 0:
            raise ValueError(f"workflow changed_line_count invalid for {path}")
        normalized_workflows.append(
            {
                "schema_version": WORKFLOW_SEMANTICS_SCHEMA_VERSION,
                "path": path,
                "patch_sha256": patch_sha,
                "classification": classification,
                "reason_ids": deepcopy(reason_ids),
                "authority_signals": deepcopy(authority_signals),
                "changed_line_count": changed_line_count,
            }
        )
    normalized_workflows.sort(key=lambda item: item["path"])
    if [item["path"] for item in normalized_workflows] != expected_paths:
        raise ValueError("workflow diff evidence workflow paths do not match changed_files")
    if value.get("workflow_count") != len(normalized_workflows):
        raise ValueError("workflow diff evidence workflow_count mismatch")

    projection = {
        "schema_version": WORKFLOW_SEMANTICS_SCHEMA_VERSION,
        "source_revision": expected_revision,
        "source_evidence_sha256": value["source_evidence_sha256"],
        "diff_sha256": value["diff_sha256"],
        "changed_files_sha256": value["changed_files_sha256"],
        "workflow_count": len(normalized_workflows),
        "workflows": normalized_workflows,
    }
    evidence_sha = _canonical_sha256(projection)
    if value.get("evidence_sha256") != evidence_sha:
        raise ValueError("workflow diff evidence evidence_sha256 mismatch")
    return {
        **projection,
        "evidence_sha256": evidence_sha,
    }
