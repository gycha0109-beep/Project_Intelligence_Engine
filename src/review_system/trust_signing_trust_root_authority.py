from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Iterable

from .github.source import validate_pull_request_source
from .identity import canonical_json_sha256, normalize_source_revision
from .intelligence_config import normalize_path
from .trust_signing_trust_root_semantics import analyze_signing_trust_root_semantics
from .workflow_semantics import split_git_diff_by_path


CONTRACT_VERSION = "TRUST_SIGNING_TRUST_ROOT_AUTHORITY_V1"
TRUST_SIGNING_TRUST_ROOT_EVIDENCE_SCHEMA_VERSION = "1.0"
REASON_ID = "SEMANTIC_R3_SIGNING_TRUST_ROOT_AUTHORITY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def _normalize_sha256(value: Any, field: str) -> str:
    text = str(value).strip().lower()
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{field} must be a 64-hex SHA-256")
    return text


def _normalize_analysis(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("signing trust-root file evidence must be an object")
    required = {
        "contract_version",
        "path",
        "is_signing_trust_root_authority",
        "reason_ids",
        "signals",
        "patch_sha256",
    }
    if set(value) != required:
        raise ValueError("signing trust-root file evidence fields do not match the v1 contract")
    if value.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("signing trust-root contract_version mismatch")
    path = normalize_path(value.get("path"))
    authority = value.get("is_signing_trust_root_authority")
    if not isinstance(authority, bool):
        raise ValueError("signing trust-root authority flag must be boolean")
    reason_ids = value.get("reason_ids")
    if not isinstance(reason_ids, list) or any(
        not isinstance(item, str) or not item.strip() for item in reason_ids
    ):
        raise ValueError("signing trust-root reason_ids are invalid")
    expected_reasons = [REASON_ID] if authority else []
    normalized_reasons = [item.strip() for item in reason_ids]
    if normalized_reasons != expected_reasons:
        raise ValueError("signing trust-root reason_ids do not match authority flag")
    signals = value.get("signals")
    if not isinstance(signals, dict):
        raise ValueError("signing trust-root signals must be an object")
    return {
        "contract_version": CONTRACT_VERSION,
        "path": path,
        "is_signing_trust_root_authority": authority,
        "reason_ids": normalized_reasons,
        "signals": deepcopy(signals),
        "patch_sha256": _normalize_sha256(value.get("patch_sha256"), "patch_sha256"),
    }


def _analyze_authoritative_signing_trust_root(path: str, patch: str) -> dict[str, Any]:
    candidate = analyze_signing_trust_root_semantics(path, patch)
    authority = bool(candidate["candidate_triggered"])
    return {
        "contract_version": CONTRACT_VERSION,
        "path": candidate["path"],
        "is_signing_trust_root_authority": authority,
        "reason_ids": [REASON_ID] if authority else [],
        "signals": deepcopy(candidate["signals"]),
    }


def build_trust_signing_trust_root_evidence(
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
        raise TypeError("signing trust-root diff must be a string")

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
        raise ValueError("signing trust-root diff SHA-256 does not match GitHub source")
    if diff_metadata.get("bytes") != len(encoded):
        raise ValueError("signing trust-root diff byte length does not match GitHub source")

    sections = split_git_diff_by_path(diff_text)
    missing = sorted(set(files) - set(sections))
    if missing:
        raise ValueError(
            "signing trust-root diff is missing changed file sections: " + ", ".join(missing)
        )

    analyses: list[dict[str, Any]] = []
    for path in files:
        patch = sections[path]
        analyses.append(
            {
                **_analyze_authoritative_signing_trust_root(path, patch),
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            }
        )

    semantics = {
        "contract_version": CONTRACT_VERSION,
        "source_revision": revision,
        "source_evidence_sha256": github_source["source_sha256"],
        "diff_sha256": diff_sha256,
        "changed_files_sha256": canonical_json_sha256(files),
        "files": analyses,
    }
    repository = github_source["repository"]
    projection = {
        "schema_version": TRUST_SIGNING_TRUST_ROOT_EVIDENCE_SCHEMA_VERSION,
        "repository_hostname": repository["hostname"],
        "repository_name_with_owner": repository["name_with_owner"],
        "pull_request_number": pull_request["number"],
        "semantics": semantics,
    }
    return {
        **projection,
        "evidence_sha256": canonical_json_sha256(projection),
    }


def normalize_trust_signing_trust_root_evidence(
    value: Any,
    *,
    source_revision: str,
    changed_files: Iterable[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Trust signing trust-root evidence must be an object")
    required = {
        "schema_version",
        "repository_hostname",
        "repository_name_with_owner",
        "pull_request_number",
        "semantics",
        "evidence_sha256",
    }
    if set(value) != required:
        raise ValueError("Trust signing trust-root evidence fields do not match the v1 contract")
    if value.get("schema_version") != TRUST_SIGNING_TRUST_ROOT_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported Trust signing trust-root evidence schema_version")

    hostname = value.get("repository_hostname")
    repository = value.get("repository_name_with_owner")
    pr_number = value.get("pull_request_number")
    if not isinstance(hostname, str) or not hostname.strip():
        raise ValueError("Trust signing trust-root evidence repository_hostname is required")
    if not isinstance(repository, str) or not repository.strip() or "/" not in repository:
        raise ValueError("Trust signing trust-root evidence repository_name_with_owner is invalid")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
        raise ValueError("Trust signing trust-root evidence pull_request_number is invalid")

    files = _normalize_changed_files(changed_files)
    revision = normalize_source_revision(source_revision)
    semantics_value = value.get("semantics")
    if not isinstance(semantics_value, dict):
        raise ValueError("Trust signing trust-root evidence semantics must be an object")
    expected_semantic_fields = {
        "contract_version",
        "source_revision",
        "source_evidence_sha256",
        "diff_sha256",
        "changed_files_sha256",
        "files",
    }
    if set(semantics_value) != expected_semantic_fields:
        raise ValueError("Trust signing trust-root semantics fields do not match the v1 contract")
    if semantics_value.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("Trust signing trust-root contract_version mismatch")
    if normalize_source_revision(semantics_value.get("source_revision")) != revision:
        raise ValueError("Trust signing trust-root source revision does not match Trust request")
    source_hash = _normalize_sha256(
        semantics_value.get("source_evidence_sha256"),
        "source_evidence_sha256",
    )
    diff_hash = _normalize_sha256(semantics_value.get("diff_sha256"), "diff_sha256")
    changed_hash = _normalize_sha256(
        semantics_value.get("changed_files_sha256"),
        "changed_files_sha256",
    )
    if changed_hash != canonical_json_sha256(files):
        raise ValueError("Trust signing trust-root changed_files_sha256 mismatch")

    raw_analyses = semantics_value.get("files")
    if not isinstance(raw_analyses, list):
        raise ValueError("Trust signing trust-root files must be an array")
    analyses = [_normalize_analysis(item) for item in raw_analyses]
    paths = [item["path"] for item in analyses]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError("Trust signing trust-root file evidence paths must be sorted and unique")
    if paths != files:
        raise ValueError("Trust signing trust-root file evidence does not cover changed files exactly")

    semantics = {
        "contract_version": CONTRACT_VERSION,
        "source_revision": revision,
        "source_evidence_sha256": source_hash,
        "diff_sha256": diff_hash,
        "changed_files_sha256": changed_hash,
        "files": analyses,
    }
    projection = {
        "schema_version": TRUST_SIGNING_TRUST_ROOT_EVIDENCE_SCHEMA_VERSION,
        "repository_hostname": hostname.strip().lower(),
        "repository_name_with_owner": repository.strip(),
        "pull_request_number": pr_number,
        "semantics": semantics,
    }
    expected_sha = canonical_json_sha256(projection)
    if value.get("evidence_sha256") != expected_sha:
        raise ValueError("Trust signing trust-root evidence evidence_sha256 mismatch")
    return {
        **projection,
        "evidence_sha256": expected_sha,
    }
