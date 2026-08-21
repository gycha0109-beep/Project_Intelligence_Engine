from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

WORKFLOW_SEMANTICS_SCHEMA_VERSION = "1.0"
WORKFLOW_CLASSIFICATIONS = (
    "CI_TEST_WIRING_ONLY",
    "AUTHORITY_MUTATION",
    "UNKNOWN",
)

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


def _normalize_workflow_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("workflow path must be a non-empty string")
    normalized = PurePosixPath(path.strip().replace("\\", "/")).as_posix()
    lowered = normalized.lower()
    if not lowered.startswith(".github/workflows/") or PurePosixPath(lowered).suffix not in {".yml", ".yaml"}:
        raise ValueError(f"not a GitHub Actions workflow path: {path}")
    return normalized


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
