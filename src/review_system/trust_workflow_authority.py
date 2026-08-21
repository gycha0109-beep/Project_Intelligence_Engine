from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Iterable

from .github.source import validate_pull_request_source
from .identity import canonical_json_sha256, normalize_source_revision
from .intelligence_config import normalize_path
from .workflow_semantics import (
    build_workflow_diff_evidence,
    normalize_workflow_diff_evidence,
)


TRUST_WORKFLOW_EVIDENCE_SCHEMA_VERSION = "1.0"


def _normalize_changed_files(paths: Iterable[str]) -> list[str]:
    source = list(paths)
    try:
        normalized = sorted({normalize_path(path) for path in source})
    except ValueError as exc:
        raise ValueError(f"changed files are invalid: {exc}") from exc
    if not normalized:
        raise ValueError("changed files must not be empty")
    if len(normalized) != len(source):
        raise ValueError("changed files must not contain normalized duplicates")
    return normalized


def build_trust_workflow_evidence(
    *,
    github_source: dict[str, Any],
    diff_text: str,
    source_revision: str,
    changed_files: Iterable[str],
) -> dict[str, Any]:
    errors = validate_pull_request_source(github_source)
    if errors:
        raise ValueError("invalid GitHub source: " + "; ".join(errors))
    if not isinstance(diff_text, str):
        raise TypeError("workflow diff must be a string")

    revision = normalize_source_revision(source_revision)
    if revision == "unresolved":
        raise ValueError("source revision must be stable")
    files = _normalize_changed_files(changed_files)

    pull_request = github_source["pull_request"]
    head_revision = normalize_source_revision(pull_request.get("head_oid"))
    if head_revision != revision:
        raise ValueError("GitHub source head revision does not match Trust request")

    source_files = _normalize_changed_files(
        item["path"] for item in pull_request.get("changed_files", [])
    )
    if source_files != files:
        raise ValueError("GitHub source changed files do not match Trust request")

    diff_metadata = github_source.get("diff")
    if not isinstance(diff_metadata, dict) or not diff_metadata.get("available"):
        raise ValueError("GitHub source does not contain available diff evidence")
    encoded = diff_text.encode("utf-8")
    diff_sha256 = hashlib.sha256(encoded).hexdigest()
    if diff_metadata.get("sha256") != diff_sha256:
        raise ValueError("workflow diff SHA-256 does not match GitHub source")
    if diff_metadata.get("bytes") != len(encoded):
        raise ValueError("workflow diff byte length does not match GitHub source")

    semantics = build_workflow_diff_evidence(
        source_revision=revision,
        source_evidence_sha256=github_source["source_sha256"],
        changed_files=files,
        diff_text=diff_text,
    )
    repository = github_source["repository"]
    projection = {
        "schema_version": TRUST_WORKFLOW_EVIDENCE_SCHEMA_VERSION,
        "repository_hostname": repository["hostname"],
        "repository_name_with_owner": repository["name_with_owner"],
        "pull_request_number": pull_request["number"],
        "semantics": semantics,
    }
    return {
        **projection,
        "evidence_sha256": canonical_json_sha256(projection),
    }


def normalize_trust_workflow_evidence(
    value: Any,
    *,
    source_revision: str,
    changed_files: Iterable[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Trust workflow evidence must be an object")
    required = {
        "schema_version",
        "repository_hostname",
        "repository_name_with_owner",
        "pull_request_number",
        "semantics",
        "evidence_sha256",
    }
    if set(value) != required:
        raise ValueError("Trust workflow evidence fields do not match the v1 contract")
    if value.get("schema_version") != TRUST_WORKFLOW_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported Trust workflow evidence schema_version")

    hostname = value.get("repository_hostname")
    repository = value.get("repository_name_with_owner")
    pr_number = value.get("pull_request_number")
    if not isinstance(hostname, str) or not hostname.strip():
        raise ValueError("Trust workflow evidence repository_hostname is required")
    if not isinstance(repository, str) or not repository.strip() or "/" not in repository:
        raise ValueError("Trust workflow evidence repository_name_with_owner is invalid")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
        raise ValueError("Trust workflow evidence pull_request_number is invalid")

    semantics = normalize_workflow_diff_evidence(
        value.get("semantics"),
        source_revision=source_revision,
        changed_files=changed_files,
    )
    projection = {
        "schema_version": TRUST_WORKFLOW_EVIDENCE_SCHEMA_VERSION,
        "repository_hostname": hostname.strip().lower(),
        "repository_name_with_owner": repository.strip(),
        "pull_request_number": pr_number,
        "semantics": semantics,
    }
    expected_sha = canonical_json_sha256(projection)
    if value.get("evidence_sha256") != expected_sha:
        raise ValueError("Trust workflow evidence evidence_sha256 mismatch")
    return {
        **projection,
        "evidence_sha256": expected_sha,
    }


def workflow_semantic_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": value["schema_version"],
        "repository_hostname": value["repository_hostname"],
        "repository_name_with_owner": value["repository_name_with_owner"],
        "pull_request_number": value["pull_request_number"],
        "semantics": deepcopy(value["semantics"]),
        "evidence_sha256": value["evidence_sha256"],
    }
